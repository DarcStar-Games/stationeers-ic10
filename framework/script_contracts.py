"""Extract deterministic machine-readable contracts from deployable IC10 programs."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import json
import math
import re
from typing import Any

from framework.source_metadata import deployable_scripts, load_manifest, resolve_script_metadata

FORMAT = "IC10_SCRIPT_CONTRACT_V2"
INDEX_FORMAT = "IC10_SCRIPT_CONTRACT_INDEX_V1"
PROTOCOL_FORMAT = "IC10_STACK_PROTOCOL_REGISTRY_V1"
PROTOCOL_DEFINITION_FORMAT = "IC10_PROTOCOL_DEFINITION_V1"
PORTS = tuple(f"d{i}" for i in range(6))
VERSION_RE = re.compile(r"_v(\d+)_(\d+)\.ic10$")
INTEGER_RE = re.compile(r"^-?\d+$")
DYNAMIC_PROPERTY_RE = re.compile(r"^(?:r(?:1[0-7]|[0-9])|ra|sp)$")
SEMANTIC_WORDS = re.compile(
    r"(?i)\b(generation|token|status|state|reference\s*id|schema|count|capacity|width|epoch|revision|sequence|"
    r"reserved|owner|unit|class|kind|mode|identity|pressure|temperature|quantity|rate|cost|signature|command)\b"
)
SUPPLEMENTAL_REFS = {
    "input-profile-catalog": "data/input_profiles.json#",
    "resource-profile-catalog": "data/resource_profiles.json#",
    "transform-catalog": "data/resource_transforms.json#",
}


def generated_artifact_paths(root: Path, pattern: str) -> set[Path]:
    return set((Path(root) / "contracts").rglob(pattern))


def verify_override_source(path: Path, override: dict[str, Any]) -> None:
    actual_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if override.get("source_sha256") != actual_sha256:
        raise ValueError(
            f"contract override source fingerprint mismatch for {path}; "
            "re-review dynamic ranges and semantic exceptions before updating source_sha256"
        )


def _instructions(source: str) -> list[list[str]]:
    rows = []
    for raw in source.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code or code.endswith(":"):
            continue
        rows.append(code.replace(",", " ").split())
    return rows


def _program(source: str) -> list[dict[str, Any]]:
    program: list[dict[str, Any]] = []
    for raw in source.splitlines():
        code = raw.split("#", 1)[0].strip()
        if not code:
            continue
        if code.endswith(":"):
            program.append({"label": code[:-1], "row": []})
        else:
            program.append({"label": None, "row": code.replace(",", " ").split()})
    return program


def _row_nodes(program: list[dict[str, Any]]) -> list[int]:
    return [index for index, entry in enumerate(program) if entry["row"]]


def _aliases(rows: list[list[str]]) -> tuple[dict[str, str], dict[str, int]]:
    ports: dict[str, str] = {}
    integers: dict[str, int] = {}
    for row in rows:
        if len(row) != 3 or row[0] != "alias":
            continue
        if row[2] in PORTS:
            ports[row[1]] = row[2]
        elif INTEGER_RE.fullmatch(row[2]):
            integers[row[1]] = int(row[2])
    return ports, integers


def _port(token: str, aliases: dict[str, str]) -> str | None:
    return token if token in PORTS else aliases.get(token)


def _integer(token: str, aliases: dict[str, int]) -> int | None:
    if INTEGER_RE.fullmatch(token):
        return int(token)
    return aliases.get(token)


def _literal_value(token: str, aliases: dict[str, int]) -> int | float | str | None:
    integer = _integer(token, aliases)
    if integer is not None:
        return integer
    try:
        number = float(token)
        return number if math.isfinite(number) else token.lower()
    except ValueError:
        pass
    if re.fullmatch(r'HASH\("[^"\n]+"\)', token):
        return token
    return None


def _external_equality_checks(
    source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int]
) -> dict[str, dict[int, set[Any]]]:
    program = _program(source)
    row_nodes = _row_nodes(program)
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    _, _, successors, _ = _control_flow_dominators(program)
    checks: dict[str, dict[int, set[Any]]] = defaultdict(lambda: defaultdict(set))
    for index, row in enumerate(rows):
        if len(row) < 4 or row[0] != "get":
            continue
        port = _port(row[2], aliases)
        cell = _integer(row[3], integer_aliases)
        if port is None or cell is None or not 0 <= cell <= 511:
            continue
        register = row[1]
        for later_index, later in enumerate(rows[index + 1:index + 6], index + 1):
            if len(later) >= 3 and later[0] == "bne" and later[1] == register:
                expected = _literal_value(later[2], integer_aliases)
                read_node = row_nodes[index]
                compare_node = row_nodes[later_index]
                fallthrough_node = compare_node + 1 if compare_node + 1 < len(program) else None
                if (
                    expected is not None
                    and fallthrough_node is not None
                    and _must_reach(read_node, compare_node, successors)
                    and _paths_preserve_register(read_node, compare_node, register, program, successors)
                    and _branch_rejects_before_success(
                        later, compare_node, fallthrough_node, {read_node}, program,
                        side_effect_barriers=True,
                    )
                ):
                    checks[port][cell].add(expected)
                break
            if len(later) >= 2 and later[1] == register and later[0] not in {"beq", "bne", "beqz", "bnez"}:
                break
    return checks


def _revision(path: Path) -> str:
    match = VERSION_RE.search(path.name)
    if not match:
        raise ValueError(f"versioned IC10 filename required: {path}")
    return f"{match.group(1)}.{match.group(2)}"


def _service_id(path: Path) -> str:
    stem = re.sub(r"_v\d+_\d+$", "", path.stem)
    return "ic10.script." + stem.replace("_", ".")


def _protocol_id(magic: int, abi: int) -> str:
    return f"ic10.stack.{magic}.abi{abi}"


def _protocol_name(pid: str, abi: int, provider_sources: list[str], definitions: dict[str, Any]) -> str:
    if pid in definitions and definitions[pid].get("name"):
        return definitions[pid]["name"]
    if pid.startswith("ic10.stack.27182818."):
        return f"Generic Controller Telemetry ABI{abi}"
    if provider_sources:
        stem = re.sub(r"_v\d+_\d+$", "", Path(provider_sources[0]).stem)
        return f"{' '.join(word.capitalize() for word in stem.split('_'))} ABI{abi}"
    return pid


def _verify_declared_headers(rows: list[list[str]], integer_aliases: dict[str, int], declared: list[dict[str, int]]) -> list[dict[str, int]]:
    writes: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        if len(row) >= 3 and row[0] == "poke":
            address = _integer(row[1], integer_aliases)
            value = _integer(row[2], integer_aliases)
            if address is not None and value is not None and 0 <= address <= 511:
                writes[address].add(value)
    headers = []
    for header in declared:
        base = header["base"]; magic = header["magic"]; abi = header["abi"]
        if not 0 <= base < 511 or magic <= 0 or abi <= 0:
            raise ValueError(f"invalid declared header: {header}")
        if magic not in writes[base] or abi not in writes[base + 1]:
            raise ValueError(f"declared header {header} is not written literally by source")
        headers.append({"base": base, "magic": magic, "abi": abi})
    return sorted(headers, key=lambda item: (item["base"], item["magic"], item["abi"]))


def _ranges(value: Any) -> list[dict[str, int]]:
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


def _merge_ranges(ranges: list[dict[str, int]]) -> list[dict[str, int]]:
    merged: list[dict[str, int]] = []
    for item in sorted(ranges, key=lambda value: (value["start"], value["end"])):
        if merged and item["start"] <= merged[-1]["end"] + 1:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        else:
            merged.append(dict(item))
    return merged


def _writes_register(row: list[str], register: str) -> bool:
    if row and register == "sp" and row[0] in {"push", "pop"}:
        return True
    if len(row) < 2 or row[1] != register:
        return False
    return row[0] not in {
        "b", "beq", "bne", "beqz", "bnez", "bdns", "bdse", "j", "jal", "jr",
        "poke", "push", "put", "putd", "s", "sb", "sbn", "sr", "ss",
    } and not row[0].startswith("bdn")


def _control_flow_dominators(
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


def _can_reach(start: int, target: int, successors: dict[int, set[int]]) -> bool:
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


def _can_reach_avoiding_calls(
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


def _reachable_states_avoiding_calls(
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


def _must_reach(start: int, target: int, successors: dict[int, set[int]]) -> bool:
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


def _all_paths_retain_target(
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


def _nodes_before_target(
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


def _paths_preserve_register(
    start: int, target: int, register: str, program: list[dict[str, Any]],
    successors: dict[int, set[int]],
) -> bool:
    return not any(
        program[node]["row"] and _writes_register(program[node]["row"], register)
        for node in _nodes_before_target(start, target, successors)
    )


def _first_executable_node(
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


def _fallthrough_spine(
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


def _branch_rejects_before_success(
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
    _, _, successors, _ = _control_flow_dominators(program)
    for node in range(len(program)):
        if _first_executable_node(node, program, successors) in yield_nodes | side_effect_nodes:
            barriers.add(node)
    success_spine = _fallthrough_spine(
        success_node, program, barriers, max(reset_nodes, default=-1)
    )
    failure_states = _reachable_states_avoiding_calls(target_node, program, barriers)
    return success_spine.isdisjoint(failure_states)


def _linear_dynamic_range(
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
        if _writes_register(row, address_register):
            if row[0] == "move" and len(row) >= 3:
                start = _integer(row[2], integer_aliases)
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
        if _can_reach(access_index, access_index, successors):
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
            address_updates.append((index, _integer(row[3], integer_aliases)))
    counter = branch[1]
    if counter == address_register:
        return None
    limit = _integer(branch[2], integer_aliases)
    counter_updates = []
    for index in range(access_index + 1, branch_index):
        row = program[index]["row"]
        if row and row[0] == "add" and len(row) >= 4 and row[1] == counter and row[2] == counter:
            counter_updates.append((index, _integer(row[3], integer_aliases)))
    counter_start = None
    for index in range(label_index - 1, max(-1, seed_index - 40), -1):
        row = program[index]["row"]
        if row and _writes_register(row, counter):
            if row[0] == "move" and len(row) >= 3:
                counter_start = _integer(row[2], integer_aliases)
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
            if program[index]["row"] and _writes_register(program[index]["row"], counter)
        ),
        None,
    )
    if counter_seed_index is None or counter_seed_index not in dominators.get(label_index, set()):
        return None
    address_writes = [
        index for index in range(label_index, branch_index)
        if program[index]["row"] and _writes_register(program[index]["row"], address_register)
    ]
    counter_writes = [
        index for index in range(label_index, branch_index)
        if program[index]["row"] and _writes_register(program[index]["row"], counter)
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
    return _merge_ranges([{"start": address, "end": address} for address in set(addresses)])


def _dynamic_range_proofs(
    source: str, integer_aliases: dict[str, int], accesses: list[tuple[int, Any, str]]
) -> dict[Any, dict[str, Any]]:
    """Apply the shared strict linear-loop proof to classified dynamic accesses."""
    program = _program(source)
    dominators, predecessors, successors, control_flow_complete = _control_flow_dominators(program)
    proofs: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "proved_accesses": 0, "ranges": []}
    )
    for index, key, address_token in accesses:
        proof = proofs[key]
        proof["total"] += 1
        inferred = _linear_dynamic_range(
            program, index, address_token, integer_aliases, dominators, predecessors, successors,
            control_flow_complete
        )
        if inferred is not None:
            proof["proved_accesses"] += 1
            proof["ranges"].extend(inferred)
    for proof in proofs.values():
        proof["ranges"] = _merge_ranges(proof["ranges"])
    return proofs


def _dynamic_port_proofs(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int]
) -> dict[tuple[str, str], dict[str, Any]]:
    accesses: list[tuple[int, tuple[str, str], str]] = []
    for index, entry in enumerate(_program(source)):
        row = entry["row"]
        port = direction = address_token = None
        if row and row[0] == "get" and len(row) >= 4:
            port = _port(row[2], aliases)
            direction = "read"
            address_token = row[3]
        elif row and row[0] == "put" and len(row) >= 4:
            port = _port(row[1], aliases)
            direction = "write"
            address_token = row[2]
        if port is None or direction is None or address_token is None or _integer(address_token, integer_aliases) is not None:
            continue
        accesses.append((index, (port, direction), address_token))
    return _dynamic_range_proofs(source, integer_aliases, accesses)


def _resolve_dynamic_ranges(
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


def _stable_cells(
    source: str, integer_aliases: dict[str, int], expected: dict[int, Any]
) -> set[int]:
    """Find cells initialized to an expected value before every observable control-flow boundary."""
    program = _program(source)
    if not program:
        return set()

    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    entry = (0, ())
    reachable: set[tuple[int, tuple[int, ...]]] = set()
    successors: dict[tuple[int, tuple[int, ...]], set[tuple[int, tuple[int, ...]]]] = defaultdict(set)
    terminal_states: set[tuple[int, tuple[int, ...]]] = set()
    pending = [entry]
    control_flow_complete = True
    while pending:
        state = pending.pop()
        if state in reachable:
            continue
        if len(reachable) >= 8192:
            control_flow_complete = False
            break
        reachable.add(state)
        index, return_stack = state
        row = program[index]["row"]
        fallthrough = index + 1 if index + 1 < len(program) else None
        outgoing: set[tuple[int, tuple[int, ...]]] = set()
        if return_stack and row and row[0] != "jal" and _writes_register(row, "ra"):
            control_flow_complete = False
            successors[state] = outgoing
            continue
        if not row:
            if fallthrough is not None:
                outgoing.add((fallthrough, return_stack))
        elif row[0] == "jal":
            target = labels.get(row[-1])
            if target is None or fallthrough is None or return_stack:
                control_flow_complete = False
            else:
                outgoing.add((target, return_stack + (fallthrough,)))
        elif row[0] in {"j", "jr"}:
            if row[-1] == "ra":
                if return_stack:
                    outgoing.add((return_stack[-1], return_stack[:-1]))
            else:
                target = labels.get(row[-1])
                if target is None:
                    control_flow_complete = False
                else:
                    outgoing.add((target, return_stack))
        elif row[0].endswith("al"):
            control_flow_complete = False
        elif row[0] == "hcf":
            pass
        elif row[0].startswith("b"):
            if row[-1] == "ra":
                if return_stack:
                    outgoing.add((return_stack[-1], return_stack[:-1]))
                else:
                    terminal_states.add(state)
            else:
                target = labels.get(row[-1])
                if target is None:
                    control_flow_complete = False
                else:
                    outgoing.add((target, return_stack))
            if fallthrough is not None:
                outgoing.add((fallthrough, return_stack))
        elif fallthrough is not None:
            outgoing.add((fallthrough, return_stack))
        successors[state] = outgoing
        pending.extend(outgoing - reachable)
    if not control_flow_complete:
        return set()

    predecessors: dict[tuple[int, tuple[int, ...]], set[tuple[int, tuple[int, ...]]]] = defaultdict(set)
    for state, outgoing in successors.items():
        for target in outgoing:
            predecessors[target].add(state)
    observations = {
        state for state in reachable
        if (
            (program[state[0]]["row"] and program[state[0]]["row"][0] in {"yield", "hcf"})
            or state in terminal_states
            or not successors.get(state, set())
            or any(
                target[0] <= state[0] and target[1] == state[1]
                for target in successors.get(state, set())
            )
        )
    }
    if not observations:
        return set()

    stable: set[int] = set()
    for address, value in expected.items():
        matching_writes = {
            state for state in reachable
            if (
                program[state[0]]["row"]
                and program[state[0]]["row"][0] == "poke"
                and len(program[state[0]]["row"]) >= 3
                and _integer(program[state[0]]["row"][1], integer_aliases) == address
                and _literal_value(program[state[0]]["row"][2], integer_aliases) == value
            )
        }
        initialized_after = {state: True for state in reachable}
        changed = True
        while changed:
            changed = False
            for state in sorted(reachable):
                incoming = predecessors.get(state, set()) & reachable
                initialized_before = False if state == entry else bool(incoming) and all(
                    initialized_after[parent] for parent in incoming
                )
                updated = initialized_before or state in matching_writes
                if updated != initialized_after[state]:
                    initialized_after[state] = updated
                    changed = True
        if all(initialized_after[state] for state in observations):
            stable.add(address)
    return stable


def _semantic_name(comment: str) -> str | None:
    if not SEMANTIC_WORDS.search(comment):
        return None
    phrase = re.split(r"[;,(]|\bLAST\b|\bafter\b|\bbefore\b|\bsupplied\b|\bfrom\b", comment, maxsplit=1, flags=re.IGNORECASE)[0]
    phrase = re.sub(r"(?i)\b(current|initial|opaque|exact|published|committed|physical)\b", " ", phrase)
    words = re.findall(r"[A-Za-z]+|[0-9]+", phrase)
    if not words or len(words) > 6:
        return None
    return "".join(word if re.search(r"[A-Z].*[A-Z]|Id$", word) else word[:1].upper() + word[1:] for word in words)


def _value_type(name: str, comment: str) -> str:
    text = f"{name} {comment}".lower()
    if "referenceid" in text.replace(" ", "") or "reference id" in text:
        return "reference-id"
    if "hash" in text or "schema" in text or "identity" in text or "type" in text:
        return "hash"
    if any(word in text for word in ("status", "state", "mode", "kind", "class", "unit")):
        return "enum"
    if any(word in text for word in ("generation", "token", "epoch", "revision", "sequence", "count", "capacity", "width", "slot")):
        return "integer"
    return "number"


def _commit_last_violation(lines: list[str], marker_index: int) -> str | None:
    labels = {
        line.split("#", 1)[0].strip()[:-1]: index
        for index, line in enumerate(lines)
        if line.split("#", 1)[0].strip().endswith(":")
    }
    pending = [marker_index + 1]
    visited: set[int] = set()
    while pending:
        index = pending.pop()
        while 0 <= index < len(lines) and index not in visited:
            visited.add(index)
            code = lines[index].split("#", 1)[0].strip()
            if not code or code.endswith(":"):
                index += 1
                continue
            row = code.replace(",", " ").split()
            if row[0] in {"poke", "push"} or (row[0] == "clr" and len(row) >= 2 and row[1] == "db"):
                return code
            if row[0] == "yield":
                break
            if row[0] == "jal":
                return f"unproved call after publication marker: {code}"
            if row[0] in {"j", "jr"}:
                target = row[-1]
                if target in labels:
                    index = labels[target]
                    continue
                break
            if row[0].startswith("b") and row[-1] in labels:
                pending.append(labels[row[-1]])
            index += 1
    return None


def _source_semantics(source: str, integer_aliases: dict[str, int]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Extract semantics explicitly documented next to literal own-stack accesses."""
    annotations: dict[int, dict[str, Any]] = defaultdict(lambda: {"descriptions": [], "enums": []})
    publication_rules: list[dict[str, Any]] = []
    lines = source.splitlines()
    for line_index, raw in enumerate(lines):
        code, separator, comment_text = raw.partition("#")
        comment = comment_text.strip() if separator else ""
        row = code.strip().replace(",", " ").split()
        if not row:
            continue
        address = None
        value = None
        if row[0] == "poke" and len(row) >= 3:
            address = _integer(row[1], integer_aliases)
            value = _literal_value(row[2], integer_aliases)
        elif row[0] == "get" and len(row) >= 4 and row[2] == "db":
            address = _integer(row[3], integer_aliases)
        if address is None or not 0 <= address <= 511:
            continue
        target = annotations[address]
        if comment and comment not in target["descriptions"]:
            target["descriptions"].append(comment)
        name = _semantic_name(comment)
        if name and "name" not in target:
            target["name"] = name
        state_comment = re.split(r"\s+#", comment, maxsplit=1)[0].strip()
        if value is not None and re.fullmatch(r"[A-Z][A-Z0-9 _/-]{1,30}", state_comment):
            enum_name = re.sub(r"[^A-Z0-9]+", "_", state_comment).strip("_")
            entry = {"value": value, "name": enum_name}
            if entry not in target["enums"]:
                target["enums"].append(entry)
        named_enum = re.fullmatch(r"(.+?)\s+([A-Z][A-Z0-9_/-]+)", state_comment)
        if value is not None and named_enum and SEMANTIC_WORDS.search(named_enum.group(1)):
            enum_name = re.sub(r"[^A-Z0-9]+", "_", named_enum.group(2)).strip("_")
            entry = {"value": value, "name": enum_name}
            if entry not in target["enums"]:
                target["enums"].append(entry)
        if "reserved" in comment.lower():
            target["reserved"] = True
        if "last" in comment.lower() and "identity" not in comment.lower() and row[0] == "poke":
            violation = _commit_last_violation(lines, line_index)
            if violation is not None:
                raise ValueError(
                    f"commit-last claim at source line {line_index + 1} is followed by own-stack write: {violation}"
                )
            publication_rules.append({
                "kind": "commit-last",
                "address": address,
                "description": comment,
                "source": "verified-inline-order",
            })
        if "seqlock" in comment.lower() or "odd/even" in comment.lower():
            raise ValueError(
                f"seqlock claim at source line {line_index + 1} requires an explicit odd/even source verifier"
            )
    unique_rules = {(item["kind"], item["address"], item["description"]): item for item in publication_rules}
    return annotations, sorted(unique_rules.values(), key=lambda item: (item["address"], item["kind"], item["description"]))


def _verified_publication_overrides(
    source: str, rows: list[list[str]], integer_aliases: dict[str, int], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    program = _program(source)
    row_nodes = _row_nodes(program)
    _, _, successors, _ = _control_flow_dominators(program)
    rules = []
    for declared in overrides.get("publication_rules", []):
        if declared["kind"] != "seqlock":
            raise ValueError(f"unsupported publication override: {declared}")
        address = declared["address"]
        reads = [
            row for row in rows
            if len(row) >= 4 and row[0] == "get" and row[2] == "db" and _integer(row[3], integer_aliases) == address
        ]
        writes = [
            (index, row) for index, row in enumerate(rows)
            if len(row) >= 3 and row[0] == "poke" and _integer(row[1], integer_aliases) == address
        ]
        if not reads or len(writes) < 2:
            raise ValueError(
                f"seqlock S{address} requires a literal read and at least two publication writes"
            )
        verification = declared.get("verification")
        if verification == "paired-sequence":
            verified_pair = False
            for pair_index, (first_index, first_row) in enumerate(writes[:-1]):
                second_index, second_row = writes[pair_index + 1]
                first_node = row_nodes[first_index]
                second_node = row_nodes[second_index]
                yield_nodes = {
                    node for node, entry in enumerate(program)
                    if entry["row"] and entry["row"][0] == "yield"
                }
                if any(
                    _can_reach_avoiding_calls(
                        first_node, yield_node, program, {second_node}
                    )
                    for yield_node in yield_nodes
                ):
                    continue
                if not _all_paths_retain_target(
                    first_node, second_node, successors, yield_nodes
                ):
                    continue
                if not _can_reach_avoiding_calls(
                    first_node, second_node, program, yield_nodes
                ):
                    continue
                payload_indices = [
                    index for index, row in enumerate(
                        rows[first_index + 1:second_index], first_index + 1
                    )
                    if row[0] in {"poke", "put", "putd"}
                    and not (row[0] == "poke" and _integer(row[1], integer_aliases) == address)
                ]
                if not any(
                    _can_reach_avoiding_calls(
                        first_node, row_nodes[payload_index], program, yield_nodes
                    )
                    and _can_reach_avoiding_calls(
                        row_nodes[payload_index], second_node, program, yield_nodes
                    )
                    for payload_index in payload_indices
                ):
                    continue
                pair_ok = True
                previous_add_index = None
                for write_index, write_row in ((first_index, first_row), (second_index, second_row)):
                    register = write_row[2]
                    add_index = next(
                        (
                            index for index in range(write_index - 1, max(-1, write_index - 5), -1)
                            if _writes_register(rows[index], register)
                        ),
                        None,
                    )
                    if add_index is None:
                        pair_ok = False
                        break
                    add_row = rows[add_index]
                    if not (
                        len(add_row) >= 4 and add_row[0] == "add"
                        and add_row[1] == register and add_row[2] == register
                        and _integer(add_row[3], integer_aliases) == 1
                    ):
                        pair_ok = False
                        break
                    prior_write = next(
                        (
                            index for index in range(add_index - 1, -1, -1)
                            if _writes_register(rows[index], register)
                        ),
                        None,
                    )
                    read_current = (
                        prior_write is not None
                        and len(rows[prior_write]) >= 4
                        and rows[prior_write][0] == "get"
                        and rows[prior_write][2] == "db"
                        and _integer(rows[prior_write][3], integer_aliases) == address
                    )
                    carried_from_first = previous_add_index is not None and prior_write == previous_add_index
                    if not read_current and not carried_from_first:
                        pair_ok = False
                        break
                    previous_add_index = add_index
                if pair_ok:
                    verified_pair = True
                    break
            if not verified_pair:
                raise ValueError(f"seqlock S{address} has no verified odd/payload/even publication pair")
            source = "source-fingerprinted-paired-sequence"
        elif verification == "source-declaration":
            source = "source-fingerprinted-declaration"
        else:
            raise ValueError(f"seqlock S{address} requires an explicit verification mode")
        rules.append({
            "kind": "seqlock",
            "address": address,
            "description": declared["description"],
            "source": source,
        })
    return rules


def _network_dependencies(
    source: str, rows: list[list[str]], integer_aliases: dict[str, int], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    program = _program(source)
    row_nodes = _row_nodes(program)
    _, _, successors, _ = _control_flow_dominators(program)
    dependencies: dict[tuple[str, str], dict[str, Any]] = {}

    def ensure(reference: str, transport: str) -> dict[str, Any]:
        return dependencies.setdefault((transport, reference), {
            "transport": transport,
            "reference": reference,
            "literal_reads": set(),
            "literal_writes": set(),
            "dynamic_read": False,
            "dynamic_write": False,
            "constraints": [],
            "accepted": [],
        })

    for index, row in enumerate(rows):
        register = None
        if row[0] == "getd" and len(row) >= 4:
            target = ensure(row[2], "reference-id")
            address = _integer(row[3], integer_aliases)
            target["dynamic_read"] |= address is None
            if address is not None:
                target["literal_reads"].add(address)
            register = row[1]
        elif row[0] == "putd" and len(row) >= 4:
            target = ensure(row[1], "reference-id")
            address = _integer(row[2], integer_aliases)
            target["dynamic_write"] |= address is None
            if address is not None:
                target["literal_writes"].add(address)
        elif row[0] == "get" and len(row) >= 4 and row[2].startswith("db:"):
            target = ensure(row[2], "device-index")
            address = _integer(row[3], integer_aliases)
            target["dynamic_read"] |= address is None
            if address is not None:
                target["literal_reads"].add(address)
            register = row[1]
        else:
            continue
        if register is None:
            continue
        read_node = row_nodes[index]
        check_start_node = read_node
        for later_index, later in enumerate(rows[index + 1:index + 5], index + 1):
            if len(later) >= 3 and later[1] == register and later[0] in {"bne", "blt", "bgt"}:
                value = _literal_value(later[2], integer_aliases)
                compare_node = row_nodes[later_index]
                verified = (
                    value is not None
                    and address is not None
                    and _must_reach(check_start_node, compare_node, successors)
                    and _paths_preserve_register(
                        check_start_node, compare_node, register, program, successors
                    )
                    and _branch_rejects_before_success(
                        later, compare_node, compare_node + 1, {read_node}, program,
                        side_effect_barriers=True,
                    )
                )
                if verified:
                    operator = {"bne": "equals", "blt": "minimum", "bgt": "maximum"}[later[0]]
                    target["constraints"].append({"address": address, "operator": operator, "value": value})
                    check_start_node = compare_node + 1
                    continue
                break
            if len(later) >= 2 and later[1] == register and later[0] not in {"beq", "bne", "blt", "bgt", "ble", "bge", "beqz", "bnez"}:
                break

    for declaration in overrides.get("network_protocols", []):
        key = (declaration.get("transport", "reference-id"), declaration["reference"])
        if key not in dependencies:
            raise ValueError(f"network protocol declaration has no matching access: {declaration}")
        constraints = dependencies[key]["constraints"]
        magic_ok = any(item == {"address": declaration["header_base"], "operator": "equals", "value": declaration["magic"]} for item in constraints)
        abi_constraints = [item for item in constraints if item["address"] == declaration["header_base"] + 1]
        exact_abis = {item["value"] for item in abi_constraints if item["operator"] == "equals"}
        minimums = [item["value"] for item in abi_constraints if item["operator"] == "minimum" and isinstance(item["value"], int)]
        maximums = [item["value"] for item in abi_constraints if item["operator"] == "maximum" and isinstance(item["value"], int)]
        declared_abis = set(range(declaration["abi_min"], declaration["abi_max"] + 1))
        abi_ok = declared_abis <= exact_abis or (
            minimums and maximums
            and max(minimums) == declaration["abi_min"]
            and min(maximums) == declaration["abi_max"]
        )
        if not magic_ok or not abi_ok:
            raise ValueError(f"network protocol declaration is not enforced by source checks: {declaration}")
        for abi in range(declaration["abi_min"], declaration["abi_max"] + 1):
            dependencies[key]["accepted"].append({
                "protocol_id": _protocol_id(declaration["magic"], abi),
                "header_base": declaration["header_base"],
                "magic": declaration["magic"],
                "abi": abi,
                "publication_requirements": declaration.get("publication_requirements", []),
            })

    result = []
    for key in sorted(dependencies):
        item = dependencies[key]
        item["literal_reads"] = sorted(item["literal_reads"])
        item["literal_writes"] = sorted(item["literal_writes"])
        unique_constraints = {
            (value["address"], value["operator"], type(value["value"]).__name__, str(value["value"])): value
            for value in item["constraints"]
        }
        item["constraints"] = sorted(unique_constraints.values(), key=lambda value: (value["address"], value["operator"], str(value["value"])))
        item["accepted"] = sorted(item["accepted"], key=lambda value: (value["header_base"], value["magic"], value["abi"]))
        result.append(item)
    return result


def _device_ports(source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int], overrides: dict[str, Any]) -> list[dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    alias_names: dict[str, list[str]] = defaultdict(list)
    for name, port in aliases.items():
        alias_names[port].append(name)

    def ensure(port: str) -> dict[str, Any]:
        return state.setdefault(port, {
            "port": port,
            "role": sorted(alias_names[port])[0] if alias_names[port] else port,
            "aliases": sorted(alias_names[port]),
            "requirement": "required",
            "device_properties": {"reads": set(), "writes": set(), "slot_reads": set(), "slot_writes": set()},
            "stack": {"literal_reads": set(), "literal_writes": set(), "dynamic_read": False, "dynamic_write": False,
                      "dynamic_read_ranges": [], "dynamic_write_ranges": [], "dynamic_read_range_source": "none",
                      "dynamic_write_range_source": "none", "constraints": []},
        })

    comments = "\n".join(line for line in source.splitlines()[:6] if line.lstrip().startswith("#"))
    optional_ports = set()
    port_mentions = list(re.finditer(r"\bd[0-5]\b", comments))
    for index, mention in enumerate(port_mentions):
        end = port_mentions[index + 1].start() if index + 1 < len(port_mentions) else len(comments)
        clause = comments[mention.start():end]
        if "optional" in clause.lower():
            optional_ports.add(mention.group())
    for row in rows:
        if row[0] == "alias":
            continue
        referenced = {_port(token, aliases) for token in row}
        for port in referenced - {None}:
            ensure(port)
        op = row[0]
        if op == "get" and len(row) >= 4:
            port = _port(row[2], aliases)
            if port:
                address = _integer(row[3], integer_aliases)
                target = ensure(port)["stack"]
                target["dynamic_read"] |= address is None
                if address is not None:
                    target["literal_reads"].add(address)
        elif op == "put" and len(row) >= 4:
            port = _port(row[1], aliases)
            if port:
                address = _integer(row[2], integer_aliases)
                target = ensure(port)["stack"]
                target["dynamic_write"] |= address is None
                if address is not None:
                    target["literal_writes"].add(address)
        elif op in {"l", "lr"} and len(row) >= 4:
            port = _port(row[2], aliases)
            if port:
                ensure(port)["device_properties"]["reads"].add(row[3])
        elif op in {"s", "sr"} and len(row) >= 4:
            port = _port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["writes"].add(row[2])
        elif op == "ls" and len(row) >= 5:
            port = _port(row[2], aliases)
            if port:
                slot = _integer(row[3], integer_aliases)
                ensure(port)["device_properties"]["slot_reads"].add((slot if slot is not None else "dynamic", row[4]))
        elif op == "ss" and len(row) >= 5:
            port = _port(row[1], aliases)
            if port:
                slot = _integer(row[2], integer_aliases)
                ensure(port)["device_properties"]["slot_writes"].add((slot if slot is not None else "dynamic", row[3]))
        elif op == "bdnvl" and len(row) >= 3:
            port = _port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["reads"].add(row[2])
        elif op == "bdnvs" and len(row) >= 3:
            port = _port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["writes"].add(row[2])

    for port, cells in _external_equality_checks(source, rows, aliases, integer_aliases).items():
        target = ensure(port)["stack"]["constraints"]
        for address, values in sorted(cells.items()):
            for value in sorted(values, key=lambda item: (type(item).__name__, str(item))):
                target.append({"address": address, "equals": value})
    for port, declared in overrides.get("ports", {}).items():
        target = ensure(port)["stack"]
        target["dynamic_read_ranges"] = _ranges(declared.get("dynamic_read_ranges"))
        target["dynamic_write_ranges"] = _ranges(declared.get("dynamic_write_ranges"))
        if "role" in declared:
            ensure(port)["role"] = declared["role"]
        if "requirement" in declared:
            ensure(port)["requirement"] = declared["requirement"]
    proofs = _dynamic_port_proofs(source, aliases, integer_aliases)
    for port, item in state.items():
        if port in optional_ports:
            item["requirement"] = "optional"
        properties = item["device_properties"]
        item["device_properties"] = {
            "reads": sorted(properties["reads"]),
            "writes": sorted(properties["writes"]),
            "slot_reads": [
                {"slot": slot, "property": prop}
                for slot, prop in sorted(properties["slot_reads"], key=lambda value: (str(value[0]), value[1]))
            ],
            "slot_writes": [
                {"slot": slot, "property": prop}
                for slot, prop in sorted(properties["slot_writes"], key=lambda value: (str(value[0]), value[1]))
            ],
        }
        dynamic_operands = {
            value for direction in ("reads", "writes")
            for value in item["device_properties"][direction]
            if DYNAMIC_PROPERTY_RE.fullmatch(value)
        } | {
            value["property"] for direction in ("slot_reads", "slot_writes")
            for value in item["device_properties"][direction]
            if DYNAMIC_PROPERTY_RE.fullmatch(value["property"])
        }
        declared_sources = overrides.get("ports", {}).get(port, {}).get("dynamic_property_sources", [])
        source_operands = [value["operand"] for value in declared_sources]
        if len(source_operands) != len(set(source_operands)) or set(source_operands) != dynamic_operands:
            raise ValueError(
                f"{port} dynamic LogicType provenance mismatch: "
                f"operands={sorted(dynamic_operands)}, declared={sorted(source_operands)}"
            )
        if declared_sources:
            item["dynamic_property_sources"] = sorted(
                declared_sources, key=lambda value: (value["operand"], value["source_port"], value["address"])
            )
        stack = item["stack"]
        stack["literal_reads"] = sorted(stack["literal_reads"])
        stack["literal_writes"] = sorted(stack["literal_writes"])
        for direction in ("read", "write"):
            dynamic_key = f"dynamic_{direction}"
            ranges_key = f"dynamic_{direction}_ranges"
            source_key = f"dynamic_{direction}_range_source"
            declared_ranges = stack[ranges_key]
            proof = proofs.get((port, direction), {"total": 0, "proved_accesses": 0, "ranges": []})
            stack[ranges_key], stack[source_key] = _resolve_dynamic_ranges(
                stack[dynamic_key], proof, declared_ranges, f"{port} {direction}"
            )
    return [state[port] for port in sorted(state)]


def _own_stack(source: str, rows: list[list[str]], integer_aliases: dict[str, int], headers: list[dict[str, int]], overrides: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reads: set[int] = set(); writes: set[int] = set()
    write_values: dict[int, set[Any]] = defaultdict(set); unknown_values: set[int] = set()
    dynamic_read = False; dynamic_write = False; clears_all = False
    for row in rows:
        if row[0] == "get" and len(row) >= 4 and row[2] == "db":
            address = _integer(row[3], integer_aliases)
            dynamic_read |= address is None
            if address is not None:
                reads.add(address)
        elif row[0] == "poke" and len(row) >= 3:
            address = _integer(row[1], integer_aliases)
            dynamic_write |= address is None
            if address is not None:
                writes.add(address)
                value = _literal_value(row[2], integer_aliases)
                if value is None:
                    unknown_values.add(address)
                else:
                    write_values[address].add(value)
        elif row[0] == "peek":
            dynamic_read = True
        elif row[0] in {"push", "pop"}:
            dynamic_read = True; dynamic_write = True
        elif row[0] == "clr" and len(row) >= 2 and row[1] == "db":
            clears_all = True
            dynamic_write = True
    annotations, publication_rules = _source_semantics(source, integer_aliases)
    publication_rules.extend(_verified_publication_overrides(source, rows, integer_aliases, overrides))
    accesses: list[tuple[int, str, str]] = []
    unproved = {"read": 0, "write": 0}
    clears = 0
    for index, entry in enumerate(_program(source)):
        row = entry["row"]
        if row and row[0] == "get" and len(row) >= 4 and row[2] == "db" and _integer(row[3], integer_aliases) is None:
            accesses.append((index, "read", row[3]))
        elif row and row[0] == "poke" and len(row) >= 3 and _integer(row[1], integer_aliases) is None:
            accesses.append((index, "write", row[1]))
        elif row and row[0] == "peek":
            unproved["read"] += 1
        elif row and row[0] in {"push", "pop"}:
            unproved["read"] += 1
            unproved["write"] += 1
        elif row and row[0] == "clr" and len(row) >= 2 and row[1] == "db":
            clears += 1
    proofs = _dynamic_range_proofs(source, integer_aliases, accesses)
    for direction in ("read", "write"):
        proof = proofs.setdefault(direction, {"total": 0, "proved_accesses": 0, "ranges": []})
        proof["total"] += unproved[direction]
    write_proof = proofs["write"]
    write_proof["total"] += clears
    write_proof["proved_accesses"] += clears
    if clears:
        write_proof["ranges"] = _merge_ranges(write_proof["ranges"] + [{"start": 0, "end": 511}])
    dynamic_read_ranges, dynamic_read_range_source = _resolve_dynamic_ranges(
        dynamic_read, proofs["read"], _ranges(overrides.get("dynamic_read_ranges")),
        "own-stack read", fallback_full_stack=True,
    )
    dynamic_write_ranges, dynamic_write_range_source = _resolve_dynamic_ranges(
        dynamic_write, proofs["write"], _ranges(overrides.get("dynamic_write_ranges")),
        "own-stack write", fallback_full_stack=True,
    )
    dynamic_write_cells = {
        address for item in dynamic_write_ranges for address in range(item["start"], item["end"] + 1)
    }
    envelope_names = (
        (320, "StackEnvelope.Magic", "integer"),
        (321, "StackEnvelope.Version", "integer"),
        (322, "StackEnvelope.ServiceId", "hash"),
        (323, "StackEnvelope.ServiceABI", "integer"),
        (324, "StackEnvelope.SchemaId", "hash"),
        (325, "StackEnvelope.SchemaVersion", "integer"),
        (326, "StackEnvelope.PrimaryPayloadBase", "integer"),
        (327, "StackEnvelope.ExtensionBase", "integer"),
    )
    has_envelope = (
        write_values[320] == {31416053}
        and write_values[321] == {1}
        and all(address in writes for address, _, _ in envelope_names)
    )
    stable_expected: dict[int, Any] = {header["base"]: header["magic"] for header in headers}
    stable_expected.update({header["base"] + 1: header["abi"] for header in headers})
    if has_envelope:
        stable_expected.update({
            address: next(iter(write_values[address]))
            for address, _, _ in envelope_names
            if address not in unknown_values and len(write_values[address]) == 1
        })
    stable_cells = _stable_cells(source, integer_aliases, stable_expected)
    fields: dict[int, dict[str, Any]] = {}
    for address in sorted(reads | writes):
        access = []
        if address in reads:
            access.append("self-read")
        if address in writes:
            access.append("self-write")
        fields[address] = {
            "address": address,
            "name": f"S{address}",
            "value_type": "number",
            "semantic_source": "unresolved",
            "access": access,
        }
        if address not in dynamic_write_cells and address not in unknown_values and len(write_values[address]) == 1:
            fields[address]["const"] = next(iter(write_values[address]))
        annotation = annotations.get(address, {})
        if any(annotation.get(key) for key in ("name", "descriptions", "enums", "reserved")):
            fields[address]["semantic_source"] = "source"
        if annotation.get("name"):
            fields[address]["name"] = annotation["name"]
        if annotation.get("descriptions"):
            fields[address]["description"] = " | ".join(annotation["descriptions"])
        if "default" in annotation:
            fields[address]["default"] = annotation["default"]
        if annotation.get("enums"):
            fields[address]["enum_values"] = annotation["enums"]
        if annotation.get("reserved"):
            fields[address]["reserved"] = True
        fields[address]["value_type"] = _value_type(fields[address]["name"], fields[address].get("description", ""))
    for header in headers:
        fields[header["base"]]["name"] = f"Header@S{header['base']}.Magic"
        fields[header["base"]]["value_type"] = "hash"
        fields[header["base"]]["semantic_source"] = "protocol-header"
        if (
            header["base"] not in dynamic_write_cells
            and header["base"] not in unknown_values
            and write_values[header["base"]] == {header["magic"]}
            and header["base"] in stable_cells
        ):
            fields[header["base"]]["const"] = header["magic"]
        else:
            fields[header["base"]].pop("const", None)
        fields[header["base"] + 1]["name"] = f"Header@S{header['base']}.ABI"
        fields[header["base"] + 1]["value_type"] = "integer"
        fields[header["base"] + 1]["semantic_source"] = "protocol-header"
        if (
            header["base"] + 1 not in dynamic_write_cells
            and header["base"] + 1 not in unknown_values
            and write_values[header["base"] + 1] == {header["abi"]}
            and header["base"] + 1 in stable_cells
        ):
            fields[header["base"] + 1]["const"] = header["abi"]
        else:
            fields[header["base"] + 1].pop("const", None)
    for declared in overrides.get("stack_fields", []):
        address = declared["address"]
        current = fields.setdefault(address, {"address": address, "name": f"S{address}", "value_type": "number", "semantic_source": "override", "access": []})
        current["name"] = declared["name"]
        current["value_type"] = declared.get("value_type", _value_type(current["name"], declared.get("description", "")))
        current["semantic_source"] = "override"
        current["access"] = sorted(set(current["access"]) | set(declared["access"]))
        if "description" in declared:
            current["description"] = declared["description"]
        for key in ("default", "enum_values", "reserved"):
            if key in declared:
                current[key] = declared[key]
    if has_envelope:
        for address, name, value_type in envelope_names:
            field = fields[address]
            field["name"] = name
            field["value_type"] = value_type
            field["semantic_source"] = "source"
            field["access"] = sorted(set(field["access"]) | {"external-read"})
            if (
                address not in dynamic_write_cells
                and address not in unknown_values
                and len(write_values[address]) == 1
                and address in stable_cells
            ):
                field["const"] = next(iter(write_values[address]))
            else:
                field.pop("const", None)
    external_readable_ranges = _ranges(overrides.get("external_readable_ranges"))
    if has_envelope:
        external_readable_ranges = _merge_ranges(
            external_readable_ranges + [{"start": 320, "end": 327}]
        )
        extension_bases = write_values[327]
        if len(extension_bases) == 1:
            extension_base = next(iter(extension_bases))
            if isinstance(extension_base, int) and extension_base != 0:
                extension_lengths = write_values[extension_base + 2]
                if (
                    write_values[extension_base] == {31416054}
                    and write_values[extension_base + 1] == {1}
                    and len(extension_lengths) == 1
                ):
                    extension_length = next(iter(extension_lengths))
                    if (
                        isinstance(extension_length, int)
                        and 4 <= extension_length <= 192
                        and extension_base + extension_length <= 512
                    ):
                        external_readable_ranges = _merge_ranges(external_readable_ranges + [{
                            "start": extension_base,
                            "end": extension_base + extension_length - 1,
                        }])
    return {
        "size": 512,
        "literal_reads": sorted(reads),
        "literal_writes": sorted(writes),
        "dynamic_read": dynamic_read,
        "dynamic_write": dynamic_write,
        "dynamic_read_ranges": dynamic_read_ranges,
        "dynamic_write_ranges": dynamic_write_ranges,
        "dynamic_read_proven_ranges": proofs["read"]["ranges"] if dynamic_read else [],
        "dynamic_write_proven_ranges": proofs["write"]["ranges"] if dynamic_write else [],
        "dynamic_read_range_source": dynamic_read_range_source,
        "dynamic_write_range_source": dynamic_write_range_source,
        "clears_all": clears_all,
        "external_readable_ranges": external_readable_ranges,
        "external_writable_ranges": _ranges(overrides.get("external_writable_ranges")),
        "fields": [fields[address] for address in sorted(fields)],
    }, sorted(publication_rules, key=lambda item: (item["address"], item["kind"], item["description"]))


def _restart_behavior(rows: list[list[str]], clears_all: bool) -> dict[str, str]:
    """Classify only an entry-path clear as unconditional initialization."""
    if not clears_all:
        return {"mode": "preserved-unless-overwritten", "source": "static-entry-path-analysis"}
    for row in rows:
        if row[0] in {"alias", "define"}:
            continue
        if row[0] == "clr" and len(row) >= 2 and row[1] == "db":
            return {"mode": "cleared-on-init", "source": "static-entry-path-analysis"}
        if row[0] in {"j", "jal", "jr", "yield"} or row[0].startswith("b"):
            break
    return {"mode": "conditional-reset", "source": "static-entry-path-analysis"}


def _header_invariants(headers: list[dict[str, int]], own_stack: dict[str, Any]) -> list[dict[str, Any]]:
    constants = {
        field["address"]: field["const"] for field in own_stack["fields"] if "const" in field
    }
    stable_headers = [
        header for header in headers
        if constants.get(header["base"]) == header["magic"]
        and constants.get(header["base"] + 1) == header["abi"]
    ]
    return [
        {
            "id": f"header.s{header['base']}.magic",
            "kind": "cell-equals",
            "address": header["base"],
            "equals": header["magic"],
            "source": "generated-protocol-header",
        }
        for header in stable_headers
    ] + [
        {
            "id": f"header.s{header['base']}.abi",
            "kind": "cell-equals",
            "address": header["base"] + 1,
            "equals": header["abi"],
            "source": "generated-protocol-header",
        }
        for header in stable_headers
    ]


def _verify_declared_consumers(source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int], declared: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = _external_equality_checks(source, rows, aliases, integer_aliases)
    out = []
    for requirement in declared:
        port = requirement["port"]
        accepted = []
        for item in requirement["accepted"]:
            base = item["header_base"]
            magic = item["magic"]
            abi = item["abi"]
            if magic not in checks[port][base] or abi not in checks[port][base + 1]:
                raise ValueError(f"declared consumer {requirement} is not enforced by literal source checks")
            for publication in item.get("publication_requirements", []):
                address = publication["address"]
                publication_reads = sum(
                    1
                    for row in rows
                    if len(row) >= 4
                    and row[0] == "get"
                    and _port(row[2], aliases) == port
                    and _integer(row[3], integer_aliases) == address
                )
                if publication["kind"] == "commit-last" and not checks[port][address] and publication_reads < 2:
                    raise ValueError(
                        f"declared commit-last consumer {requirement} neither checks nor double-reads publication cell S{address}"
                    )
                if publication["kind"] == "seqlock" and not _verified_seqlock_consumer(
                    source, rows, aliases, integer_aliases, port, address
                ):
                    raise ValueError(
                        f"declared seqlock consumer {requirement} does not parity-check and re-read S{address}"
                    )
            accepted.append({
                "protocol_id": _protocol_id(magic, abi),
                "header_base": base,
                "magic": magic,
                "abi": abi,
                "publication_requirements": item.get("publication_requirements", []),
            })
        out.append({
            "port": port,
            "accepted": sorted(accepted, key=lambda item: (item["header_base"], item["magic"], item["abi"])),
            "source": "authoritative-literal-header-check",
        })
    return sorted(out, key=lambda item: item["port"])


def _verified_seqlock_consumer(
    source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int],
    port: str, address: int,
) -> bool:
    program = _program(source)
    row_nodes = _row_nodes(program)

    reads = [
        (index, row[1]) for index, row in enumerate(rows)
        if len(row) >= 4
        and row[0] == "get"
        and _port(row[2], aliases) == port
        and _integer(row[3], integer_aliases) == address
    ]
    for read_position, (first_index, first_register) in enumerate(reads[:-1]):
        next_read_index = reads[read_position + 1][0]
        parity = next(
            (
                (index, row[1])
                for index, row in enumerate(rows[first_index + 1:next_read_index], first_index + 1)
                if len(row) >= 4
                and row[1] != first_register
                and row[2] == first_register
                and (
                    (row[0] == "and" and _integer(row[3], integer_aliases) == 1)
                    or (row[0] == "mod" and _integer(row[3], integer_aliases) == 2)
                )
            ),
            None,
        )
        if parity is None:
            continue
        parity_index, parity_register = parity
        parity_branch = next(
            (
                (index, row)
                for index, row in enumerate(
                    rows[parity_index + 1:min(next_read_index, parity_index + 4)], parity_index + 1
                )
                if len(row) >= 3 and row[0] == "bnez" and row[1] == parity_register
            ),
            None,
        )
        if parity_branch is None:
            continue
        parity_branch_index, parity_branch_row = parity_branch
        for second_index, second_register in reads[read_position + 1:]:
            if second_register == first_register:
                continue
            compare = next(
                (
                    (index, row)
                    for index, row in enumerate(rows[second_index + 1:second_index + 5], second_index + 1)
                    if len(row) >= 4
                    and row[0] == "bne"
                    and {row[1], row[2]} == {first_register, second_register}
                    and row[-1] == parity_branch_row[-1]
                ),
                None,
            )
            if compare is None:
                continue
            compare_index, compare_row = compare
            first_node = row_nodes[first_index]
            parity_node = row_nodes[parity_index]
            parity_branch_node = row_nodes[parity_branch_index]
            second_node = row_nodes[second_index]
            compare_node = row_nodes[compare_index]
            even_path_node = parity_branch_node + 1
            if even_path_node >= len(program):
                continue
            if not (
                _branch_rejects_before_success(
                    parity_branch_row, parity_branch_node, even_path_node,
                    {first_node}, program,
                )
                and _branch_rejects_before_success(
                    compare_row, compare_node, compare_node + 1,
                    {first_node}, program,
                )
            ):
                continue
            first_register_writes = {
                node for node, entry in enumerate(program)
                if entry["row"] and _writes_register(entry["row"], first_register)
            } - {first_node}
            second_register_writes = {
                node for node, entry in enumerate(program)
                if entry["row"] and _writes_register(entry["row"], second_register)
            } - {second_node}
            if not all((
                _can_reach_avoiding_calls(
                    first_node, parity_node, program, first_register_writes
                ),
                _can_reach_avoiding_calls(
                    parity_node, parity_branch_node, program, first_register_writes
                ),
                _can_reach_avoiding_calls(
                    even_path_node, second_node, program, first_register_writes
                ),
                _can_reach_avoiding_calls(
                    second_node, compare_node, program,
                    first_register_writes | second_register_writes,
                ),
            )):
                continue
            return True
    return False


def access_interface_id(stack: dict[str, Any], assumptions: dict[str, Any]) -> str:
    signature = json.dumps(
        {"stack": stack, "assumptions": assumptions}, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"ic10.interface.access.{hashlib.sha256(signature).hexdigest()[:16]}"


def access_provider_obligations(stack: dict[str, Any], assumptions: dict[str, Any]) -> dict[str, Any]:
    readable = _merge_ranges(
        [{"start": address, "end": address} for address in stack["literal_reads"]]
        + stack["dynamic_read_ranges"]
    )
    writable = _merge_ranges(
        [{"start": address, "end": address} for address in stack["literal_writes"]]
        + stack["dynamic_write_ranges"]
    )
    return {
        "verification": "commissioning-required",
        "stack_readable_ranges": readable,
        "stack_writable_ranges": writable,
        "constraints": stack["constraints"],
        "properties_readable": assumptions["properties_read"],
        "properties_writable": assumptions["properties_written"],
        "slot_properties_readable": assumptions["slot_properties_read"],
        "slot_properties_writable": assumptions["slot_properties_written"],
    }


def _port_target(port: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = sorted({item["protocol_id"] for requirement in requirements if requirement["port"] == port["port"] for item in requirement["accepted"]})
    stack = port["stack"]
    uses_stack = bool(stack["literal_reads"] or stack["literal_writes"] or stack["dynamic_read"] or stack["dynamic_write"])
    if accepted:
        return {"kind": "stack-protocol", "verification": "literal-header", "protocol_ids": accepted}
    assumptions = {
        "properties_read": port["device_properties"]["reads"],
        "properties_written": port["device_properties"]["writes"],
        "slot_properties_read": port["device_properties"]["slot_reads"],
        "slot_properties_written": port["device_properties"]["slot_writes"],
    }
    if uses_stack:
        interface_id = access_interface_id(stack, assumptions)
        return {
            "kind": "stack-interface",
            "verification": "access-only",
            "interface_id": interface_id,
            "definition_ref": f"contracts/index.json#/interfaces/{interface_id}",
            "provider_resolution": "deployment-supplied",
            "assumptions": assumptions,
        }
    return {"kind": "physical-device", "verification": "device-properties", "assumptions": assumptions}


def build_contract(path: Path, root: Path, manifest: dict[str, Any], declared_headers: list[dict[str, int]], declared_consumers: list[dict[str, Any]], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    rows = _instructions(source)
    port_aliases, integer_aliases = _aliases(rows)
    metadata = resolve_script_metadata(path, manifest, root)
    rel = path.relative_to(root).as_posix()
    service_id = _service_id(path)
    overrides = overrides or {}
    headers = _verify_declared_headers(rows, integer_aliases, declared_headers)
    consumes = _verify_declared_consumers(source, rows, port_aliases, integer_aliases, declared_consumers)
    ports = _device_ports(source, rows, port_aliases, integer_aliases, overrides)
    for port in ports:
        port["target"] = _port_target(port, consumes)
    own_stack, publication_rules = _own_stack(source, rows, integer_aliases, headers, overrides)
    provides = [{
        "protocol_id": _protocol_id(header["magic"], header["abi"]),
        **header,
        "source": "literal-own-stack-header",
    } for header in headers]
    invariants = _header_invariants(headers, own_stack) + overrides.get("invariants", [])
    return {
        "$schema": "../../schemas/script_contract_v2.schema.json",
        "format": FORMAT,
        "source": rel,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "identity": {
            "service_id": service_id,
            "implementation_revision": _revision(path),
            "deployment_family": metadata["deployment_family"],
            "deployment_class": metadata["deployment_class"],
            "layer": metadata["layer"],
            "purpose": metadata["purpose"],
        },
        "device_ports": ports,
        "network_dependencies": _network_dependencies(source, rows, integer_aliases, overrides),
        "own_stack": {**own_stack, "headers": headers},
        "behavior": {
            "publication_rules": publication_rules,
            "restart": _restart_behavior(rows, own_stack["clears_all"]),
            "invariants": invariants,
        },
        "contracts": {"provides": provides, "consumes": consumes},
        "extraction": {
            "mode": "static-v2",
            "limitations": [
                "Unproved dynamic own-stack addresses fail closed to the full 512-cell stack.",
                "Strict literal-seeded linear loops are source-derived; other reviewed bounds are source-fingerprinted overrides.",
                "Provided and consumed protocols require authoritative declarations verified against source literals.",
                "Field semantics not represented by source comments or literals remain in supplemental canonical data.",
            ],
        },
    }


def build_all(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    root = Path(root)
    manifest = load_manifest(root)
    override_path = root / "data" / "script_contract_overrides.json"
    override_data = json.loads(override_path.read_text()) if override_path.exists() else {"scripts": {}}
    if override_data.get("format") != "IC10_SCRIPT_CONTRACT_OVERRIDES_V1":
        raise ValueError("unsupported script contract override format")
    script_overrides = override_data.get("scripts", {})
    definitions_path = root / "data" / "script_contract_protocol_definitions.json"
    definitions_data = json.loads(definitions_path.read_text())
    if definitions_data.get("format") != "IC10_PROTOCOL_DEFINITIONS_V1":
        raise ValueError("unsupported script contract protocol definition format")
    definitions = definitions_data.get("protocols", {})
    header_path = root / "data" / "script_protocol_headers.json"
    header_data = json.loads(header_path.read_text())
    if header_data.get("format") != "IC10_PROTOCOL_HEADERS_V1":
        raise ValueError("unsupported script protocol header format")
    declared_headers = header_data.get("scripts", {})
    declared_consumers = header_data.get("consumers", {})
    source_paths = {source.relative_to(root).as_posix() for source in deployable_scripts(root)}
    if set(declared_headers) != source_paths:
        raise ValueError(f"protocol header coverage mismatch: missing={sorted(source_paths-set(declared_headers))}, stale={sorted(set(declared_headers)-source_paths)}")
    if set(declared_consumers) != source_paths:
        raise ValueError(f"protocol consumer coverage mismatch: missing={sorted(source_paths-set(declared_consumers))}, stale={sorted(set(declared_consumers)-source_paths)}")
    contracts: dict[str, dict[str, Any]] = {}
    for source in deployable_scripts(root):
        source_rel = source.relative_to(root).as_posix()
        override = script_overrides.get(source_rel)
        if override:
            verify_override_source(source, override)
        contract = build_contract(source, root, manifest, declared_headers[source_rel], declared_consumers[source_rel], override)
        family = contract["identity"]["deployment_family"]
        rel = f"contracts/{family}/{source.stem}.contract.json"
        if rel in contracts:
            raise ValueError(f"duplicate contract path: {rel}")
        contracts[rel] = contract
    stale_overrides = sorted(set(script_overrides) - {contract["source"] for contract in contracts.values()})
    if stale_overrides:
        raise ValueError(f"contract overrides reference missing scripts: {stale_overrides}")

    providers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    consumers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    headers: dict[str, tuple[int, int]] = {}
    for contract in contracts.values():
        for provided in contract["contracts"]["provides"]:
            pid = provided["protocol_id"]
            headers[pid] = (provided["magic"], provided["abi"])
            providers[pid].append({"source": contract["source"], "header_base": provided["base"]})
        for requirement in contract["contracts"]["consumes"]:
            for accepted in requirement["accepted"]:
                pid = accepted["protocol_id"]
                headers[pid] = (accepted["magic"], accepted["abi"])
                consumers[pid].append({"source": contract["source"], "endpoint": {"kind": "device-port", "value": requirement["port"]}, "header_base": accepted["header_base"]})
        for dependency in contract["network_dependencies"]:
            for accepted in dependency["accepted"]:
                pid = accepted["protocol_id"]
                headers[pid] = (accepted["magic"], accepted["abi"])
                consumers[pid].append({"source": contract["source"], "endpoint": {"kind": "network-reference", "value": dependency["reference"]}, "header_base": accepted["header_base"]})
    unknown_definitions = sorted(set(definitions) - set(headers))
    if unknown_definitions:
        raise ValueError(f"protocol definitions have no provider or consumer: {unknown_definitions}")
    by_source = {contract["source"]: contract for contract in contracts.values()}
    protocol_registry = {
        "format": PROTOCOL_FORMAT,
        "protocols": [{
            "protocol_id": pid,
            "transport": "ic-housing-stack",
            "magic": headers[pid][0],
            "abi": headers[pid][1],
            "name": _protocol_name(pid, headers[pid][1], sorted(item["source"] for item in providers[pid]), definitions),
            "definition_ref": f"contracts/protocols/{pid}.protocol.json",
            "canonical_refs": sorted(set(definitions.get(pid, {}).get("definition_refs", [])) | {
                SUPPLEMENTAL_REFS[by_source[item["source"]]["identity"]["deployment_family"]]
                for item in providers[pid]
                if by_source[item["source"]]["identity"]["deployment_family"] in SUPPLEMENTAL_REFS
            }),
            "providers": sorted(providers[pid], key=lambda item: (item["source"], item["header_base"])),
            "consumers": sorted(consumers[pid], key=lambda item: (item["source"], item["endpoint"]["kind"], item["endpoint"]["value"], item["header_base"])),
        } for pid in sorted(headers)],
    }
    protocol_definitions: dict[str, dict[str, Any]] = {}
    for protocol in protocol_registry["protocols"]:
        provider_interfaces = []
        for provider in protocol["providers"]:
            contract = by_source[provider["source"]]
            own = contract["own_stack"]
            provider_interfaces.append({
                **provider,
                "readable_ranges": own["external_readable_ranges"],
                "writable_ranges": own["external_writable_ranges"],
                "fields": own["fields"],
                "behavior": contract["behavior"],
            })
        consumer_interfaces = []
        for consumer in protocol["consumers"]:
            contract = by_source[consumer["source"]]
            endpoint = consumer["endpoint"]
            if endpoint["kind"] == "device-port":
                access = next(item["stack"] for item in contract["device_ports"] if item["port"] == endpoint["value"])
                interface = {
                    "literal_reads": access["literal_reads"],
                    "literal_writes": access["literal_writes"],
                    "dynamic_read_ranges": access["dynamic_read_ranges"],
                    "dynamic_write_ranges": access["dynamic_write_ranges"],
                    "dynamic_read_range_source": access["dynamic_read_range_source"],
                    "dynamic_write_range_source": access["dynamic_write_range_source"],
                    "constraints": [{"address": item["address"], "operator": "equals", "value": item["equals"]} for item in access["constraints"]],
                    "publication_requirements": next(
                        accepted["publication_requirements"]
                        for requirement in contract["contracts"]["consumes"]
                        if requirement["port"] == endpoint["value"]
                        for accepted in requirement["accepted"]
                        if accepted["protocol_id"] == protocol["protocol_id"] and accepted["header_base"] == consumer["header_base"]
                    ),
                }
            else:
                access = next(item for item in contract["network_dependencies"] if item["reference"] == endpoint["value"])
                interface = {
                    "literal_reads": access["literal_reads"],
                    "literal_writes": access["literal_writes"],
                    "dynamic_read_ranges": [],
                    "dynamic_write_ranges": [],
                    "dynamic_read_range_source": "none",
                    "dynamic_write_range_source": "none",
                    "constraints": access["constraints"],
                    "publication_requirements": [],
                }
            consumer_interfaces.append({**consumer, **interface})
        rel = protocol["definition_ref"]
        protocol_definitions[rel] = {
            "$schema": "../../schemas/protocol_definition.schema.json",
            "format": PROTOCOL_DEFINITION_FORMAT,
            "protocol_id": protocol["protocol_id"],
            "name": protocol["name"],
            "transport": protocol["transport"],
            "magic": protocol["magic"],
            "abi": protocol["abi"],
            "header_bases": sorted({item["header_base"] for item in protocol["providers"] + protocol["consumers"]}),
            "canonical_refs": protocol["canonical_refs"],
            "provider_interfaces": provider_interfaces,
            "consumer_interfaces": consumer_interfaces,
        }
    interface_definitions: dict[str, dict[str, Any]] = {}
    for contract in contracts.values():
        for port in contract["device_ports"]:
            target = port["target"]
            if target["kind"] != "stack-interface":
                continue
            interface_id = target["interface_id"]
            definition = interface_definitions.setdefault(interface_id, {
                "stack": port["stack"],
                "assumptions": target["assumptions"],
                "provider_obligations": access_provider_obligations(port["stack"], target["assumptions"]),
                "consumers": [],
            })
            if definition["stack"] != port["stack"] or definition["assumptions"] != target["assumptions"]:
                raise ValueError(f"structural interface hash collision: {interface_id}")
            definition["consumers"].append({"source": contract["source"], "port": port["port"]})
    for definition in interface_definitions.values():
        definition["consumers"].sort(key=lambda item: (item["source"], item["port"]))
    own_stack_range_inventory = []
    for contract in sorted(contracts.values(), key=lambda item: item["source"]):
        own = contract["own_stack"]
        if not own["dynamic_read"] and not own["dynamic_write"]:
            continue
        own_stack_range_inventory.append({
            "source": contract["source"],
            "read": {
                "dynamic": own["dynamic_read"],
                "ranges": own["dynamic_read_ranges"],
                "proven_ranges": own["dynamic_read_proven_ranges"],
                "provenance": own["dynamic_read_range_source"],
            },
            "write": {
                "dynamic": own["dynamic_write"],
                "ranges": own["dynamic_write_ranges"],
                "proven_ranges": own["dynamic_write_proven_ranges"],
                "provenance": own["dynamic_write_range_source"],
            },
        })
    index = {
        "format": INDEX_FORMAT,
        "contract_count": len(contracts),
        "own_stack_range_inventory": {
            "dynamic_script_count": len(own_stack_range_inventory),
            "source_proven_surface_count": sum(
                bool(item[direction]["proven_ranges"])
                for item in own_stack_range_inventory for direction in ("read", "write")
            ),
            "unresolved_fallback_count": sum(
                item[direction]["provenance"] == "conservative-full-stack"
                for item in own_stack_range_inventory for direction in ("read", "write")
            ),
            "scripts": own_stack_range_inventory,
        },
        "interfaces": {key: interface_definitions[key] for key in sorted(interface_definitions)},
        "contracts": [{
            "source": contract["source"],
            "contract": rel,
            "service_id": contract["identity"]["service_id"],
            "provides": [item["protocol_id"] for item in contract["contracts"]["provides"]],
            "consumes": sorted(
                {accepted["protocol_id"] for item in contract["contracts"]["consumes"] for accepted in item["accepted"]}
                | {accepted["protocol_id"] for item in contract["network_dependencies"] for accepted in item["accepted"]}
            ),
        } for rel, contract in sorted(contracts.items())],
    }
    return contracts, index, protocol_registry, protocol_definitions


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n"


def _expanded_ranges(ranges: list[dict[str, int]]) -> set[int]:
    return {address for item in ranges for address in range(item["start"], item["end"] + 1)}


def invariant_errors(contract: dict[str, Any]) -> list[str]:
    """Evaluate every machine-readable invariant declared by one contract."""
    constants = {
        field["address"]: field["const"] for field in contract["own_stack"]["fields"] if "const" in field
    }
    errors = []
    dynamic_writes = _expanded_ranges(contract["own_stack"]["dynamic_write_ranges"])
    for invariant in contract["behavior"]["invariants"]:
        if invariant["kind"] == "cell-equals":
            if invariant["address"] in dynamic_writes:
                errors.append(
                    f"{contract['source']}: invariant {invariant['id']} is not proven across dynamic writes"
                )
                continue
            actual = constants.get(invariant["address"])
            if actual != invariant["equals"]:
                errors.append(
                    f"{contract['source']}: invariant {invariant['id']} expected S{invariant['address']}="
                    f"{invariant['equals']!r}, got {actual!r}"
                )
    return errors


def compatibility_errors(contracts: list[dict[str, Any]]) -> list[str]:
    """Return provider/consumer header, cell, and access-direction incompatibilities."""
    providers: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for contract in contracts:
        for provided in contract["contracts"]["provides"]:
            providers[(provided["protocol_id"], provided["base"])].append(contract)
    errors = []
    for consumer in contracts:
        ports = {item["port"]: item for item in consumer["device_ports"]}
        for requirement in consumer["contracts"]["consumes"]:
            port = ports.get(requirement["port"])
            if port is None:
                errors.append(f"{consumer['source']}: consumed protocol uses undeclared {requirement['port']}")
                continue
            for accepted in requirement["accepted"]:
                key = (accepted["protocol_id"], accepted["header_base"])
                candidates = providers.get(key, [])
                if not candidates:
                    errors.append(f"{consumer['source']} {requirement['port']}: no provider for {key[0]} at S{key[1]}")
                    continue
                failures = []
                for provider in candidates:
                    own = provider["own_stack"]
                    readable = set(own["literal_writes"]) | _expanded_ranges(own["external_readable_ranges"])
                    writable = set(own["literal_reads"]) | _expanded_ranges(own["external_writable_ranges"])
                    for field in own["fields"]:
                        if "external-read" in field["access"]:
                            readable.add(field["address"])
                        if "external-write" in field["access"]:
                            writable.add(field["address"])
                    requested_reads = set(port["stack"]["literal_reads"]) | _expanded_ranges(port["stack"]["dynamic_read_ranges"])
                    requested_writes = set(port["stack"]["literal_writes"]) | _expanded_ranges(port["stack"]["dynamic_write_ranges"])
                    missing_reads = requested_reads - readable
                    missing_writes = requested_writes - writable
                    constants = {field["address"]: field["const"] for field in own["fields"] if "const" in field}
                    wrong_values = [
                        (constraint["address"], constraint["equals"], constants[constraint["address"]])
                        for constraint in port["stack"]["constraints"]
                        if constraint["address"] in constants and constants[constraint["address"]] != constraint["equals"]
                    ]
                    provider_rules = {(item["kind"], item["address"]) for item in provider["behavior"]["publication_rules"]}
                    missing_publication = [
                        item for item in accepted.get("publication_requirements", [])
                        if (item["kind"], item["address"]) not in provider_rules
                    ]
                    unresolved = []
                    if port["stack"]["dynamic_read"] and not port["stack"]["dynamic_read_ranges"]:
                        unresolved.append("consumer dynamic read has no declared range")
                    if port["stack"]["dynamic_write"] and not port["stack"]["dynamic_write_ranges"]:
                        unresolved.append("consumer dynamic write has no declared range")
                    if not missing_reads and not missing_writes and not wrong_values and not missing_publication and not unresolved:
                        break
                    failures.append((provider["source"], sorted(missing_reads), sorted(missing_writes), wrong_values, missing_publication, unresolved))
                else:
                    detail = "; ".join(f"{source}: unreadable={reads}, unwritable={writes}, unequal={values}, publication={publication}, unresolved={unresolved}" for source, reads, writes, values, publication, unresolved in failures)
                    errors.append(f"{consumer['source']} {requirement['port']}: {key[0]} at S{key[1]} has no value/direction-compatible provider ({detail})")
        for dependency in consumer["network_dependencies"]:
            for accepted in dependency["accepted"]:
                key = (accepted["protocol_id"], accepted["header_base"])
                candidates = providers.get(key, [])
                if not candidates:
                    errors.append(f"{consumer['source']} network {dependency['reference']}: no provider for {key[0]} at S{key[1]}")
                    continue
                requested_reads = set(dependency["literal_reads"])
                requested_writes = set(dependency["literal_writes"])
                if not any(
                    not (requested_reads - (set(provider["own_stack"]["literal_writes"]) | _expanded_ranges(provider["own_stack"]["external_readable_ranges"])))
                    and not (requested_writes - (set(provider["own_stack"]["literal_reads"]) | _expanded_ranges(provider["own_stack"]["external_writable_ranges"])))
                    for provider in candidates
                ):
                    errors.append(f"{consumer['source']} network {dependency['reference']}: {key[0]} at S{key[1]} has no access-compatible provider")
    return errors
