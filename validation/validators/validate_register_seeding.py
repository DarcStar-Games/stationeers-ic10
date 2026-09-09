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
the value the next tick reads. This validator checks the claim against the
tree: no wired peer's contract writes the cell, and no network write
attributed to this program's identity writes it. Every network write has an
attributed target since issue #174 (`framework.network_provenance`, held by
`validate_network_provenance.py`), so there is no residue the check has to
accept.

The same-image edge proves the contract, not the program: a housing reflashed
between two programs publishing one `S0` identity takes the skip edge over the
other program's registers and private cells. So a carry under an identity two or
more programs publish is admissible only as the identity's
`framework.register_seeding.SHARED_IMAGE_CARRIES` entry declares it, once for
every program behind the identity, and the members must declare the same private
cells (issue #175).
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import sys

from framework.network_provenance import attributed_network_writes
from framework.register_seeding import (
    FRESH,
    PRIVATE_STATE_CELLS,
    SHARED_IMAGE_CARRIES,
    BootPaths,
    ImageState,
    image_header,
    image_identity,
    peer_written_cells,
    shared_identity_errors,
)
from framework.scan_coverage import require_nonempty
from framework.script_contracts import build_all
from framework.script_wiring import load_wiring

ROOT = _PROJECT_ROOT
# (path, register) -> why the register may be read on a fresh housing before
# the boot path writes it. An entry no finding matches fails as stale.
SEEDING_EXEMPTIONS: dict[tuple[str, str], str] = {}


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
    reached = attributed_network_writes(contracts)
    failed = False
    for path, cells in sorted(PRIVATE_STATE_CELLS.items()):
        contract = by_source.get(path)
        if contract is None:
            print(f"FAIL {path}: private state cells declared for a program with no contract")
            failed = True
            continue
        header = image_header(contract)
        magic = header["magic"] if header is not None else None
        for cell in sorted(cells):
            if cell in peer_written[path]:
                print(f"FAIL {path}: S{cell} is declared private but a wired peer's contract writes it")
                failed = True
            elif magic is not None and cell in reached.get(magic, ()):
                print(f"FAIL {path}: S{cell} is declared private but a network write attributed to"
                      f" this program's S0 identity writes it")
                failed = True
    fresh_seen: set[tuple[str, str]] = set()
    fresh_total = carried_total = unexempt_total = 0
    states: dict[str, ImageState] = {}
    for path in require_nonempty(sorted(by_source), "deployable programs with a contract"):
        private = frozenset(PRIVATE_STATE_CELLS.get(path, {})) - peer_written[path]
        findings = BootPaths((ROOT / path).read_text(), private).findings()
        fresh = [item for item in findings if item.edge == FRESH]
        carried = [item for item in findings if item.edge != FRESH]
        states[path] = ImageState(image_identity(by_source[path]), frozenset(PRIVATE_STATE_CELLS.get(path, {})),
                                  frozenset(item.register for item in carried))
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
    shared, shared_errors = shared_identity_errors(states)
    print("Identities published by two or more programs (the same-image edge proves the contract):")
    for identity, members in shared.items():
        entry = SHARED_IMAGE_CARRIES.get(identity, {})
        carried_registers = sorted({register for path in members for register in states[path].carries},
                                   key=lambda name: (len(name), name))
        cells = sorted({cell for path in members for cell in states[path].private_cells})
        declared = "yes" if entry else "MISSING" if carried_registers or cells else "none needed"
        print(f"  {identity:28} {len(members):2} programs  carries={carried_registers}  private cells={cells}"
              f"  declared={declared}")
        for register, meaning in entry.get("registers", {}).items():
            print(f"     - {register:3} {meaning}")
        for cell, meaning in entry.get("cells", {}).items():
            print(f"     - S{cell:<2} {meaning}")
    for error in shared_errors:
        print(f"FAIL {error}")
    failed |= bool(shared_errors)
    print(f"Registers read before written on a fresh housing: {fresh_total}"
          f" ({fresh_total - unexempt_total} reviewed exemptions);"
          f" carried over a same-image reflash guard: {carried_total};"
          f" shared identities: {len(shared)} ({len(SHARED_IMAGE_CARRIES)} with a carry declaration)")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
