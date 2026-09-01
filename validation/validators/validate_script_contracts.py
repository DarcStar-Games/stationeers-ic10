#!/usr/bin/env python3
"""Validate generated per-script contracts and provider/consumer compatibility."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation

from pathlib import Path
import json

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import (
    access_interface_id,
    access_provider_obligations,
    build_all,
    compatibility_errors,
    DYNAMIC_PROPERTY_RE,
    generated_artifact_paths,
    invariant_errors,
    ranges_overlap,
)

ROOT = _PROJECT_ROOT
validation = Validation(ROOT)

# Ports that declare a dynamic range without a declared consumer edge. The range is
# still compared -- validate_script_wiring.py checks it against the declared peer's
# published surface -- but nothing at *runtime* stops the port acting on whatever is
# wired to it. Each entry says what the port pins instead and what blocks the S0 check.
UNENFORCED_RANGES = {
    ("ic10/manufacturing/print_material_resolver_v1_0.ic10", "d0"):
        "pins the Recipe Execution View's S15 ready status. Not blocked, priced: the"
        " program sits exactly on the 120-line limit, so checking both its ports takes it"
        " to 124 and needs a reviewed SOFT_LIMIT_EXEMPTIONS entry of its own (issue #90"
        " argues the comparison belongs somewhere that costs the consumer no lines)",
    ("ic10/manufacturing/print_material_resolver_v1_0.ic10", "d1"):
        "pins the directory's S9 DirectorySchemaId and S11 record width, which name the"
        " schema the records follow rather than the host publishing them; same price as d0",
    ("ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10", "d0"):
        "any-of by lane: the port accepts the transform Link Resolver or the print"
        " Material Resolver, so no single S0 equality expresses the edge. It pins S12==1"
        " instead, the admission surface both resolvers publish identically",
    ("ic10/material-transform/multi_material_reservation_stager_v1_0.ic10", "d0"):
        "any-of by lane, pinning the same shared S12==1 admission surface as the"
        " paired Allocator",
    ("ic10/live-commissioning/stack_cell_monitor_v1_0.ic10", "d0"):
        "diagnostic: reads one selected cell of whatever IC housing it is wired to, and"
        " rejects non-housings by PrefabHash instead",
    ("ic10/live-commissioning/stack_header_reader_v1_0.ic10", "d0"):
        "diagnostic: reports the header of any header-publishing IC, so pinning one"
        " identity would defeat its purpose",
}


def check_reference(reference: str) -> None:
    path_text, separator, fragment = reference.partition("#")
    path = ROOT / path_text
    if not path.is_file():
        validation.fail(f"protocol definition reference is missing: {reference}")
        return
    try:
        value = json.loads(path.read_text())
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValueError("fragment must be an absolute JSON pointer")
            for token in fragment[1:].split("/"):
                value = value[token.replace("~1", "/").replace("~0", "~")]
    except Exception as error:
        validation.fail(f"invalid protocol definition reference {reference}: {error}")


try:
    schema = json.loads((ROOT / "schemas/script_contract_v2.schema.json").read_text())
    protocol_schema = json.loads((ROOT / "schemas/protocol_definition.schema.json").read_text())
    expected, expected_index, expected_protocols, expected_definitions = build_all(ROOT)
except Exception as error:
    print("Script contract validation: FAIL")
    print(f" - unable to build expected contracts: {error}")
    raise SystemExit(1)

actual_paths = {path.relative_to(ROOT).as_posix() for path in generated_artifact_paths(ROOT, "*.contract.json")}
if actual_paths != set(expected):
    validation.fail(f"contract coverage mismatch: missing={sorted(set(expected)-actual_paths)}, stale={sorted(actual_paths-set(expected))}")

actual_contracts = []
service_ids: dict[str, str] = {}
interface_ids: dict[str, tuple[str, str]] = {}
for rel, generated in sorted(expected.items()):
    path = ROOT / rel
    if not path.is_file():
        continue
    try:
        actual = json.loads(path.read_text())
        validate(actual, schema)
    except (json.JSONDecodeError, SchemaValidationError) as error:
        validation.fail(f"{rel}: schema validation failed: {error}")
        continue
    actual_contracts.append(actual)
    if actual != generated:
        validation.fail(f"{rel}: generated contract is stale; run tools/generate/generate_script_contracts.py")
    service_id = actual["identity"]["service_id"]
    if service_id in service_ids:
        validation.fail(f"duplicate service_id {service_id}: {service_ids[service_id]} and {actual['source']}")
    service_ids[service_id] = actual["source"]
    port_contracts = {item["port"]: item for item in actual["device_ports"]}
    if len(port_contracts) != len(actual["device_ports"]):
        validation.fail(f"{actual['source']}: duplicate device port")
    fields = [item["address"] for item in actual["own_stack"]["fields"]]
    if len(fields) != len(set(fields)):
        validation.fail(f"{actual['source']}: duplicate own-stack field address")
    for port_index, port in enumerate(actual["device_ports"]):
        stack = port["stack"]
        dynamic_operands = {
            value for direction in ("reads", "writes")
            for value in port["device_properties"][direction]
            if DYNAMIC_PROPERTY_RE.fullmatch(value)
        } | {
            value["property"] for direction in ("slot_reads", "slot_writes")
            for value in port["device_properties"][direction]
            if DYNAMIC_PROPERTY_RE.fullmatch(value["property"])
        }
        dynamic_sources = port.get("dynamic_property_sources", [])
        if {item["operand"] for item in dynamic_sources} != dynamic_operands:
            validation.fail(f"{actual['source']} {port['port']}: dynamic LogicType provenance is incomplete")
        for source in dynamic_sources:
            source_port = source["source_port"]
            if source_port == "self":
                source_stack = actual["own_stack"]
            elif source_port in port_contracts:
                source_stack = port_contracts[source_port]["stack"]
            else:
                validation.fail(
                    f"{actual['source']} {port['port']}: dynamic LogicType source {source_port} is not a used port"
                )
                continue
            readable = set(source_stack["literal_reads"]) | {
                cell for item in source_stack["dynamic_read_ranges"]
                for cell in range(item["start"], item["end"] + 1)
            }
            required_cells = {source["address"]}
            if "fence" in source:
                required_cells.add(source["fence"]["address"])
            if not required_cells <= readable:
                validation.fail(
                    f"{actual['source']} {port['port']}: dynamic LogicType provenance reads "
                    f"unavailable {source_port} cells {sorted(required_cells - readable)}"
                )
        if stack["dynamic_read"] and not stack["dynamic_read_ranges"]:
            validation.fail(f"{actual['source']} {port['port']}: dynamic read has no declared range")
        if stack["dynamic_write"] and not stack["dynamic_write_ranges"]:
            validation.fail(f"{actual['source']} {port['port']}: dynamic write has no declared range")
        if not stack["dynamic_read"] and (stack["dynamic_read_ranges"] or stack["dynamic_read_range_source"] != "none"):
            validation.fail(f"{actual['source']} {port['port']}: non-dynamic read has range metadata")
        if not stack["dynamic_write"] and (stack["dynamic_write_ranges"] or stack["dynamic_write_range_source"] != "none"):
            validation.fail(f"{actual['source']} {port['port']}: non-dynamic write has range metadata")
        if stack["dynamic_read"] and stack["dynamic_read_range_source"] == "none":
            validation.fail(f"{actual['source']} {port['port']}: dynamic read range lacks provenance")
        if stack["dynamic_write"] and stack["dynamic_write_range_source"] == "none":
            validation.fail(f"{actual['source']} {port['port']}: dynamic write range lacks provenance")
        for access in ("dynamic_read_ranges", "dynamic_write_ranges"):
            if any(item["start"] > item["end"] for item in stack[access]):
                validation.fail(f"{actual['source']} {port['port']}: inverted {access} entry")
            if ranges_overlap(stack[access]):
                validation.fail(f"{actual['source']} {port['port']}: overlapping {access} entries")
        target = port["target"]
        expected_keys = {
            "stack-protocol": {"kind", "verification", "protocol_ids"},
            "stack-interface": {"kind", "verification", "interface_id", "definition_ref", "provider_resolution", "assumptions"},
            "physical-device": {"kind", "verification", "assumptions"},
        }[target["kind"]]
        if set(target) != expected_keys:
            validation.fail(f"{actual['source']} {port['port']}: malformed {target['kind']} target")
        if target["kind"] == "stack-interface":
            expected_ref = f"contracts/index.json#/interfaces/{target['interface_id']}"
            if target["definition_ref"] != expected_ref:
                validation.fail(f"{actual['source']} {port['port']}: interface target does not resolve to its canonical definition")
            if target.get("provider_resolution") != "deployment-supplied":
                validation.fail(f"{actual['source']} {port['port']}: access-only provider resolution is not explicit")
            location = f"{actual['source']} {port['port']}"
            expected_id = access_interface_id(stack, target["assumptions"])
            if target["interface_id"] != expected_id:
                validation.fail(f"{location}: access interface identity does not match its structural contract")
            signature = json.dumps({"stack": stack, "assumptions": target["assumptions"]}, sort_keys=True)
            previous = interface_ids.get(target["interface_id"])
            if previous is not None and previous[1] != signature:
                validation.fail(f"interface_id collision {target['interface_id']}: {previous[0]} and {location}")
            interface_ids[target["interface_id"]] = (location, signature)
            definition = expected_index["interfaces"].get(target["interface_id"])
            if definition is None or definition["stack"] != stack or definition["assumptions"] != target["assumptions"]:
                validation.fail(f"{location}: canonical access interface definition is missing or incompatible")
            elif definition["provider_obligations"] != access_provider_obligations(stack, target["assumptions"]):
                validation.fail(f"{location}: canonical provider obligations are incomplete")
    own = actual["own_stack"]
    if own["dynamic_read"] != bool(own["dynamic_read_ranges"]):
        validation.fail(f"{actual['source']}: own dynamic read range does not match dynamic access")
    if own["dynamic_write"] != bool(own["dynamic_write_ranges"]):
        validation.fail(f"{actual['source']}: own dynamic write range does not match dynamic access")
    for direction in ("read", "write"):
        dynamic = own[f"dynamic_{direction}"]
        ranges = own[f"dynamic_{direction}_ranges"]
        proven_ranges = own[f"dynamic_{direction}_proven_ranges"]
        provenance = own[f"dynamic_{direction}_range_source"]
        if not dynamic and (ranges or proven_ranges or provenance != "none"):
            validation.fail(f"{actual['source']}: non-dynamic own {direction} has range metadata")
        if dynamic and provenance == "none":
            validation.fail(f"{actual['source']}: dynamic own {direction} lacks range provenance")
        if provenance == "conservative-full-stack" and ranges != [{"start": 0, "end": 511}]:
            validation.fail(f"{actual['source']}: own {direction} fallback is not the full stack")
        effective_cells = {cell for item in ranges for cell in range(item["start"], item["end"] + 1)}
        proven_cells = {cell for item in proven_ranges for cell in range(item["start"], item["end"] + 1)}
        if not proven_cells <= effective_cells:
            validation.fail(f"{actual['source']}: own {direction} range omits source-proven cells")
        if provenance == "source-derived" and proven_cells != effective_cells:
            validation.fail(f"{actual['source']}: own {direction} source-derived range exceeds its proof")
    for access in (
        "dynamic_read_ranges",
        "dynamic_write_ranges",
        "dynamic_read_proven_ranges",
        "dynamic_write_proven_ranges",
        "external_readable_ranges",
        "external_writable_ranges",
    ):
        if ranges_overlap(actual["own_stack"][access]):
            validation.fail(f"{actual['source']}: overlapping {access} entries")
    provided = {(item["base"], item["magic"], item["abi"]) for item in actual["contracts"]["provides"]}
    headers = {(item["base"], item["magic"], item["abi"]) for item in actual["own_stack"]["headers"]}
    if provided != headers:
        validation.fail(f"{actual['source']}: provided protocols do not match declared headers")
    validation.extend(invariant_errors(actual))

for rel, expected_value in (("contracts/index.json", expected_index), ("contracts/protocol_registry.json", expected_protocols)):
    path = ROOT / rel
    try:
        actual_value = json.loads(path.read_text())
        if actual_value != expected_value:
            validation.fail(f"{rel}: generated inventory is stale; run tools/generate/generate_script_contracts.py")
    except Exception as error:
        validation.fail(f"{rel}: cannot read generated inventory: {error}")

actual_definition_paths = {path.relative_to(ROOT).as_posix() for path in generated_artifact_paths(ROOT, "*.protocol.json")}
if actual_definition_paths != set(expected_definitions):
    validation.fail(f"protocol definition coverage mismatch: missing={sorted(set(expected_definitions)-actual_definition_paths)}, stale={sorted(actual_definition_paths-set(expected_definitions))}")
for rel, generated in sorted(expected_definitions.items()):
    try:
        actual = json.loads((ROOT / rel).read_text())
        validate(actual, protocol_schema)
        if actual != generated:
            validation.fail(f"{rel}: generated protocol definition is stale; run tools/generate/generate_script_contracts.py")
        for interface in actual["provider_interfaces"] + actual["consumer_interfaces"]:
            for key in ("readable_ranges", "writable_ranges", "dynamic_read_ranges", "dynamic_write_ranges"):
                if any(item["start"] > item["end"] for item in interface.get(key, [])):
                    validation.fail(f"{rel}: inverted {key} entry")
                if ranges_overlap(interface.get(key, [])):
                    validation.fail(f"{rel}: overlapping {key} entries")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
        validation.fail(f"{rel}: protocol definition validation failed: {error}")

for protocol in expected_protocols["protocols"]:
    check_reference(protocol["definition_ref"])
    for reference in protocol["canonical_refs"]:
        check_reference(reference)

validation.extend(compatibility_errors(actual_contracts))

unenforced = 0
for contract in actual_contracts:
    declared_edges = {item["port"] for item in contract["contracts"]["consumes"]}
    for port in contract["device_ports"]:
        stack = port["stack"]
        if not stack["dynamic_read_ranges"] and not stack["dynamic_write_ranges"]:
            continue
        if port["port"] in declared_edges:
            continue
        unenforced += 1
        reason = UNENFORCED_RANGES.get((contract["source"], port["port"]))
        if reason is None:
            validation.fail(
                f"{contract['source']} {port['port']}: declares a dynamic range with no declared"
                " consumer edge and no reviewed entry in UNENFORCED_RANGES -- add the S0 identity"
                " check and the edge, or record why the port cannot carry one")

stale = sorted(set(UNENFORCED_RANGES) - {
    (contract["source"], port["port"]) for contract in actual_contracts
    for port in contract["device_ports"]
    if (port["stack"]["dynamic_read_ranges"] or port["stack"]["dynamic_write_ranges"])
    and port["port"] not in {item["port"] for item in contract["contracts"]["consumes"]}
})
for source, name in stale:
    validation.fail(f"{source} {name}: UNENFORCED_RANGES entry no longer applies")

raise SystemExit(validation.finish("Script contract validation",[
    f"{len(actual_contracts)} deployable scripts have schema-valid, source-current JSON contracts",
    f"{len(expected_protocols['protocols'])} stack protocols have canonical generated field/access definitions",
    "wired and network-discovered dependencies resolve header locations, schema constraints, and access direction",
    f"every port declaring a dynamic range carries a declared consumer edge, except"
    f" {unenforced} with a reviewed reason",
]))
