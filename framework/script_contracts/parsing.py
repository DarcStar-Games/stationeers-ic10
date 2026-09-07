"""Contract-analysis views over the canonical IC10 source representation."""
from __future__ import annotations

import re
from typing import Any

from framework.ic10_source import (
    INTEGER_RE,
    Label,
    integer_value,
    literal_value,
    parse_ic10,
)

PORTS = tuple(f"d{i}" for i in range(6))
# A register-indexed port: `dr9` addresses whichever pin `r9` holds. The pins it
# can name are a fact about the register's values, resolved by
# `framework.script_contracts.register_ports` and passed to the scans as
# `register_ports` (`{"dr9": ("d1", "d2")}`).
REGISTER_PORT_RE = re.compile(r"^dr(?:[0-9]|1[0-5])$")
RegisterPorts = dict[str, tuple[str, ...]]


def parse_rows(source: str) -> list[list[str]]:
    """Return mutable rows for the existing contract-analysis phases."""
    return [list(row.tokens) for row in parse_ic10(source).rows]


def parse_program(source: str) -> list[dict[str, Any]]:
    """Return the legacy control-flow view over canonical source statements."""
    return [
        {"label": statement.name, "row": []}
        if isinstance(statement, Label)
        else {"label": None, "row": list(statement.tokens)}
        for statement in parse_ic10(source).statements
    ]


def row_nodes(program: list[dict[str, Any]]) -> list[int]:
    return [index for index, entry in enumerate(program) if entry["row"]]


def collect_aliases(rows: list[list[str]]) -> tuple[dict[str, str], dict[str, int]]:
    ports: dict[str, str] = {}
    integers: dict[str, int] = {}
    for row in rows:
        if len(row) != 3 or row[0] != "alias":
            continue
        if row[2] in PORTS:
            ports[row[1]] = row[2]
        elif INTEGER_RE.fullmatch(row[2]):
            integers[row[1]] = int(row[2])
    return ports, integers


def resolve_port(token: str, aliases: dict[str, str]) -> str | None:
    return token if token in PORTS else aliases.get(token)


def register_port(token: str) -> str | None:
    """The register a `dr<n>` operand indexes by, or None for any other token."""
    return token[1:] if REGISTER_PORT_RE.fullmatch(token) else None


def resolve_ports(
    token: str, aliases: dict[str, str], register_ports: RegisterPorts | None = None,
) -> tuple[str, ...]:
    """Every pin one port operand can address: one for `d<n>` or an alias, the
    resolved set for a register-indexed `dr<n>`, none for anything else."""
    port = resolve_port(token, aliases)
    if port is not None:
        return (port,)
    if register_ports and token in register_ports:
        return tuple(register_ports[token])
    return ()


def resolve_integer(token: str, aliases: dict[str, int]) -> int | None:
    return integer_value(token, aliases)


def resolve_literal(token: str, aliases: dict[str, int]) -> int | float | str | None:
    return literal_value(token, aliases)
