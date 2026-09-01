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
program writes as a subroutine. The branch bounds read that walk projected onto
indices, where merging a subroutine's call strings can only weaken them; the
reaching writes read the states themselves, because there the merge would
strengthen an answer instead.

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
"""
from __future__ import annotations

from framework.script_contracts.control_flow import (
    CallState,
    call_state_graph,
    project_call_states,
    writes_register,
)
from framework.script_contracts.parsing import parse_program, resolve_integer, resolve_port

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
# Operand pairs one arithmetic step may enumerate. Each operand is already
# capped at `STACK_CELLS` values, so this only bounds the work of combining
# them; a whole-stack window built from a bank base and a record counter is the
# widest legitimate combination and needs about 37k.
PAIR_BUDGET = 1 << 16


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


def region_induction(program: list[dict], region: tuple[int, int]) -> dict[str, list[tuple[int, int]]]:
    """Registers one loop carries, each as the `(index, amount)` of every advance.

    A register is loop-carried only when every write to it inside the loop
    advances it by a positive literal: anything else -- a `mul` that rebuilds
    the address from a counter, say -- means the value does not survive the
    back edge and the seed scan already sees it. A register advanced more than
    once per pass keeps every advance, because how far it moves in a pass is
    their sum and where it stands at an access is the sum of those before it.
    """
    start, end = region
    registers = ("sp", "ra", *(f"r{number}" for number in range(16)))
    written: dict[str, list[tuple[int, list[str]]]] = {}
    for index in range(start, end + 1):
        row = program[index]["row"]
        for register in registers:
            if row and writes_register(row, register):
                written.setdefault(register, []).append((index, row))
    return {
        register: [(index, int(row[3])) for index, row in updates]
        for register, updates in written.items()
        if all(
            row[0] == "add" and len(row) >= 4 and row[1] == row[2]
            and row[3].lstrip("-").isdigit() and int(row[3]) > 0
            for _, row in updates
        )
    }


def dynamic_accesses(
    program: list[dict], aliases: dict[str, str], integer_aliases: dict[str, int],
) -> list[tuple[int, str, str, str, list[str]]]:
    """`(index, target, direction, address token, row)` for every computed access.

    `target` is a device port name or `db` for the program's own housing stack;
    an access through an unresolvable port token is not one this analysis can
    attribute to anything, so it is left out.
    """
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
        found.append((index, target, direction, token, row))
    return found


def meet(first: tuple[int | None, int | None], second: tuple[int | None, int | None]):
    """The tighter of two intervals -- what holds when both constraints apply."""
    low = first[0] if second[0] is None else (second[0] if first[0] is None else max(first[0], second[0]))
    high = first[1] if second[1] is None else (second[1] if first[1] is None else min(first[1], second[1]))
    return (low, high)


class ValueBounds:
    """What one program's branches permit its registers and dynamic addresses to hold."""

    def __init__(self, source: str, integer_aliases: dict[str, int]) -> None:
        self.program = parse_program(source)
        self.integer_aliases = integer_aliases
        self.states, self.complete = call_state_graph(self.program)
        self.dominators, _, self.successors = project_call_states(self.states)
        self.labels = {entry["label"]: index for index, entry in enumerate(self.program) if entry["label"]}
        self.regions = back_edges(self.program)
        self._sites: dict[int, dict[str, set[int]]] = {}
        self._carried: dict[tuple[int, int], dict[str, list[tuple[int, int]]]] = {}
        self._forward: dict[tuple[int, int], set[int]] = {}
        self._backward: dict[tuple[int, int], set[int]] = {}
        self._reaching: dict[tuple[str, frozenset[int]], dict[int, frozenset[int | None]]] = {}

    def sites(self, index: int) -> dict[str, set[int]]:
        """Every loop advance around `index`, by register -- the writes a seed scan skips."""
        if index not in self._sites:
            found: dict[str, set[int]] = {}
            for region in self.regions:
                if region[0] <= index <= region[1]:
                    for register, updates in self.region_carried(region).items():
                        found.setdefault(register, set()).update(place for place, _ in updates)
            self._sites[index] = found
        return self._sites[index]

    def forward(self, start: int, blocked: int) -> set[int]:
        """Nodes reachable from `start` without re-entering `blocked`."""
        key = (start, blocked)
        if key not in self._forward:
            seen: set[int] = set()
            pending = [start]
            while pending:
                node = pending.pop()
                if node in seen or node == blocked:
                    continue
                seen.add(node)
                pending.extend(self.successors.get(node, set()) - seen)
            self._forward[key] = seen
        return self._forward[key]

    def backward(self, target: int, blocked: int) -> set[int]:
        """Nodes that can reach `target` without passing through `blocked`."""
        key = (target, blocked)
        if key not in self._backward:
            reverse: dict[int, set[int]] = {}
            for source, targets in self.successors.items():
                for node in targets:
                    reverse.setdefault(node, set()).add(source)
            seen: set[int] = set()
            pending = [target]
            while pending:
                node = pending.pop()
                if node in seen or node == blocked:
                    continue
                seen.add(node)
                pending.extend(reverse.get(node, set()) - seen)
            self._backward[key] = seen
        return self._backward[key]

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

    def guard_interval(self, access: int, register: str, sites, depth: int, seen) -> tuple:
        """The interval every branch that gates `access` permits `register` to hold.

        The third answer is whether those ends can be trusted not to cut a value
        the register really reaches. A limit read from a token whose own values
        were never shown whole may be smaller than the real one, and a bound that
        is too tight bounds nothing.
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
                index, against, sites, depth + 1, seen
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

    def trip_bound(self, region: tuple[int, int], depth: int, seen) -> tuple[int | None, bool]:
        """Most passes `region` can make, from whatever branch counts it out.

        The test may sit at the top and leave when it holds, or at the bottom and
        return to the head when it holds; either way it names a counter the loop
        advances and the last value whose pass still runs the body. A test some
        path around the loop can skip is not a bound, so only tests that dominate
        the back edge are read.

        Whether the count is also a ceiling is a separate answer, and the
        tightest count is the one that has to carry it: a looser bound beside it
        proves nothing about a program the tighter one under-counts. Each of the
        three inputs can under-count on its own -- a limit that is really higher,
        a seed that is really lower, and an advance some pass around the loop
        skips, which makes the step smaller than the sum of its parts.
        """
        if not self.complete:
            return None, False
        head, back = region
        carried = self.region_carried(region)
        sites = {register: {place for place, _ in updates} for register, updates in carried.items()}
        trips, counted = None, False
        for index in range(head, back + 1):
            compared = self.comparison(index)
            if compared is None or index not in self.dominators.get(back, ()):
                continue
            operator, counter, against, target = compared
            updates = carried.get(counter, ())
            step = sum(amount for _, amount in updates)
            table = LAST_PASS_CONTINUING if head <= target <= back else LAST_PASS_EXITING
            if not step or operator not in table:
                continue
            _, limit, limit_trusted = self.interval_of(index, against, sites, depth + 1, seen)
            # The counter enters the loop at its seed: asking for its value here
            # would ask for the trip count that is being derived.
            entering, entering_whole = self.seed_values(head, counter, sites, depth + 1, seen)
            if limit is None or not entering:
                continue
            passes = max(0, (limit + table[operator] - min(entering)) // step + 1)
            whole = limit_trusted and entering_whole and all(
                place in self.dominators.get(back, ()) for place, _ in updates
            )
            if trips is None or passes < trips:
                trips, counted = passes, whole
            elif passes == trips:
                counted = counted or whole
        return trips, counted

    def region_carried(self, region: tuple[int, int]) -> dict[str, list[tuple[int, int]]]:
        if region not in self._carried:
            self._carried[region] = region_induction(self.program, region)
        return self._carried[region]

    def carrying_regions(self, index: int, token: str) -> list[tuple[int, int]]:
        """Every loop around `index` that advances `token` and never resets it."""
        return [
            region for region in self.regions
            if region[0] <= index <= region[1] and token in self.region_carried(region)
        ]

    def carried(self, index: int, token: str) -> tuple[tuple[int, int], int, int] | None:
        """`(region, stride, prefix)` for the innermost loop that advances `token`.

        `stride` is how far one whole pass moves the register, `prefix` how far
        the advances standing before the access have already moved it by the time
        the access runs. The innermost loop is the safe one to read: an enclosing
        loop that also carries the register only moves it further, so bounding it
        by the inner pass understates the reach rather than inventing it.

        Several advances only sum into one stride when the pass really makes all
        of them. Two that a branch chooses between move the register by one or
        the other, never their sum, and reading them as a sequence would claim
        cells no execution reaches -- so unless every advance dominates the back
        edge, a register advanced more than once is left at its first pass.

        A prefix asks more of an advance than a stride does. Skipping one only
        ever leaves the register somewhere the stride already names, but a prefix
        says the access stands *behind* it, and a pass that reached the access
        without it reads the cell before -- which the prefix drops off the front
        of the window. So an advance the access can be reached without is not one
        it stands behind, however few there are.
        """
        region = None
        for candidate in self.carrying_regions(index, token):
            if region is None or candidate[0] > region[0]:
                region = candidate
        if region is None:
            return None
        updates = self.region_carried(region)[token]
        every_pass = self.complete and all(
            place in self.dominators.get(region[1], ()) for place, _ in updates
        )
        if len(updates) > 1 and not every_pass:
            return None
        standing = [(place, amount) for place, amount in updates if place < index]
        if standing and not (self.complete and all(
            place in self.dominators.get(index, ()) for place, _ in standing
        )):
            return None
        return (region,
                sum(amount for _, amount in updates),
                sum(amount for _, amount in standing))

    def interval_of(self, index: int, token: str, sites, depth: int, seen) -> tuple:
        """How far `token` can reach either way, even where its values do not enumerate.

        A count checked by `bgt r3 8 Bad` alone has a ceiling and no floor, so it
        never enumerates -- but the ceiling is the whole of what a loop counted
        against it needs.
        """
        values, whole = self.values(index, token, sites, depth, seen)
        if values is not None:
            return (min(values), max(values), whole)
        return self.guard_interval(index, token, sites, depth, seen)

    def values(self, index: int, token: str, sites, depth: int = 0, seen=frozenset()) -> Derived:
        """Every value `token` can hold just before `program[index]`, and whether that is all.

        The values are a floor whatever the second answer says, so a consumer
        asking a declaration to *contain* them reads the first alone. Only a
        consumer that wants to hold a declaration to this set exactly needs the
        second, and every step that leaves a value unaccounted for -- a write
        nothing evaluates, a loop nothing counts out, a guard read off an
        untrusted limit -- takes it away.
        """
        literal = resolve_integer(token, self.integer_aliases)
        if literal is not None:
            return {literal}, True
        if depth > MAX_DEPTH or (index, token) in seen:
            return OPEN
        seen = seen | {(index, token)}
        values, whole = self.seed_values(index, token, sites, depth, seen)
        low, high, trusted = self.guard_interval(index, token, sites, depth, seen)
        if values is None:
            if low is None or high is None or high - low >= STACK_CELLS:
                return OPEN
            # Nothing named the value, so what the guards permit is both every
            # cell a peer can steer this to and every cell it can reach at all.
            return set(range(low, high + 1)), trusted
        carried = self.carried(index, token) if token in sites else None
        if token in sites:
            # A loop this cannot read the advances of leaves the register
            # somewhere past the seed, and an enclosing loop that advances it too
            # leaves it somewhere past the innermost pass read below.
            whole = whole and carried is not None and len(self.carrying_regions(index, token)) == 1
        if carried is not None:
            region, stride, prefix = carried
            values = {value + prefix for value in values}
            trips, counted = self.trip_bound(region, depth, seen)
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
        if not 0 < len(values) <= STACK_CELLS:
            return OPEN
        return values, whole and trusted

    def arriving(self, token: str, transparent: frozenset[int]) -> dict[int, frozenset[int | None]]:
        """Which write is still in `token` at each index, over the call states.

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
        states, where a return goes back to the site that made it.
        """
        key = (token, transparent)
        if key not in self._reaching:
            writers = {
                node for node, entry in enumerate(self.program)
                if entry["row"] and writes_register(entry["row"], token)
            } - transparent
            incoming: dict[CallState, frozenset[int | None]] = {state: frozenset() for state in self.states}
            start: CallState = (0, None)
            pending: list[CallState] = []
            if start in incoming:
                incoming[start] = frozenset({None})
                pending.append(start)
            while pending:
                state = pending.pop()
                leaving = frozenset({state[0]}) if state[0] in writers else incoming[state]
                for target in self.states.get(state, ()):
                    if not leaving <= incoming[target]:
                        incoming[target] |= leaving
                        pending.append(target)
            merged: dict[int, frozenset[int | None]] = {}
            for state, reaching in incoming.items():
                merged[state[0]] = merged.get(state[0], frozenset()) | reaching
            self._reaching[key] = merged
        return self._reaching[key]

    def seed_values(self, index: int, token: str, sites, depth: int, seen) -> Derived:
        """The join over every write that can still be in `token` at `index`.

        One write is enough to witness a value, so a write nothing can evaluate
        costs the join its closure and not its other terms. Arriving with no
        write at all costs the closure too: what a reflash left in the register
        is not something a branch here bounds.
        """
        reaching = self.arriving(token, frozenset(sites.get(token, ()))).get(index, frozenset())
        known: set[int] = set()
        closed = None not in reaching
        for back in sorted(node for node in reaching if node is not None):
            values, whole = self.definition_values(back, token, sites, depth, seen)
            if values is None:
                closed = False
            else:
                known |= values
                closed = closed and whole
        return (known, closed) if known else OPEN

    def definition_values(self, back: int, token: str, sites, depth: int, seen) -> Derived:
        """The values one write leaves in `token`."""
        row = self.program[back]["row"]
        if row[0] in BOOLEAN_RESULTS:
            return {0, 1}, True
        if row[0] == "select" and len(row) >= 5:
            when_true, true_whole = self.values(back, row[3], sites, depth + 1, seen)
            when_false, false_whole = self.values(back, row[4], sites, depth + 1, seen)
            if when_true is None or when_false is None:
                return OPEN
            return when_true | when_false, true_whole and false_whole
        if row[0] == "move" and len(row) >= 3:
            return self.values(back, row[2], sites, depth + 1, seen)
        if row[0] in {"add", "sub", "mul"} and len(row) >= 4:
            left, left_whole = self.values(back, row[2], sites, depth + 1, seen)
            right, right_whole = self.values(back, row[3], sites, depth + 1, seen)
            if left is None or right is None or len(left) * len(right) > PAIR_BUDGET:
                return OPEN
            whole = left_whole and right_whole
            if row[0] == "add":
                return {first + second for first in left for second in right}, whole
            if row[0] == "sub":
                return {first - second for first in left for second in right}, whole
            return {first * second for first in left for second in right}, whole
        return OPEN

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
) -> list[tuple[str, str, set[int], str]]:
    """`(target, direction, cells, instruction)` for every witnessed dynamic access.

    `target` is a device port name or `db` for the program's own housing stack.
    An access whose address depends on a value no branch bounds is omitted: it
    has no witness a declared range can be held to.
    """
    analyzer = ValueBounds(source, integer_aliases)
    found = []
    for index, target, direction, token, row in dynamic_accesses(
        analyzer.program, aliases, integer_aliases
    ):
        cells, _ = analyzer.access_bounds(index, token)
        if cells is not None:
            found.append((target, direction, cells, " ".join(row)))
    return found


def declared_coverage_errors(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int],
    declared: dict[tuple[str, str], list[dict[str, int]]],
) -> list[str]:
    """Report every dynamic access reaching cells no declared range covers."""
    errors = []
    for target, direction, cells, instruction in dynamic_access_cells(
        source, aliases, integer_aliases
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
