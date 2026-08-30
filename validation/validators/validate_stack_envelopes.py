#!/usr/bin/env python3
"""Validate Stack Envelope v1 declarations, generated inventory, and migration gates."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import re
import sys

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import build_all
from framework.stack_envelope import BASE, LENGTH, DeclarationError, build_inventory

ROOT = _PROJECT_ROOT
PILOT_FAMILIES = {"stack-monitor", "generic-telemetry", "directory", "catalog", "catalog-control-plane", "diagnostics", "power-jobs", "material-transform", "catalog-loader", "input-profile-catalog", "resource-profile-catalog", "transform-catalog", "transaction", "manufacturing", "controller-discovery", "pressure-domain"}
fails: list[str] = []

try:
    contracts, _, protocols, _ = build_all(ROOT)
    expected = build_inventory(ROOT, contracts, protocols)
except DeclarationError as error:
    print("Stack envelope validation: FAIL")
    [print(" -", failure) for failure in error.errors]
    raise SystemExit(1)
except Exception as error:
    print("Stack envelope validation: FAIL")
    print(f" - unable to build expected inventory: {error}")
    raise SystemExit(1)

try:
    actual = json.loads((ROOT / "contracts" / "stack_envelope_inventory.json").read_text())
    schema = json.loads((ROOT / "schemas" / "stack_envelope_inventory.schema.json").read_text())
    validate(actual, schema)
except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
    fails.append(f"generated inventory schema validation failed: {error}")
    actual = None

if actual is not None:
    if actual != expected:
        fails.append("generated inventory is stale; run tools/generate/generate_script_contracts.py")
    services = actual["services"]
    migrated = [item for item in services if item["status"] == "migrated-v1"]
    legacy = [item for item in services if item["status"] == "legacy-exempt"]
    if len(services) != len(contracts):
        fails.append("inventory does not cover every deployable script contract")
    for item in services:
        has_envelope = "envelope" in item
        has_exemption = "legacy_exemption" in item
        if has_envelope == has_exemption:
            fails.append(f"{item['source']}: service must have exactly one migration status payload")
        if item["status"] == "migrated-v1" and not has_envelope:
            fails.append(f"{item['source']}: migrated status lacks envelope declaration")
        if item["status"] == "legacy-exempt" and not has_exemption:
            fails.append(f"{item['source']}: legacy status lacks explicit exemption")
    families = {item["envelope"]["pilot_family"] for item in migrated if "envelope" in item}
    if not families <= PILOT_FAMILIES:
        fails.append(f"unknown pilot families declared: {sorted(families - PILOT_FAMILIES)}")
    if "stack-monitor" not in families:
        fails.append("the monitor pilot must stay migrated; it is the reference reader")
    if any(item["window_collision"]["literal_cells"] for item in migrated
           if set(item["window_collision"]["literal_cells"]) - set(range(BASE, BASE + LENGTH))):
        fails.append("a migrated service uses header cells outside S0..S4 as header cells")
    totals = actual["totals"]
    if totals["deployable_programs"] != len(services):
        fails.append("deployable total does not match inventory rows")
    if totals["migrated_v1"] != len(migrated) or totals["legacy_exempt"] != len(legacy):
        fails.append("migration totals do not match inventory rows")

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
}
for wired_source, wired_ports in json.loads((ROOT / "data" / "script_wiring.json").read_text())["ports"].items():
    for wired_port, peer in wired_ports.items():
        if peer.get("header_reads"):
            HEADER_READS[(wired_source, wired_port)] = {
                int(cell) for cell in peer["header_reads"] if cell.isdigit()}
read0 = re.compile(r"^get (r\d+) (d[0-5]) 0$")
refread0 = re.compile(r"^getd (r\d+) (r\d+|ra|sp) 0$")
compare = re.compile(r"^(?:bne|beq) (r\d+) (\d{7,8}) \w+$")
access = re.compile(r"^(?:get|put) (?:r\d+ )?(d[0-5]) (\d+)|^(?:getd|putd) (?:r\d+ )?(r\d+|ra|sp) (\d+)")
publishers = {}
for path, entries in json.loads((ROOT / "data" / "script_protocol_headers.json").read_text())["scripts"].items():
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
                peers[found.group(2)] = int(checked.group(2))
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
            fails.append(
                f"{rel} {handle}: reads S{reserved} of migrated {targets[0]} -- those are header cells now"
            )

if fails:
    print("Stack envelope validation: FAIL")
    [print(" -", failure) for failure in fails]
    sys.exit(1)
print("Stack envelope validation: PASS")
print(f" - all {len(contracts)} deployable programs are migrated or in the immutable pre-v1 baseline")
print(f" - migrated families: {', '.join(sorted(families)) or 'none'}; backlog: {len(legacy)} programs, {actual["totals"]["backlog_reserved_cell_users"]} using reserved cells")
print(" - S0..S7 writes, derived capability mask, schema binding, and extension bounds are enforced")
print(f" - no consumer reads a migrated peer's S2..S7 as payload; {len(HEADER_READS)} reviewed header reads are declared")
