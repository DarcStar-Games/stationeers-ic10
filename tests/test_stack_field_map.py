#!/usr/bin/env python3
"""Exercise the reviewed stack field map: shape, coverage, override agreement, docs, and outputs."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import json
import sys

from framework.json_schema import validate
from framework.stack_field_map import (
    FIELD_MAP_DOC,
    LAYOUT_SEMANTIC_SOURCE,
    LayoutEntry,
    ROLES,
    TOKEN_ROLES,
    apply_layout,
    all_doc_layout_errors,
    all_documented_cells,
    declared_peer_cells,
    doc_layout_blocks,
    doc_layout_errors,
    documented_cells,
    field_map_document,
    fields_by_role,
    format_cell_set,
    header_cells,
    layout_documents_in,
    layout_errors,
    load_generated,
    load_layouts,
    normalize_layout,
    parse_cells,
    payload_fields,
    peer_touched_cells,
)

ROOT = _PROJECT_ROOT
HOST = "ic10.stack.generic-snapshot-directory-host.v1"
HOST_SOURCE = "ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10"
STORE = "ic10.stack.generic-catalog-store.v6"
STORE_SOURCE = "ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10"
fails: list[str] = []


def ck(condition, message):
    if not condition:
        fails.append(message)


# --- cell specs -----------------------------------------------------------------------
ck(parse_cells("S10") == (10, 10) and parse_cells("S32..S415") == (32, 415), "cell specs did not parse")
for bad in ("10", "S10..", "S415..S32", "S512", "S1..S600", 10, None):
    try:
        parse_cells(bad)
    except ValueError:
        continue
    ck(False, f"cell spec {bad!r} was accepted")
ck(format_cell_set({3, 4, 5, 9, 11, 12}) == "S3..S5, S9, S11..S12", "cell sets did not format as runs")
ck(header_cells(0) == set(range(8)) and header_cells(96) == {96, 97}, "header windows are wrong")

# --- layout shape ---------------------------------------------------------------------
entries, errors = normalize_layout("p", [
    {"cells": "S10", "name": "RequestToken", "role": "request_token"},
    {"cells": "S12..S14", "name": "Payload", "role": "request"},
])
ck(not errors and [entry.start for entry in entries] == [10, 12], "a well-formed layout was rejected")
_, errors = normalize_layout("p", [
    {"cells": "S10", "name": "A", "role": "request"},
    {"cells": "S10..S11", "name": "B", "role": "request"},
])
ck(any("overlaps" in error for error in errors), "overlapping entries were not rejected")
_, errors = normalize_layout("p", [
    {"cells": "S10", "name": "A", "role": "request"},
    {"cells": "S11", "name": "A", "role": "request"},
])
ck(any("is used at" in error for error in errors), "a duplicate name was not rejected")
_, errors = normalize_layout("p", [{"cells": "S10", "name": "A", "role": "payload"}])
ck(any("role" in error for error in errors), "an unknown role was not rejected")
_, errors = normalize_layout("p", [{"cells": "S10", "name": "lower", "role": "request"}])
ck(any("CamelCase" in error for error in errors), "a lower-case name was not rejected")
_, errors = normalize_layout("p", [{"cells": "S10", "name": "A", "role": "request", "extra": 1}])
ck(any("unknown keys" in error for error in errors), "an unknown key was not rejected")
_, errors = normalize_layout("p", {"cells": "S10"})
ck(errors == ["p: layout must be a list of entries"], "a non-list layout was not rejected")

# --- the tree -------------------------------------------------------------------------
layouts = load_layouts(ROOT)
definitions, contracts = load_generated(ROOT)
by_pid = {definition["protocol_id"]: definition for definition in definitions.values()}
wired = declared_peer_cells(ROOT, contracts)
documents = layout_documents_in(ROOT)
documented = all_documented_cells(documents)
ck(FIELD_MAP_DOC not in documents and "docs/ABI_REFERENCE.md" in documents and "docs/CATALOG_STORAGE.md" in documents,
   "the documents held to the map are not the markdown under docs/ minus the generated map")
ck(HOST in layouts and STORE in layouts, "the two reference protocols have no layout")
ck(all(entry.role in ROLES for entries in layouts.values() for entry in entries), "an entry escaped the role vocabulary")
tree_errors = layout_errors(definitions, contracts, layouts, wired, documented)
ck(tree_errors == [], "the tree's layouts do not hold: " + "; ".join(tree_errors[:5]))
consumed = {pid for pid, definition in by_pid.items() if peer_touched_cells(definition)}
ck(consumed <= set(layouts), f"consumed protocols without a layout: {sorted(consumed - set(layouts))[:5]}")
touched_total = sum(len(peer_touched_cells(definition)) for definition in definitions.values())
ck(touched_total > 400, f"peer-touched payload cells were not counted ({touched_total})")

# A peer-touched cell without an entry fails, naming the cell and the peer.
missing = deepcopy(layouts)
missing[HOST] = [entry for entry in missing[HOST] if entry.start != 9]
errors = layout_errors(definitions, contracts, missing)
ck(any(f"{HOST}: peer-touched payload cell(s) have no layout entry: S9 (" in error for error in errors),
   "an unmapped peer-touched cell was not reported")

# An entry on cells nothing touches or declares fails.
stray = deepcopy(layouts)
stray[HOST] = stray[HOST] + [LayoutEntry(500, 500, "Stray", "reserved")]
errors = layout_errors(definitions, contracts, stray)
ck(any("Stray S500 names S500, which no provider touches" in error for error in errors),
   "an entry outside the provider surface was not reported")

# An entry on a header cell fails: the header is declared, not mapped.
header = deepcopy(layouts)
header[HOST] = header[HOST] + [LayoutEntry(3, 3, "SchemaAgain", "schema")]
errors = layout_errors(definitions, contracts, header)
ck(any("SchemaAgain S3 names header cell(s) S3" in error for error in errors), "a header cell entry was not reported")

# A layout whose single-cell name disagrees with a reviewed per-program override fails.
renamed = deepcopy(layouts)
renamed[STORE] = [LayoutEntry(e.start, e.end, "Other" if e.start == 8 else e.name, e.role) for e in renamed[STORE]]
errors = layout_errors(definitions, contracts, renamed)
ck(any(f"{STORE_SOURCE} override names S8 StoreOrdinal but the layout names it Other" in error for error in errors),
   "an override disagreement was not reported")

# A per-program override inside a range entry fails: the cell needs its own entry.
swallowed = deepcopy(layouts)
swallowed[STORE] = [e for e in swallowed[STORE] if not 8 <= e.start <= 9] + [LayoutEntry(8, 9, "OrdinalAndCount", "result")]
errors = layout_errors(definitions, contracts, swallowed)
ck(any(f"{STORE_SOURCE} override names S8 StoreOrdinal inside the range entry OrdinalAndCount S8..S9" in error
       for error in errors), "an override swallowed by a range was not reported")

# Attributed network writes count as peers: the Reservation Stager prepares the Grant Guard's
# S16..S26 through a ReferenceId, which the contracts record as a network dependency.
GUARD = "ic10.stack.material-transfer-grant-guard.v1"
stager = "ic10/material-transform/multi_material_reservation_stager_v1_0.ic10"
ck(stager in wired.get(GUARD, {}).get(17, set()), "the Stager's network write to the Grant Guard's S17 was not attributed")

# The wiring map's declared peers count: the Dependency Planner writes the Plan Store's request
# cells through a port with no contract consumer edge, and the map must still name them.
PLAN_STORE = "ic10.stack.dependency-plan-store.v2"
planner = "ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10"
ck(planner in wired.get(PLAN_STORE, {}).get(12, set()) and 12 not in peer_touched_cells(by_pid[PLAN_STORE]),
   "the Planner's wired write to the Plan Store's S12 was not attributed through the wiring map")
ck(planner in peer_touched_cells(by_pid[PLAN_STORE], wired).get(12, set()),
   "wiring-declared peers were not merged into the touched cells")
unmapped_plan = deepcopy(layouts)
unmapped_plan[PLAN_STORE] = [e for e in unmapped_plan[PLAN_STORE] if e.start != 12]
ck(not any(f"{PLAN_STORE}: peer-touched" in error for error in layout_errors(definitions, contracts, unmapped_plan)) and any(
       f"{PLAN_STORE}: peer-touched payload cell(s) have no layout entry: S12 (" in error
       for error in layout_errors(definitions, contracts, unmapped_plan, wired)),
   "a cell only a wiring-declared peer writes was not required to be named")

# An entry on cells only the provider touches fails under the grounding rule: the Snapshot
# Host's S31 is its reflash marker, read and written by nobody else and cited by no block.
private = deepcopy(layouts)
private[HOST] = private[HOST] + [LayoutEntry(31, 31, "ReflashIdentity", "metadata")]
errors = layout_errors(definitions, contracts, private, wired, documented)
ck(any(f"{HOST}: ReflashIdentity S31 names only cells the provider keeps to itself" in error for error in errors),
   "an entry nothing outside the provider can hold was accepted")
ck(not any("keeps to itself" in error for error in layout_errors(definitions, contracts, private, wired)),
   "the grounding rule ran without a documented-cells map")
# A document grounds a name only through a layout block or table that names its contract on an
# S0 line; a reviewed external range does not. The Store's S30 is reserved in the storage table
# and nothing reads it, so it stands or falls with the table.
store_documented = deepcopy(documented)
store_documented[STORE] = store_documented[STORE] - {30}
errors = layout_errors(definitions, contracts, layouts, wired, store_documented)
ck(any(f"{STORE}: Reserved30 S30 names only cells the provider keeps to itself" in error for error in errors),
   "a table-documented cell was grounded by something other than the table")
ck(not any("Reserved30" in error for error in layout_errors(definitions, contracts, layouts, wired, documented)),
   "the storage table did not ground the Store's reserved cell")

# Network reads attributed by the provenance walk count as peers too: the Catalog Inspector reads
# Store cells through a reference it checked against the Store's identity.
INSPECTOR = "ic10/catalog-control-plane/catalog_inspector_v4_0.ic10"
ck(INSPECTOR in wired.get(STORE, {}).get(9, set()), "an attributed network read did not make the reader a peer")

# A layout for a protocol nothing provides or consumes fails.
orphan = deepcopy(layouts)
orphan["ic10.stack.nothing.v1"] = [LayoutEntry(8, 8, "X", "state")]
errors = layout_errors(definitions, contracts, orphan)
ck(any("ic10.stack.nothing.v1: layout declared for a protocol nothing provides" in error for error in errors),
   "an orphan layout was not reported")

# Dropping a consumed protocol's layout entirely fails, listing the touched cells.
dropped = deepcopy(layouts)
del dropped["ic10.stack.pressure-grid-cost-profile.v1"]
errors = layout_errors(definitions, contracts, dropped)
ck(any("ic10.stack.pressure-grid-cost-profile.v1: peers read or write S8..S12 but the protocol has no layout" in error
       for error in errors), "a missing layout for a consumed protocol was not reported")

# --- provider contracts carry the map -------------------------------------------------
host = contracts[HOST_SOURCE]
host_fields = {field["address"]: field for field in host["own_stack"]["fields"]}
ck(host_fields[24]["name"] == "ActiveBank" and host_fields[24]["role"] == "bank"
   and host_fields[24]["semantic_source"] == LAYOUT_SEMANTIC_SOURCE,
   "the Snapshot Host's S24 did not take the layout's name, role, and source")
ck(host_fields[0]["name"] == "Header@S0.Magic" and "role" not in host_fields[0], "a header field was renamed by the layout")
store = contracts[STORE_SOURCE]
store_fields = {field["address"]: field for field in store["own_stack"]["fields"]}
ck(store_fields[8]["name"] == "StoreOrdinal" and store_fields[8]["semantic_source"] == "override"
   and store_fields[8]["role"] == "topology", "an override field lost its name or did not gain the role")
ck(store_fields[17]["name"] == "DataSequence" and store_fields[17]["role"] == "generation",
   "the Store's S17 did not take the layout")
editor = contracts["ic10/controller-config/generic_config_editor_v1_0.ic10"]
editor_fields = {field["address"]: field for field in editor["own_stack"]["fields"]}
ck(editor_fields[101]["name"] == "ButtonPreviousStates[0]" and editor_fields[103]["name"] == "ButtonPreviousStates[2]"
   and editor_fields[103]["role"] == "state", "cells inside a range entry did not take indexed names")
unresolved_named = sum(
    1 for definition in definitions.values() for provider in definition["provider_interfaces"]
    for field in contracts.get(provider["source"], {"own_stack": {"fields": []}})["own_stack"]["fields"]
    if field["semantic_source"] == "unresolved"
    and any(entry.covers(field["address"]) for entry in layouts.get(definition["protocol_id"], [])))
ck(unresolved_named == 0, f"{unresolved_named} provider fields sit under a layout entry yet remain unresolved")

# apply_layout is idempotent and leaves fields outside the map alone.
own = deepcopy(host["own_stack"])
apply_layout(own, layouts)
ck(own == host["own_stack"], "applying the layout a second time changed the contract")
own = deepcopy(host["own_stack"])
apply_layout(own, {})
ck(own == host["own_stack"], "applying no layout changed a generated contract")

# --- protocol documents, inventory, schema ---------------------------------------------
host_definition = by_pid[HOST]
banks = next(item for item in host_definition["layout"] if item["name"] == "Banks")
ck(banks["start"] == 32 and banks["end"] == 415 and banks["cells"] == "S32..S415" and banks["role"] == "table",
   "the protocol document does not carry the expanded layout entry")
ck(all(definition["layout"] == [] for pid, definition in by_pid.items() if pid not in layouts),
   "a protocol without a layout carries entries in its document")
schema = json.loads((ROOT / "schemas/protocol_definition.schema.json").read_text())
for definition in definitions.values():
    try:
        validate(definition, schema)
    except Exception as error:  # noqa: BLE001 - the message is the assertion
        ck(False, f"{definition['protocol_id']}: {error}")
        break
inventory = json.loads((ROOT / "contracts/stack_envelope_inventory.json").read_text())
host_service = next(item for item in inventory["services"] if item["source"] == HOST_SOURCE)
ck({"protocol_id": HOST, "cells": "S24", "name": "ActiveBank", "role": "bank"} in host_service["current_layout"]["payload_fields"],
   "the envelope inventory does not carry the host's payload fields")
ck(payload_fields(host, layouts) == host_service["current_layout"]["payload_fields"],
   "the inventory's payload fields differ from the map")
ck(sum(len(item["current_layout"]["payload_fields"]) for item in inventory["services"]) > 500,
   "the inventory carries too few payload fields")

# --- the documents under docs/ are held to the map -------------------------------------
reference = documents["docs/ABI_REFERENCE.md"]
blocks = doc_layout_blocks(reference)
ck(len(blocks) >= 25 and any(block.protocol_id == HOST for block in blocks), "the ABI reference layout blocks were not found")
ck(all_doc_layout_errors(documents, layouts) == [], "a document cites a cell the map does not name")
table_blocks = doc_layout_blocks(documents["docs/CATALOG_STORAGE.md"])
ck([block.protocol_id for block in table_blocks] == [STORE, "ic10.stack.catalog-loader.v5"]
   and any(start == 32 for start, _, _ in table_blocks[0].cells),
   "markdown table rows were not read as layout lines")
synthetic = "\n".join([
    "```text", "S0   magic = GenericSnapshotDirectoryHost.v1", "S1   ABI = 1", "S24  active bank",
    "S25/S26 generation A/B", "S32..159 bank A", "S450 something new", "```", "",
    "```text", "S0 magic = Nothing.v1", "S8 a cell", "```", "",
    "```text", "S96 magic = 27182818", "S130 not attributable", "```", "",
    # Two services in one fence: each cell line is held to its own service.
    "```text", "Cost profile", "S0 magic = PressureGridCostProfile.v1", "S8 HopWeight", "S13 not a cost cell", "",
    "Domain inventory", "S0 magic = PressureDomainInventory.v2", "S13 PressureDomain ReferenceId", "S19 not an inventory cell", "```", "",
    # A table names its contract on an S0 row and ends at the first non-row line.
    "| Cell | Meaning |", "|---:|---|", "| S0 | magic = PressureGridCostProfile.v1 |", "| S9 | StorageWeight |", "| S14 | not a cost cell |",
    # An indented row (a table inside a list item) is a row of the same table.
    "  | S16 | not a cost cell either |", "",
    "prose after the table", "| S15 | a row of a table that names no contract |", "",
    # Four spaces of indentation after a blank line is a code block, not a table.
    "    | S0 | magic = PressureGridCostProfile.v1 |", "    | S17 | in a code block, not a table |",
])
fixture_lines = synthetic.split("\n")


def line_of(text):
    return fixture_lines.index(text) + 1


errors = doc_layout_errors(synthetic, layouts, "doc.md")
ck(errors == [
    f"doc.md:{line_of('S450 something new')}: {HOST} cites S450 but the layout does not name S450",
    f"doc.md:{line_of('S0 magic = Nothing.v1')}: layout block for ic10.stack.nothing.v1 but the protocol has no layout in data/script_contract_protocol_definitions.json",
    f"doc.md:{line_of('S13 not a cost cell')}: ic10.stack.pressure-grid-cost-profile.v1 cites S13 but the layout does not name S13",
    f"doc.md:{line_of('S19 not an inventory cell')}: ic10.stack.pressure-domain-inventory.v2 cites S19 but the layout does not name S19",
    f"doc.md:{line_of('| S14 | not a cost cell |')}: ic10.stack.pressure-grid-cost-profile.v1 cites S14 but the layout does not name S14",
    f"doc.md:{line_of('  | S16 | not a cost cell either |')}: ic10.stack.pressure-grid-cost-profile.v1 cites S16 but the layout does not name S16",
], f"doc holding reported {errors}")
sub_blocks = doc_layout_blocks(synthetic)
ck([block.protocol_id for block in sub_blocks][-3:] == ["ic10.stack.pressure-grid-cost-profile.v1", "ic10.stack.pressure-domain-inventory.v2", "ic10.stack.pressure-grid-cost-profile.v1"]
   and sub_blocks[-2].cells == (
       (0, 0, line_of("S0 magic = PressureDomainInventory.v2")),
       (13, 13, line_of("S13 PressureDomain ReferenceId")),
       (19, 19, line_of("S19 not an inventory cell"))),
   "a fence holding two services was not split at its second S0 line")
ck(documented[HOST] >= {9, 11, 12, 24, 25, 26, 32, 415} and 31 not in documented[HOST],
   "documented cells were not collected from the ABI reference blocks")

# --- the report ----------------------------------------------------------------------
by_role = fields_by_role(layouts, definitions, wired, documented)
ck({row["grounding"] for rows in by_role.values() for row in rows} <= {"peer", "document", "peer, document"},
   "an entry in the report has no grounding")
token_rows = [row for role in TOKEN_ROLES for row in by_role[role]]
ck(len(token_rows) >= 60, f"too few token cells in the report ({len(token_rows)})")
ck(len({row["start"] for row in by_role["request_token"]}) >= 10, "request tokens did not spread across offsets as measured")
host_row = next(row for row in by_role["bank"] if row["protocol_id"] == HOST and row["name"] == "ActiveBank")
ck(host_row["consumers"] >= 13 and host_row["peers_touching"] >= 13, "the report's fan-in for the host is wrong")
plan_row = next(row for row in by_role["request_token"] if row["protocol_id"] == PLAN_STORE)
ck(plan_row["peers_touching"] >= 1, "the report counts no peer for the Plan Store's request token although the Planner is wired to it")
document = field_map_document(ROOT)
ck(document == (ROOT / FIELD_MAP_DOC).read_text(), f"{FIELD_MAP_DOC} is stale")
ck("### request_token" in document and "## By protocol" in document and f"### {HOST}" in document,
   "the field map document lacks its sections")

if fails:
    print("Stack field map: FAIL")
    for failure in fails:
        print(" -", failure)
    sys.exit(1)
print("Stack field map: PASS")
print(" - cell specs, roles, overlap, and name uniqueness are checked at load")
print(" - unmapped peer-touched cells, stray entries, header entries, override disagreements, and orphans fail")
print(" - provider contracts, protocol documents, and the envelope inventory carry the map")
print(" - the ABI reference is held to the map per S0 block and the per-role report is generated from it")
print(" - wiring-declared peers without a contract consumer edge still require a named cell and count in the report")
print(" - every entry names a cell a peer touches or a documented block or table cites; provider-private cells are not mapped")
print(" - attributed network reads make their reader a peer, and every markdown document under docs/ is held to the map")
