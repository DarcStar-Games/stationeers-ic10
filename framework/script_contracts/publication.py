"""Publication-ordering proofs and source-comment semantic extraction.

Stable-cell initialization, commit-last ordering, and seqlock pairing are
verified against the control-flow graph; field names, enums, and value types
are inferred only from what the source explicitly documents.
"""
from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from framework.ic10_source import IC10Source, parse_ic10
from framework.script_contracts.control_flow import (
    CallState,
    all_paths_retain_target,
    branch_rejects_before_success,
    call_state_graph,
    can_reach_avoiding_calls,
    control_flow_dominators,
    control_flow_with_wrap,
    writes_register,
)
from framework.script_contracts.parsing import (
    parse_program,
    resolve_integer,
    resolve_literal,
    resolve_port,
    row_nodes,
)

SEMANTIC_WORDS = re.compile(
    r"(?i)\b(generation|token|status|state|reference\s*id|schema|count|capacity|width|epoch|revision|sequence|"
    r"reserved|owner|unit|class|kind|mode|identity|pressure|temperature|quantity|rate|cost|signature|command)\b"
)


def stable_cells(
    source: str, integer_aliases: dict[str, int], expected: dict[int, Any]
) -> set[int]:
    """Find cells initialized to an expected value before every observable control-flow boundary.

    `clr db` de-initializes: it costs a cell whatever it held and hands a cell
    that expects zero the value it wants, so a clear is a write of 0 to all 512
    rather than an instruction the walk steps over.
    """
    program = parse_program(source)
    if not program:
        return set()

    successors, control_flow_complete = call_state_graph(program)
    if not control_flow_complete:
        return set()
    entry = (0, None)
    # `ra` is None wherever no call is outstanding, so states need a total order
    # of their own before the fixpoint below can iterate them in one.
    reachable = sorted(successors, key=lambda state: (state[0], -1 if state[1] is None else state[1]))

    predecessors: dict[CallState, set[CallState]] = defaultdict(set)
    for state, outgoing in successors.items():
        for target in outgoing:
            predecessors[target].add(state)

    def goes_round_again(state: CallState) -> bool:
        """Does this state transfer backwards without leaving its own context?

        A return transfers backwards too -- to the instruction after its call --
        but that is the caller carrying on, not the program starting over, and
        counting it as a boundary would demand a header be published before the
        first call that helps publish it. A return onto itself is the exception:
        a second call has overwritten the address this one meant to read, and the
        program spins there.
        """
        row = program[state[0]]["row"]
        returning = bool(row) and row[-1] == "ra" and (
            row[0] in {"j", "jr"} or row[0].startswith("b")
        )
        return any(
            target[0] <= state[0] and target[1] == state[1]
            and not (returning and state[1] == target[0] != state[0])
            for target in successors.get(state, set())
        )

    observations = {
        state for state in reachable
        if (
            (program[state[0]]["row"] and program[state[0]]["row"][0] in {"yield", "hcf"})
            or not successors.get(state, set())
            or goes_round_again(state)
        )
    }
    if not observations:
        return set()

    clearing = {
        state for state in reachable if program[state[0]]["row"][:2] == ["clr", "db"]
    }

    stable: set[int] = set()
    for address, value in expected.items():
        matching_writes = {
            state for state in reachable
            if (
                program[state[0]]["row"]
                and program[state[0]]["row"][0] == "poke"
                and len(program[state[0]]["row"]) >= 3
                and resolve_integer(program[state[0]]["row"][1], integer_aliases) == address
                and resolve_literal(program[state[0]]["row"][2], integer_aliases) == value
            )
        }
        initialized_after = {state: True for state in reachable}
        changed = True
        while changed:
            changed = False
            for state in reachable:
                incoming = predecessors.get(state, set())
                initialized_before = False if state == entry else bool(incoming) and all(
                    initialized_after[parent] for parent in incoming
                )
                updated = state in matching_writes or (
                    value == 0 if state in clearing else initialized_before
                )
                if updated != initialized_after[state]:
                    initialized_after[state] = updated
                    changed = True
        if all(initialized_after[state] for state in observations):
            stable.add(address)
    return stable


def _reaches_observation(
    start: int, successors: dict[int, set[int]], observations: set[int], republished: set[int]
) -> bool:
    """Can a walk from `start` reach somewhere observable without rewriting the cell?

    Somewhere observable is a yield, a halt, or any cycle at all: a program that
    can go round with the cell still zeroed can be read with it zeroed, and it
    makes no difference whether it goes round through a branch, through a call
    and its return, or through the tail's own edge back to the entry. Asking for
    the cycle rather than for a backward edge is what lets this stay silent about
    which of the three a transfer was -- the distinction `goes_round_again` needs
    the call states to draw, and that a graph of plain indices has already lost.
    """
    stack: list[tuple[int, list[int]]] = [(start, sorted(successors.get(start, ())))]
    on_path = {start}
    settled: set[int] = set()
    while stack:
        node, pending = stack[-1]
        if not pending:
            stack.pop()
            on_path.discard(node)
            settled.add(node)
            continue
        target = pending.pop()
        if target in republished or target in settled:
            continue
        if target in observations or target in on_path:
            return True
        stack.append((target, sorted(successors.get(target, ()))))
        on_path.add(target)
    return False


def cells_erased_by_clear(
    source: str, integer_aliases: dict[str, int], expected: dict[int, Any]
) -> set[int]:
    """Expected cells a `clr db` can leave at zero somewhere a consumer reads them.

    `clr db` zeroes all 512 cells, so it de-publishes every expected cell whose
    value is not itself zero -- and the boot idiom is safe only because the
    publication that follows the clear puts them all back before anything can
    look. That is what this asks, one cell at a time: walk forward from each
    clear and see whether anywhere observable is reachable without passing a
    literal write of the expected value. Only a literal write counts, because a
    computed one proves nothing about what lands in the cell.

    A graph with a transfer nobody can follow answers with every erasable cell:
    a re-publication this cannot trace is not a re-publication it can vouch for.
    """
    program = parse_program(source)
    clears = [index for index, entry in enumerate(program) if entry["row"][:2] == ["clr", "db"]]
    if not clears:
        return set()
    erasable = {address for address, value in expected.items() if value != 0}
    successors, complete = control_flow_with_wrap(program)
    if not complete:
        return erasable
    observations = {
        node for node, entry in enumerate(program)
        if entry["row"][:1] in (["yield"], ["hcf"])
    }
    erased: set[int] = set()
    for address in sorted(erasable):
        republished = {
            node for node, entry in enumerate(program)
            if entry["row"][:1] == ["poke"] and len(entry["row"]) >= 3
            and resolve_integer(entry["row"][1], integer_aliases) == address
            # `resolve_literal` says None for a computed operand, so an expected
            # value of None would otherwise be met by any write at all.
            and resolve_literal(entry["row"][2], integer_aliases) is not None
            and resolve_literal(entry["row"][2], integer_aliases) == expected[address]
        }
        if any(
            _reaches_observation(clear, successors, observations, republished)
            for clear in clears
        ):
            erased.add(address)
    return erased


def semantic_name(comment: str) -> str | None:
    if not SEMANTIC_WORDS.search(comment):
        return None
    phrase = re.split(r"[;,(]|\bLAST\b|\bafter\b|\bbefore\b|\bsupplied\b|\bfrom\b", comment, maxsplit=1, flags=re.IGNORECASE)[0]
    phrase = re.sub(r"(?i)\b(current|initial|opaque|exact|published|committed|physical)\b", " ", phrase)
    words = re.findall(r"[A-Za-z]+|[0-9]+", phrase)
    if not words or len(words) > 6:
        return None
    return "".join(word if re.search(r"[A-Z].*[A-Z]|Id$", word) else word[:1].upper() + word[1:] for word in words)


def value_type(name: str, comment: str) -> str:
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


def _commit_last_violation(parsed: IC10Source, marker_line: int) -> str | None:
    """Find an own-stack write reachable after a commit-last marker."""
    labels = {label.name: label.line.number for label in parsed.labels}
    rows = {row.line.number: row for row in parsed.rows}
    pending = [marker_line + 1]
    visited: set[int] = set()
    while pending:
        index = pending.pop()
        while 1 <= index <= len(parsed.lines) and index not in visited:
            visited.add(index)
            source_row = rows.get(index)
            if source_row is None:
                index += 1
                continue
            row = source_row.tokens
            code = source_row.line.code_text
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


def source_semantics(source: str, integer_aliases: dict[str, int]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    """Extract semantics explicitly documented next to literal own-stack accesses."""
    annotations: dict[int, dict[str, Any]] = defaultdict(lambda: {"descriptions": [], "enums": []})
    publication_rules: list[dict[str, Any]] = []
    parsed = parse_ic10(source)
    for source_row in parsed.rows:
        line_number = source_row.line.number
        comment = source_row.line.comment_text
        row = source_row.tokens
        address = None
        value = None
        if row[0] == "poke" and len(row) >= 3:
            address = resolve_integer(row[1], integer_aliases)
            value = resolve_literal(row[2], integer_aliases)
        elif row[0] == "get" and len(row) >= 4 and row[2] == "db":
            address = resolve_integer(row[3], integer_aliases)
        if address is None or not 0 <= address <= 511:
            continue
        target = annotations[address]
        if comment and comment not in target["descriptions"]:
            target["descriptions"].append(comment)
        name = semantic_name(comment)
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
            violation = _commit_last_violation(parsed, line_number)
            if violation is not None:
                raise ValueError(
                    f"commit-last claim at source line {line_number} is followed by own-stack write: {violation}"
                )
            publication_rules.append({
                "kind": "commit-last",
                "address": address,
                "description": comment,
                "source": "verified-inline-order",
            })
        if "seqlock" in comment.lower() or "odd/even" in comment.lower():
            raise ValueError(
                f"seqlock claim at source line {line_number} requires an explicit odd/even source verifier"
            )
    unique_rules = {(item["kind"], item["address"], item["description"]): item for item in publication_rules}
    return annotations, sorted(unique_rules.values(), key=lambda item: (item["address"], item["kind"], item["description"]))


def verified_publication_overrides(
    source: str, rows: list[list[str]], integer_aliases: dict[str, int], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    program = parse_program(source)
    nodes = row_nodes(program)
    _, _, successors, _ = control_flow_dominators(program)
    rules = []
    for declared in overrides.get("publication_rules", []):
        if declared["kind"] != "seqlock":
            raise ValueError(f"unsupported publication override: {declared}")
        address = declared["address"]
        reads = [
            row for row in rows
            if len(row) >= 4 and row[0] == "get" and row[2] == "db" and resolve_integer(row[3], integer_aliases) == address
        ]
        writes = [
            (index, row) for index, row in enumerate(rows)
            if len(row) >= 3 and row[0] == "poke" and resolve_integer(row[1], integer_aliases) == address
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
                first_node = nodes[first_index]
                second_node = nodes[second_index]
                yield_nodes = {
                    node for node, entry in enumerate(program)
                    if entry["row"] and entry["row"][0] == "yield"
                }
                if any(
                    can_reach_avoiding_calls(
                        first_node, yield_node, program, {second_node}
                    )
                    for yield_node in yield_nodes
                ):
                    continue
                if not all_paths_retain_target(
                    first_node, second_node, successors, yield_nodes
                ):
                    continue
                if not can_reach_avoiding_calls(
                    first_node, second_node, program, yield_nodes
                ):
                    continue
                payload_indices = [
                    index for index, row in enumerate(
                        rows[first_index + 1:second_index], first_index + 1
                    )
                    if row[0] in {"poke", "put", "putd"}
                    and not (row[0] == "poke" and resolve_integer(row[1], integer_aliases) == address)
                ]
                if not any(
                    can_reach_avoiding_calls(
                        first_node, nodes[payload_index], program, yield_nodes
                    )
                    and can_reach_avoiding_calls(
                        nodes[payload_index], second_node, program, yield_nodes
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
                            if writes_register(rows[index], register)
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
                        and resolve_integer(add_row[3], integer_aliases) == 1
                    ):
                        pair_ok = False
                        break
                    prior_write = next(
                        (
                            index for index in range(add_index - 1, -1, -1)
                            if writes_register(rows[index], register)
                        ),
                        None,
                    )
                    read_current = (
                        prior_write is not None
                        and len(rows[prior_write]) >= 4
                        and rows[prior_write][0] == "get"
                        and rows[prior_write][2] == "db"
                        and resolve_integer(rows[prior_write][3], integer_aliases) == address
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


def verified_seqlock_consumer(
    source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int],
    port: str, address: int,
) -> bool:
    program = parse_program(source)
    nodes = row_nodes(program)

    reads = [
        (index, row[1]) for index, row in enumerate(rows)
        if len(row) >= 4
        and row[0] == "get"
        and resolve_port(row[2], aliases) == port
        and resolve_integer(row[3], integer_aliases) == address
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
                    (row[0] == "and" and resolve_integer(row[3], integer_aliases) == 1)
                    or (row[0] == "mod" and resolve_integer(row[3], integer_aliases) == 2)
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
            first_node = nodes[first_index]
            parity_node = nodes[parity_index]
            parity_branch_node = nodes[parity_branch_index]
            second_node = nodes[second_index]
            compare_node = nodes[compare_index]
            even_path_node = parity_branch_node + 1
            if even_path_node >= len(program):
                continue
            if not (
                branch_rejects_before_success(
                    parity_branch_row, parity_branch_node, even_path_node,
                    {first_node}, program,
                )
                and branch_rejects_before_success(
                    compare_row, compare_node, compare_node + 1,
                    {first_node}, program,
                )
            ):
                continue
            first_register_writes = {
                node for node, entry in enumerate(program)
                if entry["row"] and writes_register(entry["row"], first_register)
            } - {first_node}
            second_register_writes = {
                node for node, entry in enumerate(program)
                if entry["row"] and writes_register(entry["row"], second_register)
            } - {second_node}
            if not all((
                can_reach_avoiding_calls(
                    first_node, parity_node, program, first_register_writes
                ),
                can_reach_avoiding_calls(
                    parity_node, parity_branch_node, program, first_register_writes
                ),
                can_reach_avoiding_calls(
                    even_path_node, second_node, program, first_register_writes
                ),
                can_reach_avoiding_calls(
                    second_node, compare_node, program,
                    first_register_writes | second_register_writes,
                ),
            )):
                continue
            return True
    return False
