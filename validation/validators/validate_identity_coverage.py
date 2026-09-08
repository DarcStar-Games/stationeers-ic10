#!/usr/bin/env python3
"""Refuse a port access on a path that never passed the port's identity check (issue #109).

A declared consumer edge is backed by a literal `S0` equality check that
`verify_declared_consumers` proves exists and rejects. This validator asks the
other half: whether the program can reach an access to that port on a path
that never took the check's success edge. `framework/identity_coverage.py`
walks every path from the entry carrying the ports each has established and
the reads each holds unsettled, and reports an access met on a path that never
passed the check. A reflash guard's same-image edge earns no carry here: what
is on a pin is wiring, which a reflash does not preserve.

A finding fails unless `IDENTITY_EXEMPTIONS` names it with the reason the
access is safe. The walk reads a program's own state cells back through
`framework.register_seeding.PRIVATE_STATE_CELLS`, the reviewed claim
`validate_register_seeding.py` holds to the tree.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import sys

from framework.identity_coverage import IdentityCoverage, declared_identities
from framework.register_seeding import PRIVATE_STATE_CELLS, peer_written_cells
from framework.scan_coverage import require_nonempty
from framework.script_contracts import build_all
from framework.script_wiring import load_wiring

ROOT = _PROJECT_ROOT
# (path, port) -> why the port may be acted on before the path has checked
# its identity. An entry no finding matches fails as stale.
IDENTITY_EXEMPTIONS: dict[tuple[str, str], str] = {}


def main() -> int:
    print("IC10 identity-check coverage")
    print("=" * 100)
    try:
        contracts, _, _, _ = build_all(ROOT)
    except Exception as error:  # noqa: BLE001 - the contract build's own message is the diagnostic
        print(f"FAIL unable to build script contracts: {error}")
        return 1
    peer_written = peer_written_cells(contracts, load_wiring(ROOT))
    by_source = {contract["source"]: contract for contract in contracts.values()}
    consumers = {path for path, contract in by_source.items() if contract["contracts"]["consumes"]}
    seen: set[tuple[str, str]] = set()
    edges = accesses = total = unexempt_total = 0
    failed = False
    for path in require_nonempty(sorted(consumers), "programs with a declared consumer edge"):
        contract = by_source[path]
        identities = declared_identities(contract)
        private = frozenset(PRIVATE_STATE_CELLS.get(path, {})) - peer_written[path]
        pins = {token: tuple(item["pins"]) for token, item in contract.get("register_ports", {}).items()}
        coverage = IdentityCoverage((ROOT / path).read_text(), identities, private, pins)
        findings = coverage.findings()
        unexempt = [item for item in findings if (path, item.port) not in IDENTITY_EXEMPTIONS]
        seen.update((path, item.port) for item in findings)
        edges += len(identities)
        accesses += sum(len(ports) for ports in coverage.reads.values())
        accesses += sum(len(ports) for ports in coverage.writes.values())
        total += len(findings)
        unexempt_total += len(unexempt)
        failed |= bool(unexempt)
        state = "FAIL" if unexempt else "PASS"
        print(f"{state:4} {path:70} ports={len(identities)} unchecked={len(findings)}")
        for item in findings:
            note = ""
            if (path, item.port) in IDENTITY_EXEMPTIONS:
                note = f"  [exempt: {IDENTITY_EXEMPTIONS[(path, item.port)]}]"
            print(f"     - {item.port} acted on at line {item.line_number}"
                  f" `{item.code_text}` on a path that never checked its identity"
                  f" ({item.accesses} such access{'es' if item.accesses != 1 else ''}){note}")
    print("=" * 100)
    for path, port in sorted(IDENTITY_EXEMPTIONS):
        if (path, port) not in seen:
            print(f"FAIL stale identity exemption: {path} {port} is checked on every path;"
                  f" remove the entry")
            failed = True
    print(f"Declared consumer ports: {edges} across {len(consumers)} programs, {accesses} accesses walked")
    print(f"Accesses on a path that never checked the port: {total}"
          f" ({total - unexempt_total} reviewed exemptions)")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
