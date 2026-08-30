"""Control-flow graph construction and the reachability and ordering proofs.

Everything here works on the parsed program: nodes are program indices, and a
state pairs a node with a bounded jal return stack where calls are followed.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


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


def control_flow_dominators(
    program: list[dict[str, Any]],
) -> tuple[dict[int, set[int]], dict[int, set[int]], dict[int, set[int]], bool]:
    """Return reachable-node dominators, predecessors, and whether all transfers are modeled."""
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    successors: dict[int, set[int]] = defaultdict(set)
    complete = True
    for index, entry in enumerate(program):
        row = entry["row"]
        fallthrough = index + 1 if index + 1 < len(program) else None
        if not row:
            if fallthrough is not None:
                successors[index].add(fallthrough)
            continue
        op = row[0]
        if op in {"jal", "jr"} or op.endswith("al"):
            complete = False
            continue
        if op == "j":
            target = labels.get(row[-1])
            if target is None:
                complete = False
            else:
                successors[index].add(target)
            continue
        if op.startswith("b"):
            target = labels.get(row[-1])
            if target is None:
                complete = False
            else:
                successors[index].add(target)
            if fallthrough is not None:
                successors[index].add(fallthrough)
            continue
        if fallthrough is not None:
            successors[index].add(fallthrough)

    reachable: set[int] = set()
    pending = [0] if program else []
    while pending:
        index = pending.pop()
        if index in reachable:
            continue
        reachable.add(index)
        pending.extend(successors[index] - reachable)
    predecessors: dict[int, set[int]] = defaultdict(set)
    for source, targets in successors.items():
        for target in targets:
            if source in reachable and target in reachable:
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
    """Follow local jal/j ra calls while looking for one register-preserving path."""
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    pending: list[tuple[int, tuple[int, ...]]] = [(start, ())]
    visited: set[tuple[int, tuple[int, ...]]] = set()
    while pending:
        node, return_stack = pending.pop()
        state = (node, return_stack)
        if state in visited:
            continue
        visited.add(state)
        if node == target and node != start:
            return True
        if node != start and node in blocked:
            continue
        row = program[node]["row"]
        fallthrough = node + 1 if node + 1 < len(program) else None
        if not row:
            if fallthrough is not None:
                pending.append((fallthrough, return_stack))
            continue
        op = row[0]
        if op == "jal":
            call_target = labels.get(row[-1])
            if call_target is not None and fallthrough is not None and len(return_stack) < 16:
                pending.append((call_target, return_stack + (fallthrough,)))
            continue
        if op in {"j", "jr"}:
            if row[-1] == "ra":
                if return_stack:
                    pending.append((return_stack[-1], return_stack[:-1]))
            else:
                jump_target = labels.get(row[-1])
                if jump_target is not None:
                    pending.append((jump_target, return_stack))
            continue
        if op.startswith("b"):
            if row[-1] == "ra":
                if return_stack:
                    pending.append((return_stack[-1], return_stack[:-1]))
            else:
                branch_target = labels.get(row[-1])
                if branch_target is not None:
                    pending.append((branch_target, return_stack))
            if fallthrough is not None:
                pending.append((fallthrough, return_stack))
            continue
        if fallthrough is not None:
            pending.append((fallthrough, return_stack))
    return False


def reachable_states_avoiding_calls(
    start: int, program: list[dict[str, Any]], blocked: set[int]
) -> set[tuple[int, tuple[int, ...]]]:
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    pending: list[tuple[int, tuple[int, ...]]] = [(start, ())]
    visited: set[tuple[int, tuple[int, ...]]] = set()
    while pending:
        node, return_stack = pending.pop()
        state = (node, return_stack)
        if state in visited or node in blocked:
            continue
        visited.add(state)
        row = program[node]["row"]
        fallthrough = node + 1 if node + 1 < len(program) else None
        if not row:
            if fallthrough is not None:
                pending.append((fallthrough, return_stack))
            continue
        op = row[0]
        if op == "jal":
            target = labels.get(row[-1])
            if target is not None and fallthrough is not None and len(return_stack) < 16:
                pending.append((target, return_stack + (fallthrough,)))
            continue
        if op in {"j", "jr"}:
            if row[-1] == "ra":
                if return_stack:
                    pending.append((return_stack[-1], return_stack[:-1]))
            else:
                target = labels.get(row[-1])
                if target is not None:
                    pending.append((target, return_stack))
            continue
        if op.startswith("b"):
            if row[-1] == "ra":
                if return_stack:
                    pending.append((return_stack[-1], return_stack[:-1]))
            else:
                target = labels.get(row[-1])
                if target is not None:
                    pending.append((target, return_stack))
            if fallthrough is not None:
                pending.append((fallthrough, return_stack))
            continue
        if fallthrough is not None:
            pending.append((fallthrough, return_stack))
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
) -> set[tuple[int, tuple[int, ...]]]:
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    ordered_states: list[tuple[int, tuple[int, ...]]] = []
    segment_start = 0
    node = start
    return_stack: tuple[int, ...] = ()
    visited: set[tuple[int, tuple[int, ...]]] = set()
    while 0 <= node < len(program) and node not in blocked:
        state = (node, return_stack)
        if state in visited:
            break
        visited.add(state)
        if program[node]["label"]:
            segment_start = len(ordered_states)
        ordered_states.append(state)
        row = program[node]["row"]
        fallthrough = node + 1
        if not row:
            node = fallthrough
        elif row[0] == "jal":
            target = labels.get(row[-1])
            if target is None or fallthrough >= len(program) or len(return_stack) >= 16:
                break
            return_stack += (fallthrough,)
            node = target
        elif row[0] in {"j", "jr"}:
            if row[-1] == "ra":
                if not return_stack:
                    break
                node, return_stack = return_stack[-1], return_stack[:-1]
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
