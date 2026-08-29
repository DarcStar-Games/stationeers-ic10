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
    schema_hash,
    build_inventory,
    canonical_schema_pairs,
    declaration_errors,
    extension_ownership_errors,
    generation_errors,
    state_errors,
    legacy_source_digest,
    load_declarations,
    publication_errors,
)

ROOT = _PROJECT_ROOT
MONITOR = "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
READER = "ic10/live-commissioning/stack_header_reader_v1_0.ic10"
fails: list[str] = []


def ck(condition, message):
    if not condition:
        fails.append(message)


contracts, _, protocols, _ = build_all(ROOT)
inventory = build_inventory(ROOT, contracts, protocols)
validate(inventory, json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text()))
ck(inventory["envelope"]["base"] == 0 and inventory["envelope"]["length"] == 8,
   "the common header is no longer the first eight stack cells")
ck(inventory["totals"] == {
    "deployable_programs": 174,
    "migrated_v1": 42,
    "legacy_exempt": 132,
    "backlog_reserved_cell_users": 120,
    "backlog_dynamic_range_users": 43,
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
ck(sum(bool(set(item["window_collision"]["literal_cells"]) & set(range(2, 8)))
       for item in backlog) == 120,
   "backlog rows no longer report which programs occupy the reserved cells")
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

# The monitor publishes the mandatory header cells and its declared state.
vm = IC10((ROOT / MONITOR).read_text())
vm.run(1)
ck(vm.stack.get(0) == 31416052 and vm.stack.get(1) == 1,
   "monitor does not publish its identity at S0/S1")
ck(vm.stack.get(2) == 20, "monitor does not publish the derived capability mask at S2")
ck(vm.stack.get(5) == 1, "monitor does not publish its booting state at S5")
ck(vm.stack.get(7) == 0, "monitor does not initialize its generation cell to zero")
contract = next(document for document in contracts.values() if document["source"] == MONITOR)
ck([header for header in contract["own_stack"]["headers"]
    if header["base"] == 0 and header["magic"] == 31416052 and header["abi"] == 1],
   "the monitor's S0/S1 identity is not a verified contract header")

# The Generic Telemetry family migrated additively: the S96 block never moved.
telemetry = [item for item in inventory["services"]
             if item.get("envelope", {}).get("pilot_family") == "generic-telemetry"]
ck(len(telemetry) == 7, "the Generic Telemetry family is not fully migrated")
for item in telemetry:
    envelope = item["envelope"]
    ck(envelope["telemetry_base"] == 96 and envelope["capability_mask"] == 8,
       f"{item['source']}: does not advertise its telemetry block through S7")
    runtime = IC10((ROOT / item["source"]).read_text())
    runtime.run(1)
    ck(runtime.stack.get(96) == 27182818,
       f"{item['source']}: the established telemetry magic moved")
    ck(runtime.stack.get(0) == envelope["magic"] and runtime.stack.get(1) == 1,
       f"{item['source']}: does not publish its identity at S0/S1")
    ck(runtime.stack.get(2) == 8 and runtime.stack.get(6) == 96,
       f"{item['source']}: does not publish the telemetry pointer it declares")
    ck(sorted(header["base"] for header in item["current_layout"]["headers"]) == [0, 96],
       f"{item['source']}: contract does not carry both the header and the telemetry block")

# The reader discovers S0..S7 and republishes only what the mask declares.
target = Device(201, stack={0: 27182818, 1: 2, 2: 0},
                props={"ReferenceId": 201, "PrefabHash": "HASH:StructureCircuitHousing"})
mirror = Device(202, props={"ReferenceId": 202, "Setting": 0})
reader = IC10((ROOT / READER).read_text(), {"d0": target, "d1": mirror})
reader.run(2)
ck(reader.stack.get(8) == 3, "reader rejected a valid header that declares no optional field")
ck(reader.stack.get(9) == 27182818 and reader.stack.get(10) == 2,
   "reader did not republish the discovered identity and ABI")
ck(reader.stack.get(17) == 201, "reader did not report the target ReferenceId")
ck(reader.stack.get(5) == 2, "reader does not report ready state once its target is wired")
ck(mirror.props.get("Setting") == 27182818,
   "discovered identity was not mirrored to the optional output")
ck([reader.stack.get(cell) for cell in range(12, 17)] == [0, 0, 0, 0, 0],
   "reader republished fields the capability mask never declared")

# Stale cells outside the mask are never read, so they cannot fail a valid header.
target.stack.update({3: float("nan"), 4: 1.5, 5: 99, 6: 4, 7: -3})
reader.run(1)
ck(reader.stack.get(8) == 3, "reader read cells the capability mask does not declare")
target.stack.update({2: 32})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted a reserved capability bit")

# Each declared field is validated and then republished.
target.stack.update({2: 1, 3: "HASH:DirectorySchema.ResourceLink.v1"})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(12) == "HASH:DirectorySchema.ResourceLink.v1",
   "reader did not republish a declared schema identity")
for bad_schema in (0, 1.5, float("nan")):
    target.stack.update({3: bad_schema})
    reader.run(1)
    ck(reader.stack.get(8) == -6, f"reader accepted schema identity {bad_schema!r}")
target.stack.update({2: 4, 5: 2})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(14) == 2,
   "reader did not republish a declared state")
for bad_state in (-1, 6, 2.5, float("nan")):
    target.stack.update({5: bad_state})
    reader.run(1)
    ck(reader.stack.get(8) == -6, f"reader accepted state value {bad_state!r}")
target.stack.update({2: 8, 6: 96})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(15) == 96,
   "reader did not republish a declared telemetry base")
for bad_base in (7, 512, 96.5, float("nan")):
    target.stack.update({6: bad_base})
    reader.run(1)
    ck(reader.stack.get(8) == -6, f"reader accepted telemetry base {bad_base!r}")
target.stack.update({2: 16, 7: 4})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(16) == 4,
   "reader did not republish a declared generation")
for bad_generation in (-1, 2.5, float("nan")):
    target.stack.update({7: bad_generation})
    reader.run(1)
    ck(reader.stack.get(8) == -6, f"reader accepted generation {bad_generation!r}")

# HAS_EXTENSION: bounds are checked before any family cell is trusted.
target.stack.update({2: 2, 4: 508, 508: 31416054, 509: 1, 510: 4, 511: 0})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(13) == 508,
   "reader rejected an in-bounds four-cell extension")
target.stack.update({4: 509, 509: 31416054, 510: 1, 511: 4})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted an extension that exceeds S511")
target.stack.update({4: 7})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted an extension overlapping the common header")
target.stack.update({4: 100, 100: 31416054, 101: 1, 102: 193, 103: 0})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted an extension above the v1 length limit")
target.stack.update({4: 508, 508: 31416054, 509: 1, 510: 4, 511: 1})
reader.run(1)
ck(reader.stack.get(8) == -6,
   "reader accepted HAS_IMPLEMENTATION_ID without an in-bounds ImplementationId cell")
target.stack.update({4: 508, 508: 31416054, 509: 1, 510: 4, 511: 2})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted reserved extension flag bits")

# Identity itself is validated, and a failed read publishes no stale discovery.
target.stack.update({2: 0, 1: 1.5})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted a fractional ABI")
target.stack.update({1: float("nan")})
reader.run(1)
ck(reader.stack.get(8) == -6, "reader accepted a NaN ABI")
for invalid_magic in (0, 1.5, float("nan")):
    target.stack.update({1: 2, 0: invalid_magic})
    reader.run(1)
    ck(reader.stack.get(8) == -5, f"reader mis-reported an unusable magic {invalid_magic!r}")
    ck(reader.stack.get(11) == 0 and reader.stack.get(15) == 0,
       "a failed read republished the previous target's fields")

# The reader publishes the same header it reads, and fences its own samples.
solo = IC10((ROOT / READER).read_text())
solo.run(2)
ck(solo.stack.get(5) == 4 and solo.stack.get(8) == -1,
   "an unwired reader does not report blocked state alongside its missing target")
solo = IC10((ROOT / READER).read_text())
solo.run(1)
ck([solo.stack.get(cell) for cell in (0, 1, 2, 7)] == [31416067, 1, 20, 0],
   "the reader does not publish the header it validates")

# State packs a v1 field, reserved zeros, and declared service-specific bits.
ck(not state_errors({2, 4}, 0), "a plain v1 state value was rejected")
ck(not state_errors({2 | (5 << 8)}, 5), "a declared custom state bit was rejected")
ck(any("undefined v1 state field" in error for error in state_errors({7}, 0)),
   "an undefined state field passed validation")
ck(any("reserved bit" in error for error in state_errors({2 | 0x10}, 0)),
   "a reserved state bit passed validation")
ck(any("never declared" in error for error in state_errors({2 | (1 << 8)}, 0)),
   "an undeclared custom state bit passed validation")
ck(any("53-bit cell width" in error for error in state_errors({2 ** 53}, 0)),
   "a state value beyond the cell's exact integer width passed validation")
ck(any("53-bit cell width" in error for error in state_errors({-1, 2.5}, 0)),
   "a negative or fractional state passed validation")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["custom_state_bits"] = 2 ** 60
ck(any("custom_state_bits must fit" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "custom state bits outside the usable cell width were accepted")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["publishes_state"] = False
bad["migrated"][MONITOR]["custom_state_bits"] = 1
ck(any("custom state bits require HAS_STATE" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "custom state bits were accepted without a declared state cell")

# An identity-only migration publishes three cells and declares nothing optional.
worker = by_source["ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10"]
ck(worker["envelope"]["capability_mask"] == 0,
   "an identity-only service declared optional header fields")
vm_worker = IC10((ROOT / worker["source"]).read_text())
vm_worker.run(1)
ck([vm_worker.stack.get(cell) for cell in (0, 1, 2)] == [31416071, 1, 0],
   "the migration worker does not publish an identity-only header")

# The capability mask is derived from the declaration, never hand-written.
ck(by_source[MONITOR]["envelope"]["capability_mask"] == 20,
   "the generated inventory does not derive the monitor's capability mask")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["telemetry_base"] = 96
ck(any("S6 must be written exactly as 96" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "a declared telemetry base did not require the source to publish it")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["telemetry_base"] = 4
ck(any("cannot point inside the common header" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a telemetry base inside the reserved header")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR]["publishes_state"] = False
ck(any("reserved unless the service declares HAS_STATE" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "a source writing S6 passed without declaring HAS_STATE")

declaration = load_declarations(ROOT)["migrated"][MONITOR]
mask_expected = {0: 31416052, 1: 1, 2: 20, 7: 0}

# The state cell is the one header cell publication may change afterwards.
ck(not any("post-init write can change" in error
           for error in publication_errors(
               ROOT / MONITOR, mask_expected, declaration,
               set(range(BASE, BASE + LENGTH)), frozenset({5, 7}),
           )),
   "the declared state cell was treated as immutable after publication")
ck(any("post-init write can change reserved S5" in error
       for error in publication_errors(
           ROOT / MONITOR, mask_expected, declaration, set(range(BASE, BASE + LENGTH))
       )),
   "an undeclared mutable header cell escaped the publication gate")

# One cell carries the schema and the version it is at.
ck(schema_hash("DirectorySchema.ResourceLink", 1)
   == 'HASH("DirectorySchema.ResourceLink.v1")',
   "the published schema identity does not carry its version")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][MONITOR].update(
    {"schema_id": "DirectorySchema.ResourceLink", "schema_version": 1})
ck(any('S3 must be written exactly as HASH("DirectorySchema.ResourceLink.v1")' in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "a declared schema did not require the folded identity at S3")

# The generation is initialized, advanced, and published last.
published_last = [["poke", "7", "0"], ["yield"], ["poke", "9", "r0"], ["poke", "7", "r3"]]
ck(not generation_errors(published_last, {}, True),
   "a correctly ordered generation was rejected")
ck(any("last cell published" in error for error in generation_errors(
    published_last[:-1] + [["poke", "7", "r3"], ["poke", "9", "r0"]], {}, True)),
   "a generation published before other cells passed the ordering rule")
ck(any("requires S7 to be published" in error for error in generation_errors(
    [["poke", "9", "0"], ["yield"]], {}, True)),
   "a service declaring HAS_GENERATION without publishing S7 passed")
ck(any("reserved unless" in error for error in generation_errors(published_last, {}, False)),
   "an undeclared generation cell was accepted")

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
expected = {0: 31416052, 1: 1, 2: 20, 7: 0}
source = (ROOT / MONITOR).read_text()
with TemporaryDirectory() as temporary:
    unreachable = _ProjectPath(temporary) / "unreachable.ic10"
    unreachable.write_text(source.replace("poke 0 31416052", "j Skip\npoke 0 31416052\nSkip:", 1))
    mutated = deepcopy(declaration)
    mutated["source_sha256"] = hashlib.sha256(unreachable.read_bytes()).hexdigest()
    ck(any("control transfer occurs before" in error
           for error in publication_errors(unreachable, expected, mutated)),
       "publication validator accepted unreachable header initialization")
    guarded = _ProjectPath(temporary) / "guarded.ic10"
    guarded.write_text(source.replace("poke 0 31416052",
        "get r0 db 31\nbeq r0 31416052 Init\nclr db\npoke 31 31416052\nInit:\npoke 0 31416052", 1))
    mutated["source_sha256"] = hashlib.sha256(guarded.read_bytes()).hexdigest()
    ck(not [error for error in publication_errors(guarded, expected, mutated)
            if "control transfer" in error or "does not retain" in error],
       "publication validator rejected a reflash guard that provably publishes on both paths")
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
        source.replace("poke 2 20", "poke 2 22\npoke 4 400", 1).replace(
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
print(" - the reader validates a target from S0..S7 alone and republishes only declared fields")
print(" - schema binding, extension bounds, and the pre-v1 baseline gate fail closed")
print(f" - migration backlog: {len(backlog)} programs, {inventory['totals']['backlog_reserved_cell_users']} using S2..S7")
