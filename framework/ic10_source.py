"""Canonical, immutable representation of IC10 source text.

This module only describes source syntax.  Control-flow analysis and execution
state belong to the consumers that build on :func:`parse_ic10`.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re
from typing import TypeAlias
import zlib

LABEL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INTEGER_RE = re.compile(r"^-?\d+$")
HASH_RE = re.compile(r'^HASH\("([^"\n]+)"\)$')
DIRECTIVE_OPCODES = frozenset({"alias", "define"})


def game_hash(name: str) -> int:
    """The game's HASH(): CRC32 of the string, as the signed int32 IC10 sees."""
    crc = zlib.crc32(name.encode())
    return crc - (1 << 32) if crc >= (1 << 31) else crc


@dataclass(frozen=True, slots=True)
class SourceLine:
    """One physical source line split at its first unquoted comment marker."""

    number: int
    raw_text: str
    code_text: str
    comment_text: str


@dataclass(frozen=True, slots=True)
class SourceRow:
    """A normalized non-label source row, including directives."""

    line: SourceLine
    opcode: str
    operands: tuple[str, ...]

    @property
    def tokens(self) -> tuple[str, ...]:
        return (self.opcode, *self.operands)


@dataclass(frozen=True, slots=True)
class Directive:
    """An alias or define row retained separately from executable code."""

    row: SourceRow
    name: str | None
    value: str | None

    @property
    def kind(self) -> str:
        return self.row.opcode


@dataclass(frozen=True, slots=True)
class Label:
    """A label resolved against both normalized rows and executable code."""

    line: SourceLine
    name: str
    statement_index: int
    row_index: int
    instruction_index: int


Statement: TypeAlias = Label | SourceRow


@dataclass(frozen=True, slots=True)
class SourceDiagnostic:
    line_number: int
    code: str
    message: str
    related_line_number: int | None = None


@dataclass(frozen=True, slots=True)
class IC10Source:
    """The shared parser result used by validators, analyzers, and the harness."""

    lines: tuple[SourceLine, ...]
    statements: tuple[Statement, ...]
    rows: tuple[SourceRow, ...]
    instructions: tuple[SourceRow, ...]
    directives: tuple[Directive, ...]
    labels: tuple[Label, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    def label_indices(self) -> dict[str, int]:
        """Return label-to-executable-index resolution (last definition wins)."""
        return {label.name: label.instruction_index for label in self.labels}

    def directive_values(self, kind: str | None = None) -> dict[str, str]:
        """Return well-formed directive bindings (last definition wins)."""
        return {
            directive.name: directive.value
            for directive in self.directives
            if directive.name is not None
            and directive.value is not None
            and (kind is None or directive.kind == kind)
        }


def _split_line(raw_text: str) -> tuple[str, str]:
    """Split code and comment at an unquoted IC10 comment marker."""
    quoted = False
    escaped = False
    for index, character in enumerate(raw_text):
        if character == '"' and not escaped:
            quoted = not quoted
        if character == "#" and not quoted:
            return raw_text[:index].strip(), raw_text[index + 1:].strip()
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    return raw_text.strip(), ""


def _tokens(code: str) -> tuple[str, ...]:
    """Normalize separators while retaining quoted spaces and commas in one operand."""
    tokens: list[str] = []
    token: list[str] = []
    quoted = False
    escaped = False
    for character in code:
        if character == '"' and not escaped:
            quoted = not quoted
        if not quoted and (character.isspace() or character == ","):
            if token:
                tokens.append("".join(token))
                token = []
        else:
            token.append(character)
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    if token:
        tokens.append("".join(token))
    return tuple(tokens)


@lru_cache(maxsize=512)
def parse_ic10(source: str) -> IC10Source:
    """Parse IC10 text without performing control-flow or opcode validation."""
    lines: list[SourceLine] = []
    statements: list[Statement] = []
    rows: list[SourceRow] = []
    instructions: list[SourceRow] = []
    directives: list[Directive] = []
    labels: list[Label] = []
    diagnostics: list[SourceDiagnostic] = []
    first_label_lines: dict[str, int] = {}

    for number, raw_text in enumerate(source.splitlines(), 1):
        code_text, comment_text = _split_line(raw_text)
        line = SourceLine(number, raw_text, code_text, comment_text)
        lines.append(line)
        if not code_text:
            continue

        if code_text.endswith(":"):
            name = code_text[:-1]
            if LABEL_NAME_RE.fullmatch(name):
                label = Label(
                    line=line,
                    name=name,
                    statement_index=len(statements),
                    row_index=len(rows),
                    instruction_index=len(instructions),
                )
                statements.append(label)
                labels.append(label)
                if name in first_label_lines:
                    diagnostics.append(SourceDiagnostic(
                        number,
                        "duplicate-label",
                        f"duplicate label {name!r}",
                        first_label_lines[name],
                    ))
                else:
                    first_label_lines[name] = number
                continue
            diagnostics.append(SourceDiagnostic(
                number, "malformed-label", f"malformed label declaration {code_text!r}"
            ))
        elif ":" in code_text.split(maxsplit=1)[0]:
            diagnostics.append(SourceDiagnostic(
                number, "malformed-label", f"label must occupy its own source row: {code_text!r}"
            ))

        tokens = _tokens(code_text)
        if not tokens:
            continue
        row = SourceRow(line, tokens[0], tokens[1:])
        statements.append(row)
        rows.append(row)
        if row.opcode in DIRECTIVE_OPCODES:
            directives.append(Directive(
                row,
                row.operands[0] if len(row.operands) >= 1 else None,
                row.operands[1] if len(row.operands) >= 2 else None,
            ))
        else:
            instructions.append(row)

    return IC10Source(
        tuple(lines), tuple(statements), tuple(rows), tuple(instructions),
        tuple(directives), tuple(labels), tuple(diagnostics),
    )


def integer_value(token: str, aliases: dict[str, int] | None = None) -> int | None:
    """Resolve a literal integer, a HASH literal, or a caller-supplied integer alias."""
    if INTEGER_RE.fullmatch(token):
        return int(token)
    match = HASH_RE.fullmatch(token)
    if match:
        return game_hash(match.group(1))
    return (aliases or {}).get(token)


def literal_value(
    token: str, aliases: dict[str, int] | None = None
) -> int | float | str | None:
    """Resolve the literal forms shared by static IC10 consumers."""
    integer = integer_value(token, aliases)
    if integer is not None:
        return integer
    try:
        number = float(token)
        return number if math.isfinite(number) else token.lower()
    except ValueError:
        return None
