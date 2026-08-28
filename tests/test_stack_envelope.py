#!/usr/bin/env python3
"""Exercise Stack Envelope v1 pilots, discovery, and compatibility surfaces."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import hashlib
import json
import sys
from tempfile import TemporaryDirectory

from framework.ic10_harness import Device, IC10
from framework.json_schema import validate
from framework.script_contracts import _own_stack, build_all
from framework.stack_envelope import (
    build_inventory,
    declaration_errors,
    extension_ownership_errors,
    legacy_source_digest,
    load_declarations,
    publication_errors,
)

ROOT = _PROJECT_ROOT
fails: list[str] = []


def ck(condition, message):
    if not condition:
        fails.append(message)


contracts, _, protocols, _ = build_all(ROOT)
inventory = build_inventory(ROOT, contracts, protocols)
validate(inventory, json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text()))
ck(inventory["totals"] == {
    "deployable_programs": 173,
    "migrated_v1": 5,
    "legacy_exempt": 168,
    "legacy_literal_collisions": 0,
    "legacy_dynamic_collisions": 61,
}, "generated coverage/collision totals changed without review")
by_source = {item["source"]: item for item in inventory["services"]}
directory_layout = by_source[
    "ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10"
]["current_layout"]
ck(any(field.get("const") == 'HASH("DirectorySchema.ResourceLink")'
       for field in directory_layout["schema_fields"]),
   "literal directory schema was omitted from generated inventory")
literal_schema_publishers = {
    str(path.relative_to(ROOT))
    for path in (ROOT / "ic10").rglob("*.ic10")
    if any('poke ' in line and 'HASH("' in line and "schema" in line.lower()
           for line in path.read_text().splitlines())
}
inventoried_schema_publishers = {
    item["source"] for item in inventory["services"]
    if any("schema" in str(field.get("const", "")).lower()
           for field in item["current_layout"]["schema_fields"])
}
ck(literal_schema_publishers <= inventoried_schema_publishers,
   "one or more literal schema-hash publishers were omitted from generated inventory")
ck(all(item["current_layout"]["payload_inventory_status"] ==
       ("declared-stack-protocol" if item["current_layout"]["headers"]
        else "no-declared-stack-protocol") for item in inventory["services"]),
   "payload inventory does not distinguish declared protocols from no protocol")

extension_source = """poke 0 7
poke 1 1
poke 320 31416053
poke 321 1
poke 322 HASH(\"ic10.script.example\")
poke 323 1
poke 324 0
poke 325 0
poke 326 0
poke 327 400
poke 400 31416054
poke 401 1
poke 402 5
poke 403 1
poke 404 HASH(\"ic10.implementation.example\")
Loop:
yield
j Loop
"""
extension_rows = [
    line.split() for line in extension_source.splitlines()
    if line and not line.endswith(":")
]
extension_contract, _ = _own_stack(
    extension_source, extension_rows, {}, [{"base": 0, "magic": 7, "abi": 1}], {}
)
ck({"start": 400, "end": 404} in extension_contract["external_readable_ranges"],
   "script contract does not advertise a declared extension as externally readable")

pilots = {
    "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10": (31416052, 1, 0),
    "ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10": (31415936, 1, 0),
    "ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10": (27182818, 2, 96),
    "ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10": (31415967, 3, 0),
    "ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10": (31415983, 2, 0),
}
for source, (legacy_magic, legacy_abi, payload_base) in pilots.items():
    vm = IC10((ROOT / source).read_text())
    vm.run(1)
    ck(vm.stack.get(payload_base) == legacy_magic and vm.stack.get(payload_base + 1) == legacy_abi,
       f"{source}: established payload header changed")
    ck(vm.stack.get(320) == 31416053 and vm.stack.get(321) == 1,
       f"{source}: v1 envelope marker missing")
    ck(vm.stack.get(323) == legacy_abi and vm.stack.get(326) == payload_base,
       f"{source}: envelope does not locate the compatible payload")
    contract = next(document for document in contracts.values() if document["source"] == source)
    readable = {cell for item in contract["own_stack"]["external_readable_ranges"]
                for cell in range(item["start"], item["end"] + 1)}
    ck(set(range(320, 328)) <= readable,
       f"{source}: script contract does not advertise the envelope as externally readable")
    ck(by_source[source]["envelope"]["publication_validation"]["source_sha256"],
       f"{source}: generated inventory omits behavioral publication evidence")

# Discovery reads only S320..S327 and reports semantic identity + payload base.
target = Device(201, stack={
    320: 31416053, 321: 1, 322: "HASH:ic10.script.process.pressure.domain.runtime",
    323: 2, 324: 0, 325: 0, 326: 96, 327: 0,
}, props={"ReferenceId": 201, "PrefabHash": "HASH:StructureCircuitHousing"})
selector = Device(202, props={"ReferenceId": 202, "Setting": -1})
output = Device(203, props={"ReferenceId": 203, "Setting": 0})
monitor = IC10((ROOT / "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10").read_text(),
               {"d0": target, "d1": selector, "d2": output})
monitor.run(2)
ck(monitor.stack.get(2) == 3 and monitor.stack.get(3) == 96,
   "monitor did not discover the primary payload base")
ck(monitor.stack.get(4) == "HASH:ic10.script.process.pressure.domain.runtime",
   "monitor did not publish semantic ServiceId")
ck(output.props.get("Setting") == monitor.stack.get(4),
   "discovered ServiceId was not mirrored to optional output")

# Extension headers are validated before any family-specific cells are trusted.
target.stack.update({327: 508, 508: 31416054, 509: 1, 510: 4, 511: 0})
monitor.run(1)
ck(monitor.stack.get(2) == 3, "monitor rejected an in-bounds four-cell extension")
target.stack.update({327: 509, 509: 31416054, 510: 1, 511: 4})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted an extension that exceeds S511")
target.stack.update({327: 100, 100: 31416054, 101: 1, 102: 193, 103: 0})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted an extension above the v1 length limit")
target.stack.update({327: 508, 508: 31416054, 509: 1, 510: 4, 511: 1})
monitor.run(1)
ck(monitor.stack.get(2) == -6,
   "monitor accepted HAS_IMPLEMENTATION_ID without an in-bounds ImplementationId cell")
target.stack.update({327: 508, 508: 31416054, 509: 1, 510: 4, 511: 2})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted reserved extension flag bits")
target.stack.update({
    327: 507, 507: 31416054, 508: 1, 509: 5, 510: 1,
    511: "HASH:ic10.implementation.example",
})
monitor.run(1)
ck(monitor.stack.get(2) == 3, "monitor rejected a valid ImplementationId extension")
for invalid_identity in (0, 1.5, float("nan")):
    target.stack.update({511: invalid_identity})
    monitor.run(1)
    ck(monitor.stack.get(2) == -6,
       f"monitor accepted invalid ImplementationId {invalid_identity!r}")
target.stack.update({327: 0, 324: "HASH:Schema", 325: 0})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted mismatched schema zero/unknown semantics")
target.stack.update({324: 0, 325: 0, 323: 1.5})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted a fractional ServiceABI")
target.stack.update({323: float("nan")})
monitor.run(1)
ck(monitor.stack.get(2) == -6, "monitor accepted a NaN ServiceABI")
for invalid_version in (-1, 1.5, float("nan")):
    target.stack.update({323: 1, 324: "HASH:Schema", 325: invalid_version})
    monitor.run(1)
    ck(monitor.stack.get(2) == -6,
       f"monitor accepted invalid SchemaVersion {invalid_version!r}")
for field, invalid_identity in ((322, 1.5), (322, float("nan")), (324, 1.5)):
    target.stack.update({323: 1, 322: 123, 324: 0, 325: 0, field: invalid_identity})
    if field == 324:
        target.stack[325] = 1
    monitor.run(1)
    ck(monitor.stack.get(2) == -6,
       f"monitor accepted invalid identity at S{field}: {invalid_identity!r}")

target.stack.update({320: 0})
monitor.run(1)
ck(monitor.stack.get(2) == -5 and monitor.stack.get(3) == -1,
   "monitor reported a payload base it never discovered")

# A cell a full-stack clear can overwrite is not published as a contract constant.
by_contract = {document["source"]: document for document in contracts.values()}
envelope_cells = set(range(320, 328))
ck(all("const" not in field
       for field in by_contract[
           "ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10"
       ]["own_stack"]["fields"] if field["address"] in envelope_cells),
   "envelope cells claim constants the same contract calls dynamically writable")
ck(any(field.get("const") == 31416053
       for field in by_contract[
           "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
       ]["own_stack"]["fields"] if field["address"] == 320),
   "a stable envelope publication lost its contract constant")

# The reviewed source-set digest is the enforcement gate for every future service.
bad = deepcopy(load_declarations(ROOT))
bad["legacy_exemption"]["source_set_sha256"] = "0" * 64
ck(any("source set changed" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted an unreviewed legacy source-set change")
bad = deepcopy(load_declarations(ROOT))
bad["legacy_exemption"]["sources"].pop()
ck(any("must publish the envelope or receive explicit exemptions" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator automatically classified an undeclared deployable as legacy")
bad = deepcopy(load_declarations(ROOT))
bad["legacy_exemption"]["sources"].append(
    "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
)
bad["legacy_exemption"]["source_count"] += 1
bad["legacy_exemption"]["source_set_sha256"] = legacy_source_digest(
    bad["legacy_exemption"]["sources"]
)
ck(any("baseline is immutable" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator allowed a new path into the pre-v1 legacy baseline")

# Declarations bind to canonical contract and established payload identities.
bad = deepcopy(load_declarations(ROOT))
bad["migrated"]["ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"][
    "service_id"
] = "ic10.script.unrelated.service"
ck(any("canonical contract identity" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a ServiceId that differs from the script contract")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"]["ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10"][
    "schema_version"
] = 2
ck(any("established payload schema/version" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted an envelope schema that differs from the legacy payload")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"]["ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10"]["schema_version"] = 4
ck(any("established payload schema/version" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a schema/version no established payload publishes or verifies")
ck(extension_ownership_errors([{"start": 0, "end": 15}], 12, 4),
   "validator allowed an extension to overwrite established payload cells")
ck(not extension_ownership_errors([{"start": 0, "end": 15}], 16, 4),
   "validator rejected an extension in unowned stack cells")
for field in ("service_abi", "primary_payload_base", "extension_base"):
    bad = deepcopy(load_declarations(ROOT))
    bad["migrated"]["ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"][field] = "1"
    try:
        malformed_errors = declaration_errors(ROOT, contracts, bad)
    except TypeError:
        malformed_errors = []
    ck(any(field in error for error in malformed_errors),
       f"malformed {field} crashed or bypassed declaration validation")

# Text in an unreachable branch or erased after publication is not publication.
declaration = load_declarations(ROOT)["migrated"][
    "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
]
expected = {
    320: 31416053, 321: 1,
    322: 'HASH("ic10.script.stack.cell.monitor")', 323: 1,
    324: 0, 325: 0, 326: 0, 327: 0,
}
source = (ROOT / "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10").read_text()
with TemporaryDirectory() as temporary:
    unreachable = _ProjectPath(temporary) / "unreachable.ic10"
    unreachable.write_text(source.replace("poke 320 31416053", "j SkipEnvelope\npoke 320 31416053\nSkipEnvelope:", 1))
    mutated = deepcopy(declaration)
    mutated["source_sha256"] = hashlib.sha256(unreachable.read_bytes()).hexdigest()
    ck(any("control transfer occurs before" in error
           for error in publication_errors(unreachable, expected, mutated)),
       "publication validator accepted unreachable envelope initialization")
    erased = _ProjectPath(temporary) / "erased.ic10"
    erased.write_text(source.replace("Loop:\nyield", "Loop:\nyield\nclr db", 1))
    mutated["source_sha256"] = hashlib.sha256(erased.read_bytes()).hexdigest()
    ck(any("can erase" in error for error in publication_errors(erased, expected, mutated)),
       "publication validator accepted a post-publication clear")
    pushed = _ProjectPath(temporary) / "pushed.ic10"
    pushed.write_text(source.replace("Loop:\nyield", "move sp 320\npush r0\nLoop:\nyield", 1))
    mutated["source_sha256"] = hashlib.sha256(pushed.read_bytes()).hexdigest()
    ck(any("dynamic own-stack write occurs before" in error
           for error in publication_errors(pushed, expected, mutated)),
       "publication validator ignored an own-stack push before the first yield")
    extension_expected = dict(expected)
    extension_expected[327] = 400
    extension_expected.update({400: 31416054, 401: 1, 402: 4, 403: 0})
    delayed = _ProjectPath(temporary) / "delayed-extension.ic10"
    delayed.write_text(
        source.replace("poke 327 0", "poke 327 400", 1).replace(
            "Loop:\nyield",
            "Loop:\nyield\npoke 400 31416054\npoke 401 1\npoke 402 4\npoke 403 0",
            1,
        )
    )
    mutated["source_sha256"] = hashlib.sha256(delayed.read_bytes()).hexdigest()
    ck(any("does not retain S400" in error for error in publication_errors(
        delayed, extension_expected, mutated, set(range(320, 328)) | set(range(400, 404))
    )), "publication validator accepted an extension initialized after the first yield")

if fails:
    print("Stack envelope tests: FAIL")
    [print(" -", failure) for failure in fails]
    sys.exit(1)
print("Stack envelope tests: PASS")
print(" - all five pilots preserve their established payload headers while publishing v1")
print(" - monitor discovers semantic ServiceId and payload base from only S320..S327")
print(" - schema zero pairing, extension bounds, and the legacy source-set gate fail closed")
