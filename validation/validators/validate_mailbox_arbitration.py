#!/usr/bin/env python3
"""Every request mailbox with more than one writer program names what keeps them from posting at once.

A `serial` claim is held in both halves: the wiring map puts every writer under
the named root, and `framework/request_blocking.py` walks every program on the
tree from the root to a writer and refuses a post some path leaves unanswered
when the program posts to another peer or replies to its own caller (issue
#146). A finding fails unless `BLOCKING_EXEMPTIONS` names it with the reason
the post is safe, and an entry no finding matches fails as stale.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import sys

from framework.json_schema import SchemaValidationError
from framework.register_seeding import PRIVATE_STATE_CELLS, peer_written_cells
from framework.request_blocking import RequestBlocking, own_response_cells, port_tokens
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
# (path, port posted on) -> why a post the walk sees unanswered at a later post
# or reply is safe. An entry no finding matches fails as stale.
BLOCKING_EXEMPTIONS: dict[tuple[str, str], str] = {
    ("ic10/manufacturing/manufacturing_driver_router_v2_0.ic10", "d0"):
        "LIVE_CURRENT mirror: a new token from the Gate re-dispatches to the selected driver at once,"
        " and the walk cannot decide the token-change branch; the Gate posts a token only after"
        " reading the Router's reply to the last one, which the walk proves",
    ("ic10/manufacturing/manufacturing_driver_router_v2_0.ic10", "d1"):
        "LIVE_CURRENT mirror: a new token from the Gate re-dispatches to the selected driver at once,"
        " and the walk cannot decide the token-change branch; the Gate posts a token only after"
        " reading the Router's reply to the last one, which the walk proves",
}

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
by_source = {contract["source"]: contract for contract in contracts.values()}
peer_written = peer_written_cells(contracts, wiring)
manifest = load_manifest(ROOT)
classes = {source: resolve_script_metadata(source, manifest, ROOT)["deployment_class"]
           for source in wiring["ports"]}
walked: dict[str, int] = {}
exempted: dict[tuple[str, str], int] = {}


def blocking(path: str) -> list[str]:
    """The posts `path` leaves unanswered before posting elsewhere or replying, one line each."""
    contract = by_source[path]
    private = frozenset(PRIVATE_STATE_CELLS.get(path, {})) - peer_written[path]
    pins = {token: tuple(item["pins"]) for token, item in contract.get("register_ports", {}).items()}
    check = RequestBlocking((ROOT / path).read_text(), port_tokens(path, contract, wiring, by_source),
                            own_response_cells(contract), private, pins)
    findings = check.findings()
    walked[path] = check.posts
    out: list[str] = []
    for item in findings:
        if (path, item.port) in BLOCKING_EXEMPTIONS:
            exempted[(path, item.port)] = exempted.get((path, item.port), 0) + 1
            continue
        out.append(f"posts to {item.port} at line {item.line_number} `{item.code_text}` and {item.offence}"
                   f" at line {item.offence_line} `{item.offence_text}` before reading {item.port}'s"
                   " response token")
    return out


failures = arbitration_failures(wiring, ports, declarations, classes,
                                lambda path: (ROOT / path).read_text(), blocking)
for key in sorted(BLOCKING_EXEMPTIONS):
    if key not in exempted:
        failures.append(f"{key[0]}: stale blocking exemption for {key[1]}; every post on it is answered"
                        " before the next post or reply, remove the entry")

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
groups = sum(1 for entry in declarations.values() if entry["arbitration"] == "serial")
groups += sum(1 for entry in declarations.values() if entry["arbitration"] == "dedicated"
              for instance in entry["instances"] if "serialized_by" in instance)
print("Mailbox arbitration validation: PASS")
print(f" - {len(edges)} programs have their request cells written by a declared peer;"
      f" {len(shared)} of them by more than one program")
print(f" - {len(laned)} are laned (writers never overlap a cell): "
      + ", ".join(item.split('/')[-1] for item in laned))
print(f" - the other {len(shared) - len(laned)} carry a reviewed arbitration whose writer set matches"
      " the map: " + ", ".join(f"{count} {kind}" for kind, count in sorted(kinds.items()))
      + f"; {extra} more single-writer selection surface(s) are declared reselect so a dedicated"
      " closure stops there")
print(f" - every serial group sits downstream of its root through declared mailbox writes, and the"
      f" {len(walked)} programs on the {groups} serialized trees wait on each of their {sum(walked.values())}"
      f" posts before posting elsewhere or replying ({len(exempted)} reviewed exemptions"
      f" on {len({path for path, _ in exempted})} program)")
for (path, port), count in sorted(exempted.items()):
    print(f"     {path.split('/')[-1]} {port}: {count} finding(s) [exempt: {BLOCKING_EXEMPTIONS[(path, port)]}]")
print(f" - {instances} dedicated instances are named in the deployment text they cite, with"
      " every request mailbox the instance brings:")
for provider, entry in sorted(declarations.items()):
    if entry["arbitration"] != "dedicated":
        continue
    closure = sorted(item.split("/")[-1] for item in dedicated_closure(edges, declarations, provider))
    print(f"     {provider.split('/')[-1]}: {len(entry['instances'])} instances, each with {closure}")
