#!/usr/bin/env python3
"""Validate Stack Envelope v1 declarations, generated inventory, and migration gates."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import sys

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import build_all
from framework.stack_envelope import DeclarationError, build_inventory

ROOT = _PROJECT_ROOT
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
    if {item["envelope"]["pilot_family"] for item in migrated if "envelope" in item} != {
        "stack-monitor", "generic-telemetry", "directory", "catalog", "transaction"
    }:
        fails.append("required pilot-family coverage is incomplete")
    if any(item["window_collision"]["literal_cells"] for item in legacy):
        fails.append("a legacy service already occupies the selected fixed v1 window")
    totals = actual["totals"]
    if totals["deployable_programs"] != len(services):
        fails.append("deployable total does not match inventory rows")
    if totals["migrated_v1"] != len(migrated) or totals["legacy_exempt"] != len(legacy):
        fails.append("migration totals do not match inventory rows")

if fails:
    print("Stack envelope validation: FAIL")
    [print(" -", failure) for failure in fails]
    sys.exit(1)
print("Stack envelope validation: PASS")
print(f" - all {len(contracts)} deployable programs are migrated or in the immutable pre-v1 baseline")
print(" - five pilots cover monitor, Generic Telemetry, directory, catalog, and transaction families")
print(" - fixed cells, semantic identities, payload bases, schema pairing, and extension bounds are enforced")
