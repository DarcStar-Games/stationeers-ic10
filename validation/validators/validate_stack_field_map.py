#!/usr/bin/env python3
"""Hold the reviewed stack field map to the tree.

Every layout entry names cells its provider touches or declares; every payload cell a
peer reads or writes carries a name and a role; every layout block in the ABI
reference that names its contract cites only header cells or mapped cells; and the
generated field map document is current (issue #190).
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from framework.stack_field_map import (
    ABI_REFERENCE_DOC,
    DEFINITIONS_FILE,
    FIELD_MAP_DOC,
    ROLES,
    TOKEN_ROLES,
    doc_layout_blocks,
    doc_layout_errors,
    documented_cells,
    field_map_document,
    layout_errors,
    load_generated,
    load_layouts,
    peer_touched_cells,
    wiring_touched_cells,
)

ROOT = _PROJECT_ROOT
validation = Validation(ROOT)

try:
    layouts = load_layouts(ROOT)
except ValueError as error:
    validation.fail(f"{DEFINITIONS_FILE}: {error}")
    raise SystemExit(validation.finish("Stack field map validation"))

definitions, contracts = load_generated(ROOT)
reference = (ROOT / ABI_REFERENCE_DOC).read_text()
# Peers come from two places: the consumer edges the contracts prove, and the peers the
# wiring map declares for a port that carries no such edge. Both must find a named cell,
# and every entry must name a cell one of them touches or a documented block cites.
wired = wiring_touched_cells(ROOT, contracts)
validation.extend(layout_errors(definitions, contracts, layouts, wired, documented_cells(reference)))
validation.extend(doc_layout_errors(reference, layouts))

# The provider contracts must carry what the layout says, so a hand edit of a generated
# contract, or a generator that stopped applying the map, is caught here rather than
# in a reader that trusted the field name.
for definition in definitions.values():
    entries = layouts.get(definition["protocol_id"], [])
    for provider in definition["provider_interfaces"]:
        contract = contracts.get(provider["source"])
        if contract is None:
            continue
        for field in contract["own_stack"]["fields"]:
            if field["semantic_source"] == "protocol-header":
                continue
            entry = next((item for item in entries if item.covers(field["address"])), None)
            if entry is None:
                continue
            if field.get("role") != entry.role:
                validation.fail(
                    f"{provider['source']}: contract field S{field['address']} carries role "
                    f"{field.get('role')!r}, the layout says {entry.role!r}; regenerate contracts")
            expected_name = entry.field_name(field["address"])
            if field["semantic_source"] != "override" and field["name"] != expected_name:
                validation.fail(
                    f"{provider['source']}: contract field S{field['address']} is named {field['name']}, "
                    f"the layout names it {expected_name}; regenerate contracts")

expected = field_map_document(ROOT)
target = ROOT / FIELD_MAP_DOC
if not target.is_file() or target.read_text() != expected:
    validation.fail(f"{FIELD_MAP_DOC} is stale; run tools/generate/generate_stack_field_map.py")

touched = sum(len(peer_touched_cells(definition, wired)) for definition in definitions.values())
wired_only = sum(
    1 for definition in definitions.values()
    for cell in peer_touched_cells(definition, wired)
    if cell not in peer_touched_cells(definition))
mapped = sum(entry.end - entry.start + 1 for entries in layouts.values() for entry in entries)
tokens = sum(1 for entries in layouts.values() for entry in entries if entry.role in TOKEN_ROLES)
blocks = doc_layout_blocks(reference)
raise SystemExit(validation.finish("Stack field map validation", [
    f"{len(layouts)} protocols carry a reviewed layout naming {mapped} cells across {len(ROLES)} roles",
    f"every one of the {touched} payload cells a peer reads or writes has a name and a role ({wired_only} of"
    " them reached only through a wiring-declared port or an attributed network write), and every entry"
    " sits on cells its provider touches or declares",
    f"{len(blocks)} layout blocks in {ABI_REFERENCE_DOC} name their contract and cite only header or mapped cells;"
    " every entry names a peer-touched or documented cell",
    f"{tokens} token cells are named; provider contract fields agree with the map and {FIELD_MAP_DOC} is current",
]))
