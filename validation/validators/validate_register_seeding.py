#!/usr/bin/env python3
"""Refuse a register read on a boot path before that path has written it (issue #168).

Registers survive a reflash and a power loss, and the rule that a program
explicitly initializes any persistent register whose starting value matters was
enforced for the stack (the boot clear, the reflash guard) and reviewed by eye
for the registers. `framework/register_seeding.py` walks every path from the
entry and reports a register read before that path wrote it, on the fresh
housing path (`fresh`) or only over the same-image edge of a reflash guard
(`same-image`, a carry the guard exists to allow, reported for the record).

A `fresh` read fails unless `SEEDING_EXEMPTIONS` names it with the reason the
carry is safe. `framework.register_seeding.PRIVATE_STATE_CELLS` is the reviewed
claim that lets the walk read a program's own state back from its stack: a
cell nothing but the program writes, so a value the boot path poked there is
the value the next tick reads. This validator checks the claim as far as the
tree can see -- no wired peer's contract writes the cell, and no network write
that pins this program's `S0` identity writes it -- and the residue it accepts
is a network write with no identity check, which nothing in the tree
attributes to a target.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import sys

from framework.register_seeding import FRESH, PRIVATE_STATE_CELLS, BootPaths, peer_written_cells
from framework.scan_coverage import require_nonempty
from framework.script_contracts import build_all
from framework.script_wiring import load_wiring

ROOT = _PROJECT_ROOT
# (path, register) -> why the register may be read on a fresh housing before
# the boot path writes it. An entry no finding matches fails as stale.
SEEDING_EXEMPTIONS: dict[tuple[str, str], str] = {}


def identity_magic(contract: dict) -> int | None:
    for field in contract["own_stack"]["fields"]:
        if field["address"] == 0 and isinstance(field.get("const"), int):
            return field["const"]
    return None


def identity_pinned_network_writes(contracts: dict) -> dict[int, set[int]]:
    """Cells written through a reference id whose `S0` the writer pinned, by that magic."""
    pinned: dict[int, set[int]] = {}
    for contract in contracts.values():
        for dependency in contract["network_dependencies"]:
            magics = [c["value"] for c in dependency["constraints"]
                      if c["address"] == 0 and c["operator"] == "equals"]
            cells = set(dependency["literal_writes"])
            if dependency["dynamic_write"]:
                cells = set(range(512))
            for magic in magics:
                pinned.setdefault(magic, set()).update(cells)
    return pinned


def main() -> int:
    print("IC10 register seeding")
    print("=" * 100)
    try:
        contracts, _, _, _ = build_all(ROOT)
    except Exception as error:  # noqa: BLE001 - the contract build's own message is the diagnostic
        print(f"FAIL unable to build script contracts: {error}")
        return 1
    wiring = load_wiring(ROOT)
    peer_written = peer_written_cells(contracts, wiring)
    by_source = {contract["source"]: contract for contract in contracts.values()}
    pinned = identity_pinned_network_writes(contracts)
    failed = False
    for path, cells in sorted(PRIVATE_STATE_CELLS.items()):
        contract = by_source.get(path)
        if contract is None:
            print(f"FAIL {path}: private state cells declared for a program with no contract")
            failed = True
            continue
        magic = identity_magic(contract)
        for cell in sorted(cells):
            if cell in peer_written[path]:
                print(f"FAIL {path}: S{cell} is declared private but a wired peer's contract writes it")
                failed = True
            elif magic is not None and cell in pinned.get(magic, ()):
                print(f"FAIL {path}: S{cell} is declared private but a network write pinned to"
                      f" this program's S0 identity writes it")
                failed = True
    fresh_seen: set[tuple[str, str]] = set()
    fresh_total = carried_total = unexempt_total = 0
    for path in require_nonempty(sorted(by_source), "deployable programs with a contract"):
        private = frozenset(PRIVATE_STATE_CELLS.get(path, {})) - peer_written[path]
        findings = BootPaths((ROOT / path).read_text(), private).findings()
        fresh = [item for item in findings if item.edge == FRESH]
        carried = [item for item in findings if item.edge != FRESH]
        unexempt = [item for item in fresh if (path, item.register) not in SEEDING_EXEMPTIONS]
        fresh_seen.update((path, item.register) for item in fresh)
        fresh_total += len(fresh)
        carried_total += len(carried)
        unexempt_total += len(unexempt)
        failed |= bool(unexempt)
        state = "FAIL" if unexempt else "PASS"
        print(f"{state:4} {path:70} fresh={len(fresh):2} same-image={len(carried):2}")
        for item in findings:
            note = ""
            if item.edge == FRESH and (path, item.register) in SEEDING_EXEMPTIONS:
                note = f"  [exempt: {SEEDING_EXEMPTIONS[(path, item.register)]}]"
            print(f"     - {item.edge:10} {item.register:3} read at line {item.line_number}"
                  f" `{item.code_text}` before any write on the path"
                  f" ({item.reads} such read{'s' if item.reads != 1 else ''}){note}")
    print("=" * 100)
    for path, register in sorted(SEEDING_EXEMPTIONS):
        if (path, register) not in fresh_seen:
            print(f"FAIL stale seeding exemption: {path} reads {register} on no fresh path"
                  f" before writing it; remove the entry")
            failed = True
    print(f"Registers read before written on a fresh housing: {fresh_total}"
          f" ({fresh_total - unexempt_total} reviewed exemptions);"
          f" carried over a same-image reflash guard: {carried_total}")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
