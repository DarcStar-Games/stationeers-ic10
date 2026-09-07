"""Register read/write roles of IC10 instructions, from the game's own signatures.

``data/ic10_instruction_set.json`` records each instruction's signature as the
game prints it, e.g. ``get r? device(d?|r?|id) address(r?|num)``.  One rule
covers the whole set: an instruction whose first signature operand is exactly
``r?`` writes its first operand, and every other register operand is a read.
That is true of the loads, the arithmetic, ``move``, and the ``s*`` comparisons,
and it keeps the store family honest -- ``put``, ``poke``, ``push``, ``s`` and
``sd`` name their value operand ``r?`` in a later position, where it is read.

The analysis here is whole-file and deliberately conservative: a write is dead
only when no instruction anywhere in the file reads that register.  A flow-
sensitive version would also find a write overwritten before use, but this one
needs no control-flow graph and has no false positives on a program that reads
a register on any path.  Three operand forms need care:

* an ``alias`` name stands for the register it was bound to, so a read through
  the alias is a read of that register;
* ``rrN`` reads ``rN`` to pick a register and, in a read position, reads the
  register it picked -- which could be any of them, so a file that reads through
  ``rrN`` anywhere is treated as reading every register;
* ``drN`` reads ``rN`` to pick a device pin and no other register.

``sp`` and ``ra`` are outside the rule: ``push``/``pop``/``peek`` and ``jal``
read and write them implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from framework.ic10_source import parse_ic10

INSTRUCTION_SET_PATH = "data/ic10_instruction_set.json"
INSTRUCTION_SET_FORMAT = "IC10_INSTRUCTION_SET_V1"
REGISTER_RE = re.compile(r"^r(?:[0-9]|1[0-5])$")
INDIRECT_REGISTER_RE = re.compile(r"^rr(\d+)$")
INDIRECT_DEVICE_RE = re.compile(r"^dr(\d+)$")

Signatures = dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class RegisterWrite:
    """One instruction that writes a register, located by source line."""

    line_number: int
    register: str
    code_text: str


def load_instruction_signatures(root: Path) -> Signatures:
    """Map each opcode to the operand tokens of its official signature."""
    data = json.loads((root / INSTRUCTION_SET_PATH).read_text())
    if data.get("format") != INSTRUCTION_SET_FORMAT:
        raise ValueError(f"unsupported instruction set format: {data.get('format')!r}")
    signatures: Signatures = {}
    for name, entry in data["instructions"].items():
        tokens = entry.get("example", "").split()
        if tokens and tokens[0] == name:
            signatures[name] = tuple(tokens[1:])
    return signatures


def writes_first_operand(signatures: Signatures) -> frozenset[str]:
    """Opcodes whose first operand is the register they write."""
    return frozenset(name for name, operands in signatures.items() if operands[:1] == ("r?",))


def _index_register(match: re.Match[str] | None) -> str | None:
    if match is None:
        return None
    register = f"r{int(match.group(1))}"
    return register if REGISTER_RE.fullmatch(register) else None


def dead_register_writes(source: str, signatures: Signatures) -> tuple[RegisterWrite, ...]:
    """Writes to ``r0..r15`` that no instruction in ``source`` ever reads."""
    parsed = parse_ic10(source)
    writers = writes_first_operand(signatures)
    aliases: dict[str, set[str]] = {}
    for directive in parsed.directives:
        if directive.kind == "alias" and directive.value and REGISTER_RE.fullmatch(directive.value):
            aliases.setdefault(directive.name or "", set()).add(directive.value)

    def registers(token: str) -> set[str]:
        if REGISTER_RE.fullmatch(token):
            return {token}
        return set(aliases.get(token, ()))

    reads: set[str] = set()
    reads_indirectly = False
    writes: list[RegisterWrite] = []
    for row in parsed.instructions:
        if row.opcode == "label":
            continue
        operands = row.operands
        read_from = 0
        if row.opcode in writers and operands:
            for register in registers(operands[0]):
                writes.append(RegisterWrite(row.line.number, register, row.line.code_text.strip()))
            index = _index_register(INDIRECT_REGISTER_RE.fullmatch(operands[0]))
            if index:
                reads.add(index)
            read_from = 1
        for token in operands[read_from:]:
            reads.update(registers(token))
            index = _index_register(INDIRECT_REGISTER_RE.fullmatch(token))
            if index:
                reads.add(index)
                reads_indirectly = True
            index = _index_register(INDIRECT_DEVICE_RE.fullmatch(token))
            if index:
                reads.add(index)
    if reads_indirectly:
        return ()
    return tuple(write for write in writes if write.register not in reads)
