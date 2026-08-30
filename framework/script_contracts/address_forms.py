"""Reduce a computed stack address to an affine form and read off its base cell.

A dynamic `get`/`poke`/`put` names its address in a register, so a declared
range is the only record of which cells it reaches -- and a declaration nothing
re-derives can drift away from the source silently. Each dynamic access is
reduced here to `constant + sum(coefficient * unknown)`, where every loop
induction variable enclosing the access contributes one unknown and the
constant is therefore the address on the first iteration of every such loop.

When an access's address is a constant plus induction terms alone, that
constant is the *base*: the one cell the access reaches whenever it runs at
all, whatever the trip counts turn out to be. A declared range that omits the
base cannot be describing that access, which is what makes the base checkable
without a trip-count proof. Addresses that also depend on a value read at
runtime (a bank index, a peer-published record pointer) have no such witness
and are left alone.

The seed of each register is the nearest earlier write, found by a linear
backward scan rather than a dominance proof: the strict proof in
`dynamic_ranges` needs a fully modeled control-flow graph, and a program with a
`jal` in it has none -- which would exempt exactly the programs whose record
loops sit behind a subroutine. A seed that a forward jump can skip therefore
yields a base the access need not reach, so a spurious report here names the
instruction it derived and the range it wanted, and is answered by reading the
source rather than by widening the range.
"""
from __future__ import annotations

from framework.script_contracts.control_flow import writes_register
from framework.script_contracts.parsing import parse_program, resolve_integer, resolve_port

MAX_DEPTH = 20


class AffineForm(dict):
    """`{"": constant, "<unknown>": coefficient}` -- the empty key is the constant."""

    @property
    def constant(self) -> int:
        return self.get("", 0)

    @property
    def unknowns(self) -> set[str]:
        return {key for key in self if key}

    @property
    def induction_only(self) -> bool:
        """True when every unknown is a loop counter, so the constant is a real address."""
        return all(key.startswith("n<") for key in self.unknowns)

    def added(self, other: "AffineForm") -> "AffineForm":
        combined = AffineForm(self)
        for key, coefficient in other.items():
            combined[key] = combined.get(key, 0) + coefficient
        return AffineForm({key: value for key, value in combined.items() if value or not key})

    def scaled(self, factor: int) -> "AffineForm":
        return AffineForm({key: value * factor for key, value in self.items()})


def _constant(value: int) -> AffineForm:
    return AffineForm({"": value})


def _unknown(name: str) -> AffineForm:
    return AffineForm({"": 0, name: 1})


def back_edges(program: list[dict]) -> list[tuple[int, int]]:
    """Loop regions [target, source] for every branch or jump that goes backwards."""
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    regions = []
    for index, entry in enumerate(program):
        row = entry["row"]
        if not row or not (row[0] == "j" or row[0].startswith("b")):
            continue
        target = labels.get(row[-1])
        if target is not None and target <= index:
            regions.append((target, index))
    return regions


def induction_variables(program: list[dict], access: int) -> tuple[dict[str, int], dict[str, set[int]]]:
    """Registers carried across a loop enclosing `access`, with their step and update sites.

    A register is loop-carried only when every write to it inside the loop
    advances it by a positive literal: anything else -- a `mul` that rebuilds
    the address from a counter, say -- means the value does not survive the
    back edge and the seed scan already sees it.
    """
    enclosing = [region for region in back_edges(program) if region[0] <= access <= region[1]]
    registers = ("sp", "ra", *(f"r{number}" for number in range(16)))
    steps: dict[str, int] = {}
    sites: dict[str, set[int]] = {}
    for start, end in enclosing:
        written: dict[str, list[tuple[int, list[str]]]] = {}
        for index in range(start, end + 1):
            row = program[index]["row"]
            for register in registers:
                if row and writes_register(row, register):
                    written.setdefault(register, []).append((index, row))
        for register, updates in written.items():
            if all(
                row[0] == "add" and len(row) >= 4 and row[1] == row[2]
                and row[3].lstrip("-").isdigit() and int(row[3]) > 0
                for _, row in updates
            ):
                steps[register] = max(steps.get(register, 0), max(int(row[3]) for _, row in updates))
                sites.setdefault(register, set()).update(index for index, _ in updates)
    return steps, sites


def address_form(
    program: list[dict], index: int, token: str, integer_aliases: dict[str, int],
    steps: dict[str, int], sites: dict[str, set[int]], memo: dict | None = None, depth: int = 0,
) -> AffineForm:
    """The affine value of `token` as seen just before program[index]."""
    literal = resolve_integer(token, integer_aliases)
    if literal is not None:
        return _constant(literal)
    if depth > MAX_DEPTH:
        return _unknown(f"?{token}@{index}")
    memo = {} if memo is None else memo
    key = (index, token)
    if key in memo:
        return memo[key]
    memo[key] = _unknown(f"?{token}@{index}")

    def operand(at: int, name: str) -> AffineForm:
        return address_form(program, at, name, integer_aliases, steps, sites, memo, depth + 1)

    form = None
    for back in range(index - 1, -1, -1):
        row = program[back]["row"]
        if not row or not writes_register(row, token):
            continue
        if back in sites.get(token, set()):
            continue  # the induction term is added once, below, after the seed is found
        if row[0] == "move" and len(row) >= 3:
            form = operand(back, row[2])
        elif row[0] in {"add", "sub"} and len(row) >= 4:
            left, right = operand(back, row[2]), operand(back, row[3])
            form = left.added(right if row[0] == "add" else right.scaled(-1))
        elif row[0] == "mul" and len(row) >= 4:
            left, right = operand(back, row[2]), operand(back, row[3])
            if not left.unknowns:
                form = right.scaled(left.constant)
            elif not right.unknowns:
                form = left.scaled(right.constant)
        break
    if form is None:
        form = _unknown(f"?{token}@{index}")
    counter = f"n<{token}>"
    if token in steps and counter not in form:
        form = form.added(_unknown(counter).scaled(steps[token]))
    memo[key] = form
    return form


def dynamic_access_bases(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int],
) -> list[tuple[str, str, int, str]]:
    """`(target, direction, base, instruction)` for every base-bearing dynamic access.

    `target` is a device port name or `db` for the program's own housing stack.
    Accesses whose address depends on a runtime-read value are omitted: they
    have no first-iteration witness to check a declared range against.
    """
    program = parse_program(source)
    found = []
    for index, entry in enumerate(program):
        row = entry["row"]
        if not row:
            continue
        if row[0] == "get" and len(row) >= 4:
            target, direction, token = resolve_port(row[2], aliases), "read", row[3]
            if row[2] == "db":
                target = "db"
        elif row[0] == "put" and len(row) >= 4:
            target, direction, token = resolve_port(row[1], aliases), "write", row[2]
            if row[1] == "db":
                target = "db"
        elif row[0] == "poke" and len(row) >= 3:
            target, direction, token = "db", "write", row[1]
        else:
            continue
        if target is None or resolve_integer(token, integer_aliases) is not None:
            continue
        steps, sites = induction_variables(program, index)
        form = address_form(program, index, token, integer_aliases, steps, sites)
        if form.induction_only and 0 <= form.constant <= 511:
            found.append((target, direction, form.constant, " ".join(row)))
    return found


def declared_base_errors(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int],
    declared: dict[tuple[str, str], list[dict[str, int]]],
) -> list[str]:
    """Report every dynamic access whose base cell no declared range covers."""
    errors = []
    for target, direction, base, instruction in dynamic_access_bases(source, aliases, integer_aliases):
        ranges = declared.get((target, direction))
        if ranges is None:
            continue
        if not any(item["start"] <= base <= item["end"] for item in ranges):
            shown = [[item["start"], item["end"]] for item in ranges]
            errors.append(
                f"{target} {direction} range {shown} omits S{base}, the address "
                f"`{instruction}` computes on its first pass"
            )
    return errors
