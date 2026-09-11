#!/usr/bin/env python3
"""Refuse a network write whose target neither an identity check nor a reviewed provenance names (issue #174).

A `putd` lands on whatever housing its reference register names. For a device
port the rule is settled -- a declared consumer edge rests on a literal `S0`
check, and `validate_identity_coverage.py` holds every access to it -- but a
network write had no rule: the contract recorded the cells written and
whatever the writer checked on the target, which for most references was
nothing, because the reference came out of a directory record or a request
cell whose meaning lived in the reviewer's head. `framework.network_provenance`
walks every path from the entry and asks, at every write, where the reference
came from: a reference the path has identity-checked (a `getd rX rR 0` and an
equality branch against a magic some program publishes, carried through
`move`) attributes the write to that identity's providers; a reference loaded
from somewhere else needs a `network_provenance` declaration in
`data/script_contract_overrides.json` naming what a ReferenceId in that place
points at, with the reason. The build records the result on the contract and
counts it in `contracts/index.json`; this validator prints it, fails a write
with no attributed target, and holds an own-cell declaration to who actually
fills the cell: a `peer` cell is one some wired peer's contract writes, a
`self` cell is one the program writes and no peer does, and an `operator` cell
is one nothing in the tree writes.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import sys

from framework.network_provenance import CHECKED, filled_by_errors, writing
from framework.register_seeding import peer_written_cells
from framework.scan_coverage import require_nonempty
from framework.script_contracts import build_all
from framework.script_wiring import load_wiring

ROOT = _PROJECT_ROOT


def describe(dependency: dict) -> str:
    """One line on what attributes a dependency's writes."""
    parts = []
    if any(token.startswith(CHECKED + ":") for token in dependency["origins"]):
        parts.append("identity checked on the path")
    for declaration in dependency.get("provenance", ()):
        origin = declaration["origin"]
        detail = " ".join(str(origin[key]) for key in origin if key != "kind")
        parts.append(f"declared {origin['kind']} {detail}")
    return "; ".join(parts) or "nothing"


def main() -> int:
    print("IC10 network write provenance")
    print("=" * 100)
    try:
        contracts, index, _, _ = build_all(ROOT)
    except Exception as error:  # noqa: BLE001 - the contract build's own message is the diagnostic
        print(f"FAIL unable to build script contracts: {error}")
        return 1
    peer_written = peer_written_cells(contracts, load_wiring(ROOT))
    by_source = {contract["source"]: contract for contract in contracts.values()}
    writers = {path for path, contract in by_source.items()
               if any(writing(item) for item in contract["network_dependencies"])}
    failed = False
    references = sites = declarations = unattributed_total = 0
    for path in require_nonempty(sorted(writers), "programs that write through a reference id"):
        contract = by_source[path]
        dependencies = [item for item in contract["network_dependencies"] if writing(item)]
        problems = []
        for dependency in dependencies:
            references += 1
            sites += len(dependency["origins"])
            declarations += len(dependency.get("provenance", ()))
            unattributed_total += len(dependency["unattributed"])
            if dependency["unattributed"]:
                problems.append(f"{dependency['reference']}: no attributed target for a reference loaded from"
                                f" {', '.join(dependency['unattributed'])}")
            for declaration in dependency.get("provenance", ()):
                problems.extend(filled_by_errors(contract, declaration, peer_written[path]))
        failed |= bool(problems)
        state = "FAIL" if problems else "PASS"
        print(f"{state:4} {path:70} refs={len(dependencies):2}"
              f" unattributed={sum(len(item['unattributed']) for item in dependencies):2}")
        for dependency in dependencies:
            targets = ", ".join(dependency["targets"]) or "-"
            devices = "".join(f"; device: {item}" for item in dependency.get("devices", ()))
            print(f"     - {dependency['reference']:16} -> {targets}{devices}  [{describe(dependency)}]")
        for problem in problems:
            print(f"     ! {problem}")
    print("=" * 100)
    inventory = index["network_write_inventory"]
    if inventory["unattributed_count"] != sum(1 for path in writers for item in by_source[path]["network_dependencies"]
                                               if writing(item) and item["unattributed"]):
        print("FAIL the index's unattributed count disagrees with the contracts")
        failed = True
    if inventory["declared_provenance_count"] != declarations:
        print(f"FAIL the index counts {inventory['declared_provenance_count']} declarations on writing references,"
              f" the contracts carry {declarations}")
        failed = True
    print(f"Network writes: {references} references in {len(writers)} programs,"
          f" {declarations} reviewed provenance declarations")
    print(f"Writes with no attributed target: {unattributed_total}")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
