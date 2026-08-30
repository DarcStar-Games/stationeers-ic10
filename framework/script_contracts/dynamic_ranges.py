"""Prove and resolve the stack cell ranges dynamic addresses can reach.

Range lists are validated and merged here, the strict literal-seeded linear
loop proof turns a computed address into an exact range, and the resolver
arbitrates between source-derived proofs, fingerprinted overrides, and the
conservative full-stack fallback -- failing closed on any disagreement.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from framework.script_contracts.control_flow import can_reach, control_flow_dominators, writes_register
from framework.script_contracts.parsing import parse_program, resolve_integer, resolve_port


def validated_ranges(value: Any) -> list[dict[str, int]]:
    ranges = sorted(({"start": int(item[0]), "end": int(item[1])} for item in value or []), key=lambda item: (item["start"], item["end"]))
    previous_end = -1
    for item in ranges:
        if not 0 <= item["start"] <= item["end"] <= 511:
            raise ValueError(f"invalid stack cell range: {item}")
        if item["start"] <= previous_end:
            raise ValueError(f"overlapping stack cell ranges: {ranges}")
        previous_end = item["end"]
    return ranges


def ranges_overlap(ranges: list[dict[str, int]]) -> bool:
    ordered = sorted(ranges, key=lambda item: (item["start"], item["end"]))
    return any(current["start"] <= previous["end"] for previous, current in zip(ordered, ordered[1:]))


def merge_ranges(ranges: list[dict[str, int]]) -> list[dict[str, int]]:
    merged: list[dict[str, int]] = []
    for item in sorted(ranges, key=lambda value: (value["start"], value["end"])):
        if merged and item["start"] <= merged[-1]["end"] + 1:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def expanded_ranges(ranges: list[dict[str, int]]) -> set[int]:
    return {address for item in ranges for address in range(item["start"], item["end"] + 1)}


def linear_dynamic_range(
    program: list[dict[str, Any]], access_index: int, address_register: str, integer_aliases: dict[str, int],
    dominators: dict[int, set[int]], predecessors: dict[int, set[int]], successors: dict[int, set[int]],
    control_flow_complete: bool,
) -> list[dict[str, int]] | None:
    """Prove a singleton or a simple literal-seeded linear loop address range."""
    seed_index = None
    start = None
    for index in range(access_index - 1, -1, -1):
        row = program[index]["row"]
        if not row:
            continue
        if writes_register(row, address_register):
            if row[0] == "move" and len(row) >= 3:
                start = resolve_integer(row[2], integer_aliases)
                seed_index = index
            break
    if (
        seed_index is None or start is None or not 0 <= start <= 511
        or not control_flow_complete or seed_index not in dominators.get(access_index, set())
    ):
        return None

    loop_label = None
    label_index = None
    for index in range(seed_index + 1, access_index + 1):
        if program[index]["label"]:
            loop_label = program[index]["label"]
            label_index = index
    if loop_label is None:
        return [{"start": start, "end": start}]

    branch_index = None
    branch = None
    for index in range(access_index + 1, min(len(program), access_index + 80)):
        row = program[index]["row"]
        if row and row[0] == "move" and len(row) >= 2 and row[1] == address_register:
            break
        if row and row[0] in {"ble", "blt"} and len(row) >= 4 and row[-1] == loop_label:
            branch_index = index
            branch = row
            break
        if program[index]["label"] and index > access_index + 1:
            break
    if branch_index is None or branch is None or label_index is None:
        if can_reach(access_index, access_index, successors):
            return None
        return [{"start": start, "end": start}]

    if label_index not in successors.get(branch_index, set()):
        return None
    loop_nodes = set(range(label_index, branch_index + 1))
    backedges = {
        (source, target)
        for source in loop_nodes
        for target in successors.get(source, set())
        if label_index <= target <= source
    }
    if backedges != {(branch_index, label_index)}:
        return None
    allowed_entry = {(label_index - 1, label_index)} if label_index else set()
    external_entries = {
        (source, target)
        for source, targets in successors.items()
        if source not in loop_nodes
        for target in targets
        if target in loop_nodes
    }
    if external_entries - allowed_entry:
        return None
    if any(successors.get(index, set()) != {index + 1} for index in range(label_index, access_index)):
        return None

    address_updates = []
    for index in range(access_index + 1, branch_index):
        row = program[index]["row"]
        if row and row[0] == "add" and len(row) >= 4 and row[1] == address_register and row[2] == address_register:
            address_updates.append((index, resolve_integer(row[3], integer_aliases)))
    counter = branch[1]
    if counter == address_register:
        return None
    limit = resolve_integer(branch[2], integer_aliases)
    counter_updates = []
    for index in range(access_index + 1, branch_index):
        row = program[index]["row"]
        if row and row[0] == "add" and len(row) >= 4 and row[1] == counter and row[2] == counter:
            counter_updates.append((index, resolve_integer(row[3], integer_aliases)))
    counter_start = None
    for index in range(label_index - 1, max(-1, seed_index - 40), -1):
        row = program[index]["row"]
        if row and writes_register(row, counter):
            if row[0] == "move" and len(row) >= 3:
                counter_start = resolve_integer(row[2], integer_aliases)
            break
    if (
        len(address_updates) != 1 or len(counter_updates) != 1
        or counter_start is None or limit is None
    ):
        return None
    address_update_index, address_step = address_updates[0]
    counter_update_index, counter_step = counter_updates[0]
    if address_step is None or counter_step is None or counter_step <= 0:
        return None
    if (
        address_update_index not in dominators.get(branch_index, set())
        or counter_update_index not in dominators.get(branch_index, set())
    ):
        return None
    counter_seed_index = next(
        (
            index for index in range(label_index - 1, max(-1, seed_index - 40), -1)
            if program[index]["row"] and writes_register(program[index]["row"], counter)
        ),
        None,
    )
    if counter_seed_index is None or counter_seed_index not in dominators.get(label_index, set()):
        return None
    address_writes = [
        index for index in range(label_index, branch_index)
        if program[index]["row"] and writes_register(program[index]["row"], address_register)
    ]
    counter_writes = [
        index for index in range(label_index, branch_index)
        if program[index]["row"] and writes_register(program[index]["row"], counter)
    ]
    if address_writes != [address_update_index] or counter_writes != [counter_update_index]:
        return None

    count = 1
    current = counter_start
    while count <= 512:
        current += counter_step
        continues = current <= limit if branch[0] == "ble" else current < limit
        if not continues:
            break
        count += 1
    else:
        return None
    addresses = [start + iteration * address_step for iteration in range(count)]
    if any(not 0 <= address <= 511 for address in addresses):
        return None
    return merge_ranges([{"start": address, "end": address} for address in set(addresses)])


def dynamic_range_proofs(
    source: str, integer_aliases: dict[str, int], accesses: list[tuple[int, Any, str]]
) -> dict[Any, dict[str, Any]]:
    """Apply the shared strict linear-loop proof to classified dynamic accesses."""
    program = parse_program(source)
    dominators, predecessors, successors, control_flow_complete = control_flow_dominators(program)
    proofs: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "proved_accesses": 0, "ranges": []}
    )
    for index, key, address_token in accesses:
        proof = proofs[key]
        proof["total"] += 1
        inferred = linear_dynamic_range(
            program, index, address_token, integer_aliases, dominators, predecessors, successors,
            control_flow_complete
        )
        if inferred is not None:
            proof["proved_accesses"] += 1
            proof["ranges"].extend(inferred)
    for proof in proofs.values():
        proof["ranges"] = merge_ranges(proof["ranges"])
    return proofs


def dynamic_port_proofs(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int]
) -> dict[tuple[str, str], dict[str, Any]]:
    accesses: list[tuple[int, tuple[str, str], str]] = []
    for index, entry in enumerate(parse_program(source)):
        row = entry["row"]
        port = direction = address_token = None
        if row and row[0] == "get" and len(row) >= 4:
            port = resolve_port(row[2], aliases)
            direction = "read"
            address_token = row[3]
        elif row and row[0] == "put" and len(row) >= 4:
            port = resolve_port(row[1], aliases)
            direction = "write"
            address_token = row[2]
        if port is None or direction is None or address_token is None or resolve_integer(address_token, integer_aliases) is not None:
            continue
        accesses.append((index, (port, direction), address_token))
    return dynamic_range_proofs(source, integer_aliases, accesses)


def resolve_dynamic_ranges(
    dynamic: bool, proof: dict[str, Any], declared_ranges: list[dict[str, int]], context: str,
    fallback_full_stack: bool = False,
) -> tuple[list[dict[str, int]], str]:
    if not dynamic:
        if declared_ranges:
            raise ValueError(f"{context} declares ranges without a dynamic access")
        return [], "none"
    inferred_ranges = proof["ranges"]
    inferred_cells = {
        address for value in inferred_ranges for address in range(value["start"], value["end"] + 1)
    }
    declared_cells = {
        address for value in declared_ranges for address in range(value["start"], value["end"] + 1)
    }
    all_proven = proof["total"] > 0 and proof["proved_accesses"] == proof["total"]
    if all_proven:
        if declared_ranges and declared_cells != inferred_cells:
            raise ValueError(
                f"{context} range {declared_ranges} disagrees with source-derived {inferred_ranges}"
            )
        return inferred_ranges, "source-derived"
    if declared_ranges:
        if not inferred_cells <= declared_cells:
            raise ValueError(
                f"{context} range {declared_ranges} omits source-proven cells "
                f"{sorted(inferred_cells-declared_cells)}"
            )
        return declared_ranges, "source-fingerprinted-exception"
    if fallback_full_stack:
        return [{"start": 0, "end": 511}], "conservative-full-stack"
    return [], "source-fingerprinted-exception"
