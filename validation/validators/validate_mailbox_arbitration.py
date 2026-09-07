#!/usr/bin/env python3
"""Every request mailbox with more than one writer program names what keeps them from posting at once."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import sys

from framework.json_schema import SchemaValidationError
from framework.script_contracts import build_all
from framework.script_wiring import (
    arbitration_failures,
    contended_pairs,
    dedicated_closure,
    load_arbitration,
    load_wiring,
    port_index,
    writer_edges,
)
from framework.source_metadata import load_manifest, resolve_script_metadata

ROOT = _PROJECT_ROOT

try:
    wiring = load_wiring(ROOT)
    declarations = load_arbitration(ROOT)["mailboxes"]
except (OSError, json.JSONDecodeError, SchemaValidationError) as error:
    print("Mailbox arbitration validation: FAIL")
    print(f" - unable to load the wiring map or data/mailbox_arbitration.json: {error}")
    raise SystemExit(1)

try:
    contracts, _, _, _ = build_all(ROOT)
except Exception as error:
    print("Mailbox arbitration validation: FAIL")
    print(f" - unable to build script contracts: {error}")
    raise SystemExit(1)

ports = port_index(contracts)
manifest = load_manifest(ROOT)
classes = {source: resolve_script_metadata(source, manifest, ROOT)["deployment_class"]
           for source in wiring["ports"]}
failures = arbitration_failures(wiring, ports, declarations, classes,
                                lambda path: (ROOT / path).read_text())

if failures:
    print("Mailbox arbitration validation: FAIL")
    [print(" -", failure) for failure in failures]
    sys.exit(1)

edges = writer_edges(wiring, ports)
shared = {provider: writers for provider, writers in edges.items() if len(writers) > 1}
laned = sorted(provider for provider, writers in shared.items() if not contended_pairs(writers))
kinds = {}
for provider, entry in declarations.items():
    if provider in shared and provider not in laned:
        kinds[entry["arbitration"]] = kinds.get(entry["arbitration"], 0) + 1
extra = sum(1 for provider in declarations if provider not in shared)
instances = sum(len(entry["instances"]) for entry in declarations.values()
                if entry["arbitration"] == "dedicated")
print("Mailbox arbitration validation: PASS")
print(f" - {len(edges)} programs have their request cells written by a declared peer;"
      f" {len(shared)} of them by more than one program")
print(f" - {len(laned)} are laned (writers never overlap a cell): "
      + ", ".join(item.split('/')[-1] for item in laned))
print(f" - the other {len(shared) - len(laned)} carry a reviewed arbitration whose writer set matches"
      " the map: " + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
      + f"; {extra} more single-writer selection surface(s) are declared reselect so a dedicated"
      " closure stops there")
print(f" - every serial group sits downstream of its root through declared mailbox writes;"
      f" {instances} dedicated instances are named in the deployment text they cite, with"
      " every request mailbox the instance brings:")
for provider, entry in sorted(declarations.items()):
    if entry["arbitration"] != "dedicated":
        continue
    closure = sorted(item.split("/")[-1] for item in dedicated_closure(edges, declarations, provider))
    print(f"     {provider.split('/')[-1]}: {len(entry['instances'])} instances, each with {closure}")
