"""Contract-analysis views over the canonical IC10 source representation."""
from __future__ import annotations

from typing import Any

from framework.ic10_source import (
    INTEGER_RE,
    Label,
    integer_value,
    literal_value,
    parse_ic10,
)

PORTS = tuple(f"d{i}" for i in range(6))


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


def resolve_integer(token: str, aliases: dict[str, int]) -> int | None:
    return integer_value(token, aliases)


def resolve_literal(token: str, aliases: dict[str, int]) -> int | float | str | None:
    return literal_value(token, aliases)
