"""Bound the cells a computed stack address reaches, so a loop's far end is checked.

`address_forms` reduces an address to `constant + sum(step x loop counter)` and
holds a declared range to that constant -- the cell the access reaches on its
first pass. That catches a window anchored in the wrong place but not one
anchored right and cut short, because a record loop's trip count is a count
somebody publishes rather than a literal in the source.

The branches supply the missing number, two ways. A branch that gates an access
constrains what the registers reaching it hold: `blt r3 0 Bad` then
`bgt r3 8 Bad` says the program accepts 0..8 and rejects the rest, so the count
it loops on is worth eight passes however the peer fills it in. A branch that
decides whether a loop runs again bounds its trip count directly, whether it is
written at the top against the counter (`bge r4 r3 Stable`) or at the bottom
against a different one (`ble r4 23 CopyIn`, which is what pins an address
register advanced beside it). Between them the whole `S32..S95` plan window
falls out of a validator that only ever names `8` and `32`.

Two things follow from reading a branch as the bound. The derived set is what
the program *permits*, not what one execution performs -- a declared range has
to cover every cell a legal peer can steer the loop to, which is the surface a
declaration exists to state. And the set is only ever a floor: a declared range
must contain it, never equal it, so a coarser reviewed window stays legal and a
branch this module cannot read costs a check rather than inventing one. Where a
loop's count is never validated locally, nothing here bounds it and the far end
stays a review obligation.

Reading a branch as a gate or an exit needs the control-flow graph to be the
whole graph, and a program with a `jal` in it has no such graph: dropping the
call and return edges leaves a block with fewer predecessors than it really has,
which is the direction that over-states what dominates it. Both bounds therefore
stand down on a program with an unmodeled transfer, leaving it the base rule that
never consults the graph at all.
"""
from __future__ import annotations

from framework.script_contracts.address_forms import (
    address_form,
    back_edges,
    dynamic_accesses,
    induction_variables,
)
from framework.script_contracts.control_flow import control_flow_dominators, writes_register
from framework.script_contracts.parsing import parse_program, resolve_integer

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
        self.dominators, _, self.successors, self.complete = control_flow_dominators(self.program)
        self.labels = {entry["label"]: index for index, entry in enumerate(self.program) if entry["label"]}
        self.regions = back_edges(self.program)
        self._induction: dict[int, tuple[dict[str, int], dict[str, set[int]]]] = {}
        self._forward: dict[tuple[int, int], set[int]] = {}
        self._backward: dict[tuple[int, int], set[int]] = {}

    def induction(self, index: int) -> tuple[dict[str, int], dict[str, set[int]]]:
        if index not in self._induction:
            self._induction[index] = induction_variables(self.program, index)
        return self._induction[index]

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
        """The interval every branch that gates `access` permits `register` to hold."""
        interval = UNBOUNDED
        if not self.complete:
            return interval
        for index in self.dominators.get(access, ()):
            compared = self.comparison(index)
            if compared is None or compared[1] != register:
                continue
            operator, _register, against, target = compared
            table, entered = self.gated_edge(access, index, target)
            if table is None or self.rewritten(entered, index, access, register):
                continue
            other = self.interval_of(index, against, sites, depth + 1, seen)
            low_delta, high_delta = table[operator]
            low = None if low_delta is None or other[0] is None else other[0] + low_delta
            high = None if high_delta is None or other[1] is None else other[1] + high_delta
            interval = meet(interval, (low, high))
        return interval

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

    def trip_bound(self, region: tuple[int, int], depth: int, seen) -> int | None:
        """Most passes `region` can make, from whatever branch counts it out.

        The test may sit at the top and leave when it holds, or at the bottom and
        return to the head when it holds; either way it names a counter the loop
        advances and the last value whose pass still runs the body. A test some
        path around the loop can skip is not a bound, so only tests that dominate
        the back edge are read.
        """
        if not self.complete:
            return None
        head, back = region
        steps, sites = induction_variables(self.program, head)
        trips = None
        for index in range(head, back + 1):
            compared = self.comparison(index)
            if compared is None or index not in self.dominators.get(back, ()):
                continue
            operator, counter, against, target = compared
            step = steps.get(counter)
            table = LAST_PASS_CONTINUING if head <= target <= back else LAST_PASS_EXITING
            if not step or operator not in table:
                continue
            limit = self.interval_of(index, against, sites, depth + 1, seen)[1]
            # The counter enters the loop at its seed: asking for its value here
            # would ask for the trip count that is being derived.
            entering = self.seed_values(head, counter, sites, depth + 1, seen)
            if limit is None or not entering:
                continue
            passes = max(0, (limit + table[operator] - min(entering)) // step + 1)
            trips = passes if trips is None else min(trips, passes)
        return trips

    def induction_passes(self, index: int, token: str, depth: int, seen) -> int | None:
        """Most times the loops around `index` can advance `token` before it is read."""
        passes = None
        for region in self.regions:
            if not region[0] <= index <= region[1]:
                continue
            if token not in induction_variables(self.program, region[0])[0]:
                continue
            trips = self.trip_bound(region, depth, seen)
            if trips is None:
                return None
            passes = trips if passes is None else min(passes, trips)
        return passes

    def interval_of(self, index: int, token: str, sites, depth: int, seen) -> tuple:
        values = self.values(index, token, sites, depth, seen)
        return UNBOUNDED if values is None else (min(values), max(values))

    def values(self, index: int, token: str, sites, depth: int = 0, seen=frozenset()):
        """Every value `token` can hold just before `program[index]`; None when open."""
        literal = resolve_integer(token, self.integer_aliases)
        if literal is not None:
            return {literal}
        if depth > MAX_DEPTH or (index, token) in seen:
            return None
        seen = seen | {(index, token)}
        values = self.seed_values(index, token, sites, depth, seen)
        low, high = self.guard_interval(index, token, sites, depth, seen)
        if values is None:
            if low is None or high is None or high - low >= STACK_CELLS:
                return None
            return set(range(low, high + 1))
        step = self.induction(index)[0].get(token) if token in sites else None
        if step:
            passes = self.induction_passes(index, token, depth, seen)
            advances = -1 if passes is None else passes - 1
            if high is not None:
                reachable = (high - min(values)) // step
                advances = reachable if advances < 0 else min(advances, reachable)
            if advances >= 0:
                values = {value + offset * step for value in values for offset in range(advances + 1)}
            # Otherwise nothing counts the loop out and only the first pass is
            # witnessed, which is the base rule this analysis started from.
        if low is not None:
            values = {value for value in values if value >= low}
        if high is not None:
            values = {value for value in values if value <= high}
        return values if 0 < len(values) <= STACK_CELLS else None

    def seed_values(self, index: int, token: str, sites, depth: int, seen):
        """The values the nearest earlier write leaves in `token`."""
        for back in range(index - 1, -1, -1):
            row = self.program[back]["row"]
            if not row or not writes_register(row, token):
                continue
            if back in sites.get(token, ()):
                continue  # a loop step, folded in by the caller once the seed is found
            if row[0] == "move" and len(row) >= 3:
                return self.values(back, row[2], sites, depth + 1, seen)
            if row[0] in {"add", "sub", "mul"} and len(row) >= 4:
                left = self.values(back, row[2], sites, depth + 1, seen)
                right = self.values(back, row[3], sites, depth + 1, seen)
                if left is None or right is None or len(left) * len(right) > STACK_CELLS:
                    return None
                if row[0] == "add":
                    return {first + second for first in left for second in right}
                if row[0] == "sub":
                    return {first - second for first in left for second in right}
                return {first * second for first in left for second in right}
            return None
        return None

    def access_cells(self, index: int, token: str) -> set[int] | None:
        """The stack cells one dynamic access reaches, or None when nothing witnesses it."""
        steps, sites = self.induction(index)
        cells = self.values(index, token, sites)
        if cells is None:
            form = address_form(self.program, index, token, self.integer_aliases, steps, sites)
            cells = {form.constant} if form.induction_only else None
        if cells is None:
            return None
        return {cell for cell in cells if 0 <= cell < STACK_CELLS} or None


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
        cells = analyzer.access_cells(index, token)
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
