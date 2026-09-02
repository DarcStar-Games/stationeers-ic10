#!/usr/bin/env python3
"""Exercise the common S0 stack header, its monitor reader, and migration gates."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import sys
from tempfile import TemporaryDirectory

from framework.ic10_harness import Device, IC10
from framework.json_schema import validate
from framework.script_contracts import build_all
from framework.script_contracts.own_stack import analyze_own_stack
from framework.ic10_source import game_hash
from framework.stack_envelope import (
    BASE,
    CAPABILITY_BITS_V1,
    FIELD_CAPABILITY_BITS_V1,
    HAS_SCHEMA,
    HAS_ASYNC_REQUEST_V1,
    HAS_BANKED_TRANSACTION_V1,
    HAS_GENERIC_JOB_ABI_V1,
    LENGTH,
    STATE_CELL,
    NormalizedDeclaration,
    StackRange,
    schema_hash,
    schema_hash_token,
    build_inventory,
    canonical_schema_pairs,
    declaration_errors,
    declaration_set_errors,
    expected_envelope_cells,
    extension_rule_result,
    extension_ownership_errors,
    generation_errors,
    identity_header_errors,
    legacy_layout_errors,
    normalize_declaration,
    post_init_coverage_errors,
    post_init_range_errors,
    proven_post_init_writes,
    publication_rule_errors,
    schema_capability_errors,
    state_errors,
    state_generation_rule_errors,
    standard_participation_errors,
    standards_by_source,
    legacy_source_digest,
    load_declarations,
    publication_errors,
)

ROOT = _PROJECT_ROOT
MONITOR = "ic10/live-commissioning/stack_cell_monitor_v1_0.ic10"
READER = "ic10/live-commissioning/stack_header_reader_v1_0.ic10"
# `bgt r2 3 Bad` bounds its Save loop, so its post-init write window is three proven cells
RANKER = "ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10"
# clears and writes a 64-cell NodeId presence bitmap at S448..S511 on every scan
ADAPTER = "ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10"
fails: list[str] = []


def ck(condition, message):
    if not condition:
        fails.append(message)


contracts, _, protocols, _ = build_all(ROOT)
inventory = build_inventory(ROOT, contracts, protocols)
validate(inventory, json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text()))
ck(inventory["envelope"]["base"] == 0 and inventory["envelope"]["length"] == 8,
   "the common header is no longer the first eight stack cells")
ck(CAPABILITY_BITS_V1 == 255 and inventory["envelope"]["standard_capability_bits"] == {
    "ASYNC_REQUEST_V1": HAS_ASYNC_REQUEST_V1,
    "BANKED_TRANSACTION_V1": HAS_BANKED_TRANSACTION_V1,
    "GENERIC_JOB_ABI_V1": HAS_GENERIC_JOB_ABI_V1,
}, "the v1 standard capability-bit registry changed without review")
ck(inventory["totals"] == {
    "deployable_programs": 181,
    "migrated_v1": 181,
    "legacy_exempt": 0,
    "backlog_reserved_cell_users": 0,
    "backlog_dynamic_range_users": 0,
}, "generated coverage/backlog totals changed without review")
by_source = {item["source"]: item for item in inventory["services"]}


def expected_publication_cost(item):
    envelope = item.get("envelope", {})
    mask = envelope.get("capability_mask", 0)
    externally_assigned = HAS_SCHEMA if envelope.get("schema_assigned_externally") else 0
    return 3 + (mask & FIELD_CAPABILITY_BITS_V1 & ~externally_assigned).bit_count()


ck(all(
    item["stack_pressure"]["measured_v1_publication_cost_lines"]
    == expected_publication_cost(item)
    for item in inventory["services"]
), "per-service publication costs do not match mandatory and declared field writes")
for external_schema_source in (
    "ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10",
    "ic10/directory-core/generic_registry_directory_host_v2_0.ic10",
):
    ck(by_source[external_schema_source]["stack_pressure"]
       ["measured_v1_publication_cost_lines"] == 3,
       f"{external_schema_source}: externally assigned schema adds a source publication line")
    ck(by_source[external_schema_source]["envelope"]["schema_assigned_externally"],
       f"{external_schema_source}: inventory omits external schema ownership")
job_store = by_source["ic10/generic-jobs/generic_job_store_v1_0.ic10"]["envelope"]
config_host = by_source["ic10/controller-config/generic_persistent_config_host_v1_1.ic10"]["envelope"]
directory_adapter = by_source[
    "ic10/controller-discovery/controller_directory_adapter_v4_0.ic10"
]["envelope"]
ck(job_store["capability_mask"] == 224 and job_store["standard_capabilities"] == [
    "ASYNC_REQUEST_V1", "BANKED_TRANSACTION_V1", "GENERIC_JOB_ABI_V1"
], "Generic Job Store does not publish all three data-derived standard capabilities")
ck(config_host["capability_mask"] == 96 and config_host["standard_capabilities"] == [
    "ASYNC_REQUEST_V1", "BANKED_TRANSACTION_V1"
], "Config Host does not publish its async and banked-transaction capabilities")
ck(directory_adapter["capability_mask"] == 49 and directory_adapter[
    "standard_capabilities"
] == ["ASYNC_REQUEST_V1"], "directory adapter did not preserve field bits with async")
ck(by_source[MONITOR]["envelope"]["magic"] == game_hash("StackCellMonitor.v1"),
   "the migrated monitor does not carry its registered magic as its on-stack identity")
ck(all(item["current_layout"]["payload_inventory_status"] ==
       ("declared-stack-protocol" if item["current_layout"]["headers"]
        else "no-declared-stack-protocol") for item in inventory["services"]),
   "payload inventory does not distinguish declared protocols from no protocol")

# Every backlog row records what the migration must move, per program.
backlog = [item for item in inventory["services"] if item["status"] == "legacy-exempt"]
ck(sum(bool(set(item["window_collision"]["literal_cells"]) & set(range(2, 8)))
       for item in backlog) == 0,
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
extension_contract, _ = analyze_own_stack(
    extension_source, extension_rows, {}, [{"base": 0, "magic": 7, "abi": 1}], {}
)
ck({"start": 400, "end": 404} in extension_contract["external_readable_ranges"],
   "script contract does not advertise a declared extension as externally readable")

# The monitor publishes the mandatory header cells and its declared state.
vm = IC10((ROOT / MONITOR).read_text())
vm.run(1)
ck(vm.stack.get(0) == 'HASH:StackCellMonitor.v1' and vm.stack.get(1) == 1,
   "monitor does not publish its identity at S0/S1")
ck(vm.stack.get(2) == 20, "monitor does not publish the derived capability mask at S2")
ck(vm.stack.get(5) == 1, "monitor does not publish its booting state at S5")
ck(vm.stack.get(7) == 0, "monitor does not initialize its generation cell to zero")
contract = next(document for document in contracts.values() if document["source"] == MONITOR)
ck([header for header in contract["own_stack"]["headers"]
    if header["base"] == 0 and header["magic"] == game_hash("StackCellMonitor.v1") and header["abi"] == 1],
   "the monitor's S0/S1 identity is not a verified contract header")

# The Generic Telemetry family migrated additively: the S96 block never moved.
telemetry = [item for item in inventory["services"]
             if item.get("envelope", {}).get("pilot_family") == "generic-telemetry"]
ck(len(telemetry) == 7, "the Generic Telemetry family is not fully migrated")
for item in telemetry:
    envelope = item["envelope"]
    ck(envelope["telemetry_base"] == 96 and envelope["capability_mask"] == 8,
       f"{item['source']}: does not advertise its telemetry block through S6")
    runtime = IC10((ROOT / item["source"]).read_text())
    runtime.run(1)
    ck(runtime.stack.get(96) == 27182818,
       f"{item['source']}: the established telemetry magic moved")
    ck(runtime.stack.get(0) == f'HASH:{envelope["contract"]}.v{envelope["service_abi"]}'
       and runtime.stack.get(1) == 1,
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
target.stack.update({2: 224})
reader.run(1)
ck(reader.stack.get(8) == 3 and reader.stack.get(11) == 224,
   "reader rejected allocated cross-cutting standard capabilities")
target.stack.update({2: 256})
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
ck([solo.stack.get(cell) for cell in (0, 1, 2, 7)] == ['HASH:StackHeaderReader.v1', 1, 20, 0],
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
ck([vm_worker.stack.get(cell) for cell in (0, 1, 2)] == ['HASH:CatalogItemMigrationWorker.v1', 1, 0],
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

# Cross-cutting standard bits come from reviewed data, not validator source text.
participation = load_declarations(ROOT)["standard_participation"]
by_participant = standards_by_source(participation)
ck(by_participant["ic10/generic-jobs/generic_job_store_v1_0.ic10"] == frozenset({
    "ASYNC_REQUEST_V1", "BANKED_TRANSACTION_V1", "GENERIC_JOB_ABI_V1"
}), "standard participation did not invert into per-service capabilities")
ck(not standard_participation_errors(load_declarations(ROOT)["migrated"], participation),
   "the reviewed standard participation registry failed validation")
bad_participation = deepcopy(participation)
bad_participation["ASYNC_REQUEST_V1"].append("ic10/missing.ic10")
ck(any("not migrated services" in error for error in standard_participation_errors(
    load_declarations(ROOT)["migrated"], bad_participation
)), "an unknown standard participant passed validation")
bad_participation = deepcopy(participation)
del bad_participation["GENERIC_JOB_ABI_V1"]
ck(any("keys differ" in error for error in standard_participation_errors(
    load_declarations(ROOT)["migrated"], bad_participation
)), "an incomplete v1 standard capability registry passed validation")
bad = deepcopy(load_declarations(ROOT))
async_participants = bad["standard_participation"]["ASYNC_REQUEST_V1"]
async_participants[0], async_participants[1] = async_participants[1], async_participants[0]
ck(declaration_errors(ROOT, contracts, bad) == [
    "ASYNC_REQUEST_V1 participant list must be sorted"
], "a presentation error discarded valid participation and cascaded mask failures")
bad = deepcopy(load_declarations(ROOT))
bad["standard_participation"]["ASYNC_REQUEST_V1"] = "not-a-list"
ck(declaration_errors(ROOT, contracts, bad) == [
    "ASYNC_REQUEST_V1 participants must be an explicit path list"
], "an unusable participant list cascaded into false source-mask failures")
bad = deepcopy(load_declarations(ROOT))
del bad["standard_participation"]["ASYNC_REQUEST_V1"]
ck(len(declaration_errors(ROOT, contracts, bad)) == 1 and "keys differ" in
   declaration_errors(ROOT, contracts, bad)[0],
   "a missing participant list cascaded into false source-mask failures")
bad = deepcopy(load_declarations(ROOT))
bad["standard_participation"]["ASYNC_REQUEST_V1"].remove(
    "ic10/generic-jobs/generic_job_store_v1_0.ic10"
)
ck(any("S2 must be written exactly as 192" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "removing declared standard participation did not change the derived capability mask")

declaration = load_declarations(ROOT)["migrated"][MONITOR]
mask_expected = {0: game_hash("StackCellMonitor.v1"), 1: 1, 2: 20, 7: 0}

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
   == game_hash("DirectorySchema.ResourceLink.v1")
   and schema_hash_token("DirectorySchema.ResourceLink", 1)
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
bad["migrated"][MONITOR]["contract"] = "UnpublishedService"
ck(any("do not publish the declared magic" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted an identity the source never publishes at S0")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][RANKER]["post_init_dynamic_write_ranges"] = [[16, 31]]
bad["migrated"][RANKER]["legacy_owned_ranges"] = [[8, 11], [16, 31], [32, 34]]
ck(any("post-init dynamic write range claims S19..S31" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a reviewed post-init range past the source-proven write window")
bad = deepcopy(load_declarations(ROOT))
bad["migrated"][ADAPTER]["post_init_dynamic_write_ranges"] = [[18, 401]]
bad["migrated"][ADAPTER]["legacy_owned_ranges"] = [[10, 401]]
ck(any("provably reach S448..S511" in error
       for error in declaration_errors(ROOT, contracts, bad)),
   "validator accepted a reviewed post-init range omitting cells the source provably writes")
ck(extension_ownership_errors([{"start": 0, "end": 15}], 12, 4),
   "validator allowed an extension to overwrite established payload cells")
ck(not extension_ownership_errors([{"start": 0, "end": 15}], 16, 4),
   "validator rejected an extension in unowned stack cells")
for field in ("contract", "service_abi", "extension_base"):
    bad = deepcopy(load_declarations(ROOT))
    bad["migrated"][MONITOR][field] = 1 if field == "contract" else "1"
    try:
        malformed_errors = declaration_errors(ROOT, contracts, bad)
    except TypeError:
        malformed_errors = []
    ck(any(field in error for error in malformed_errors),
       f"malformed {field} crashed or bypassed declaration validation")

# Normalization gates independent rules, which accept a minimal typed declaration.
minimal = NormalizedDeclaration(source="minimal.ic10")
minimal_contract = {
    "identity": {"service_id": "ic10.script.example"},
    "own_stack": {
        "headers": [{"base": 0, "contract": "Example",
                     "magic": game_hash("Example.v1"), "abi": 1}],
        "literal_reads": [],
        "literal_writes": [],
        "dynamic_write_ranges": [],
        "dynamic_write_range_source": "none",
    },
}
minimal_writes = {address: {value} for address, value in expected_envelope_cells(minimal).items()}
ck(not identity_header_errors(minimal, minimal_contract),
   "the identity/header rule rejected a minimal normalized declaration")
ck(not schema_capability_errors(minimal, set(), minimal_writes),
   "the schema/capability rule rejected a minimal normalized declaration")
ck(not state_generation_rule_errors(minimal, [["yield"]], {}, minimal_writes),
   "the state/generation rule rejected a minimal normalized declaration")
minimal_extension = extension_rule_result(minimal, minimal_writes)
ck(not minimal_extension.errors,
   "the extension rule rejected a minimal normalized declaration")
ck(not legacy_layout_errors(minimal, minimal_contract, minimal_extension.reserved_cells),
   "the legacy-layout rule rejected a minimal normalized declaration")
ck(not post_init_range_errors(minimal, minimal_contract, minimal_extension.reserved_cells),
   "the post-init containment rule rejected a minimal normalized declaration")

# A reviewed post-init dynamic write range is narrower than the contract's derived one
# in time, never wider in space -- and only the wider direction is a contradiction.
windowed_contract = deepcopy(minimal_contract)
windowed_contract["own_stack"]["dynamic_write_ranges"] = [{"start": 16, "end": 18}]
windowed_contract["own_stack"]["dynamic_write_range_source"] = "source-derived"
overclaiming = replace(minimal, post_init_dynamic_write_ranges=(StackRange(16, 31),))
overclaim_errors = post_init_range_errors(
    overclaiming, windowed_contract, minimal_extension.reserved_cells
)
ck(overclaim_errors == ["reviewed post-init dynamic write range claims S19..S31, which the"
                        " source-derived dynamic write range S16..S18 never reaches"],
   "a reviewed post-init range outside the derived one passed or was misreported")
# The message has to name every span it objects to, not just the first: a declaration
# straddling a derived window is corrected by moving both ends, and one span named
# looks like one span wrong.
straddling = post_init_range_errors(
    replace(minimal, post_init_dynamic_write_ranges=(StackRange(14, 20),)),
    windowed_contract, minimal_extension.reserved_cells,
)
ck(straddling == ["reviewed post-init dynamic write range claims S14..S15, S19..S20, which the"
                  " source-derived dynamic write range S16..S18 never reaches"],
   "the containment rule reported only part of a range straddling the derived window")
ck(not post_init_range_errors(
    replace(minimal, post_init_dynamic_write_ranges=(StackRange(17, 17),)),
    windowed_contract, minimal_extension.reserved_cells,
), "the containment rule rejected a reviewed range inside the derived one")
cleared_contract = deepcopy(minimal_contract)
cleared_contract["own_stack"]["dynamic_write_ranges"] = [{"start": 0, "end": 511}]
cleared_contract["own_stack"]["dynamic_write_range_source"] = "source-derived"
ck(not post_init_range_errors(
    replace(minimal, post_init_dynamic_write_ranges=(StackRange(9, 17),)),
    cleared_contract, minimal_extension.reserved_cells,
), "the containment rule fired on a reviewed range far tighter than a boot clear")
# Envelope and extension cells belong to the reserved-overlap rule, which rejects them
# outright; reporting them here as well would name the same cell for a weaker reason.
ck(not post_init_range_errors(
    replace(minimal, post_init_dynamic_write_ranges=(StackRange(0, 7),)),
    windowed_contract, minimal_extension.reserved_cells,
), "the containment rule duplicated the reserved-overlap rule on envelope cells")
extended = replace(minimal, extension_base=64)
extended_writes = {address: {value} for address, value in expected_envelope_cells(extended).items()}
extended_writes.update({64: {31416054}, 65: {1}, 66: {4}, 67: {0}})
extended_reserved = extension_rule_result(extended, extended_writes).reserved_cells
ck(extended_reserved == frozenset(range(64, 68)) and not post_init_range_errors(
    replace(extended, post_init_dynamic_write_ranges=(StackRange(64, 67),)),
    windowed_contract, extended_reserved,
), "the containment rule duplicated the reserved-overlap rule on extension cells")
ck(StackRange(10, 12).cells() == {10, 11, 12},
   "normalized stack ranges do not retain their inclusive cells")
ck(any("missing scripts" in error for error in declaration_set_errors(
    {}, {"missing.ic10": {}}, {"sources": [], "source_count": 0}
)), "the declaration-set rule did not reject a missing migrated source")
with TemporaryDirectory() as temporary:
    temporary_root = _ProjectPath(temporary)
    minimal_source = temporary_root / minimal.source
    minimal_source.write_text('poke 0 HASH("Example.v1")\npoke 1 1\npoke 2 0\nyield\n')
    publishable = replace(
        minimal, source_sha256=hashlib.sha256(minimal_source.read_bytes()).hexdigest()
    )
    ck(not publication_rule_errors(
        temporary_root, publishable, minimal_contract, {}, frozenset()
    ), "the publication rule rejected a minimal normalized declaration")
    # A source with no dynamic write at all belongs to the publication rule, which
    # rejects the whole declaration; the containment rule would name a span instead.
    claiming = replace(publishable, post_init_dynamic_write_ranges=(StackRange(16, 18),))
    ck(any("source has no such writes" in error for error in publication_rule_errors(
        temporary_root, claiming, minimal_contract, {}, frozenset()
    )), "a post-init range against a source with no dynamic write went unreported")
    ck(not post_init_range_errors(claiming, minimal_contract, frozenset()),
       "the containment rule restated a claim the no-dynamic-write rule already owns")
    ck(not post_init_coverage_errors(temporary_root, publishable, frozenset()),
       "the coverage rule rejected a source with no computed write to cover")

    # The coverage rule holds the reviewed range to what the source proves, and only
    # to that. This fixture carries all three cases at once: a guarded computed write
    # before the first yield (S40..S43, which the entry-path rule owns, not this one),
    # a guarded one after it (S16..S19), and one the analysis cannot bound at all,
    # which is exactly what the reviewed range exists to state.
    covered = temporary_root / "covered.ic10"
    covered.write_text(
        'poke 0 HASH("Example.v1")\npoke 1 1\npoke 2 0\n'
        'get r4 db 3\nblt r4 0 Loop\nbgt r4 3 Loop\nadd r5 r4 40\npoke r5 1\n'
        'Loop:\nyield\n'
        'get r0 db 9\nblt r0 0 Loop\nbgt r0 3 Loop\nadd r1 r0 16\npoke r1 1\n'
        'peek r2\nadd r3 r2 200\npoke r3 1\nj Loop\n'
    )
    proved = replace(minimal, source=covered.name)
    ck(proven_post_init_writes(covered) == frozenset({16, 17, 18, 19}),
       "the post-init write proof did not bound a guarded computed write, bounded an"
       " unguarded one, or reached back past the first yield")
    ck(post_init_coverage_errors(
        temporary_root, replace(proved, post_init_dynamic_write_ranges=(StackRange(16, 17),)),
        frozenset(),
    ) == ["post-init computed writes provably reach S18..S19, which the reviewed post-init"
          " dynamic write range does not name and so does not own"],
       "the coverage rule missed proven cells the reviewed range leaves unowned")
    ck(not post_init_coverage_errors(
        temporary_root, replace(proved, post_init_dynamic_write_ranges=(StackRange(16, 19),)),
        frozenset(),
    ), "the coverage rule demanded cells beyond what the source proves")
    # With nothing declared at all the publication rule already names the missing
    # declaration, and a span measured against a range that does not exist reads as
    # though one does.
    covered_publishable = replace(
        proved, source_sha256=hashlib.sha256(covered.read_bytes()).hexdigest()
    )
    ck(any("lack reviewed, source-fingerprinted bounds" in error
           for error in publication_rule_errors(
               temporary_root, covered_publishable, minimal_contract, {}, frozenset())),
       "an undeclared post-init dynamic write stopped being reported at all")
    ck(not post_init_coverage_errors(temporary_root, covered_publishable, frozenset()),
       "the coverage rule measured a span against a declaration that does not exist")
    # Naming a reserved cell is what the overlap rule rejects, so a proven write into
    # one is reported as the program's fault rather than as a range that is too small.
    ck(post_init_coverage_errors(
        temporary_root, replace(proved, post_init_dynamic_write_ranges=(StackRange(16, 19),)),
        frozenset({17}),
    ) == ["post-init computed writes provably reach reserved S17"],
       "the coverage rule asked a declaration to name a cell the overlap rule forbids")

malformed = deepcopy(load_declarations(ROOT)["migrated"][MONITOR])
malformed["contract"] = 1
normalized, shape_errors = normalize_declaration(MONITOR, malformed)
ck(normalized is None and shape_errors == [f"{MONITOR}: contract must be a str"],
   "malformed declaration shape cascaded into secondary validation errors")
for missing_field in (
    "schema_id",
    "implementation_id",
    "legacy_owned_ranges",
    "post_init_dynamic_write_ranges",
):
    missing = deepcopy(load_declarations(ROOT))
    del missing["migrated"][MONITOR][missing_field]
    missing_errors = declaration_errors(ROOT, contracts, missing)
    ck(any(f"{missing_field} is required" in error for error in missing_errors),
       f"missing {missing_field} reached inventory rendering without a shape error")

malformed_top_level = deepcopy(load_declarations(ROOT))
malformed_top_level["migrated"] = []
ck(declaration_errors(ROOT, contracts, malformed_top_level) == [
    "migrated declarations must be an object keyed by source path"
], "malformed migrated declarations cascaded into coverage errors")
malformed_top_level = deepcopy(load_declarations(ROOT))
malformed_top_level["legacy_exemption"]["sources"] = "not-a-list"
ck(declaration_errors(ROOT, contracts, malformed_top_level) == [
    "legacy exemption sources must be an explicit path list"
], "malformed legacy sources cascaded into baseline and classification errors")
for missing_field, expected_error in (
    ("migrated", "migrated declarations are required as an object keyed by source path"),
    ("legacy_exemption", "legacy_exemption is required as an object"),
):
    malformed_top_level = deepcopy(load_declarations(ROOT))
    del malformed_top_level[missing_field]
    ck(declaration_errors(ROOT, contracts, malformed_top_level) == [expected_error],
       f"missing {missing_field} cascaded into derived declaration errors")

for missing_field in (
    "id", "reason", "migration_rule", "sources", "source_count", "source_set_sha256"
):
    malformed_exemption = deepcopy(load_declarations(ROOT))
    del malformed_exemption["legacy_exemption"][missing_field]
    exemption_errors = declaration_errors(ROOT, contracts, malformed_exemption)
    ck(len(exemption_errors) == 1 and missing_field in exemption_errors[0],
       f"missing legacy exemption {missing_field} bypassed or cascaded after shape validation")
malformed_exemption = deepcopy(load_declarations(ROOT))
malformed_exemption["legacy_exemption"]["source_count"] = float(
    malformed_exemption["legacy_exemption"]["source_count"]
)
ck(declaration_errors(ROOT, contracts, malformed_exemption) == [
    "legacy exemption source_count must be an integer"
], "a floating-point legacy source_count passed integer shape validation")

range_declaration = deepcopy(load_declarations(ROOT)["migrated"][MONITOR])
for range_field in ("legacy_owned_ranges", "post_init_dynamic_write_ranges"):
    for invalid_ranges in (0, False, "", {}):
        malformed_range = deepcopy(range_declaration)
        malformed_range[range_field] = invalid_ranges
        normalized, range_errors = normalize_declaration(MONITOR, malformed_range)
        ck(normalized is None and any("must be an explicit list" in error
                                     for error in range_errors),
           f"{range_field} accepted malformed value {invalid_ranges!r} as an empty list")
    malformed_range = deepcopy(range_declaration)
    malformed_range[range_field] = [[False, False]]
    normalized, range_errors = normalize_declaration(MONITOR, malformed_range)
    ck(normalized is None and any("invalid reviewed dynamic range" in error
                                 for error in range_errors),
       f"{range_field} accepted boolean endpoints as integer cells")

invalid_custom_mask = replace(minimal, custom_state_bits=-1)
ck(state_generation_rule_errors(
    invalid_custom_mask, [["yield"]], {}, {}
) == ["custom_state_bits must fit the service-specific state range"],
   "an invalid custom-state mask cascaded into a HAS_STATE error")
invalid_custom_mask = replace(minimal, publishes_state=True, custom_state_bits=-1)
invalid_state_errors = state_generation_rule_errors(
    invalid_custom_mask,
    [["poke", str(STATE_CELL), "18"], ["yield"]],
    {},
    {STATE_CELL: {18}},
)
ck(any("custom_state_bits must fit" in error for error in invalid_state_errors)
   and any("reserved bit" in error for error in invalid_state_errors),
   "an invalid custom-state mask suppressed independent state-value validation")

# Text in an unreachable branch or erased after publication is not publication.
declaration = load_declarations(ROOT)["migrated"][MONITOR]
expected = {0: game_hash("StackCellMonitor.v1"), 1: 1, 2: 20, 7: 0}
source = (ROOT / MONITOR).read_text()
with TemporaryDirectory() as temporary:
    unreachable = _ProjectPath(temporary) / "unreachable.ic10"
    unreachable.write_text(source.replace('poke 0 HASH("StackCellMonitor.v1")', 'j Skip\npoke 0 HASH("StackCellMonitor.v1")\nSkip:', 1))
    mutated = deepcopy(declaration)
    mutated["source_sha256"] = hashlib.sha256(unreachable.read_bytes()).hexdigest()
    ck(any("control transfer occurs before" in error
           for error in publication_errors(unreachable, expected, mutated)),
       "publication validator accepted unreachable header initialization")
    guarded = _ProjectPath(temporary) / "guarded.ic10"
    guarded.write_text(source.replace('poke 0 HASH("StackCellMonitor.v1")',
        'get r0 db 31\nbeq r0 HASH("StackCellMonitor.v1") Init\nclr db\npoke 31 HASH("StackCellMonitor.v1")\nInit:\npoke 0 HASH("StackCellMonitor.v1")', 1))
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
print(" - the reader validates the common envelope and republishes only declared fields")
print(" - schema binding, extension bounds, and the pre-v1 baseline gate fail closed")
print(f" - migration backlog: {len(backlog)} programs, {inventory['totals']['backlog_reserved_cell_users']} using S2..S7")
