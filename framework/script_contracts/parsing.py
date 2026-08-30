"""Tokenize IC10 source into rows and resolve aliases and literal operands.

This is the layer the canonical parser proposed in issue #54 will replace;
nothing below it may re-implement tokenization.
"""
from __future__ import annotations

import math
import re
from typing import Any

PORTS = tuple(f"d{i}" for i in range(6))
INTEGER_RE = re.compile(r"^-?\d+$")


def parse_rows(source: str) -> list[list[str]]:
    rows = []
    for raw in source.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code or code.endswith(":"):
            continue
        rows.append(code.replace(",", " ").split())
    return rows


def parse_program(source: str) -> list[dict[str, Any]]:
    program: list[dict[str, Any]] = []
    for raw in source.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        if code.endswith(":"):
            program.append({"label": code[:-1], "row": []})
        else:
            program.append({"label": None, "row": code.replace(",", " ").split()})
    return program


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
    if INTEGER_RE.fullmatch(token):
        return int(token)
    return aliases.get(token)


def resolve_literal(token: str, aliases: dict[str, int]) -> int | float | str | None:
    integer = resolve_integer(token, aliases)
    if integer is not None:
        return integer
    try:
        number = float(token)
        return number if math.isfinite(number) else token.lower()
    except ValueError:
        pass
    if re.fullmatch(r'HASH\("[^"\n]+"\)', token):
        return token
    return None
