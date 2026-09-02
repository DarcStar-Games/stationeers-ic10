#!/usr/bin/env python3
"""Validate the canonical device-port wiring map against the script contracts."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import sys

from framework.json_schema import SchemaValidationError
from framework.protocol_headers import load_headers
from framework.script_contracts import build_all
from framework.script_wiring import (
    check_wiring,
    inbound_edges,
    load_wiring,
    port_index,
    stack_surfaces,
)

ROOT = _PROJECT_ROOT

try:
    wiring = load_wiring(ROOT)
except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
    print("Script wiring validation: FAIL")
    print(f" - unable to load data/script_wiring.json: {error}")
    raise SystemExit(1)

try:
    contracts, _, _, _ = build_all(ROOT)
except Exception as error:
    print("Script wiring validation: FAIL")
    print(f" - unable to build script contracts: {error}")
    raise SystemExit(1)

ports = port_index(contracts)
surfaces = stack_surfaces(contracts)
publishers = load_headers(ROOT)[0]
migrated = set(json.loads((ROOT / "data/stack_envelope_declarations.json").read_text())["migrated"])
failures = check_wiring(wiring, ports, publishers, migrated, surfaces)

if failures:
    print("Script wiring validation: FAIL")
    [print(" -", failure) for failure in failures]
    sys.exit(1)

total = sum(len(entries) for entries in wiring["ports"].values())
script_edges = [peer for entries in wiring["ports"].values() for peer in entries.values()
                if peer["kind"] == "script"]
physical = total - len(script_edges)
guarded = len(inbound_edges(wiring, ports, migrated))
reviewed = sum(1 for peer in script_edges if peer.get("header_reads"))
print("Script wiring validation: PASS")
print(f" - all {total} device ports across {len(wiring['ports'])} programs declare a peer"
      f" ({len(script_edges)} script edges, {physical} physical devices)")
print(f" - every declared provider exists, matches its port's target kind, and publishes"
      " any S0 identity the port checks")
print(f" - every one of the {len(script_edges)} script edges touches only cells a declared"
      " provider publishes or accepts")
# A provider whose dynamic write range is the whole stack publishes every cell, so a
# read of it can never fail; report how many edges the comparison can actually
# constrain. Providers are any-of, so one peer offering the whole stack in every
# direction the port uses absorbs the edge however narrow the others are. A boot
# `clr db` no longer puts a provider there -- what is left is a computed write the
# bounds analysis could not follow.
constrained = 0
for source, entries in wiring["ports"].items():
    for name, peer in entries.items():
        if peer["kind"] != "script":
            continue
        port = ports[source][name]
        offered = [surfaces[item] for item in peer["providers"] if item in surfaces]
        reads = bool(port["reads"] or port["read_ranges"])
        writes = bool(port["writes"] or port["write_ranges"])
        constrained += (reads or writes) and not any(
            (not reads or len(item["published"]) >= 512)
            and (not writes or len(item["accepted"]) >= 512)
            for item in offered
        )
print(f" - {constrained} of them can actually fail; on the rest some declared provider"
      " has an unproven computed write, so it offers every cell the port could ask for")
print(f" - {guarded} edges into migrated programs touch no S2..S7 header cell;"
      f" {reviewed} reviewed header reads are declared in the map")
