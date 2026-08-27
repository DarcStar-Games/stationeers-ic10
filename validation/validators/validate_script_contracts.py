#!/usr/bin/env python3
"""Validate generated per-script contracts and provider/consumer compatibility."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from pathlib import Path
import json

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import (
    access_interface_id,
    access_provider_obligations,
    build_all,
    compatibility_errors,
    generated_artifact_paths,
    invariant_errors,
    ranges_overlap,
)

ROOT = _PROJECT_ROOT
fails: list[str] = []


def check_reference(reference: str) -> None:
    path_text, separator, fragment = reference.partition("#")
    path = ROOT / path_text
    if not path.is_file():
        fails.append(f"protocol definition reference is missing: {reference}")
        return
    try:
        value = json.loads(path.read_text())
        if separator and fragment:
            if not fragment.startswith("/"):
                raise ValueError("fragment must be an absolute JSON pointer")
            for token in fragment[1:].split("/"):
                value = value[token.replace("~1", "/").replace("~0", "~")]
    except Exception as error:
        fails.append(f"invalid protocol definition reference {reference}: {error}")


try:
    schema = json.loads((ROOT / "schemas/script_contract.schema.json").read_text())
    protocol_schema = json.loads((ROOT / "schemas/protocol_definition.schema.json").read_text())
    expected, expected_index, expected_protocols, expected_definitions = build_all(ROOT)
except Exception as error:
    print("Script contract validation: FAIL")
    print(f" - unable to build expected contracts: {error}")
    raise SystemExit(1)

actual_paths = {path.relative_to(ROOT).as_posix() for path in generated_artifact_paths(ROOT, "*.contract.json")}
if actual_paths != set(expected):
    fails.append(f"contract coverage mismatch: missing={sorted(set(expected)-actual_paths)}, stale={sorted(actual_paths-set(expected))}")

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
        fails.append(f"{rel}: schema validation failed: {error}")
        continue
    actual_contracts.append(actual)
    if actual != generated:
        fails.append(f"{rel}: generated contract is stale; run tools/generate/generate_script_contracts.py")
    service_id = actual["identity"]["service_id"]
    if service_id in service_ids:
        fails.append(f"duplicate service_id {service_id}: {service_ids[service_id]} and {actual['source']}")
    service_ids[service_id] = actual["source"]
    ports = [item["port"] for item in actual["device_ports"]]
    if len(ports) != len(set(ports)):
        fails.append(f"{actual['source']}: duplicate device port")
    fields = [item["address"] for item in actual["own_stack"]["fields"]]
    if len(fields) != len(set(fields)):
        fails.append(f"{actual['source']}: duplicate own-stack field address")
    for port_index, port in enumerate(actual["device_ports"]):
        stack = port["stack"]
        if stack["dynamic_read"] and not stack["dynamic_read_ranges"]:
            fails.append(f"{actual['source']} {port['port']}: dynamic read has no declared range")
        if stack["dynamic_write"] and not stack["dynamic_write_ranges"]:
            fails.append(f"{actual['source']} {port['port']}: dynamic write has no declared range")
        if not stack["dynamic_read"] and (stack["dynamic_read_ranges"] or stack["dynamic_read_range_source"] != "none"):
            fails.append(f"{actual['source']} {port['port']}: non-dynamic read has range metadata")
        if not stack["dynamic_write"] and (stack["dynamic_write_ranges"] or stack["dynamic_write_range_source"] != "none"):
            fails.append(f"{actual['source']} {port['port']}: non-dynamic write has range metadata")
        if stack["dynamic_read"] and stack["dynamic_read_range_source"] == "none":
            fails.append(f"{actual['source']} {port['port']}: dynamic read range lacks provenance")
        if stack["dynamic_write"] and stack["dynamic_write_range_source"] == "none":
            fails.append(f"{actual['source']} {port['port']}: dynamic write range lacks provenance")
        for access in ("dynamic_read_ranges", "dynamic_write_ranges"):
            if any(item["start"] > item["end"] for item in stack[access]):
                fails.append(f"{actual['source']} {port['port']}: inverted {access} entry")
            if ranges_overlap(stack[access]):
                fails.append(f"{actual['source']} {port['port']}: overlapping {access} entries")
        target = port["target"]
        expected_keys = {
            "stack-protocol": {"kind", "verification", "protocol_ids"},
            "stack-interface": {"kind", "verification", "interface_id", "definition_ref", "provider_resolution", "assumptions"},
            "physical-device": {"kind", "verification", "assumptions"},
        }[target["kind"]]
        if set(target) != expected_keys:
            fails.append(f"{actual['source']} {port['port']}: malformed {target['kind']} target")
        if target["kind"] == "stack-interface":
            expected_ref = f"contracts/index.json#/interfaces/{target['interface_id']}"
            if target["definition_ref"] != expected_ref:
                fails.append(f"{actual['source']} {port['port']}: interface target does not resolve to its canonical definition")
            if target.get("provider_resolution") != "deployment-supplied":
                fails.append(f"{actual['source']} {port['port']}: access-only provider resolution is not explicit")
            location = f"{actual['source']} {port['port']}"
            expected_id = access_interface_id(stack, target["assumptions"])
            if target["interface_id"] != expected_id:
                fails.append(f"{location}: access interface identity does not match its structural contract")
            signature = json.dumps({"stack": stack, "assumptions": target["assumptions"]}, sort_keys=True)
            previous = interface_ids.get(target["interface_id"])
            if previous is not None and previous[1] != signature:
                fails.append(f"interface_id collision {target['interface_id']}: {previous[0]} and {location}")
            interface_ids[target["interface_id"]] = (location, signature)
            definition = expected_index["interfaces"].get(target["interface_id"])
            if definition is None or definition["stack"] != stack or definition["assumptions"] != target["assumptions"]:
                fails.append(f"{location}: canonical access interface definition is missing or incompatible")
            elif definition["provider_obligations"] != access_provider_obligations(stack, target["assumptions"]):
                fails.append(f"{location}: canonical provider obligations are incomplete")
    own = actual["own_stack"]
    if own["dynamic_read"] != bool(own["dynamic_read_ranges"]):
        fails.append(f"{actual['source']}: own dynamic read range does not match dynamic access")
    if own["dynamic_write"] != bool(own["dynamic_write_ranges"]):
        fails.append(f"{actual['source']}: own dynamic write range does not match dynamic access")
    expected_own_source = "conservative-full-stack" if own["dynamic_read"] or own["dynamic_write"] else "none"
    if own["dynamic_range_source"] != expected_own_source:
        fails.append(f"{actual['source']}: own dynamic range provenance is inconsistent")
    for access in (
        "dynamic_read_ranges",
        "dynamic_write_ranges",
        "external_readable_ranges",
        "external_writable_ranges",
    ):
        if ranges_overlap(actual["own_stack"][access]):
            fails.append(f"{actual['source']}: overlapping {access} entries")
    provided = {(item["base"], item["magic"], item["abi"]) for item in actual["contracts"]["provides"]}
    headers = {(item["base"], item["magic"], item["abi"]) for item in actual["own_stack"]["headers"]}
    if provided != headers:
        fails.append(f"{actual['source']}: provided protocols do not match declared headers")
    fails.extend(invariant_errors(actual))

for rel, expected_value in (("contracts/index.json", expected_index), ("contracts/protocol_registry.json", expected_protocols)):
    path = ROOT / rel
    try:
        actual_value = json.loads(path.read_text())
        if actual_value != expected_value:
            fails.append(f"{rel}: generated inventory is stale; run tools/generate/generate_script_contracts.py")
    except Exception as error:
        fails.append(f"{rel}: cannot read generated inventory: {error}")

actual_definition_paths = {path.relative_to(ROOT).as_posix() for path in generated_artifact_paths(ROOT, "*.protocol.json")}
if actual_definition_paths != set(expected_definitions):
    fails.append(f"protocol definition coverage mismatch: missing={sorted(set(expected_definitions)-actual_definition_paths)}, stale={sorted(actual_definition_paths-set(expected_definitions))}")
for rel, generated in sorted(expected_definitions.items()):
    try:
        actual = json.loads((ROOT / rel).read_text())
        validate(actual, protocol_schema)
        if actual != generated:
            fails.append(f"{rel}: generated protocol definition is stale; run tools/generate/generate_script_contracts.py")
        for interface in actual["provider_interfaces"] + actual["consumer_interfaces"]:
            for key in ("readable_ranges", "writable_ranges", "dynamic_read_ranges", "dynamic_write_ranges"):
                if any(item["start"] > item["end"] for item in interface.get(key, [])):
                    fails.append(f"{rel}: inverted {key} entry")
                if ranges_overlap(interface.get(key, [])):
                    fails.append(f"{rel}: overlapping {key} entries")
    except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
        fails.append(f"{rel}: protocol definition validation failed: {error}")

for protocol in expected_protocols["protocols"]:
    check_reference(protocol["definition_ref"])
    for reference in protocol["canonical_refs"]:
        check_reference(reference)

fails.extend(compatibility_errors(actual_contracts))

if fails:
    print("Script contract validation: FAIL")
    for failure in fails:
        print(" -", failure)
    raise SystemExit(1)
print("Script contract validation: PASS")
print(f" - {len(actual_contracts)} deployable scripts have schema-valid, source-current JSON contracts")
print(f" - {len(expected_protocols['protocols'])} stack protocols have canonical generated field/access definitions")
print(" - wired and network-discovered dependencies resolve header locations, schema constraints, and access direction")
