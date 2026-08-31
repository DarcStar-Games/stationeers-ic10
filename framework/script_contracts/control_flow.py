"""Control-flow graph construction and the reachability and ordering proofs.

Everything here works on the parsed program, and one walk answers what its
control flow does. A state pairs a program index with the return address `ra`
holds there, because `ra` is one register and not a stack: `jal` overwrites it
with its own fallthrough, so a subroutine is walked once per call site with the
edge that site really returns along, and a second `jal` reached before a return
replaces the first return address rather than nesting under it. That is what the
machine does, so a subroutine that leaves through a shared error path instead of
through `j ra` needs no special case, and every program in the tree comes out
with its calls modeled.

`control_flow_dominators` projects those states back onto plain indices for the
dominance and ordering proofs. Merging a subroutine's call strings only ever
adds edges, which costs dominators and reachability precision and never claims
either -- a guard that survives the merge really does gate every call.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# A program index paired with the return address `ra` holds there, or None where
# it holds nothing this analysis can name.
CallState = tuple[int, "int | None"]
# States one walk may enumerate. `ra` takes at most one value per call site, so a
# program stays within a small multiple of its own length; the widest in the tree
# needs 432, and the cap is only here so a graph nobody anticipated fails closed
# rather than running away.
CALL_STATE_LIMIT = 8192


@lru_cache(maxsize=1)
def assigning_instructions(root: Path = ROOT) -> dict[str, bool]:
    """Which mnemonics assign their first operand, from the game's own signatures.

    An instruction whose signature starts with a bare `r?` writes that register;
    one that starts with a named operand -- `bge a(r?|num) ...`, `poke
    address(r?|num) ...` -- only reads it. Deriving this from the extracted
    instruction set rather than a hand-kept list of exceptions keeps a branch
    from being mistaken for an assignment when the game adds one.
    """
    table = json.loads((root / "data/ic10_instruction_set.json").read_text())["instructions"]
    return {
        name: entry["example"].split()[1] == "r?"
        for name, entry in table.items()
        if len(entry["example"].split()) > 1
    }


def writes_register(row: list[str], register: str) -> bool:
    if row and register == "sp" and row[0] in {"push", "pop"}:
        return True
    if len(row) < 2 or row[1] != register:
        return False
    # An unknown mnemonic counts as an assignment: over-approximating stops a
    # backward seed scan early, which loses a proof rather than inventing one.
    return assigning_instructions().get(row[0], True)


def program_labels(program: list[dict[str, Any]]) -> dict[str, int]:
    return {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}


def call_state_successors(
    program: list[dict[str, Any]], labels: dict[str, int], state: CallState
) -> tuple[set[CallState], bool]:
    """Where one `(index, ra)` state goes, and whether that is the whole answer.

    A write to `ra` from anything but a call leaves it unknown rather than
    failing: several programs use it as a sixteenth scratch register and never
    return through it. What fails closed is a return that reads an unknown `ra`,
    together with a branch that links, an unresolvable target, and a walk past
    its own cap -- so an incomplete graph names a transfer nobody can follow, not
    a register somebody reused.

    The flag and the edges are separate answers. An edge is only ever left out
    when there is no index to name, so callers reading the edges alone still get
    every path the program has bar that one, and callers that need a whole graph
    read the flag.
    """
    index, ra = state
    row = program[index]["row"]
    fallthrough = index + 1 if index + 1 < len(program) else None
    if row and row[0] != "jal" and writes_register(row, "ra"):
        ra = None
    onward: set[CallState] = {(fallthrough, ra)} if fallthrough is not None else set()
    if not row:
        return onward, True
    if row[0] == "jal":
        target = labels.get(row[-1])
        if target is None or fallthrough is None:
            return set(), False
        return {(target, fallthrough)}, True
    if row[0] == "hcf":
        return set(), True
    if row[0] not in {"j", "jr"} and not row[0].startswith("b"):
        return onward, True
    # A branch that links leaves `ra` pointing somewhere this does not follow,
    # and only a conditional transfer carries on to the next instruction too.
    linked = row[0].endswith("al")
    conditional = row[0].startswith("b")
    if row[-1] == "ra":
        # Nothing names where an unknown `ra` goes, so nothing stands in for it.
        taken: set[CallState] = set() if ra is None else {(ra, ra)}
    else:
        target = labels.get(row[-1])
        taken = set() if target is None else {(target, None if linked else ra)}
    if linked and fallthrough is not None:
        onward = {(fallthrough, None)}
    return taken | (onward if conditional else set()), bool(taken) and not linked


def call_state_graph(
    program: list[dict[str, Any]],
) -> tuple[dict[CallState, set[CallState]], bool]:
    """Every `(index, ra)` state the program reaches, and whether all transfers are modeled."""
    labels = program_labels(program)
    successors: dict[CallState, set[CallState]] = {}
    complete = True
    pending: list[CallState] = [(0, None)] if program else []
    while pending:
        state = pending.pop()
        if state in successors:
            continue
        if len(successors) >= CALL_STATE_LIMIT:
            return successors, False
        outgoing, modeled = call_state_successors(program, labels, state)
        complete = complete and modeled
        successors[state] = outgoing
        pending.extend(target for target in outgoing if target not in successors)
    return successors, complete


def control_flow_dominators(
    program: list[dict[str, Any]],
) -> tuple[dict[int, set[int]], dict[int, set[int]], dict[int, set[int]], bool]:
    """Return reachable-node dominators, predecessors, and whether all transfers are modeled."""
    states, complete = call_state_graph(program)
    successors: dict[int, set[int]] = defaultdict(set)
    for (index, _), outgoing in states.items():
        successors[index].update(target for target, _ in outgoing)
    reachable = {index for index, _ in states}
    predecessors: dict[int, set[int]] = defaultdict(set)
    for source, targets in successors.items():
        for target in targets:
            predecessors[target].add(source)
    dominators = {index: set(reachable) for index in reachable}
    if reachable:
        dominators[0] = {0}
    changed = True
    while changed:
        changed = False
        for index in sorted(reachable - {0}):
            incoming = predecessors[index]
            updated = {index} | (set.intersection(*(dominators[parent] for parent in incoming)) if incoming else set())
            if updated != dominators[index]:
                dominators[index] = updated
                changed = True
    return dominators, predecessors, successors, complete


def can_reach(start: int, target: int, successors: dict[int, set[int]]) -> bool:
    pending = list(successors.get(start, set()))
    visited: set[int] = set()
    while pending:
        index = pending.pop()
        if index == target:
            return True
        if index in visited:
            continue
        visited.add(index)
        pending.extend(successors.get(index, set()) - visited)
    return False


def can_reach_avoiding_calls(
    start: int, target: int, program: list[dict[str, Any]], blocked: set[int]
) -> bool:
    """Is there one path from `start` to `target` with no blocked node on it?

    Calls are followed, and a transfer the state walk cannot place drops its edge
    rather than failing: a path this cannot follow is a path it does not claim.
    """
    labels = program_labels(program)
    pending: list[CallState] = [(start, None)]
    visited: set[CallState] = set()
    while pending:
        state = pending.pop()
        if state in visited:
            continue
        visited.add(state)
        if state[0] == target and state[0] != start:
            return True
        if state[0] != start and state[0] in blocked:
            continue
        outgoing, _ = call_state_successors(program, labels, state)
        pending.extend(outgoing - visited)
    return False


def reachable_states_avoiding_calls(
    start: int, program: list[dict[str, Any]], blocked: set[int]
) -> set[CallState]:
    labels = program_labels(program)
    pending: list[CallState] = [(start, None)]
    visited: set[CallState] = set()
    while pending:
        state = pending.pop()
        if state in visited or state[0] in blocked:
            continue
        visited.add(state)
        outgoing, _ = call_state_successors(program, labels, state)
        pending.extend(outgoing - visited)
    return visited


def must_reach(start: int, target: int, successors: dict[int, set[int]]) -> bool:
    """Return whether every modeled path from start reaches target without cycling or terminating."""
    guaranteed = {target}
    changed = True
    while changed:
        changed = False
        for node, outgoing in successors.items():
            if node not in guaranteed and outgoing and outgoing <= guaranteed:
                guaranteed.add(node)
                changed = True
    return start in guaranteed


def all_paths_retain_target(
    start: int, target: int, successors: dict[int, set[int]], blocked: set[int]
) -> bool:
    reverse: dict[int, set[int]] = defaultdict(set)
    for source, targets in successors.items():
        for destination in targets:
            if source not in blocked and destination not in blocked:
                reverse[destination].add(source)
    can_reach = {target}
    pending = [target]
    while pending:
        node = pending.pop()
        for predecessor in reverse.get(node, set()) - can_reach:
            can_reach.add(predecessor)
            pending.append(predecessor)
    if start not in can_reach:
        return False
    pending = [start]
    visited: set[int] = set()
    while pending:
        node = pending.pop()
        if node == target or node in visited:
            continue
        visited.add(node)
        outgoing = successors.get(node, set())
        if not outgoing or not outgoing <= can_reach:
            return False
        pending.extend(outgoing - visited)
    return True


def nodes_before_target(
    start: int, target: int, successors: dict[int, set[int]]
) -> set[int]:
    if start == target:
        return set()
    pending = list(successors.get(start, set()))
    visited: set[int] = set()
    while pending:
        node = pending.pop()
        if node == target or node in visited:
            continue
        visited.add(node)
        pending.extend(successors.get(node, set()) - visited)
    return visited


def paths_preserve_register(
    start: int, target: int, register: str, program: list[dict[str, Any]],
    successors: dict[int, set[int]],
) -> bool:
    return not any(
        program[node]["row"] and writes_register(program[node]["row"], register)
        for node in nodes_before_target(start, target, successors)
    )


def first_executable_node(
    index: int, program: list[dict[str, Any]], successors: dict[int, set[int]]
) -> int | None:
    visited = set()
    while 0 <= index < len(program) and index not in visited:
        visited.add(index)
        if program[index]["row"]:
            return index
        outgoing = successors.get(index, set())
        if len(outgoing) != 1:
            return None
        index = next(iter(outgoing))
    return None


def fallthrough_spine(
    start: int, program: list[dict[str, Any]], blocked: set[int], reset_floor: int
) -> set[CallState]:
    labels = program_labels(program)
    ordered_states: list[CallState] = []
    segment_start = 0
    node = start
    ra: int | None = None
    visited: set[CallState] = set()
    while 0 <= node < len(program) and node not in blocked:
        state = (node, ra)
        if state in visited:
            break
        visited.add(state)
        if program[node]["label"]:
            segment_start = len(ordered_states)
        ordered_states.append(state)
        row = program[node]["row"]
        fallthrough = node + 1
        if row and row[0] != "jal" and (row[0].endswith("al") or writes_register(row, "ra")):
            ra = None
        if not row:
            node = fallthrough
        elif row[0] == "jal":
            target = labels.get(row[-1])
            if target is None or fallthrough >= len(program):
                break
            ra = fallthrough
            node = target
        elif row[0] in {"j", "jr"}:
            if row[-1] == "ra":
                if ra is None:
                    break
                node = ra
            else:
                target = labels.get(row[-1])
                if target is None:
                    break
                if target <= reset_floor:
                    del ordered_states[segment_start:]
                    break
                node = target
        else:
            node = fallthrough
    return set(ordered_states)


def branch_rejects_before_success(
    row: list[str], _branch_node: int, success_node: int, reset_nodes: set[int],
    program: list[dict[str, Any]], side_effect_barriers: bool = False,
) -> bool:
    if row[-1] == "ra":
        return True
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    target_node = labels.get(row[-1])
    if target_node is None or success_node >= len(program):
        return False
    yield_nodes = {
        node for node, entry in enumerate(program)
        if entry["row"] and entry["row"][0] == "yield"
    }
    side_effect_nodes = {
        node for node, entry in enumerate(program)
        if side_effect_barriers
        and entry["row"]
        and entry["row"][0] in {"poke", "put", "putd", "s", "sb", "sbn", "ss"}
    }
    barriers = set(reset_nodes) | yield_nodes | side_effect_nodes
    _, _, successors, _ = control_flow_dominators(program)
    for node in range(len(program)):
        if first_executable_node(node, program, successors) in yield_nodes | side_effect_nodes:
            barriers.add(node)
    success_spine = fallthrough_spine(
        success_node, program, barriers, max(reset_nodes, default=-1)
    )
    failure_states = reachable_states_avoiding_calls(target_node, program, barriers)
    return success_spine.isdisjoint(failure_states)
