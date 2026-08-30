#!/usr/bin/env python3
"""Validate Stack Envelope v1 declarations, generated inventory, and migration gates."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation

import json
import re
import sys

from framework.ic10_source import game_hash
from framework.json_schema import SchemaValidationError, validate
from framework.protocol_headers import load_headers
from framework.script_contracts import build_all
from framework.stack_envelope import BASE, LENGTH, DeclarationError, build_inventory

ROOT = _PROJECT_ROOT
HASH_LITERAL = re.compile(r'^HASH\("([^"\n]+)"\)$')
PILOT_FAMILIES = {"stack-monitor", "generic-telemetry", "directory", "catalog", "catalog-control-plane", "diagnostics", "power-jobs", "material-transform", "catalog-loader", "input-profile-catalog", "resource-profile-catalog", "transform-catalog", "transaction", "manufacturing", "controller-discovery", "pressure-domain", "recipe-catalog", "shared-input", "process-gas-preparation", "item-storage-common", "item-storage-larre", "material-grid", "process-furnace", "process-gfg", "pressure-grid", "item-storage-sdb", "power-grid", "resource-grid-core", "item-storage-direct", "item-storage-vending", "controller-pi", "controller-sequencer", "controller-phase-pressure", "controller-config", "printer-directory", "generic-jobs", "directory-core", "dependency-planning", "live-commissioning"}
validation = Validation(ROOT)

try:
    contracts, _, protocols, _ = build_all(ROOT)
    expected = build_inventory(ROOT, contracts, protocols)
except DeclarationError as error:
    validation.extend(error.errors)
    raise SystemExit(validation.finish("Stack envelope validation"))
except Exception as error:
    validation.fail("unable to build expected inventory",detail=str(error))
    raise SystemExit(validation.finish("Stack envelope validation"))

try:
    actual = json.loads((ROOT / "contracts" / "stack_envelope_inventory.json").read_text())
    schema = json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text())
    validate(actual, schema)
except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
    validation.fail(f"generated inventory schema validation failed: {error}")
    actual = None

if actual is not None:
    if actual != expected:
        validation.fail("generated inventory is stale; run tools/generate/generate_script_contracts.py")
    services = actual["services"]
    migrated = [item for item in services if item["status"] == "migrated-v1"]
    legacy = [item for item in services if item["status"] == "legacy-exempt"]
    if len(services) != len(contracts):
        validation.fail("inventory does not cover every deployable script contract")
    for item in services:
        has_envelope = "envelope" in item
        has_exemption = "legacy_exemption" in item
        if has_envelope == has_exemption:
            validation.fail(f"{item['source']}: service must have exactly one migration status payload")
        if item["status"] == "migrated-v1" and not has_envelope:
            validation.fail(f"{item['source']}: migrated status lacks envelope declaration")
        if item["status"] == "legacy-exempt" and not has_exemption:
            validation.fail(f"{item['source']}: legacy status lacks explicit exemption")
    families = {item["envelope"]["pilot_family"] for item in migrated if "envelope" in item}
    if not families <= PILOT_FAMILIES:
        validation.fail(f"unknown pilot families declared: {sorted(families - PILOT_FAMILIES)}")
    if "stack-monitor" not in families:
        validation.fail("the monitor pilot must stay migrated; it is the reference reader")
    if any(item["window_collision"]["literal_cells"] for item in migrated
           if set(item["window_collision"]["literal_cells"]) - set(range(BASE, BASE + LENGTH))):
        validation.fail("a migrated service uses header cells outside S0..S4 as header cells")
    totals = actual["totals"]
    if totals["deployable_programs"] != len(services):
        validation.fail("deployable total does not match inventory rows")
    if totals["migrated_v1"] != len(migrated) or totals["legacy_exempt"] != len(legacy):
        validation.fail("migration totals do not match inventory rows")

# A consumer that checks a peer's ServiceMagic names that peer exactly. Once the peer
# migrates, its S2..S7 are header cells the owner publishes -- so a consumer still
# reading payload there is reading the mask or the schema id instead. That mistake is
# invisible to the contract layer, which sees a published cell and calls the read
# satisfied, so it is checked here against every migrated peer. Reviewed device-port
# reads live in the wiring map as header_reads; only reference-register reads, which
# have no port for the map to key on, are declared here.
HEADER_READS = {
    # reads Loader ABI5 SchemaId S3 as a header field
    ("ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10", "r1"): {3},
    ("ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10", "r1"): {3},
    ("ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10", "r2"): {3},
    # read the Store's coordinator-assigned SchemaId S3 as a header field
    ("ic10/input-profile-catalog/input_profile_view_v5_0.ic10", "r2"): {3},
    ("ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10", "r1"): {3},
    ("ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10", "r2"): {3},
    ("ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10", "r2"): {3},
    ("ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10", "r2"): {3},
    # reads the Registry Host's adapter-assigned SchemaId S3 as a header field
    ("ic10/catalog-control-plane/catalog_inspector_v4_0.ic10", "r14"): {3},
}
for wired_source, wired_ports in json.loads((ROOT / "data" / "script_wiring.json").read_text())["ports"].items():
    for wired_port, peer in wired_ports.items():
        if peer.get("header_reads"):
            HEADER_READS[(wired_source, wired_port)] = {
                int(cell) for cell in peer["header_reads"] if cell.isdigit()}
read0 = re.compile(r"^get (r\d+) (d[0-5]) 0$")
refread0 = re.compile(r"^getd (r\d+) (r\d+|ra|sp) 0$")
compare = re.compile(r'^(?:bne|beq) (r\d+) (\d{7,8}|HASH\("[^"\n]+"\)) \w+$')
access = re.compile(r"^(?:get|put) (?:r\d+ )?(d[0-5]) (\d+)|^(?:getd|putd) (?:r\d+ )?(r\d+|ra|sp) (\d+)")
publishers = {}
for path, entries in load_headers(ROOT)[0].items():
    for entry in entries:
        if entry["base"] == 0:
            publishers.setdefault(entry["magic"], []).append(path)
for source in sorted(ROOT.glob("ic10/*/*.ic10")):
    rel = source.relative_to(ROOT).as_posix()
    lines = [line.split("#", 1)[0].strip() for line in source.read_text().splitlines()]
    peers = {}
    for index, line in enumerate(lines):
        found = read0.match(line) or refread0.match(line)
        if not found:
            continue
        for following in lines[index + 1:index + 4]:
            checked = compare.match(following)
            if checked and checked.group(1) == found.group(1):
                token = checked.group(2)
                literal = HASH_LITERAL.fullmatch(token)
                peers[found.group(2)] = game_hash(literal.group(1)) if literal else int(token)
                break
    if not peers:
        continue
    touched = {}
    for line in lines:
        hit = access.match(line)
        if hit:
            handle = hit.group(1) or hit.group(3)
            touched.setdefault(handle, set()).add(int(hit.group(2) or hit.group(4)))
    for handle, magic in peers.items():
        reserved = sorted(touched.get(handle, set()) & set(range(BASE + 2, BASE + LENGTH))
                          - HEADER_READS.get((rel, handle), set()))
        targets = [q for q in publishers.get(magic, []) if q in json.loads((ROOT / "data" / "stack_envelope_declarations.json").read_text())["migrated"]]
        if reserved and targets:
            validation.fail(
                f"{rel} {handle}: reads S{reserved} of migrated {targets[0]} -- those are header cells now"
            )

raise SystemExit(validation.finish("Stack envelope validation",lambda: [
    f"all {len(contracts)} deployable programs are migrated or in the immutable pre-v1 baseline",
    f"migrated families: {', '.join(sorted(families)) or 'none'}; backlog: {len(legacy)} programs, {actual['totals']['backlog_reserved_cell_users']} using reserved cells",
    "S0..S7 writes, derived capability mask, schema binding, and extension bounds are enforced",
    f"no consumer reads a migrated peer's S2..S7 as payload; {len(HEADER_READS)} reviewed header reads are declared",
]))
