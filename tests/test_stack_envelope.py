#!/usr/bin/env python3
"""Exercise the common S0 stack header, its monitor reader, and migration gates."""
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
    BASE,
    LENGTH,
    build_inventory,
    canonical_schema_pairs,
    declaration_errors,
    extension_ownership_errors,
    legacy_source_digest,
    load_declarations,
    publication_errors,
)

ROOT = _PROJECT_ROOT
MONITOR = "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
fails: list[str] = []


def ck(condition, message):
    if not condition:
        fails.append(message)


contracts, _, protocols, _ = build_all(ROOT)
inventory = build_inventory(ROOT, contracts, protocols)
validate(inventory, json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text()))
ck(inventory["envelope"]["base"] == 0 and inventory["envelope"]["length"] == 5,
   "the common header is no longer the first five stack cells")
ck(inventory["totals"] == {
    "deployable_programs": 173,
    "migrated_v1": 1,
    "legacy_exempt": 172,
    "backlog_literal_cell_users": 156,
    "backlog_dynamic_range_users": 62,
}, "generated coverage/backlog totals changed without review")
by_source = {item["source"]: item for item in inventory["services"]}
ck(by_source[MONITOR]["envelope"]["magic"] == 31416052,
   "the migrated monitor does not carry its registered magic as its on-stack identity")
ck(all(item["current_layout"]["payload_inventory_status"] ==
       ("declared-stack-protocol" if item["current_layout"]["headers"]
        else "no-declared-stack-protocol") for item in inventory["services"]),
   "payload inventory does not distinguish declared protocols from no protocol")

# Every backlog row records what the migration must move, per program.
backlog = [item for item in inventory["services"] if item["status"] == "legacy-exempt"]
ck(sum(bool(item["window_collision"]["literal_cells"]) for item in backlog) == 156,
   "backlog rows no longer report which programs occupy S0..S4")
ck(all("legacy_exemption" in item for item in backlog),
   "a backlog row lost its explicit exemption record")

# An extension is advertised as externally readable from the S4 pointer.
extension_source = """poke 0 7
poke 1 1
poke 2 0
poke 3 0
poke 4 400
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

# The monitor publishes the common header and owns only its diagnostic cells.
vm = IC10((ROOT / MONITOR).read_text())
vm.run(1)
ck([vm.stack.get(cell) for cell in range(BASE, BASE + LENGTH)] == [31416052, 1, 0, 0, 0],
   "monitor does not publish the common header at S0..S4")
ck(vm.stack.get(9) == 0, "monitor does not explicitly initialize its generation cell")
contract = next(document for document in contracts.values() if document["source"] == MONITOR)
ck([header for header in contract["own_stack"]["headers"]
    if header["base"] == 0 and header["magic"] == 31416052 and header["abi"] == 1],
   "the monitor's S0/S1 identity is not a verified contract header")

# Discovery reads only S0..S4 and reports the target's identity.
target = Device(201, stack={0: 27182818, 1: 2, 2: 0, 3: 0, 4: 0},
                props={"ReferenceId": 201, "PrefabHash": "HASH:StructureCircuitHousing"})
selector = Device(202, props={"ReferenceId": 202, "Setting": -1})
output = Device(203, props={"ReferenceId": 203, "Setting": 0})
monitor = IC10((ROOT / MONITOR).read_text(), {"d0": target, "d1": selector, "d2": output})
monitor.run(2)
ck(monitor.stack.get(5) == 3, "monitor rejected a valid common header")
ck(monitor.stack.get(7) == 27182818, "monitor did not report the discovered service magic")
ck(output.props.get("Setting") == monitor.stack.get(7),
   "discovered identity was not mirrored to the optional output")

# Extension headers are validated before any family-specific cells are trusted.
target.stack.update({4: 508, 508: 31416054, 509: 1, 510: 4, 511: 0})
monitor.run(1)
ck(monitor.stack.get(5) == 3, "monitor rejected an in-bounds four-cell extension")
target.stack.update({4: 509, 509: 31416054, 510: 1, 511: 4})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted an extension that exceeds S511")
target.stack.update({4: 4})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted an extension overlapping the common header")
target.stack.update({4: 100, 100: 31416054, 101: 1, 102: 193, 103: 0})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted an extension above the v1 length limit")
target.stack.update({4: 508, 508: 31416054, 509: 1, 510: 4, 511: 1})
monitor.run(1)
ck(monitor.stack.get(5) == -6,
   "monitor accepted HAS_IMPLEMENTATION_ID without an in-bounds ImplementationId cell")
target.stack.update({4: 508, 508: 31416054, 509: 1, 510: 4, 511: 2})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted reserved extension flag bits")
target.stack.update({
    4: 507, 507: 31416054, 508: 1, 509: 5, 510: 1,
    511: "HASH:ic10.implementation.example",
})
monitor.run(1)
ck(monitor.stack.get(5) == 3, "monitor rejected a valid ImplementationId extension")
for invalid_identity in (0, 1.5, float("nan")):
    target.stack.update({511: invalid_identity})
    monitor.run(1)
    ck(monitor.stack.get(5) == -6,
       f"monitor accepted invalid ImplementationId {invalid_identity!r}")

# Header shape is validated cell by cell, and a failure never invents an address.
target.stack.update({4: 0, 2: "HASH:Schema", 3: 0})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted mismatched schema zero/unknown semantics")
target.stack.update({2: 0, 3: 0, 1: 1.5})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted a fractional ABI")
target.stack.update({1: float("nan")})
monitor.run(1)
ck(monitor.stack.get(5) == -6, "monitor accepted a NaN ABI")
for invalid_version in (-1, 1.5, float("nan")):
    target.stack.update({1: 2, 2: "HASH:Schema", 3: invalid_version})
    monitor.run(1)
    ck(monitor.stack.get(5) == -6,
       f"monitor accepted invalid SchemaVersion {invalid_version!r}")
for invalid_magic in (0, 1.5, float("nan")):
    target.stack.update({2: 0, 3: 0, 0: invalid_magic})
    monitor.run(1)
    ck(monitor.stack.get(5) == -5 and monitor.stack.get(6) == -1,
       f"monitor mis-reported an unusable magic {invalid_magic!r}")

# Declared schemas bind to a canonical registry entry or to the source's own check.
pairs = canonical_schema_pairs(ROOT)
ck(('HASH("DirectorySchema.ResourceLink")', 1) in pairs,
   "canonical directory schema versions are not recognised")
ck(('HASH("CatalogSchema.ResourceTransform")', 4) in pairs,
   "canonical catalog schema versions are not recognised")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR].update({"schema_id": "DirectorySchema.ResourceLink", "schema_version": 9})
ck(any("not canonical and is not verified" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a schema/version no registry or source backs")

# The reviewed source-set digest is the enforcement gate for every future program.
bad = deepcopy(load_declarations(ROOT))
bad["legacy_exemption"]["source_set_sha256"] = "0" * 64
ck(any("source set changed" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted an unreviewed baseline change")
bad = deepcopy(load_declarations(ROOT))
bad["legacy_exemption"]["sources"] = [
    source for source in bad["legacy_exemption"]["sources"] if source != MONITOR
]
bad["legacy_exemption"]["source_count"] -= 1
bad["legacy_exemption"]["source_set_sha256"] = legacy_source_digest(
    bad["legacy_exemption"]["sources"]
)
ck(any("baseline is immutable" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator allowed the pre-v1 baseline to be rewritten")
bad = deepcopy(load_declarations(ROOT))
del bad["migrated"][MONITOR]
bad["legacy_exemption"]["sources"] = [
    source for source in bad["legacy_exemption"]["sources"] if source != MONITOR
]
ck(any("must publish the header or receive explicit exemptions" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator automatically classified an undeclared deployable as legacy")

# Declarations bind to canonical contract and published header identities.
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["service_id"] = "ic10.script.unrelated.service"
ck(any("canonical contract identity" in error for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a ServiceId that differs from the script contract")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["magic"] = 31415999
ck(any("do not publish the declared magic" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a magic the source never publishes at S0")
ck(extension_ownership_errors([{"start": 0, "end": 15}], 12, 4),
   "validator allowed an extension to overwrite established payload cells")
ck(not extension_ownership_errors([{"start": 0, "end": 15}], 16, 4),
   "validator rejected an extension in unowned stack cells")
for field in ("magic", "service_abi", "extension_base"):
    bad = deepcopy(load_declarations(ROOT))
    bad["migrated"][MONITOR][field] = "1"
    try:
        malformed_errors = declaration_errors(ROOT, contracts, bad)
    except TypeError:
        malformed_errors = []
    ck(any(field in error for error in malformed_errors),
       f"malformed {field} crashed or bypassed declaration validation")

# Text in an unreachable branch or erased after publication is not publication.
declaration = load_declarations(ROOT)["migrated"][MONITOR]
expected = {0: 31416052, 1: 1, 2: 0, 3: 0, 4: 0}
source = (ROOT / MONITOR).read_text()
with TemporaryDirectory() as temporary:
    unreachable = _ProjectPath(temporary) / "unreachable.ic10"
    unreachable.write_text(source.replace("poke 0 31416052", "j Skip\npoke 0 31416052\nSkip:", 1))
    mutated = deepcopy(declaration)
    mutated["source_sha256"] = hashlib.sha256(unreachable.read_bytes()).hexdigest()
    ck(any("control transfer occurs before" in error
           for error in publication_errors(unreachable, expected, mutated)),
       "publication validator accepted unreachable header initialization")
    erased = _ProjectPath(temporary) / "erased.ic10"
    erased.write_text(source.replace("Loop:\nyield", "Loop:\nyield\nclr db", 1))
    mutated["source_sha256"] = hashlib.sha256(erased.read_bytes()).hexdigest()
    ck(any("can erase" in error for error in publication_errors(erased, expected, mutated)),
       "publication validator accepted a post-publication clear")
    pushed = _ProjectPath(temporary) / "pushed.ic10"
    pushed.write_text(source.replace("Loop:\nyield", "move sp 0\npush r0\nLoop:\nyield", 1))
    mutated["source_sha256"] = hashlib.sha256(pushed.read_bytes()).hexdigest()
    ck(any("dynamic own-stack write occurs before" in error
           for error in publication_errors(pushed, expected, mutated)),
       "publication validator ignored an own-stack push before the first yield")
    extension_expected = dict(expected)
    extension_expected[4] = 400
    extension_expected.update({400: 31416054, 401: 1, 402: 4, 403: 0})
    delayed = _ProjectPath(temporary) / "delayed-extension.ic10"
    delayed.write_text(
        source.replace("poke 4 0", "poke 4 400", 1).replace(
            "Loop:\nyield",
            "Loop:\nyield\npoke 400 31416054\npoke 401 1\npoke 402 4\npoke 403 0",
            1,
        )
    )
    mutated["source_sha256"] = hashlib.sha256(delayed.read_bytes()).hexdigest()
    ck(any("does not retain S400" in error for error in publication_errors(
        delayed, extension_expected, mutated, set(range(BASE, BASE + LENGTH)) | set(range(400, 404))
    )), "publication validator accepted an extension initialized after the first yield")

if fails:
    print("Stack header tests: FAIL")
    [print(" -", failure) for failure in fails]
    sys.exit(1)
print("Stack header tests: PASS")
print(" - the monitor publishes S0..S4 and reads a target's identity from those cells alone")
print(" - schema binding, extension bounds, and the pre-v1 baseline gate fail closed")
print(f" - migration backlog: {len(backlog)} programs, {inventory['totals']['backlog_literal_cell_users']} using S0..S4")
