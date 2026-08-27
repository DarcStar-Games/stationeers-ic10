#!/usr/bin/env python3
"""Generate one deterministic JSON contract for every deployable IC10 script."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from framework.script_contracts import build_all, generated_artifact_paths, json_text

ROOT = _PROJECT_ROOT
INDEX_FILE = "contracts/index.json"
REGISTRY_FILE = "contracts/protocol_registry.json"
FIXED_OUTPUTS = (INDEX_FILE, REGISTRY_FILE)


def declared_outputs(root=ROOT):
    contracts, _, _, protocol_definitions = build_all(root)
    return tuple(sorted(set(FIXED_OUTPUTS) | set(contracts) | set(protocol_definitions)))


def main() -> None:
    contracts, index, protocols, protocol_definitions = build_all(ROOT)
    expected = {ROOT / rel for rel in contracts}
    for stale in generated_artifact_paths(ROOT, "*.contract.json"):
        if stale not in expected:
            stale.unlink()
    expected_protocols = {ROOT / rel for rel in protocol_definitions}
    for stale in generated_artifact_paths(ROOT, "*.protocol.json"):
        if stale not in expected_protocols:
            stale.unlink()
    for rel, contract in contracts.items():
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json_text(contract), encoding="utf-8")
    (ROOT / INDEX_FILE).write_text(json_text(index), encoding="utf-8")
    (ROOT / REGISTRY_FILE).write_text(json_text(protocols), encoding="utf-8")
    for rel, definition in protocol_definitions.items():
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json_text(definition), encoding="utf-8")
    print(f"Generated {len(contracts)} script contracts and {len(protocol_definitions)} protocol definitions")


if __name__ == "__main__":
    main()
