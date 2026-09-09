"""Registers a boot path reads before anything on that path has written them.

Registers survive a reflash and a power loss, so at line 0 every one of them
holds whatever the previous occupant of the housing left there. The repository's
rule is that a program explicitly initializes any persistent register whose
starting value matters, and the boot clear and the reflash guard are how a
program meets that rule for its *stack* -- nothing checked the register half
until issue #168. A program whose loop compares, indexes, or branches on a
register that no boot path wrote is carrying a value from whatever ran before,
and a same-image reflash makes that look correct, because the previous run left
the register sensible. Only a fresh or foreign housing shows the read for what
it is.

The question is asked per register as a path question: is there a path from the
entry on which the register is read before any instruction on that path writes
it? Once a path writes the register nothing further along it can be its first
read, so the walk stops there, and every read it met before is a finding.

Most such paths are not feasible, and the walk reads enough of the program to
say so. A state machine seeds its state register at boot (`move r14 0`) and
dispatches on it at the loop head (`beqz r14 New`), so on the entry path every
other state's block is unreachable, and the registers those blocks read were
written by the block the entry path *does* take before the state moved on. The
walk carries what a path has put in its registers -- a literal through `move`,
`add`, `sub`, `select`, and `clamp`, and the interval a passed branch leaves
behind, so `blez r0 Bad` makes `r0` positive on the way past -- and takes only
the edge a decidable branch permits. It carries the same for the program's own
stack cells: a boot `clr db` zeroes them all, a literal `poke` sets one, and a
`get` from a cell the path has written that way is as good as a literal, which
is how a state kept in `S20` prunes exactly as one kept in a register does. A
cell counts as the program's own only when no wired peer's contract writes it
(`private_cells`, from `peer_written_cells`); anything a peer may post is
unknown on every read, since the write could land at any tick boundary.

Everything the walk cannot evaluate is unknown, an unknown branch keeps both
edges, and a value the game may have made NaN is remembered as one, so the paths
explored are a superset of the feasible ones: losing precision costs a finding
to review, never one missed. Two limits keep the set finite. A bound is dropped
beyond `VALUE_CAP`, which a counter compared against a peer-published limit
would otherwise climb past forever, and once one instruction has been reached
under `ENVIRONMENT_CAP` distinct environments any further arrival is walked
knowing nothing.

An `rrN` operand reads or writes the register `rN` names. When the walk knows
`rN` it reads or writes that register; a read through an index it does not know
could be of any register and counts as a read of all of them; a write through
one it does not know is not credited to any register, so a read behind it is
still reported.

The reflash guard's same-image edge is the one place a carried register is by
design: `beq r0 MAGIC Header` skips the clear only over a stack this exact
contract published, and the registers beside that stack are the ones the
previous image left, which the program may rely on when its resume logic
re-validates them (the Path Enumerator's cursors behind its `S11` key). So a
read that is unwritten only on paths through that edge is reported as a
`same-image` carry, separately from a read unwritten on the fresh-housing path
-- the clear edge of a guard, or the entry of a program with no guard at all --
which is the defect the rule exists to catch.

What the edge proves is the contract, not the program. Identity is
`HASH("<Contract>.v<ABI>")`, and a contract is published by every program that
implements it: seven identities on the tree are published by two or more
programs, ten directory adapters and fifteen catalog loaders among them. For the
header cells that changes nothing -- two programs publishing one contract agree
on the header by definition. A carried register or a private state cell is read
as "what this program left", and when a housing is reflashed from one program to
its twin, the twin left it, with the twin's meaning. So a carry is admissible
under a shared identity only when every program publishing the identity agrees
on what it carries: `SHARED_IMAGE_CARRIES` declares that once per identity, and
`shared_identity_errors` holds every program behind the identity to it (issue
#175).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
import re
from typing import Any

from framework.ic10_source import Label, integer_value, parse_ic10
from framework.script_contracts.control_flow import (
    CallState,
    assigning_instructions,
    call_state_graph,
    call_state_successors,
    program_labels,
    writes_register,
)
from framework.script_contracts.parsing import collect_aliases, resolve_literal
from framework.script_contracts.publication import same_image_edge

STACK_CELLS = 512
# The largest bound a path keeps on a register or cell. States, loop counters
# that count themselves out, and `rrN` indexes are all small; a counter bounded
# only by a peer's number climbs past this and loses the bound.
VALUE_CAP = 16
# Distinct environments one instruction is walked under before every further
# arrival is walked knowing nothing.
ENVIRONMENT_CAP = 32
REGISTERS = tuple(f"r{number}" for number in range(16)) + ("sp", "ra")
FRESH = "fresh"
SAME_IMAGE = "same-image"
# Own-stack cells only the program writes, with what each holds, so a walk may
# read a boot-path literal back from them: a state kept in `S20` prunes exactly
# as one kept in a register does. A reviewed claim, held to the tree by
# `validation/validators/validate_register_seeding.py`: no wired peer's
# contract writes the cell and no network write pinned to the program's `S0`
# identity does.
PRIVATE_STATE_CELLS: dict[str, dict[int, str]] = {
    "ic10/power-jobs/power_job_prepare_v1_0.ic10": {20: "step of the prepare request; 0 at boot"},
    "ic10/power-jobs/power_job_finalize_v1_0.ic10": {20: "step of the finalize request; 0 at boot"},
    "ic10/power-grid/power_sink_flow_builder_v1_0.ic10": {20: "step of the flow request; 0 at boot"},
    "ic10/manufacturing/generic_print_runtime_v2_0.ic10": {20: "print job phase; 0 at boot"},
    "ic10/manufacturing/transform_candidate_readiness_v1_0.ic10": {20: "readiness phase; 0 at boot"},
    "ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10": {20: "feeder phase; 0 on a fresh housing"},
    "ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10": {20: "feeder phase; 0 on a fresh housing"},
    "ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10":
        {117: "generation of the loaded config; -1 at boot, so the first tick reloads"},
    "ic10/controller-pi/controller_pi_runtime_v1_1.ic10":
        {117: "generation of the loaded config; -1 at boot, so the first tick reloads"},
    "ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10":
        {117: "generation of the loaded config; cleared to 0 at boot, so the first tick reloads"},
    "ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10":
        {11: "SearchId of the search in progress; cleared to 0, which no request may carry"},
}

# Identities two or more programs publish, with the state every program behind
# the identity carries over its reflash guard's same-image edge: the registers
# the walk reports as carries and the private cells each declares, with what
# each holds. A housing reflashed between two programs publishing one identity
# takes the skip edge over the other program's registers and cells, so the
# programs must mean the same thing by them, and the declaration is where that
# agreement is reviewed. Held to the tree by `shared_identity_errors`: a carry
# outside the entry fails as a fresh read would, an entry for an identity one
# program publishes is stale, and so is a register no member carries.
SHARED_IMAGE_CARRIES: dict[str, dict[str, dict[Any, str]]] = {
    "StackerFeeder.v1": {
        "registers": {
            "r6": "RequestId of the request in progress, from S18; echoed at S8 when the buffer is"
                  " ready and at S9 when the export completes",
            "r9": "Quantity requested, from S17; the Stacker's Setting once the buffer holds it",
        },
        "cells": {20: "feeder phase; 0 on a fresh housing"},
    },
}

_INDIRECT_REGISTER = re.compile(r"^rr(\d+)$")
_INDIRECT_DEVICE = re.compile(r"^dr(\d+)$")
_AGAINST_ZERO = {
    "bltz": "blt", "blez": "ble", "bgtz": "bgt", "bgez": "bge", "beqz": "beq", "bnez": "bne",
}
_COMPARISONS = {"blt", "ble", "bgt", "bge", "beq", "bne"}
# Own-stack writes at an address the walk cannot name: the push family, a write
# to a device named by reference id (which could be this housing), a clear by
# reference id.
_OWN_STACK_UNKNOWN_WRITES = {"push", "putd", "clrd"}
_CLEARED = "clr"
_INDIRECT_FRESH = "rr"
Environment = dict[str, Any]
EnvironmentKey = tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class Range:
    """What a path knows a value to be: an interval, and whether it may be NaN."""

    low: float | None = None
    high: float | None = None
    low_open: bool = False
    high_open: bool = False
    nan: bool = True

    @property
    def exact(self) -> int | None:
        if self.nan or self.low is None or self.low != self.high or self.low_open or self.high_open:
            return None
        return int(self.low) if float(self.low).is_integer() else None

    @property
    def unknown(self) -> bool:
        """Nothing a branch could decide on: no bound either way."""
        return self.low is None and self.high is None


def exact(value: float) -> Range:
    return Range(value, value, False, False, False)


UNKNOWN = Range()


def _cap(value: Range) -> Range:
    low = None if value.low is not None and abs(value.low) > VALUE_CAP else value.low
    high = None if value.high is not None and abs(value.high) > VALUE_CAP else value.high
    return replace(value, low=low, low_open=value.low_open and low is not None,
                   high=high, high_open=value.high_open and high is not None)


def meet(first: Range, second: Range) -> Range | None:
    """What holds when both constraints do; None when nothing can."""
    if second.low is None or (first.low is not None and first.low > second.low):
        low, low_open = first.low, first.low_open
    elif first.low is None or second.low > first.low:
        low, low_open = second.low, second.low_open
    else:
        low, low_open = first.low, first.low_open or second.low_open
    if second.high is None or (first.high is not None and first.high < second.high):
        high, high_open = first.high, first.high_open
    elif first.high is None or second.high < first.high:
        high, high_open = second.high, second.high_open
    else:
        high, high_open = first.high, first.high_open or second.high_open
    nan = first.nan and second.nan
    if low is not None and high is not None and (low > high or (low == high and (low_open or high_open))):
        return None if not nan else Range(nan=True)
    return Range(low, high, low_open, high_open, nan)


def join(first: Range, second: Range) -> Range:
    if first.low is None or second.low is None:
        low, low_open = None, False
    elif first.low < second.low or (first.low == second.low and not first.low_open):
        low, low_open = first.low, first.low_open
    else:
        low, low_open = second.low, second.low_open
    if first.high is None or second.high is None:
        high, high_open = None, False
    elif first.high > second.high or (first.high == second.high and not first.high_open):
        high, high_open = first.high, first.high_open
    else:
        high, high_open = second.high, second.high_open
    return Range(low, high, low_open, high_open, first.nan or second.nan)


def join_environments(first: Environment, second: Environment) -> Environment:
    """What both environments agree on: the join of every value known to both.

    A set-valued entry is a may-fact -- something one of the paths did -- so
    it joins by union and survives from either side.
    """
    joined: Environment = {}
    for key, value in first.items():
        other = second.get(key)
        if isinstance(value, frozenset):
            joined[key] = value | other if isinstance(other, frozenset) else value
            continue
        if other is None:
            continue
        if isinstance(value, Range) and isinstance(other, Range):
            widened = _cap(join(value, other))
            if not widened.unknown:
                joined[key] = widened
        elif value == other:
            joined[key] = value
    for key, value in second.items():
        if isinstance(value, frozenset) and key not in joined:
            joined[key] = value
    return joined


def _always_below(first: Range, second: Range) -> bool:
    """Is every value of `first` strictly less than every value of `second`?"""
    return (first.high is not None and second.low is not None
            and (first.high < second.low
                 or (first.high == second.low and (first.high_open or second.low_open))))


def _always_at_most(first: Range, second: Range) -> bool:
    return first.high is not None and second.low is not None and first.high <= second.low


def decide(operator: str, left: Range, right: Range) -> bool | None:
    """Whether `left <operator> right` holds on every path, fails on every path, or neither.

    NaN compares false with everything, so a value that may be NaN never
    lets an ordering or equality hold on every path, and never lets `bne`
    fail on every path.
    """
    if operator == "blt":
        true, false = _always_below(left, right), _always_at_most(right, left)
    elif operator == "ble":
        true, false = _always_at_most(left, right), _always_below(right, left)
    elif operator == "bgt":
        true, false = _always_below(right, left), _always_at_most(left, right)
    elif operator == "bge":
        true, false = _always_at_most(right, left), _always_below(left, right)
    else:
        disjoint = _always_below(left, right) or _always_below(right, left)
        same = (left.exact is not None and left.exact == right.exact)
        true, false = (same, disjoint) if operator == "beq" else (disjoint, same)
    if left.nan or right.nan:
        if operator == "bne":
            false = False
        else:
            true = False
    if true:
        return True
    if false:
        return False
    return None


def refine(operator: str, value: Range, against: Range, holds: bool) -> Range | None:
    """What `value` is on the edge where `value <operator> against` holds or does not.

    Only an exact `against` narrows anything. On the edge where a comparison
    fails the value may be NaN, so that edge keeps the flag; on the edge where
    it holds, NaN is ruled out.
    """
    pivot = against.exact
    if pivot is None:
        return value
    if operator == "bne":
        operator, holds = "beq", not holds
    if holds:
        if operator == "beq":
            bound = exact(pivot)
        elif operator == "blt":
            bound = Range(None, pivot, False, True, False)
        elif operator == "ble":
            bound = Range(None, pivot, False, False, False)
        elif operator == "bgt":
            bound = Range(pivot, None, True, False, False)
        else:
            bound = Range(pivot, None, False, False, False)
    else:
        if operator == "beq":
            return value
        if operator == "blt":
            bound = Range(pivot, None, False, False, True)
        elif operator == "ble":
            bound = Range(pivot, None, True, False, True)
        elif operator == "bgt":
            bound = Range(None, pivot, False, False, True)
        else:
            bound = Range(None, pivot, False, True, True)
    return meet(value, bound)


@dataclass(frozen=True, slots=True)
class UnseededRead:
    """One register read on a boot path before that path has written it."""

    register: str
    edge: str
    line_number: int
    code_text: str
    reads: int


@dataclass(frozen=True, slots=True)
class ImageState:
    """What one program leaves for a same-image reflash to find: its identity, private cells, carries."""

    identity: str | None
    private_cells: frozenset[int]
    carries: frozenset[str]


def image_header(contract: dict[str, Any]) -> dict[str, Any] | None:
    """The `provides` entry for a program's literal `S0` header, or None when its contract has none."""
    return next((item for item in contract["contracts"]["provides"] if item["base"] == 0), None)


def image_identity(contract: dict[str, Any]) -> str | None:
    """The `<Contract>.v<ABI>` token a program's `S0` header publishes, from its contract.

    None for a program whose contract names no literal `S0` header: nothing
    shares an identity it does not publish, so such a program is outside the
    grouping (every deployable program publishes one today).
    """
    header = image_header(contract)
    if header is None or not header.get("contract"):
        return None
    return f"{header['contract']}.v{header['abi']}"


def shared_identity_errors(
    states: dict[str, ImageState],
    declared: dict[str, dict[str, dict[Any, str]]] = SHARED_IMAGE_CARRIES,
) -> tuple[dict[str, list[str]], list[str]]:
    """Group programs by identity and hold each shared group to its `SHARED_IMAGE_CARRIES` entry.

    Returns the members of every identity two or more programs publish, and the
    failures: a member carrying a register the entry does not name, a member
    whose private cells differ from the entry's, an entry for an identity fewer
    than two programs publish, and a declared register no member carries.
    """
    groups: dict[str, list[str]] = {}
    for path, state in sorted(states.items()):
        if state.identity is not None:
            groups.setdefault(state.identity, []).append(path)
    shared = {identity: members for identity, members in sorted(groups.items()) if len(members) > 1}
    errors: list[str] = []
    for identity in sorted(declared):
        if identity not in shared:
            count = len(groups.get(identity, ()))
            errors.append(f"stale shared-image declaration: {identity} is published by {count}"
                          f" program{'s' if count != 1 else ''}; remove the entry")
    for identity, members in shared.items():
        entry = declared.get(identity, {})
        registers = frozenset(entry.get("registers", {}))
        cells = frozenset(entry.get("cells", {}))
        carried: set[str] = set()
        for path in members:
            state = states[path]
            carried |= state.carries
            for register in sorted(state.carries - registers, key=lambda name: (len(name), name)):
                errors.append(f"{path}: carries {register} over the same-image edge of {identity}, which"
                              f" {len(members) - 1} other program{'s' if len(members) != 2 else ''} publish"
                              f"{'es' if len(members) == 2 else ''}; SHARED_IMAGE_CARRIES does not declare it")
            if state.private_cells != cells:
                errors.append(f"{path}: declares private cells {sorted(state.private_cells)} under {identity},"
                              f" whose shared-image declaration names {sorted(cells)}")
        for register in sorted(registers - carried, key=lambda name: (len(name), name)):
            errors.append(f"stale shared-image declaration: no program publishing {identity} carries"
                          f" {register}; remove it")
    return shared, errors


def peer_written_cells(
    contracts: dict[str, dict[str, Any]], wiring: dict[str, Any],
) -> dict[str, frozenset[int]]:
    """Per program (by source path): the own-stack cells some wired peer's contract writes.

    A program's port names its peer in `data/script_wiring.json` (`providers`),
    and the program's own contract lists the cells that port writes, literal and
    ranged. The union over every port pointed at a program is what its peers
    may post into it, plus the program's own declared `external_writable_ranges`
    (a mailbox a peer the wiring cannot see writes). A program with no wiring
    entry is treated as having every cell written by a peer, so nothing about
    its stack is assumed; a port with a dynamic write and no range does the
    same for its peer.
    """
    all_cells = frozenset(range(STACK_CELLS))
    by_source = {contract["source"]: contract for contract in contracts.values()}
    written: dict[str, set[int]] = {source: set() for source in by_source}
    declared = wiring.get("ports", {})
    for source, ports in declared.items():
        contract = by_source.get(source)
        if contract is None:
            continue
        by_name = {port["port"]: port for port in contract["device_ports"]}
        for name, peer in ports.items():
            port = by_name.get(name)
            if port is None or peer.get("kind") != "script":
                continue
            stack = port["stack"]
            cells = set(stack["literal_writes"])
            for item in stack["dynamic_write_ranges"]:
                cells |= set(range(item["start"], item["end"] + 1))
            if stack["dynamic_write"] and not stack["dynamic_write_ranges"]:
                cells = set(all_cells)
            for provider in peer.get("providers", ()):
                if provider in written:
                    written[provider] |= cells
    for source, contract in by_source.items():
        if source not in declared:
            written[source] = set(all_cells)
            continue
        for item in contract["own_stack"]["external_writable_ranges"]:
            written[source] |= set(range(item["start"], item["end"] + 1))
    return {source: frozenset(cells & all_cells) for source, cells in written.items()}


class BootPaths:
    """The paths from a program's entry, walked with what each has written."""

    def __init__(self, source: str, private_cells: frozenset[int] = frozenset()) -> None:
        parsed = parse_ic10(source)
        rows = [list(row.tokens) for row in parsed.rows]
        _ports, self.integers = collect_aliases(rows)
        register_aliases = {
            row[1]: row[2] for row in rows
            if len(row) == 3 and row[0] == "alias" and row[2] in REGISTERS
        }
        self.program: list[dict[str, Any]] = []
        self.line_numbers: list[int] = []
        for statement in parsed.statements:
            if isinstance(statement, Label):
                self.program.append({"label": statement.name, "row": []})
            elif statement.opcode in {"alias", "define"}:
                self.program.append({"label": None, "row": []})
            else:
                tokens = [register_aliases.get(token, token) for token in statement.tokens]
                self.program.append({"label": None, "row": tokens})
            self.line_numbers.append(statement.line.number)
        self.private_cells = private_cells
        self.labels = program_labels(self.program)
        self.assigning = assigning_instructions()
        self.states, self.complete = call_state_graph(self.program)
        magic = None
        for entry in self.program:
            row = entry["row"]
            if len(row) == 3 and row[0] == "poke" and row[1] == "0":
                magic = resolve_literal(row[2], self.integers)
                break
        self.guard = same_image_edge(self.program, self.integers, magic) if magic is not None else None
        self.clear_edge: tuple[CallState, CallState] | None = None
        self.skip_edge: tuple[CallState, CallState] | None = None
        if self.guard is not None:
            guard_state, skip_state = self.guard
            outgoing, _ = call_state_successors(self.program, self.labels, guard_state)
            others = [state for state in outgoing if state != skip_state]
            if len(others) == 1:
                self.skip_edge = (guard_state, skip_state)
                self.clear_edge = (guard_state, others[0])

    # -- operand roles -------------------------------------------------------

    def _writes_first(self, row: list[str]) -> bool:
        return len(row) > 1 and self.assigning.get(row[0], True)

    @staticmethod
    def _index_register(token: str) -> str | None:
        match = _INDIRECT_REGISTER.fullmatch(token)
        return f"r{int(match.group(1))}" if match else None

    def _named_register(self, index: str, env: Environment) -> str | None:
        value = env.get(index)
        named = value.exact if isinstance(value, Range) else None
        return f"r{named}" if named is not None and 0 <= named < 16 else None

    def _named_registers(self, index: str, env: Environment) -> set[str]:
        """The registers an `rrN` read through `index` can reach; `*` for any."""
        value = env.get(index)
        if isinstance(value, Range) and value.low is not None and value.high is not None:
            low = int(value.low) + (1 if value.low_open and float(value.low).is_integer() else 0)
            high = int(value.high) - (1 if value.high_open and float(value.high).is_integer() else 0)
            if 0 <= low and high < 16:
                return {f"r{number}" for number in range(low, high + 1)}
        if env.get(_INDIRECT_FRESH) == index:
            return set()
        return {"*"}

    def reads(self, row: list[str], env: Environment) -> set[str]:
        """Registers `row` reads under `env`; `*` stands for any register."""
        found: set[str] = set()
        if not row:
            return found
        start = 1
        if self._writes_first(row):
            start = 2
            index = self._index_register(row[1])
            if index:
                found.add(index)
        if row[0] in {"push", "pop", "peek"}:
            found.add("sp")
        for token in row[start:]:
            if token in REGISTERS:
                found.add(token)
                continue
            index = self._index_register(token)
            if index:
                found.add(index)
                found |= self._named_registers(index, env)
                continue
            device = _INDIRECT_DEVICE.fullmatch(token)
            if device:
                found.add(f"r{int(device.group(1))}")
        return found

    def writes(self, row: list[str], env: Environment) -> set[str]:
        """Registers `row` writes under `env`; an `rrN` whose index is unknown writes none."""
        found = {register for register in REGISTERS if writes_register(row, register)}
        if row[0] == "jal":
            found.add("ra")
        if self._writes_first(row):
            index = self._index_register(row[1])
            if index:
                named = self._named_register(index, env)
                if named:
                    found.add(named)
        return found

    # -- the environment -----------------------------------------------------

    def value(self, token: str, env: Environment) -> Range:
        literal = integer_value(token, self.integers)
        if literal is not None:
            return exact(literal)
        try:
            number = float(token)
        except ValueError:
            number = None
        if number is not None:
            return exact(number) if number == number else Range(nan=True)
        value = env.get(token)
        return value if isinstance(value, Range) else UNKNOWN

    def cell(self, address: int, env: Environment) -> Range:
        if address not in self.private_cells:
            return UNKNOWN
        if f"S{address}" in env:
            return env[f"S{address}"]
        return exact(0) if env.get(_CLEARED) else UNKNOWN

    @staticmethod
    def _forget_cells(env: Environment) -> None:
        for key in [key for key in env if key.startswith("S") or key == _CLEARED]:
            del env[key]

    @staticmethod
    def _set(env: Environment, key: str, value: Range) -> None:
        value = _cap(value)
        if value.unknown:
            env.pop(key, None)
        else:
            env[key] = value

    def step(self, row: list[str], env: Environment) -> Environment:
        """What the path knows after `row`, given what it knew before."""
        if not row:
            return env
        new = dict(env)
        op = row[0]
        new.pop(_INDIRECT_FRESH, None)
        if self._writes_first(row) and self._index_register(row[1]):
            index = self._index_register(row[1])
            named = self._named_register(index, new)
            if named:
                new.pop(named, None)
            else:
                for key in [key for key in new if key in REGISTERS and key != index]:
                    del new[key]
                # The next `rrN` read through this same, unchanged index reads
                # the register this write just wrote.
                new[_INDIRECT_FRESH] = index
            return new
        for register in REGISTERS:
            if writes_register(row, register) or (op == "jal" and register == "ra"):
                new.pop(register, None)
        if op == "clr" and len(row) == 2 and row[1] == "db":
            self._forget_cells(new)
            new[_CLEARED] = 1
        elif op in _OWN_STACK_UNKNOWN_WRITES or (op == "put" and len(row) >= 2 and row[1] == "db"):
            self._forget_cells(new)
        elif op == "poke" and len(row) == 3:
            address = integer_value(row[1], self.integers)
            if address is None:
                self._forget_cells(new)
            elif address in self.private_cells:
                # A cell keeps an explicit unknown: it overrides the zero a clear left.
                value = _cap(self.value(row[2], env))
                new[f"S{address}"] = UNKNOWN if value.unknown else value
        if len(row) >= 2 and row[1] in REGISTERS:
            destination = row[1]
            if op == "move" and len(row) == 3:
                self._set(new, destination, self.value(row[2], env))
            elif op in {"add", "sub"} and len(row) == 4:
                self._set(new, destination, self._sum(op, self.value(row[2], env), self.value(row[3], env)))
            elif op == "select" and len(row) == 5:
                chooser = self.value(row[2], env).exact
                if chooser is not None:
                    chosen = self.value(row[3] if chooser else row[4], env)
                else:
                    chosen = join(self.value(row[3], env), self.value(row[4], env))
                self._set(new, destination, chosen)
            elif op == "clamp" and len(row) == 5:
                low, high = self.value(row[3], env), self.value(row[4], env)
                if low.exact is not None and high.exact is not None:
                    self._set(new, destination, Range(low.exact, high.exact, False, False, True))
            elif op == "get" and len(row) == 4 and row[2] == "db":
                address = integer_value(row[3], self.integers)
                if address is not None:
                    self._set(new, destination, self.cell(address, env))
        return new

    @staticmethod
    def _sum(op: str, left: Range, right: Range) -> Range:
        if op == "sub":
            right = Range(None if right.high is None else -right.high,
                          None if right.low is None else -right.low,
                          right.high_open, right.low_open, right.nan)
        low = None if left.low is None or right.low is None else left.low + right.low
        high = None if left.high is None or right.high is None else left.high + right.high
        return Range(low, high, left.low_open or right.low_open,
                     left.high_open or right.high_open, left.nan or right.nan)

    def branch(self, row: list[str], env: Environment) -> list[tuple[bool, Environment]]:
        """The edges a conditional branch can take -- `(taken, environment on that edge)`."""
        op = row[0]
        operator = _AGAINST_ZERO.get(op, op)
        if operator not in _COMPARISONS or (row[-1] != "ra" and self.labels.get(row[-1]) is None):
            return [(True, env), (False, env)]
        if op in _AGAINST_ZERO:
            if len(row) != 3:
                return [(True, env), (False, env)]
            operands = (row[1], "0")
        else:
            if len(row) != 4:
                return [(True, env), (False, env)]
            operands = (row[1], row[2])
        left, right = self.value(operands[0], env), self.value(operands[1], env)
        verdict = decide(operator, left, right)
        edges = []
        for taken in (True, False):
            if verdict is not None and verdict != taken:
                continue
            refined = dict(env)
            feasible = True
            for token, other, mirrored in ((operands[0], right, False), (operands[1], left, True)):
                if token not in REGISTERS:
                    continue
                own = self.value(token, env)
                bound = refine(_mirror(operator) if mirrored else operator, own, other, taken)
                if bound is None:
                    feasible = False
                    break
                self._set(refined, token, bound)
            if feasible:
                edges.append((taken, refined))
        return edges

    # -- the walk ------------------------------------------------------------

    def walk(
        self, blocked: tuple[CallState, CallState] | None = None, tracked: bool = True,
        stop: Callable[[int, list[str], Environment], bool] | None = None,
        mark: Callable[[CallState, bool | None, Environment], Environment] | None = None,
        partition: Callable[[Environment], Any] | None = None,
    ) -> Iterator[tuple[int, list[str], Environment]]:
        """Every state a path from the entry reaches, with what that path knows there.

        Yields `(index, row, environment)` on arrival. `stop` ends the path at a
        state once it has been yielded; `mark` is applied to what a path knows
        on each edge it leaves a state by, with `taken` naming a branch's edge
        and None any other. `blocked` is one edge of the state graph no path may take,
        which is how the guard's two edges are told apart. An untracked walk
        knows nothing and decides nothing, so it is the cheap superset a
        tracked walk is only run to narrow.

        Past `ENVIRONMENT_CAP` arrivals at one instruction the walk widens, and
        `partition` keeps the widening from merging what the question turns on:
        arrivals are joined only with others in the same partition of their
        environment, so a distinction the caller names survives however many
        paths carry it.
        """
        if not self.program:
            return
        visited: set[tuple[CallState, EnvironmentKey]] = set()
        arrivals: dict[tuple[int, Any], set[EnvironmentKey]] = {}
        widened: dict[tuple[int, Any], Environment] = {}
        pending: list[tuple[CallState, EnvironmentKey]] = [((0, None), ())]
        while pending:
            state, env_key = pending.pop()
            if (state, env_key) in visited:
                continue
            visited.add((state, env_key))
            env: Environment = dict(env_key)
            index = state[0]
            row = self.program[index]["row"]
            yield index, row, env
            if stop is not None and stop(index, row, env):
                continue
            outgoing, _ = call_state_successors(self.program, self.labels, state)
            edges: list[tuple[CallState, bool | None, Environment]] = []
            after = self.step(row, env) if tracked else env
            target = (state[1] if row[-1] == "ra" else self.labels.get(row[-1])) if row else None
            if tracked and row and row[0].startswith("b") and len(outgoing) == 2 and target is not None:
                for taken, refined in self.branch(row, after):
                    wanted = target if taken else index + 1
                    edges.extend((next_state, taken, refined) for next_state in outgoing if next_state[0] == wanted)
            else:
                edges.extend((next_state, None, after) for next_state in outgoing)
            for next_state, taken, next_env in edges:
                if blocked is not None and state == blocked[0] and next_state == blocked[1]:
                    continue
                if mark is not None:
                    next_env = mark(state, taken, next_env)
                # Past the cap, everything arriving here is walked under the
                # join of all of it: what every path agreed on survives, and
                # the join only ever widens, so it settles.
                arrival = (next_state[0], partition(next_env) if partition is not None else None)
                seen = arrivals.setdefault(arrival, set())
                if arrival in widened:
                    next_env = join_environments(widened[arrival], next_env)
                    widened[arrival] = next_env
                key: EnvironmentKey = tuple(sorted(next_env.items()))
                if key not in seen:
                    seen.add(key)
                    if len(seen) > ENVIRONMENT_CAP and arrival not in widened:
                        joined = dict(seen.pop())
                        for other in seen:
                            joined = join_environments(joined, dict(other))
                        widened[arrival] = joined
                        key = tuple(sorted(joined.items()))
                pending.append((next_state, key))

    def unwritten_reads(
        self, register: str, blocked: tuple[CallState, CallState] | None, tracked: bool = True,
    ) -> set[int]:
        """Indices where `register` is read on a path from the entry that never wrote it.

        Once a path writes the register nothing further along it can be its
        first read, so the path ends there.
        """
        found: set[int] = set()
        for index, row, env in self.walk(
            blocked, tracked, stop=lambda _index, row, env: bool(row) and register in self.writes(row, env),
        ):
            if row:
                reads = self.reads(row, env)
                if register in reads or "*" in reads:
                    found.add(index)
        return found

    def findings(self) -> list[UnseededRead]:
        """Every register read before written: on the fresh path, or only on the same-image edge."""
        results: list[UnseededRead] = []
        for register in REGISTERS:
            # Nothing found knowing nothing means nothing to find knowing more.
            if not self.unwritten_reads(register, None, tracked=False):
                continue
            fresh = self.unwritten_reads(register, self.skip_edge)
            carried: set[int] = set()
            if self.clear_edge is not None:
                carried = self.unwritten_reads(register, self.clear_edge) - fresh
            for edge, indices in ((FRESH, fresh), (SAME_IMAGE, carried)):
                if not indices:
                    continue
                first = min(indices)
                results.append(UnseededRead(
                    register, edge, self.line_numbers[first],
                    " ".join(self.program[first]["row"]), len(indices),
                ))
        return results


def _mirror(operator: str) -> str:
    return {"blt": "bgt", "ble": "bge", "bgt": "blt", "bge": "ble"}.get(operator, operator)


def unseeded_reads(source: str, private_cells: frozenset[int] = frozenset()) -> list[UnseededRead]:
    """The registers `source` reads on some boot path before that path writes them."""
    return BootPaths(source, private_cells).findings()
