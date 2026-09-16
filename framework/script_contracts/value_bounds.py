"""Bound the cells a computed stack address reaches, so a loop's far end is checked.

A dynamic `get`/`put`/`poke` names its address in a register, so a declared range
is the only record of which cells it touches -- and a declaration nothing
re-derives drifts away from the source silently. What a record loop reaches is
not in the source as a literal, though: its trip count is a count somebody else
publishes.

The branches carry the number, two ways. A branch that gates an access
constrains what the registers reaching it hold, so `blt r3 0 Bad` then
`bgt r3 8 Bad` accepts a count of eight however the peer fills it in. A branch
that decides whether a loop runs again bounds its trip count directly, whether
it is written at the top against the counter (`bge r4 r3 Stable`) or at the
bottom against a different one (`ble r4 23 CopyIn`, which is what pins an
address register advanced beside it). Between them the whole `S32..S95` plan
window falls out of a validator that only ever names `8` and `32`.

Two things follow from reading a branch as the bound. The derived set is what
the program *permits*, not what one execution performs -- a declared range has
to cover every cell a legal peer can steer the loop to, which is the surface a
declaration exists to state. And it is a floor first: a declared range must
contain it, so a branch this module cannot read costs a check rather than
inventing one, and where a loop's count is never validated locally only the cell
the first pass reaches is witnessed.

Every derivation also carries whether it is the whole set and not just some of
it, which is the second thing a declaration can be held to -- equality rather
than containment, so a surface nobody declared can publish the derivation as its
range. That answer is lost by any step that leaves a value out: a write nothing
evaluates, a register arriving from a reflash instead of a write, a loop nothing
counts out, advances a branch chooses between, an advance the access can be
reached without, an enclosing loop that moves the register further, or a guard
read off a limit never shown whole. Losing it costs precision and never
soundness, so every one of those is answered no when in doubt.

Which write is in a register is a reaching-definition question and not the
nearest earlier one: a register holds what the last write on the path that got
here left in it, and `arriving` joins every write that can. Reading a branch as
a gate or an exit needs the control-flow graph to be the whole graph besides, so
a transfer nobody can follow stands the bounds down and leaves the program its
first pass alone. Calls are not such a transfer: one walk follows them, which is
what lets a subroutine's own guard be read against an access inside it -- and the
guard is usually the whole bound, because a record loop is exactly the thing a
program writes as a subroutine. Every question here is asked of the call states
themselves and never of their projection onto indices: projected, a return lands
on every caller's fallthrough, so a guard one caller placed before its call
looked bypassed by the path stitched through the other caller. Dominance is
asked of indices over those states -- every path to the access passes *some*
state at the guard -- which is what a guard needs, since either caller's copy of
it tests the register.

The set itself is held to a stricter standard than the flag beside it, because a
declared range is rejected for omitting any cell in it: a value in the set has
to be one the program can really compute, not one an approximation let in. Two
readings would let one in. An equality test that sends a register elsewhere at
one value rules that value out on the edge it guards, so `beqz r8 Back` before
`sub r8 r8 1` never steps down from zero. And an advance inside a loop, read
from outside the loop, is not one step past the seed but the seed plus however
many passes ran before control left. What the loop leaves behind is counted
from the exits that reach the reader: a match that leaves mid-scan can fire on
any pass, so the counter is the seed plus any number of strides up to the trip
count, while the loop's own exit test fires on exactly one pass and leaves
exactly one value. A loop nothing counts out, or one that carries the register
through an advance some pass skips, still witnesses nothing from out there,
rather than witnessing a cell the loop never leaves its address on.

A seed is only as good as the arithmetic between it and the access, and that
arithmetic is enumerated rather than approximated. A cell this module derives is
a cell a declaration is held to, so widening a sum to the interval between its
ends would claim the gaps between two sparse operands and fail a declaration
that was right. Enumerating stays exact, and reaches far enough because the
values that matter are small: a set-instruction answers one of two things, and a
`select` holds one arm or the other. Those are what carry the bank index a
service multiplies its published record width by, so without them the programs
that bound themselves most explicitly -- the generic hosts, which read a width
from a peer and guard it -- derive nothing at all.

Where a value does not enumerate, its interval still can, and an interval is
only ever a bound here and never a witness set, so widening it claims no cell.
A count checked from above alone has a ceiling and no floor, and the ceiling
carries through a `move`, an `add`, a `sub`, or a `mul` by a literal to the
limit a loop is counted against, where the ceiling is all a trip count needs. A
`clamp` between two literals is its bounds whatever it clamped, and a `mod` by a
divisor held above zero is `[0, divisor - 1]` whatever it divided, the game's
`mod` being a true modulo.

A loop is everywhere its pass runs and not the text between its header and its
last latch: a scan that calls a subroutine standing after that latch runs it
every pass, so an access inside the subroutine is advanced by the scan. One
advance site shared by every loop around an access, or one a pass may run
twice, moves the register by one amount however the loops interleave, so a
trusted ceiling at the access counts it out exactly wherever some loop around
it is counted by nothing else -- and a loop whose own test stops it short of
the ceiling keeps the closure from it, since the upper values may never run.

A register is read once per state of the access, and every guard, header, and
limit it asks about is placed against that state: a state of the asked index
counts when the access is reachable from it without passing the index again,
which is the visit the access's own execution last made. A copy loop a program
calls from three sites is three loops here, each with the seed and the limit its
own caller computed, because the other callers' copies of the exit test cannot
reach this caller's access without re-passing the test. Read merged, the
smallest seed would pair with the largest limit and the copy would appear to
reach cells no call writes -- and since a declaration is held to every cell
derived, that reading could never be published whole. The return address alone
does not tell the visits apart, since it persists past the return: the first
pass of a loop whose body calls a subroutine runs the guards before the call
with no return address and the later passes with one, and a reader after the
call is gated by both. Where no state of an index can reach the access, every
state there answers, which is the merged reading.
"""
from __future__ import annotations

from typing import Iterable

from framework.script_contracts.control_flow import CallState, call_state_graph, writes_register
from framework.script_contracts.parsing import (
    RegisterPorts,
    parse_program,
    resolve_integer,
    resolve_ports,
)

STACK_CELLS = 512
MAX_DEPTH = 12

# `b<op> a b Label` constrains `a` against `b` differently on each outgoing edge:
# (low delta, high delta) against `b`, where None leaves that side open.
FALLTHROUGH = {"blt": (0, None), "ble": (1, None), "bgt": (None, 0), "bge": (None, -1)}
TAKEN = {"blt": (None, -1), "ble": (None, 0), "bgt": (1, None), "bge": (0, None)}
AGAINST_ZERO = {"bltz": "blt", "blez": "ble", "bgtz": "bgt", "bgez": "bge"}
# The highest counter value whose pass still runs the body, as an offset from
# the compared limit -- for a test that continues into the loop when it holds,
# and for one that leaves the loop when it holds.
LAST_PASS_CONTINUING = {"ble": 0, "blt": -1}
LAST_PASS_EXITING = {"bgt": 0, "bge": -1}
UNBOUNDED: tuple[int | None, int | None] = (None, None)
# `beq a b Label` holds `a == b` on its taken edge and `a != b` on the fallthrough;
# `bne` the other way round. Either only ever takes values away from a set.
EQUAL_WHEN_TAKEN = {"beq": True, "bne": False}
EQUALITY_AGAINST_ZERO = {"beqz": "beq", "bnez": "bne"}
# What one derivation knows about a token: the values it witnessed, and whether
# those are all of them. A set nothing witnessed is None, and is never whole.
Derived = tuple["set[int] | None", bool]
OPEN: Derived = (None, False)
# A set-instruction answers a comparison, so it holds one of two values whatever
# it compared and however little is known about the operands. `sgn` is
# deliberately absent: its three answers include -1.
BOOLEAN_RESULTS = {
    "sap", "sapz", "sdns", "sdse", "seq", "seqz", "sge", "sgez", "sgt", "sgtz",
    "sle", "slez", "slt", "sltz", "sna", "snan", "snanz", "snaz", "sne", "snez",
}
# Instructions whose result is what a cell, a device, or the stack holds rather
# than anything computed from their operands: a load through a derived address
# reads data, and the data is not the pass number.
LOADS = {
    "get", "getd", "l", "lb", "lbn", "lbns", "lbs", "ld", "lr", "ls", "peek", "pop", "rand", "rmap",
}
# Operand pairs one arithmetic step may enumerate. Each operand is already
# capped at `STACK_CELLS` values, so this only bounds the work of combining
# them; a whole-stack window built from a bank base and a record counter is the
# widest legitimate combination and needs about 37k.
PAIR_BUDGET = 1 << 16


def back_edges(program: list[dict]) -> dict[int, tuple[int, ...]]:
    """Every backward branch or jump, as the latches returning to each loop header.

    Two back edges to one label are two ways around one loop and not two loops.
    A record scan that restarts from each of three rejections has three, and
    counting them separately would read one register the scan advances as
    advanced by three enclosing loops at once.
    """
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    latches: dict[int, list[int]] = {}
    for index, entry in enumerate(program):
        row = entry["row"]
        if not row or not (row[0] == "j" or row[0].startswith("b")):
            continue
        target = labels.get(row[-1])
        if target is not None and target <= index:
            latches.setdefault(target, []).append(index)
    return {header: tuple(found) for header, found in sorted(latches.items())}


def advance_amount(row: list[str]) -> int | None:
    """How far one row moves its own register, when that is all it does to it."""
    if (row[0] == "add" and len(row) >= 4 and row[1] == row[2]
            and row[3].lstrip("-").isdigit() and int(row[3]) > 0):
        return int(row[3])
    return None


def region_induction(
    program: list[dict], nodes: set[int], advancing: set[int],
) -> dict[str, list[tuple[int, int]]]:
    """Registers one loop carries, each as the `(index, amount)` of every advance.

    A register is loop-carried only when every write to it inside the loop
    advances it by a positive literal: anything else -- a `mul` that rebuilds
    the address from a counter, say -- means the value does not survive the
    back edge and the seed scan already sees it. A register advanced more than
    once per pass keeps every advance, because how far it moves in a pass is
    their sum and where it stands at an access is the sum of those before it.

    An advance the pass does not make is not one it carries. The span between a
    header and its latch is not the pass: a record scan that restarts from a
    rejection puts its latch above the block it runs once it *succeeds*, and the
    counter that block advances belongs to the loop around the scan, not to the
    scan. So the writes are looked for wherever the loop runs, and the advances
    counted only where a pass really reaches them.
    """
    registers = ("sp", "ra", *(f"r{number}" for number in range(16)))
    written: dict[str, list[tuple[int, list[str]]]] = {}
    for index in sorted(nodes | advancing):
        row = program[index]["row"]
        for register in registers:
            if row and writes_register(row, register):
                written.setdefault(register, []).append((index, row))
    carried = {
        register: [(index, advance_amount(row)) for index, row in updates if index in advancing]
        for register, updates in written.items()
        if all(advance_amount(row) is not None for _, row in updates)
    }
    return {register: updates for register, updates in carried.items() if updates}


def dynamic_accesses(
    program: list[dict], aliases: dict[str, str], integer_aliases: dict[str, int],
    register_ports: RegisterPorts | None = None,
) -> list[tuple[int, str, str, str, list[str]]]:
    """`(index, target, direction, address token, row)` for every computed access.

    `target` is a device port name or `db` for the program's own housing stack;
    an access through an unresolvable port token is not one this analysis can
    attribute to anything, so it is left out. A register-indexed port yields one
    entry per pin its register can name.
    """
    found = []
    for index, entry in enumerate(program):
        row = entry["row"]
        if not row:
            continue
        if row[0] == "get" and len(row) >= 4:
            targets, direction, token = resolve_ports(row[2], aliases, register_ports), "read", row[3]
            if row[2] == "db":
                targets = ("db",)
        elif row[0] == "put" and len(row) >= 4:
            targets, direction, token = resolve_ports(row[1], aliases, register_ports), "write", row[2]
            if row[1] == "db":
                targets = ("db",)
        elif row[0] == "poke" and len(row) >= 3:
            targets, direction, token = ("db",), "write", row[1]
        else:
            continue
        if resolve_integer(token, integer_aliases) is not None:
            continue
        for target in targets:
            found.append((index, target, direction, token, row))
    return found


def meet(first: tuple[int | None, int | None], second: tuple[int | None, int | None]):
    """The tighter of two intervals -- what holds when both constraints apply."""
    low = first[0] if second[0] is None else (second[0] if first[0] is None else max(first[0], second[0]))
    high = first[1] if second[1] is None else (second[1] if first[1] is None else min(first[1], second[1]))
    return (low, high)


def join(first: tuple[int | None, int | None], second: tuple[int | None, int | None]):
    """The looser of two intervals -- what holds when either constraint may apply."""
    low = None if first[0] is None or second[0] is None else min(first[0], second[0])
    high = None if first[1] is None or second[1] is None else max(first[1], second[1])
    return (low, high)


def context_order(ra: int | None) -> int:
    """A sort key for return addresses, with the no-call context first."""
    return -1 if ra is None else ra


def state_order(state: CallState | None) -> tuple[int, int]:
    """A sort key for call states, so a walk over them is deterministic; `None` (no write) sorts first."""
    if state is None:
        return (-1, -1)
    return (state[0], context_order(state[1]))


class ValueBounds:
    """What one program's branches permit its registers and dynamic addresses to hold."""

    def __init__(self, source: str, integer_aliases: dict[str, int]) -> None:
        self.program = parse_program(source)
        self.integer_aliases = integer_aliases
        self.states, self.complete = call_state_graph(self.program)
        self.labels = {entry["label"]: index for index, entry in enumerate(self.program) if entry["label"]}
        self.regions = back_edges(self.program)
        self._by_index: dict[int, list[CallState]] = {}
        for state in self.states:
            self._by_index.setdefault(state[0], []).append(state)
        self._state_predecessors: dict[CallState, set[CallState]] = {}
        for state, outgoing in self.states.items():
            for target in outgoing:
                self._state_predecessors.setdefault(target, set()).add(state)
        self._forward: dict[tuple[int, int], set[int]] = {}
        self._backward: dict[tuple[int, int], set[int]] = {}
        self.dominators = self.index_dominators()
        self._sites: dict[int, dict[str, set[int]]] = {}
        self._carried: dict[int, dict[str, list[tuple[int, int]]]] = {}
        self._pass_nodes: dict[int, set[int]] = {}
        self._span: dict[int, set[int]] = {}
        self._members: dict[int, set[int]] = {}
        self._written: dict[tuple[int, frozenset[CallState], str], tuple] = {}
        self._last_visits: dict[tuple[int, frozenset[CallState]], list[CallState]] = {}
        self._derived: dict[int, dict[int, set[str]]] = {}
        self._reaching: dict[tuple[str, frozenset[int]], dict[CallState, frozenset[CallState | None]]] = {}

    def states_at(self, index: int, focus: frozenset[CallState]) -> list[CallState]:
        """The states at `index` a reader in `focus` last passed through, or every state there when none.

        A reader asking about a guard, a header, or a limit wants the visit to
        that index that its own execution last made, and a state at the index
        is that visit when some focus state is reachable from it without
        passing the index again. Three copies of a loop a program calls from
        three sites are told apart this way: the other callers' copies of the
        exit test cannot reach this caller's access without re-passing the
        test. It is not the return address alone that tells them apart, because
        `ra` persists past the return: the first pass of a loop whose body calls
        a subroutine runs the guards before the call with no return address
        and the later passes run them with one, and a reader after the call is
        gated by both. Where no state at the index can reach the focus, every
        state there answers, which is the merged reading this refines.
        """
        states = self._by_index.get(index, [])
        key = (index, focus)
        if key not in self._last_visits:
            # One backward walk from the focus, stopping at the index: every
            # state of the index it steps onto is a last visit, and a focus
            # state standing at the index is its own.
            found = {state for state in focus if state[0] == index}
            seen: set[CallState] = set(found)
            pending = [state for state in focus if state[0] != index]
            while pending:
                state = pending.pop()
                if state in seen:
                    continue
                seen.add(state)
                for previous in self._state_predecessors.get(state, ()):
                    if previous[0] == index:
                        found.add(previous)
                    elif previous not in seen:
                        pending.append(previous)
            self._last_visits[key] = [state for state in states if state in found] or list(states)
        return self._last_visits[key]

    def sites(self, index: int) -> dict[str, set[int]]:
        """Every loop advance around `index`, by register -- the writes a seed scan skips."""
        if index not in self._sites:
            found: dict[str, set[int]] = {}
            for header in self.regions:
                if index in self.region_members(header):
                    for register, updates in self.region_carried(header).items():
                        found.setdefault(register, set()).update(place for place, _ in updates)
            self._sites[index] = found
        return self._sites[index]

    def walk(
        self, origins: Iterable[CallState], blocked: int, edges: dict[CallState, set[CallState]],
    ) -> set[int]:
        """Indices of the states `edges` lead to from `origins`, never entering index `blocked`.

        The walk is over states rather than their projection because a return
        goes back to the site that made the call. Projected, `j ra` leads to
        every caller's fallthrough, and a guard on one side of a shared
        subroutine looked bypassed by the path stitched through the other side.
        """
        seen: set[CallState] = set()
        pending = [state for state in origins if state[0] != blocked]
        while pending:
            state = pending.pop()
            if state in seen:
                continue
            seen.add(state)
            pending.extend(
                target for target in edges.get(state, ()) if target[0] != blocked and target not in seen
            )
        return {index for index, _ in seen}

    def forward(self, start: int, blocked: int) -> set[int]:
        """Indices reachable from `start` without re-entering `blocked`."""
        key = (start, blocked)
        if key not in self._forward:
            self._forward[key] = self.walk(self._by_index.get(start, ()), blocked, self.states)
        return self._forward[key]

    def backward(self, target: int, blocked: int) -> set[int]:
        """Indices that can reach `target` without passing through `blocked`."""
        key = (target, blocked)
        if key not in self._backward:
            self._backward[key] = self.walk(
                self._by_index.get(target, ()), blocked, self._state_predecessors
            )
        return self._backward[key]

    def index_dominators(self) -> dict[int, set[int]]:
        """Which indices every execution reaching an index has already passed through.

        Dominance is asked of indices over the state graph: `d` dominates `a`
        when no state at `a` can be reached from the entry without passing some
        state at `d`. That is weaker than one state dominating another -- two
        callers may each pass their own copy of a guard -- and exactly what a
        guard needs, since either copy tests the register. Asking it of the
        projection instead would join each caller's entry to every caller's
        return, and a guard one caller placed before its call would look
        bypassed by the path stitched through the other.
        """
        # One must-pass dataflow over the states, with the index sets as bit
        # masks: what every path to a state has passed is that state's own
        # index and whatever every predecessor's path had passed. Asking one
        # walk per index instead costs the whole graph again for each of them.
        entry: CallState = (0, None)
        passed = {state: -1 for state in self.states}
        if entry in passed:
            passed[entry] = 1
        changed = bool(passed)
        while changed:
            changed = False
            for state in self.states:
                if state == entry:
                    continue
                incoming = -1
                for parent in self._state_predecessors.get(state, ()):
                    incoming &= passed[parent]
                updated = incoming | (1 << state[0])
                if updated != passed[state]:
                    passed[state] = updated
                    changed = True
        dominators: dict[int, set[int]] = {}
        for index, states in self._by_index.items():
            mask = -1
            for state in states:
                mask &= passed[state]
            dominators[index] = {other for other in self._by_index if mask >> other & 1}
        return dominators

    def state_predecessors(self) -> dict[CallState, set[CallState]]:
        return self._state_predecessors

    def pass_nodes(self, header: int) -> set[int]:
        """What one pass runs: the header, and whatever gets back to a latch.

        A branch or jump backwards names a loop, but not which instructions the
        loop is made of, and the span between the two is the wrong answer. A
        record scan that restarts from a rejection puts its latch above the
        block it runs once it *succeeds*, so that block lies inside the span
        while no path from it reaches the latch except by entering the loop
        again -- and reading the span makes the success block's own counter look
        like something the scan advances.

        The walk is over the call states rather than their projection for the
        reason `arriving` is: merging call strings joins each caller's entry to
        every caller's return, and a pass stitched from two of them collects an
        advance from a second loop that shares the subroutine, which lands in
        this loop's stride as if one pass made both.
        """
        if header not in self._pass_nodes:
            latches = set(self.regions[header])
            reverse = self.state_predecessors()
            seen: set[CallState] = set()
            pending = [state for state in self.states if state[0] in latches]
            while pending:
                state = pending.pop()
                if state in seen or state[0] == header:
                    continue
                seen.add(state)
                pending.extend(reverse.get(state, set()) - seen)
            self._pass_nodes[header] = {header} | {index for index, _ in seen}
        return self._pass_nodes[header]

    def region_span(self, header: int) -> set[int]:
        """Everywhere the loop at `header` can run, over-counted as a plain span.

        The pass is the precise answer and this is not it: this is the wider net
        the disqualifying scan is cast over, because a write that resets a
        register the loop would otherwise carry has to be found wherever it
        stands, including on a path that leaves the loop rather than returning.
        """
        if header not in self._span:
            self._span[header] = set(range(header, max(self.regions[header]) + 1))
        return self._span[header]

    def region_members(self, header: int) -> set[int]:
        """Everywhere the loop at `header` runs: its span, and whatever its pass reaches beyond it.

        Membership -- is this access inside the loop, so that the loop's
        advances are folded onto its seed -- is a question about where the
        pass runs and not about the text. A scan that calls a subroutine
        standing after its last latch runs that subroutine every pass, and an
        access inside it is advanced by the scan exactly as one between the
        header and the latch is. The span alone would leave the subroutine's
        accesses outside, where the advance reads as an ordinary write that
        reaches itself round the back edge and evaluates to nothing. This is
        the same net the disqualifying write scan is cast over.
        """
        if header not in self._members:
            self._members[header] = self.region_span(header) | self.pass_nodes(header)
        return self._members[header]

    def every_latch(self, header: int, place: int) -> bool:
        """Does `place` stand on every way around the loop at `header`?"""
        return all(place in self.dominators.get(latch, ()) for latch in self.regions[header])

    def comparison(self, index: int) -> tuple[str, str, str, int] | None:
        """`(operator, register, compared token, branch target)` for an ordering test."""
        row = self.program[index]["row"]
        if not row:
            return None
        operator = AGAINST_ZERO.get(row[0], row[0])
        target = self.labels.get(row[-1])
        if operator not in FALLTHROUGH or target is None:
            return None
        if row[0] in AGAINST_ZERO:
            return (operator, row[1], "0", target) if len(row) >= 3 else None
        return (operator, row[1], row[2], target) if len(row) >= 4 else None

    def equality(self, index: int) -> tuple[str, int, int, bool] | None:
        """`(register, compared value, branch target, equal when taken)` for an equality test."""
        row = self.program[index]["row"]
        if not row:
            return None
        operator = EQUALITY_AGAINST_ZERO.get(row[0], row[0])
        target = self.labels.get(row[-1])
        if operator not in EQUAL_WHEN_TAKEN or target is None:
            return None
        if row[0] in EQUALITY_AGAINST_ZERO:
            operands = ((row[1], "0"),) if len(row) >= 3 else ()
        else:
            operands = ((row[1], row[2]), (row[2], row[1])) if len(row) >= 4 else ()
        for register, against in operands:
            value = resolve_integer(against, self.integer_aliases)
            if value is not None and resolve_integer(register, self.integer_aliases) is None:
                return register, value, target, EQUAL_WHEN_TAKEN[operator]
        return None

    def equality_constraints(self, access: int, register: str) -> tuple[set[int] | None, set[int]]:
        """What the equality tests gating `access` pin `register` to, and what they rule out.

        A test against a literal says one of two things on the edge every path
        to the access takes: the register is that value, or it is not. Neither
        adds a value, so the ordering bounds stay the ceiling; both take values
        away that an enumeration would otherwise witness, and a witness is a
        cell a declaration is held to. A counter that `beqz` sends elsewhere at
        zero does not step down from zero on the path it guards.
        """
        pinned: set[int] | None = None
        excluded: set[int] = set()
        if not self.complete:
            return pinned, excluded
        for index in self.dominators.get(access, ()):
            compared = self.equality(index)
            if compared is None or compared[0] != register:
                continue
            _, value, target, equal_when_taken = compared
            table, entered = self.gated_edge(access, index, target)
            if table is None or self.rewritten(entered, index, access, register):
                continue
            if (table is TAKEN) == equal_when_taken:
                pinned = {value} if pinned is None else pinned & {value}
            else:
                excluded.add(value)
        return pinned, excluded

    def guard_interval(self, access: int, register: str, sites, depth: int, seen, focus) -> tuple:
        """The interval every branch that gates `access` permits `register` to hold.

        The third answer is whether those ends can be trusted not to cut a value
        the register really reaches. A limit read from a token whose own values
        were never shown whole may be smaller than the real one, and a bound that
        is too tight bounds nothing. The compared side is read at the visits to
        the guard the access's own states last made, so a limit one caller
        computed gates that caller's copy alone.
        """
        interval = UNBOUNDED
        trusted = True
        if not self.complete:
            return (*interval, trusted)
        for index in self.dominators.get(access, ()):
            compared = self.comparison(index)
            if compared is None or compared[1] != register:
                continue
            operator, _register, against, target = compared
            table, entered = self.gated_edge(access, index, target)
            if table is None or self.rewritten(entered, index, access, register):
                continue
            other_low, other_high, other_trusted = self.interval_of(
                index, against, sites, depth + 1, seen, focus
            )
            low_delta, high_delta = table[operator]
            low = None if low_delta is None or other_low is None else other_low + low_delta
            high = None if high_delta is None or other_high is None else other_high + high_delta
            if low is None and high is None:
                continue
            trusted = trusted and other_trusted
            interval = meet(interval, (low, high))
        return (*interval, trusted)

    def gated_edge(self, access: int, index: int, target: int):
        """Which outgoing edge of the branch at `index` every path to `access` takes."""
        fallthrough = index + 1
        on_fallthrough = access in self.forward(fallthrough, index)
        on_taken = access in self.forward(target, index)
        if on_fallthrough and not on_taken:
            return FALLTHROUGH, fallthrough
        if on_taken and not on_fallthrough:
            return TAKEN, target
        return None, None

    def rewritten(self, entered: int, index: int, access: int, register: str) -> bool:
        """Can `register` change between the guard and the access it gates?"""
        live = self.forward(entered, index) & self.backward(access, index)
        return any(
            node != access and self.program[node]["row"]
            and writes_register(self.program[node]["row"], register)
            for node in live
        )

    def trip_bound(self, header: int, depth: int, seen, focus) -> tuple[int | None, bool]:
        """Most passes the loop at `header` can make, from whatever branch counts it out.

        The test may sit at the top and leave when it holds, or at the bottom and
        return to the head when it holds; either way it names a counter the loop
        advances and the last value whose pass still runs the body. A test some
        path around the loop can skip is not a bound, so only tests that dominate
        every latch are read.

        Whether the count is also a ceiling is a separate answer, and the
        tightest count is the one that has to carry it: a looser bound beside it
        proves nothing about a program the tighter one under-counts. Each of the
        three inputs can under-count on its own -- a limit that is really higher,
        a seed that is really lower, and an advance some pass around the loop
        skips, which makes the step smaller than the sum of its parts.

        A fourth thing can take the ceiling away, and it is not about counting at
        all: the edge the test declines has to leave. A loop whose bounded exit
        falls straight into an unconditional jump back to the head never stops,
        and its counter runs on past the value the test named -- so the count
        stands as a floor there and never as the whole of it.
        """
        if not self.complete:
            return None, False
        pass_nodes = self.pass_nodes(header)
        sites = self.region_sites(header)
        trips, counted = None, False
        for index, operator, counter, against, target, step in self.counting_tests(header):
            table = LAST_PASS_CONTINUING if target in pass_nodes else LAST_PASS_EXITING
            leaving = target if table is LAST_PASS_EXITING else index + 1
            _, limit, limit_trusted = self.interval_of(index, against, sites, depth + 1, seen, focus)
            # The counter enters the loop at its seed: asking for its value here
            # would ask for the trip count that is being derived.
            entering, entering_whole = self.seed_values(header, counter, sites, depth + 1, seen, focus)
            if limit is None or not entering:
                continue
            passes = max(0, (limit + table[operator] - min(entering)) // step + 1)
            whole = leaving not in pass_nodes and limit_trusted and entering_whole and all(
                self.every_latch(header, place) for place, _ in self.region_carried(header)[counter]
            )
            if trips is None or passes < trips:
                trips, counted = passes, whole
            elif passes == trips:
                counted = counted or whole
        return trips, counted

    def region_sites(self, header: int) -> dict[str, set[int]]:
        """The advance sites of every register the loop at `header` carries."""
        return {
            register: {place for place, _ in updates}
            for register, updates in self.region_carried(header).items()
        }

    def counting_tests(self, header: int) -> list[tuple[int, str, str, str, int, int]]:
        """Every test that can count the loop at `header` out, with its counter's step.

        `(index, operator, counter, compared token, branch target, step)` for
        each ordering test in the loop that stands on every way around it,
        names a register the loop advances, and is written in a direction the
        counter moves: continuing into the loop while the counter is below a
        limit, or leaving once it is not.
        """
        pass_nodes = self.pass_nodes(header)
        carried = self.region_carried(header)
        found = []
        for index in sorted(self.region_span(header)):
            compared = self.comparison(index)
            if compared is None or not self.every_latch(header, index):
                continue
            operator, counter, against, target = compared
            step = sum(amount for _, amount in carried.get(counter, ()))
            table = LAST_PASS_CONTINUING if target in pass_nodes else LAST_PASS_EXITING
            if step and operator in table:
                found.append((index, operator, counter, against, target, step))
        return found

    def exit_pass(self, header: int, index: int, leaving: int, depth: int, seen, focus) -> int | None:
        """On which pass, counted from one, the loop's own test at `index` leaves along `leaving`.

        An early exit can fire on any pass; the counted exit fires on exactly
        one, and which one is only exact when everything that decides it is a
        single value -- one counting test in the loop, a limit and a seed each
        shown whole and single, and an advance every pass makes. A limit a peer
        publishes is not a single value, and the exit it decides may fire on any
        pass up to the ceiling, so it leaves nothing exact behind it.

        A test that continues into the loop while it holds leaves on the last
        pass, after that pass's advances; one that leaves when it holds fires on
        the arrival after the last pass, with only the advances that stand before
        it in the body made.
        """
        tests = self.counting_tests(header)
        if len(tests) != 1 or tests[0][0] != index:
            return None
        _, operator, counter, against, target, step = tests[0]
        pass_nodes = self.pass_nodes(header)
        table = LAST_PASS_CONTINUING if target in pass_nodes else LAST_PASS_EXITING
        if leaving != (target if table is LAST_PASS_EXITING else index + 1) or leaving in pass_nodes:
            return None
        if not all(self.every_latch(header, place) for place, _ in self.region_carried(header)[counter]):
            return None
        sites = self.region_sites(header)
        limits, limits_whole = self.values_at(index, focus, against, sites, depth + 1, seen)
        entering, entering_whole = self.seed_values(header, counter, sites, depth + 1, seen, focus)
        if not (limits_whole and entering_whole) or limits is None or len(limits) != 1 or len(entering) != 1:
            return None
        passes = max(0, (min(limits) + table[operator] - min(entering)) // step + 1)
        return passes + 1 if table is LAST_PASS_EXITING else passes

    def reaches(self, origin: CallState, targets: set[CallState], blocked: set[int]) -> bool:
        """Does `origin` reach one of `targets` without passing any blocked index on the way?"""
        seen: set[CallState] = set()
        pending = [origin]
        while pending:
            state = pending.pop()
            if state in targets:
                return True
            if state in seen or state[0] in blocked:
                continue
            seen.add(state)
            pending.extend(self.states.get(state, ()))
        return False

    def standing_before(self, header: int, place: int, updates: list[tuple[int, int]]) -> int | None:
        """How far the loop's advances have moved a register by the time a pass reaches `place`.

        The same question `carried` asks of an access, asked of an exit: an
        advance counts when every pass reaches `place` through it, is ignored
        when no pass reaches `place` from it, and stands the answer down in
        between.
        """
        standing = 0
        for site, amount in updates:
            if site == place or place not in self.forward(site, header):
                continue
            if site not in self.dominators.get(place, ()):
                return None
            standing += amount
        return standing

    def after_loop_values(self, header: int, index: int, token: str, depth: int, seen, focus) -> Derived:
        """What the loop at `header` leaves in `token` for a reader outside its passes.

        The value is the seed plus the advances of every pass that ran before
        control left, so it is counted from the exits: each edge out of the pass
        that reaches the reader -- without passing the header again or another
        write to the register -- contributes the seed, plus the advances standing
        before the exit in the body, plus one stride for every completed pass.
        A match that leaves mid-scan can fire on any pass up to the trip count;
        the loop's own test fires on the one pass `exit_pass` names, and where
        that is not a single number the exit witnesses nothing and takes the
        closure with it. Any other exit that tests the register itself fires
        only on the passes its comparison holds, so its values are cut to what
        the compared side permits: `bge r7 40 Out` leaves `S40` and up, an
        equality against a literal leaves that one value, and a comparison
        against data nothing bounds leaves every pass, since the data can take
        any value. An exit that tests a different register the pass derives
        from a carried one -- `mul r0 r7 2` then `bge r0 80 Out` -- fires on
        passes this does not follow, so it witnesses nothing and takes the
        closure with it. A register two loops advance, or one advanced by a
        step some pass skips, is not counted from out here at all.

        The walk from an exit to the reader stops at the header and at any
        other write to the register, bar the advances of the reader's own loops:
        those are transparent to the reader, whose caller folds them onto
        whatever arrives here, so a value that seeds a second loop through its
        advance still arrives.
        """
        if not self.complete or depth > MAX_DEPTH or (header, token) in seen:
            return OPEN
        seen = seen | {(header, token)}
        updates = self.region_carried(header).get(token, [])
        around = [
            other for other in self.regions
            if token in self.region_carried(other)
            and any(place in self.region_members(other) for place, _ in updates)
        ]
        if not updates or around != [header]:
            return OPEN
        if not all(self.every_latch(header, place) for place, _ in updates):
            return OPEN
        stride = sum(amount for _, amount in updates)
        entering, entering_whole = self.seed_values(
            header, token, self.region_sites(header), depth + 1, seen, focus
        )
        trips, counted = self.trip_bound(header, depth + 1, seen, focus)
        if not entering or not trips:
            return OPEN
        pass_nodes = self.pass_nodes(header)
        transparent = self.sites(index).get(token, set())
        blocked = {header} | {
            node for node, entry in enumerate(self.program)
            if node != index and node not in transparent
            and entry["row"] and writes_register(entry["row"], token)
        }
        readers = set(self.states_at(index, focus))
        values: set[int] = set()
        whole = entering_whole and counted
        for state, outgoing in self.states.items():
            if state[0] not in pass_nodes:
                continue
            for target in outgoing:
                if target[0] in pass_nodes or not self.reaches(target, readers, blocked):
                    continue
                prefix = self.standing_before(header, state[0], updates)
                if prefix is None:
                    return OPEN
                left = {seed + prefix + (ran - 1) * stride for seed in entering for ran in range(1, trips + 1)}
                if any(test[0] == state[0] for test in self.counting_tests(header)):
                    fired = self.exit_pass(header, state[0], target[0], depth, seen, frozenset({state}))
                    if fired is None:
                        whole = False
                        continue
                    left = {seed + prefix + (fired - 1) * stride for seed in entering}
                else:
                    cut = self.exit_constraint(header, state[0], target[0], token, depth, seen, frozenset({state}))
                    if cut is None:
                        whole = False
                        continue
                    low, high, pinned, excluded, trusted = cut
                    left = {
                        value for value in left - excluded
                        if (low is None or value >= low) and (high is None or value <= high)
                        and (pinned is None or value in pinned)
                    }
                    whole = whole and trusted
                values |= left
        return (values, whole) if values else OPEN

    def derived_in_pass(self, header: int) -> dict[int, set[str]]:
        """At each node of the pass, the registers holding something computed from a carried one.

        A register the loop carries is derived everywhere in the pass. A `move`
        or arithmetic from a derived register derives its destination; a load
        does not, however derived its address -- `get r0 db r7` reads data, and
        the data is not the pass number. Any other write ends the derivation.
        The answer is a forward flow over the pass, joined at every node, so a
        register derived on one way round stays derived where the ways meet.
        """
        if header in self._derived:
            return self._derived[header]
        pass_nodes = self.pass_nodes(header)
        carried = set(self.region_carried(header))
        predecessors: dict[int, set[int]] = {node: set() for node in pass_nodes}
        for state, outgoing in self.states.items():
            if state[0] in pass_nodes:
                for target in outgoing:
                    if target[0] in pass_nodes:
                        predecessors[target[0]].add(state[0])
        entering: dict[int, set[str]] = {node: set(carried) for node in pass_nodes}
        leaving: dict[int, set[str]] = {}
        changed = True
        while changed:
            changed = False
            for node in sorted(pass_nodes):
                incoming = set(carried)
                for previous in predecessors[node]:
                    incoming |= leaving.get(previous, set())
                row = self.program[node]["row"]
                outgoing = set(incoming)
                if row and len(row) > 1 and writes_register(row, row[1]) and row[1] not in carried:
                    outgoing.discard(row[1])
                    if row[0] not in LOADS and any(operand in incoming for operand in row[2:]):
                        outgoing.add(row[1])
                if entering[node] != incoming or leaving.get(node) != outgoing:
                    entering[node], leaving[node] = incoming, outgoing
                    changed = True
        self._derived[header] = entering
        return entering

    def exit_constraint(self, header: int, index: int, leaving: int, token: str, depth: int, seen, focus):
        """What the exit at `index`, taken along `leaving`, permits `token` to hold as it fires.

        `(low, high, pinned, excluded, trusted)` for an exit whose passes this
        can follow: one that tests nothing the pass derives, and so fires on any
        pass, or one that tests `token` itself, whose comparison cuts the values
        it fires on -- against a literal exactly, against a bounded register to
        what that register permits, and against data nothing bounds not at all.
        `None` for an exit that tests some other register the pass derives from
        a carried one, whose passes this does not follow.

        The cut is by what the compared side is *permitted* to hold, which is
        the standard every derivation here is held to: a guard that admits a
        count of eight admits every count up to eight however the peer fills it
        in, so an interval read off the guards is exact by definition, and one
        read off a set not shown whole can only be too narrow -- which drops
        values and takes the closure with it through the trusted flag, never
        adding one.
        """
        row = self.program[index]["row"]
        derived = self.derived_in_pass(header).get(index, set())
        involved = [operand for operand in row[1:-1] if operand in derived]
        if not involved:
            return (None, None, None, set(), True)
        if involved != [token] or row[1] != token:
            return None
        # The two edges of an exit never coincide: a pass node has one edge that
        # reaches a latch and an exit has one that leaves, so a branch to its own
        # next line is either wholly inside the pass or not a pass node at all.
        table = TAKEN if leaving == self.labels.get(row[-1]) else FALLTHROUGH
        compared = self.comparison(index)
        if compared is not None:
            operator, _register, against, _target = compared
            other_low, other_high, trusted = self.interval_of(
                index, against, self.region_sites(header), depth + 1, seen, focus
            )
            low_delta, high_delta = table[operator]
            low = None if low_delta is None or other_low is None else other_low + low_delta
            high = None if high_delta is None or other_high is None else other_high + high_delta
            return (low, high, None, set(), trusted or (low is None and high is None))
        equal = self.equality(index)
        if equal is not None:
            _register, value, _target, equal_when_taken = equal
            if (table is TAKEN) == equal_when_taken:
                return (None, None, {value}, set(), True)
            return (None, None, None, {value}, True)
        operator = EQUALITY_AGAINST_ZERO.get(row[0], row[0])
        if operator in EQUAL_WHEN_TAKEN and len(row) >= 4:
            # An equality against a register: the equal edge fires only where
            # the other side can be, the unequal edge everywhere but a single
            # value the other side is pinned to.
            other_low, other_high, trusted = self.interval_of(
                index, row[2], self.region_sites(header), depth + 1, seen, focus
            )
            if (table is TAKEN) == EQUAL_WHEN_TAKEN[operator]:
                return (other_low, other_high, None, set(), trusted or (other_low is None and other_high is None))
            if other_low is not None and other_low == other_high:
                return (None, None, None, {other_low}, trusted)
            return (None, None, None, set(), True)
        return None

    def region_carried(self, header: int) -> dict[str, list[tuple[int, int]]]:
        if header not in self._carried:
            self._carried[header] = region_induction(
                self.program, self.region_span(header), self.pass_nodes(header)
            )
        return self._carried[header]

    def carrying_regions(self, index: int, token: str) -> list[int]:
        """Every loop around `index` that advances `token` and never resets it."""
        return [
            header for header in self.regions
            if index in self.region_members(header) and token in self.region_carried(header)
        ]

    def shared_advance(self, around: list[int], token: str) -> int | None:
        """The amount of the one site every loop in `around` advances `token` through, if there is one."""
        sites = {place: amount for header in around for place, amount in self.region_carried(header)[token]}
        if len(sites) != 1:
            return None
        return next(iter(sites.values()))

    def ceiling_counts(self, around: list[int], token: str, high, trusted: bool, depth: int, seen, focus) -> bool:
        """Does a ceiling at the access count `token` out exactly, whichever loop in `around` moved it?

        Two loops advancing one register through the same site, or one loop
        whose pass may run the site twice, move it by the same amount however
        they interleave, so a trusted ceiling at the access names the last
        value it reaches and the values are the seed plus every multiple of the
        amount up to it. That set is exact only where some loop around the
        access is counted by nothing but the ceiling, since it can re-enter the
        site until the guard fires; a loop whose own test stops it short leaves
        the upper values unreached, and a value in the set has to be one the
        program reaches.
        """
        if high is None or not trusted or self.shared_advance(around, token) is None:
            return False
        return any(self.trip_bound(header, depth, seen, focus)[0] is None for header in around)

    def carried(self, index: int, token: str) -> tuple[int, int, int] | None:
        """`(region, stride, prefix)` for the innermost loop that advances `token`.

        `stride` is how far one whole pass moves the register, `prefix` how far
        the advances standing before the access have already moved it by the time
        the access runs. The innermost loop is the safe one to read: an enclosing
        loop that also carries the register only moves it further, so bounding it
        by the inner pass understates the reach rather than inventing it.

        Several advances only sum into one stride when the pass really makes all
        of them. Two that a branch chooses between move the register by one or
        the other, never their sum, and reading them as a sequence would claim
        cells no execution reaches -- so unless every advance dominates every
        latch, a register advanced more than once is left at its first pass.

        A prefix asks more of an advance than a stride does. Skipping one only
        ever leaves the register somewhere the stride already names, but a prefix
        says the access stands *behind* it, and a pass that reached the access
        without it reads the cell before -- which the prefix drops off the front
        of the window. So an advance the access can be reached without is not one
        it stands behind, however few there are.

        Which advances those are is a question about the pass and not about where
        they are written. An advance below the access still runs before it when
        the pass reaches the access through it, and reading the prefix off the
        text there anchors the window one whole stride low -- claiming the cell
        before the first read and dropping the last. So an advance counts into
        the prefix when it dominates the access, is ignored when no pass reaches
        the access from it at all, and stands the derivation down in between,
        where some passes run it first and others do not.
        """
        around = self.carrying_regions(index, token)
        if not around:
            return None
        region = max(around)
        updates = self.region_carried(region)[token]
        every_pass = self.complete and all(
            self.every_latch(region, place) for place, _ in updates
        )
        if len(updates) > 1 and not every_pass:
            return None
        standing = []
        for place, amount in updates:
            if place == index or index not in self.forward(place, region):
                continue
            if not (self.complete and place in self.dominators.get(index, ())):
                return None
            standing.append((place, amount))
        return (region,
                sum(amount for _, amount in updates),
                sum(amount for _, amount in standing))

    def first_pass_offsets(self, index: int, token: str, focus) -> set[int] | None:
        """How far the innermost loop carrying `token` has advanced it when its first pass reaches `index`.

        One sum per way from the header to the access that does not pass the
        header again, each the amounts of the advances standing on that way.
        Where `carried` reads one prefix this is a single number; where a branch
        chooses between advances, or skips one, it is each choice. The sets are
        capped so a way through an inner loop that also advances the register
        fails closed rather than enumerating it.
        """
        header = max(self.carrying_regions(index, token))
        amounts = dict(self.region_carried(header)[token])
        offsets: dict[CallState, set[int]] = {state: {0} for state in self._by_index.get(header, ())}
        pending = list(offsets)
        while pending:
            state = pending.pop()
            leaving = offsets[state]
            if state[0] in amounts and state[0] != index:
                leaving = {offset + amounts[state[0]] for offset in leaving}
            if state[0] == index:
                continue
            for target in self.states.get(state, ()):
                if target[0] == header:
                    continue
                known = offsets.setdefault(target, set())
                if not leaving <= known:
                    known |= leaving
                    if len(known) > 64:
                        return None
                    pending.append(target)
        found = set().union(*(offsets.get(state, set()) for state in self.states_at(index, focus)))
        return found or None

    def interval_of(self, index: int, token: str, sites, depth: int, seen, focus) -> tuple:
        """How far `token` can reach either way, even where its values do not enumerate.

        A count checked by `bgt r3 8 Bad` alone has a ceiling and no floor, so it
        never enumerates -- but the ceiling is the whole of what a loop counted
        against it needs.
        """
        # The guards and the writes asked about below are placed against this
        # index's own visits, as `values_at` places its own: a guard on a limit
        # gates the limit's test, not the reader that asked about the limit,
        # and a later visit to that guard on the way to the reader is not it.
        focus = frozenset(self.states_at(index, focus))
        values, whole = self.values_at(index, focus, token, sites, depth, seen)
        if values is not None:
            return (min(values), max(values), whole)
        low, high, trusted = self.guard_interval(index, token, sites, depth, seen, focus)
        written_low, written_high, written_trusted = self.written_interval(index, token, depth, seen, focus)
        return (*meet((low, high), (written_low, written_high)), trusted and written_trusted)

    def written_interval(self, index: int, token: str, depth: int, seen, focus) -> tuple:
        """How far the writes reaching `index` can move `token`, where they do not enumerate.

        The join over every write that can still be in the register: an
        interval is open on any side some write leaves open, and a register
        arriving from a reflash is open on both. A loop advance is a write like
        any other here, and one that reaches itself round the back edge leaves
        the side it moves open, which is what an uncounted loop does to it. A
        graph with a transfer nobody can follow may be missing a write, so it
        bounds nothing, as every other bound reader here stands down on it.
        """
        if not self.complete or depth > MAX_DEPTH or ("written", index, focus, token) in seen:
            return (*UNBOUNDED, True)
        key = (index, focus, token)
        if key not in self._written:
            # A cut deeper down only ever widens the answer, so what one walk
            # found under its own cuts is a sound answer for every later asker.
            # The cycle key is its own, so a walk through here never stands a
            # value derivation down by looking like one.
            seen = seen | {("written", index, focus, token)}
            joined: tuple[int | None, int | None] | None = None
            trusted = True
            reaching = self.reaching(index, focus, token, frozenset()) or frozenset({None})
            for back in sorted(reaching, key=state_order):
                if back is None:
                    found = (*UNBOUNDED, True)
                else:
                    found = self.definition_interval(back, token, depth + 1, seen)
                joined = found[:2] if joined is None else join(joined, found[:2])
                trusted = trusted and found[2]
            self._written[key] = (*(UNBOUNDED if joined is None else joined), trusted)
        return self._written[key]

    def definition_interval(self, back: CallState, token: str, depth: int, seen) -> tuple:
        """How far one write can move `token`, read as an interval where its values do not enumerate.

        A count checked from above alone has a ceiling and no floor, so
        nothing along `move r11 r4` / `mul r9 r11 4` / `add r9 r9 r1`
        enumerates -- but the ceiling carries through each of them, and the
        ceiling is the whole of what a loop counted against the result needs:
        a smaller limit only runs fewer passes. `move` carries the operand's
        interval, `add` and `sub` combine two, and `mul` scales one by a
        literal; anything else leaves both sides open.
        """
        values, whole = self.definition_values(back, token, depth, seen)
        if values is not None:
            return (min(values), max(values), whole)
        index, focus = back[0], frozenset({back})
        row = self.program[index]["row"]
        sites = self.sites(index)
        if row[0] == "move" and len(row) >= 3:
            return self.interval_of(index, row[2], sites, depth + 1, seen, focus)
        if row[0] == "select" and len(row) >= 5:
            when_true = self.interval_of(index, row[3], sites, depth + 1, seen, focus)
            when_false = self.interval_of(index, row[4], sites, depth + 1, seen, focus)
            return (*join(when_true[:2], when_false[:2]), when_true[2] and when_false[2])
        if row[0] in {"add", "sub", "mul"} and len(row) >= 4:
            left_low, left_high, left_trusted = self.interval_of(index, row[2], sites, depth + 1, seen, focus)
            right_low, right_high, right_trusted = self.interval_of(index, row[3], sites, depth + 1, seen, focus)
            trusted = left_trusted and right_trusted
            if row[0] == "add":
                low = None if left_low is None or right_low is None else left_low + right_low
                high = None if left_high is None or right_high is None else left_high + right_high
                return (low, high, trusted)
            if row[0] == "sub":
                low = None if left_low is None or right_high is None else left_low - right_high
                high = None if left_high is None or right_low is None else left_high - right_low
                return (low, high, trusted)
            scale = resolve_integer(row[3], self.integer_aliases)
            scaled = (left_low, left_high)
            if scale is None:
                scale, scaled = resolve_integer(row[2], self.integer_aliases), (right_low, right_high)
            if scale is None or scale <= 0:
                return (*UNBOUNDED, True)
            low = None if scaled[0] is None else scaled[0] * scale
            high = None if scaled[1] is None else scaled[1] * scale
            return (low, high, trusted)
        return (*UNBOUNDED, True)

    def values(self, index: int, token: str, sites, depth: int = 0, seen=frozenset()) -> Derived:
        """Every value `token` can hold just before `program[index]`, and whether that is all.

        The values are a floor whatever the second answer says, so a consumer
        asking a declaration to *contain* them reads the first alone. Only a
        consumer that wants to hold a declaration to this set exactly needs the
        second, and every step that leaves a value unaccounted for -- a write
        nothing evaluates, a loop nothing counts out, a guard read off an
        untrusted limit -- takes it away.

        An index runs once per state it has, and each state is read on its own
        and joined here. A copy loop a program calls from three sites with a
        different seed and limit at each is three loops to this: read merged,
        the smallest seed would be paired with the largest limit and the copy
        would appear to reach cells no call reaches, and since a declaration is
        held to every cell derived, that reading could not be published as
        whole at all (issue #139).
        """
        states = sorted(self._by_index.get(index, ()), key=state_order) or [None]
        known: set[int] = set()
        closed = True
        for state in states:
            focus = frozenset() if state is None else frozenset({state})
            found, whole = self.values_at(index, focus, token, sites, depth, seen)
            if found is None:
                closed = False
            else:
                known |= found
                closed = closed and whole
        return (known, closed) if known else OPEN

    def values_at(self, index: int, focus, token: str, sites, depth: int, seen) -> Derived:
        """`values`, read for the readers in `focus` alone -- see `states_at` for how an index is placed against them."""
        literal = resolve_integer(token, self.integer_aliases)
        if literal is not None:
            return {literal}, True
        # From here on the focus is this index's own visits, so every guard,
        # header, and limit asked about below is placed relative to them.
        focus = frozenset(self.states_at(index, focus))
        if depth > MAX_DEPTH or (index, focus, token) in seen:
            return OPEN
        seen = seen | {(index, focus, token)}
        values, whole = self.seed_values(index, token, sites, depth, seen, focus)
        low, high, trusted = self.guard_interval(index, token, sites, depth, seen, focus)
        pinned, excluded = self.equality_constraints(index, token)
        if pinned is not None and (values is None or not whole):
            # An equality guard on the only edge that reaches here names the
            # value outright, however little is known about what wrote the
            # register. Seeds that were shown whole are the one thing that can
            # answer back: the value they never hold is one the guard's edge
            # never sees, and the access behind it is dead, not pinned.
            values = {value for value in pinned - excluded
                      if (low is None or value >= low) and (high is None or value <= high)}
            return (values, trusted) if values else OPEN
        if values is None:
            if low is None or high is None or high - low >= STACK_CELLS:
                return OPEN
            # Nothing named the value, so what the guards permit is both every
            # cell a peer can steer this to and every cell it can reach at all.
            values = set(range(low, high + 1)) - excluded
            return (values, trusted) if values else OPEN
        around = self.carrying_regions(index, token) if token in sites else []
        carried = self.carried(index, token) if around else None
        alone = carried is not None and len(around) == 1
        if around and not alone:
            # A loop this cannot read the advances of leaves the register
            # somewhere past the seed, and an enclosing loop that advances it too
            # leaves it somewhere past the innermost pass read below -- unless
            # one advance site is all that moves the register, whichever loop
            # re-entered it, and a trusted ceiling at the access counts it out.
            whole = whole and self.ceiling_counts(around, token, high, trusted, depth, seen, focus)
        if carried is None and around:
            # Advances a branch chooses between, or one the access stands behind
            # on some ways round and not others, leave the register at its first
            # pass: the seed plus whatever the pass advanced it by on the way to
            # the access, which is one of a few sums and never the bare seed
            # when every way passes an advance. Past that first pass a single
            # shared site moves it by one amount at a time up to the ceiling.
            offsets = self.first_pass_offsets(index, token, focus)
            if offsets is None:
                return OPEN
            values = {value + offset for value in values for offset in offsets}
            shared = self.shared_advance(around, token)
            if shared is not None and high is not None:
                reachable = (high - min(values)) // shared
                values = {value + step * shared for value in values for step in range(reachable + 1)}
        if carried is not None:
            region, stride, prefix = carried
            values = {value + prefix for value in values}
            # One loop's passes only count a register out when that loop is the
            # only one advancing it. An enclosing loop that advances it too
            # re-enters the inner one, so the inner count bounds a pass and not
            # the register, and what the register can hold is then whatever the
            # guards at the access permit.
            trips, counted = self.trip_bound(region, depth, seen, focus) if alone else (None, False)
            advances = -1 if trips is None else trips - 1
            if high is not None:
                # A guard at the access counts the loop out as well as its own
                # exit test does. Whichever of the two is tighter is the one that
                # decides the reach, so it is also the one that has to be sound:
                # a trusted guard says nothing about a program the exit test
                # under-counts, and the passes it does not reach are lost.
                reachable = (high - min(values)) // stride
                if advances < 0 or reachable < advances:
                    advances, counted = reachable, trusted
                elif reachable == advances:
                    counted = counted or trusted
            if advances >= 0:
                values = {value + offset * stride for value in values for offset in range(advances + 1)}
            # Otherwise nothing counts the loop out, and the cell the first pass
            # reaches is the only one witnessed.
            whole = whole and advances >= 0 and counted
        if low is not None:
            values = {value for value in values if value >= low}
        if high is not None:
            values = {value for value in values if value <= high}
        values -= excluded
        if pinned is not None:
            values &= pinned
        if not 0 < len(values) <= STACK_CELLS:
            return OPEN
        return values, whole and trusted

    def reaching(self, index: int, focus, token: str, transparent: frozenset[int]) -> frozenset[CallState | None]:
        """The writer states still in `token` at the visits to `index` a reader in `focus` last made."""
        arriving = self.arriving(token, transparent)
        return frozenset().union(*(arriving.get(state, frozenset()) for state in self.states_at(index, focus)))

    def arriving(self, token: str, transparent: frozenset[int]) -> dict[CallState, frozenset[CallState | None]]:
        """Which write is still in `token` at each state, as the state that made it.

        The nearest write in program order is not the answer: a register holds
        what the last write on the path that got here left in it, and different
        paths get here from different writes. `None` stands for arriving with no
        write at all -- registers survive a reflash, so nothing names what is
        there then.

        A loop advance is transparent rather than a write, because the caller
        folds the advance in once it has the seed the loop entered on.

        This is the one question here the index graph would answer too loosely
        rather than too strictly. Merging a subroutine's call strings joins each
        caller's entry to every caller's return, and a path stitched from two of
        them carries a write no execution does -- so the walk is over the call
        states, where a return goes back to the site that made it. The write
        is kept as the state that made it, not its index, so a reader in one
        caller's context evaluates the write's operands in the context they
        were computed in.
        """
        key = (token, transparent)
        if key not in self._reaching:
            writers = {
                node for node, entry in enumerate(self.program)
                if entry["row"] and writes_register(entry["row"], token)
            } - transparent
            incoming: dict[CallState, frozenset[CallState | None]] = {state: frozenset() for state in self.states}
            start: CallState = (0, None)
            pending: list[CallState] = []
            if start in incoming:
                incoming[start] = frozenset({None})
                pending.append(start)
            while pending:
                state = pending.pop()
                leaving = frozenset({state}) if state[0] in writers else incoming[state]
                for target in self.states.get(state, ()):
                    if not leaving <= incoming[target]:
                        incoming[target] |= leaving
                        pending.append(target)
            self._reaching[key] = incoming
        return self._reaching[key]

    def seed_values(self, index: int, token: str, sites, depth: int, seen, focus) -> Derived:
        """The join over every write that can still be in `token` at `index`, in the context `ra` names.

        One write is enough to witness a value, so a write nothing can evaluate
        costs the join its closure and not its other terms. Arriving with no
        write at all costs the closure too: what a reflash left in the register
        is not something a branch here bounds.
        """
        reaching = self.reaching(index, focus, token, frozenset(sites.get(token, ())))
        writers = {back[0] for back in reaching if back is not None}
        known: set[int] = set()
        closed = None not in reaching
        for back in sorted((state for state in reaching if state is not None), key=state_order):
            left = self.leaves_loop(back[0], index, token)
            entered = self.enters_loop(back[0], index, token)
            if left:
                values, whole = (self.after_loop_values(left.pop(), index, token, depth, seen, focus)
                                 if len(left) == 1 else OPEN)
            elif entered:
                # The write gets here only by entering a loop that advances the
                # register and leaving it again, so what arrives is what the loop
                # leaves behind, and that is counted from the loop's advance
                # above -- a first-arrival exit included. Reading the write
                # itself here would witness the seed along the path that leaves
                # before any pass, which a count the test decides may never take.
                advances = {place for header in entered for place, _ in self.region_carried(header)[token]}
                closed = closed and bool(advances & writers)
                continue
            else:
                values, whole = self.definition_values(back, token, depth, seen)
            if values is None:
                closed = False
            else:
                known |= values
                closed = closed and whole
        return (known, closed) if known else OPEN

    def leaves_loop(self, back: int, index: int, token: str) -> set[int]:
        """The loops `back` advances `token` around whose passes `index` stands outside of.

        Read from inside the pass, an advance is transparent and the caller
        folds the trip count in. Read from outside -- after the loop has left, or
        from an enclosing loop the inner one returns to -- the advance would be
        evaluated as one step past the seed, which is the value after the
        *first* pass and not what the loop leaves behind: a copy that always
        runs seven passes never leaves its address one past the seed. That
        reading would put a cell the program never writes in the witness set,
        and a declaration is held to every cell in it, so from out here the
        advance is read as what the loop leaves behind, by `after_loop_values`.
        """
        return {
            header for header in self.regions
            if index not in self.pass_nodes(header)
            and any(place == back for place, _ in self.region_carried(header).get(token, ()))
        }

    def enters_loop(self, back: int, index: int, token: str) -> set[int]:
        """The loops carrying `token` that every path from the write at `back` to `index` passes through.

        A seed written before a loop reaches a reader after it along the path
        that leaves on the first arrival, before any pass -- which the control
        flow has whether or not the count lets the exit fire there. What such a
        reader holds is what the loop leaves behind, so the seed is read through
        `after_loop_values` rather than as itself.

        A reader inside the span but outside the pass -- the block a restarting
        scan runs once it succeeds -- is not such a reader: the loop's advance
        is transparent there and `carried` folds the passes onto the seed, so
        the seed has to stand.
        """
        return {
            header for header in self.regions
            if token in self.region_carried(header)
            and index not in self.region_members(header)
            and back not in self.region_members(header)
            and index not in self.forward(back, header)
        }

    def definition_values(self, back: CallState, token: str, depth: int, seen) -> Derived:
        """The values one write leaves in `token`.

        Its operands are read at the write, with the loops around *it*
        transparent and not the loops around the reader. A write inside a loop
        read from outside it -- `move r7 r6` on the pass that found the slot,
        read once the scan is over -- holds what the operand held on whichever
        pass ran it, which is the operand folded over the writer's own loop;
        read with the reader's set the scan's advance is an ordinary write that
        reaches itself round the back edge and evaluates to nothing. And a seed
        the loop enters on -- `add r0 r0 128` before a copy that advances `r0`
        -- stands outside every loop that carries the register, so the
        reader's advances have nothing to say about what it computed.
        """
        index, focus = back[0], frozenset({back})
        sites = self.sites(index)
        row = self.program[index]["row"]
        if row[0] in BOOLEAN_RESULTS:
            return {0, 1}, True
        if row[0] == "select" and len(row) >= 5:
            when_true, true_whole = self.values_at(index, focus, row[3], sites, depth + 1, seen)
            when_false, false_whole = self.values_at(index, focus, row[4], sites, depth + 1, seen)
            if when_true is None or when_false is None:
                return OPEN
            return when_true | when_false, true_whole and false_whole
        if row[0] == "move" and len(row) >= 3:
            return self.values_at(index, focus, row[2], sites, depth + 1, seen)
        if row[0] == "clamp" and len(row) >= 5:
            # A clamp holds its operand to the bounds whatever the operand is,
            # so the bounds are the whole answer and the operand is never read.
            # Bounds held in registers are not read: what a register permits is
            # a question about its own writes, and a clamp between two of them
            # is not the shape a count guard takes.
            low = resolve_integer(row[3], self.integer_aliases)
            high = resolve_integer(row[4], self.integer_aliases)
            if low is None or high is None or not 0 <= high - low < STACK_CELLS:
                return OPEN
            return set(range(low, high + 1)), True
        if row[0] == "mod" and len(row) >= 4:
            return self.modulo_values(back, row, sites, depth, seen)
        if row[0] in {"add", "sub", "mul"} and len(row) >= 4:
            left, left_whole = self.values_at(index, focus, row[2], sites, depth + 1, seen)
            right, right_whole = self.values_at(index, focus, row[3], sites, depth + 1, seen)
            if left is None or right is None or len(left) * len(right) > PAIR_BUDGET:
                return OPEN
            whole = left_whole and right_whole
            if row[0] == "add":
                return {first + second for first in left for second in right}, whole
            if row[0] == "sub":
                return {first - second for first in left for second in right}, whole
            return {first * second for first in left for second in right}, whole
        return OPEN

    def modulo_values(self, back: CallState, row: list[str], sites, depth: int, seen) -> Derived:
        """What `mod` leaves: the game's `mod` is a true modulo, never negative for a positive divisor.

        Where both operands enumerate the result is enumerated like any other
        arithmetic. Where the dividend does not -- a cursor that wraps through
        the same `mod` every pass -- the divisor's ceiling is the whole answer:
        `a mod b` for `b` in `[1, high]` is in `[0, high - 1]` whatever `a`
        holds, and every value in it is one some dividend reaches. A divisor
        that can be zero or negative bounds nothing.
        """
        index, focus = back[0], frozenset({back})
        low, high, trusted = self.interval_of(index, row[3], sites, depth + 1, seen, focus)
        if low is None or low < 1 or high is None or high > STACK_CELLS:
            return OPEN
        left, left_whole = self.values_at(index, focus, row[2], sites, depth + 1, seen)
        right, right_whole = self.values_at(index, focus, row[3], sites, depth + 1, seen)
        if left is not None and right is not None and len(left) * len(right) <= PAIR_BUDGET:
            return {first % second for first in left for second in right}, left_whole and right_whole
        if left is not None:
            return OPEN
        return set(range(high)), trusted

    def access_bounds(self, index: int, token: str) -> Derived:
        """The stack cells one dynamic access reaches, and whether that is all of them.

        A derivation that runs off the stack is not a proof about a stack range,
        however closed each step of it was: the cells inside are still witnessed,
        but the address the program computes is not one a declared range covers.
        """
        cells, closed = self.values(index, token, self.sites(index))
        if cells is None:
            return OPEN
        inside = {cell for cell in cells if 0 <= cell < STACK_CELLS}
        return (inside, closed and inside == cells) if inside else OPEN


def dynamic_access_cells(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int],
    register_ports: RegisterPorts | None = None,
) -> list[tuple[str, str, set[int], str]]:
    """`(target, direction, cells, instruction)` for every witnessed dynamic access.

    `target` is a device port name or `db` for the program's own housing stack.
    An access whose address depends on a value no branch bounds is omitted: it
    has no witness a declared range can be held to.
    """
    analyzer = ValueBounds(source, integer_aliases)
    found = []
    for index, target, direction, token, row in dynamic_accesses(
        analyzer.program, aliases, integer_aliases, register_ports
    ):
        cells, _ = analyzer.access_bounds(index, token)
        if cells is not None:
            found.append((target, direction, cells, " ".join(row)))
    return found


def declared_coverage_errors(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int],
    declared: dict[tuple[str, str], list[dict[str, int]]],
    register_ports: RegisterPorts | None = None,
) -> list[str]:
    """Report every dynamic access reaching cells no declared range covers."""
    errors = []
    for target, direction, cells, instruction in dynamic_access_cells(
        source, aliases, integer_aliases, register_ports
    ):
        ranges = declared.get((target, direction))
        if ranges is None:
            continue
        missing = sorted(
            cell for cell in cells
            if not any(item["start"] <= cell <= item["end"] for item in ranges)
        )
        if missing:
            shown = [[item["start"], item["end"]] for item in ranges]
            cited = ", ".join(f"S{cell}" for cell in missing[:8])
            errors.append(
                f"{target} {direction} range {shown} omits {cited}"
                f"{', ...' if len(missing) > 8 else ''}, which the branches around "
                f"`{instruction}` let it reach"
            )
    # One instruction repeated in a second loop over the same records reports the
    # same shortfall twice; the reader only needs to be told once.
    return list(dict.fromkeys(errors))
