"""Derive service, revision, and protocol identity from filenames and headers."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

VERSION_RE = re.compile(r"_v(\d+)_(\d+)\.ic10$")


def revision(path: Path) -> str:
    match = VERSION_RE.search(path.name)
    if not match:
        raise ValueError(f"versioned IC10 filename required: {path}")
    return f"{match.group(1)}.{match.group(2)}"


def service_id(path: Path) -> str:
    stem = re.sub(r"_v\d+_\d+$", "", path.stem)
    return "ic10.script." + stem.replace("_", ".")


def protocol_id(magic: int, abi: int) -> str:
    return f"ic10.stack.{magic}.abi{abi}"


def protocol_name(pid: str, abi: int, provider_sources: list[str], definitions: dict[str, Any]) -> str:
    if pid in definitions and definitions[pid].get("name"):
        return definitions[pid]["name"]
    if pid.startswith("ic10.stack.27182818."):
        return f"Generic Controller Telemetry ABI{abi}"
    if provider_sources:
        stem = re.sub(r"_v\d+_\d+$", "", Path(provider_sources[0]).stem)
        return f"{' '.join(word.capitalize() for word in stem.split('_'))} ABI{abi}"
    return pid
