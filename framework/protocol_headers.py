"""Load and resolve the declared protocol header registry.

Registry format V2 names each base-0 service header by its contract name; the
published S0 identity value is derived, never allocated:
``HASH("<Contract>.v<ABI>")``.  Folding the ABI into the hashed identity makes a
single S0 equality check exact — a service that changes its contract changes its
name, so every consumer comparing the old identity fails closed.  Block headers
away from base 0 (the Generic Telemetry block at S96) keep an explicit numeric
magic and a separate version cell because their consumers deliberately accept a
version range.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from framework.ic10_source import game_hash

FORMAT = "IC10_PROTOCOL_HEADERS_V2"
CONTRACT_NAME_RE = r"^[A-Z][A-Za-z0-9]*$"


def header_name(contract: str, abi: int) -> str:
    """The hashed identity string a contract publishes and consumers check."""
    return f"{contract}.v{abi}"


def header_token(contract: str, abi: int) -> str:
    """The exact IC10 source literal for a contract's S0 identity."""
    return f'HASH("{header_name(contract, abi)}")'


def resolve_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return the entry with its numeric magic derived from the contract name."""
    if "contract" in entry:
        return {**entry, "magic": game_hash(header_name(entry["contract"], entry["abi"]))}
    return dict(entry)


def load_registry(root: Path) -> dict[str, Any]:
    data = json.loads((Path(root) / "data" / "script_protocol_headers.json").read_text())
    if data.get("format") != FORMAT:
        raise ValueError("unsupported script protocol header format")
    return data


def load_headers(root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """Load (scripts, consumers) with numeric magics derived from contract names."""
    data = load_registry(root)
    scripts = {
        path: [resolve_entry(entry) for entry in entries]
        for path, entries in data["scripts"].items()
    }
    consumers = {
        path: [
            {**requirement, "accepted": [resolve_entry(item) for item in requirement.get("accepted", [])]}
            for requirement in requirements
        ]
        for path, requirements in data["consumers"].items()
    }
    return scripts, consumers
