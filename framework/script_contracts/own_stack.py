"""Analyze a program's own IC housing stack: accesses, fields, and headers.

Combines the literal access scan, dynamic-range resolution, publication
verification, and semantic extraction into the contract's own_stack payload,
plus the declared-header verification and restart classification beside it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from framework.script_contracts.control_flow import can_reach, control_flow_with_wrap
from framework.script_contracts.dynamic_ranges import (
    RangeProof,
    dynamic_range_proofs,
    merge_ranges,
    resolve_dynamic_ranges,
    validated_ranges,
)
from framework.script_contracts.parsing import parse_program, resolve_integer, resolve_literal
from framework.script_contracts.publication import (
    source_semantics,
    stable_cells,
    value_type,
    verified_publication_overrides,
)


def verify_declared_headers(rows: list[list[str]], integer_aliases: dict[str, int], declared: list[dict[str, int]]) -> list[dict[str, int]]:
    writes: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        if len(row) >= 3 and row[0] == "poke":
            address = resolve_integer(row[1], integer_aliases)
            value = resolve_integer(row[2], integer_aliases)
            if address is not None and value is not None and 0 <= address <= 511:
                writes[address].add(value)
    headers = []
    for header in declared:
        base = header["base"]; magic = header["magic"]; abi = header["abi"]
        contract = header.get("contract")
        # A contract-named header derives its magic by hashing, so any non-zero
        # int32 is legitimate; only a hand-allocated block magic must be positive.
        if not 0 <= base < 511 or abi <= 0 or (magic == 0 if contract else magic <= 0):
            raise ValueError(f"invalid declared header: {header}")
        if magic not in writes[base] or abi not in writes[base + 1]:
            raise ValueError(f"declared header {header} is not written literally by source")
        headers.append({"base": base, **({"contract": contract} if contract else {}),
                        "magic": magic, "abi": abi})
    return sorted(headers, key=lambda item: (item["base"], item["magic"], item["abi"]))


@dataclass
class StackScan:
    """Every literal own-stack access and the dynamic flags one source scan finds."""

    reads: set[int] = field(default_factory=set)
    writes: set[int] = field(default_factory=set)
    write_values: dict[int, set[Any]] = field(default_factory=lambda: defaultdict(set))
    unknown_values: set[int] = field(default_factory=set)
    dynamic_read: bool = False
    dynamic_write: bool = False
    clears_all: bool = False


def _clear_nodes(program: list[dict[str, Any]]) -> list[int]:
    return [index for index, entry in enumerate(program) if entry["row"][:2] == ["clr", "db"]]


def post_publication_clears(program: list[dict[str, Any]]) -> int:
    """How many `clr db` instructions can still run after the program has published.

    A boot clear is initialization, not a write anyone can observe: it zeroes the
    housing before the first yield makes any of it readable, so the 512 cells it
    touches are not cells a consumer of this contract ever sees it write. What
    `clears_all` and the restart classification already say about it is the whole
    of what it does. A clear the control-flow graph can reach from a yield is a
    real post-publication total write and keeps every one of those cells.

    Both ways of not knowing cost the narrowing rather than claiming it: a
    transfer the graph cannot follow counts every clear, and the tail carries an
    edge back to the entry, which is what `control_flow_with_wrap` is for.
    """
    clears = _clear_nodes(program)
    yields = [index for index, entry in enumerate(program) if entry["row"][:1] == ["yield"]]
    if not clears or not yields:
        return 0
    successors, complete = control_flow_with_wrap(program)
    if not complete:
        return len(clears)
    return sum(1 for clear in clears if any(can_reach(node, clear, successors) for node in yields))


def clear_exposed_cells(program: list[dict[str, Any]], integer_aliases: dict[str, int]) -> set[int]:
    """Cells a `clr db` zeroes with nothing writing them again.

    A constant says the cell holds one value wherever a peer can look, and the
    write range is what usually keeps that claim honest -- so taking the entry
    clear out of the range takes this with it unless the cells it strands are
    named here. A cell written before a clear and never after holds zero at the
    first yield, whatever single literal the source pokes into it.

    A clear the graph cannot place strands everything, for the same reason it
    counts as post-publication above: not knowing costs the constant.
    """
    clears = _clear_nodes(program)
    if not clears:
        return set()
    writes: dict[int, list[int]] = defaultdict(list)
    for index, entry in enumerate(program):
        row = entry["row"]
        if row[:1] == ["poke"] and len(row) >= 3:
            address = resolve_integer(row[1], integer_aliases)
            if address is not None:
                writes[address].append(index)
    successors, complete = control_flow_with_wrap(program)
    if not complete:
        return set(writes)
    return {
        address for address, nodes in writes.items()
        if any(
            any(can_reach(node, clear, successors) for node in nodes)
            and not any(can_reach(clear, node, successors) for node in nodes)
            for clear in clears
        )
    }


def _scan_literal_accesses(
    rows: list[list[str]], integer_aliases: dict[str, int], clears: int
) -> StackScan:
    """Scan the literal accesses; `clears` is the `post_publication_clears` count."""
    scan = StackScan()
    for row in rows:
        if row[0] == "get" and len(row) >= 4 and row[2] == "db":
            address = resolve_integer(row[3], integer_aliases)
            scan.dynamic_read |= address is None
            if address is not None:
                scan.reads.add(address)
        elif row[0] == "poke" and len(row) >= 3:
            address = resolve_integer(row[1], integer_aliases)
            scan.dynamic_write |= address is None
            if address is not None:
                scan.writes.add(address)
                value = resolve_literal(row[2], integer_aliases)
                if value is None:
                    scan.unknown_values.add(address)
                else:
                    scan.write_values[address].add(value)
        elif row[0] == "peek":
            scan.dynamic_read = True
        elif row[0] in {"push", "pop"}:
            scan.dynamic_read = True
            scan.dynamic_write = True
        elif row[0] == "clr" and len(row) >= 2 and row[1] == "db":
            scan.clears_all = True
            scan.dynamic_write |= clears > 0
    return scan


def _own_stack_proofs(
    source: str, integer_aliases: dict[str, int], clears: int
) -> dict[str, RangeProof]:
    """Prove the dynamic own-stack accesses; peek/push/pop stay unproved, clears are total.

    `clears` counts only the clears that survive the boot test in
    `post_publication_clears`; a clear that cannot run after publication proves
    nothing about what this program writes where a consumer can see it.
    """
    accesses: list[tuple[int, str, str]] = []
    unproved = {"read": 0, "write": 0}
    for index, entry in enumerate(parse_program(source)):
        row = entry["row"]
        if row and row[0] == "get" and len(row) >= 4 and row[2] == "db" and resolve_integer(row[3], integer_aliases) is None:
            accesses.append((index, "read", row[3]))
        elif row and row[0] == "poke" and len(row) >= 3 and resolve_integer(row[1], integer_aliases) is None:
            accesses.append((index, "write", row[1]))
        elif row and row[0] == "peek":
            unproved["read"] += 1
        elif row and row[0] in {"push", "pop"}:
            unproved["read"] += 1
            unproved["write"] += 1
    proofs = dynamic_range_proofs(source, integer_aliases, accesses)
    for direction in ("read", "write"):
        proof = proofs.setdefault(direction, RangeProof())
        proof.total += unproved[direction]
    write_proof = proofs["write"]
    write_proof.total += clears
    write_proof.proved_accesses += clears
    if clears:
        write_proof.ranges = merge_ranges(write_proof.ranges + [{"start": 0, "end": 511}])
    return proofs


def _synthesize_fields(
    scan: StackScan, annotations: dict[int, dict[str, Any]], headers: list[dict[str, int]],
    stable: set[int], dynamic_write_cells: set[int], overrides: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    """Name every accessed cell from source semantics, headers, and overrides, in that order."""
    fields: dict[int, dict[str, Any]] = {}
    for address in sorted(scan.reads | scan.writes):
        access = []
        if address in scan.reads:
            access.append("self-read")
        if address in scan.writes:
            access.append("self-write")
        fields[address] = {
            "address": address,
            "name": f"S{address}",
            "value_type": "number",
            "semantic_source": "unresolved",
            "access": access,
        }
        if address not in dynamic_write_cells and address not in scan.unknown_values and len(scan.write_values[address]) == 1:
            fields[address]["const"] = next(iter(scan.write_values[address]))
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
        fields[address]["value_type"] = value_type(fields[address]["name"], fields[address].get("description", ""))
    for header in headers:
        for offset, name, kind, expected in (
            (0, "Magic", "hash", header["magic"]),
            (1, "ABI", "integer", header["abi"]),
        ):
            cell = header["base"] + offset
            fields[cell]["name"] = f"Header@S{header['base']}.{name}"
            fields[cell]["value_type"] = kind
            fields[cell]["semantic_source"] = "protocol-header"
            if (
                cell not in dynamic_write_cells
                and cell not in scan.unknown_values
                and scan.write_values[cell] == {expected}
                and cell in stable
            ):
                fields[cell]["const"] = expected
            else:
                fields[cell].pop("const", None)
    for declared in overrides.get("stack_fields", []):
        address = declared["address"]
        current = fields.setdefault(address, {"address": address, "name": f"S{address}", "value_type": "number", "semantic_source": "override", "access": []})
        current["name"] = declared["name"]
        current["value_type"] = declared.get("value_type", value_type(current["name"], declared.get("description", "")))
        current["semantic_source"] = "override"
        current["access"] = sorted(set(current["access"]) | set(declared["access"]))
        if "description" in declared:
            current["description"] = declared["description"]
        for key in ("default", "enum_values", "reserved"):
            if key in declared:
                current[key] = declared[key]
    return fields


def _extension_readable_ranges(
    headers: list[dict[str, int]], write_values: dict[int, set[Any]],
    external_readable_ranges: list[dict[str, int]],
) -> list[dict[str, int]]:
    """Advertise a literally published S4-pointed extension block as externally readable."""
    if not any(header["base"] == 0 for header in headers):
        return external_readable_ranges
    extension_bases = write_values[4]
    if len(extension_bases) != 1:
        return external_readable_ranges
    extension_base = next(iter(extension_bases))
    if not isinstance(extension_base, int) or extension_base < 8:
        return external_readable_ranges
    extension_lengths = write_values[extension_base + 2]
    if (
        write_values[extension_base] != {31416054}
        or write_values[extension_base + 1] != {1}
        or len(extension_lengths) != 1
    ):
        return external_readable_ranges
    extension_length = next(iter(extension_lengths))
    if (
        not isinstance(extension_length, int)
        or not 4 <= extension_length <= 192
        or extension_base + extension_length > 512
    ):
        return external_readable_ranges
    return merge_ranges(external_readable_ranges + [{
        "start": extension_base,
        "end": extension_base + extension_length - 1,
    }])


def analyze_own_stack(source: str, rows: list[list[str]], integer_aliases: dict[str, int], headers: list[dict[str, int]], overrides: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    program = parse_program(source)
    clears = post_publication_clears(program)
    scan = _scan_literal_accesses(rows, integer_aliases, clears)
    annotations, publication_rules = source_semantics(source, integer_aliases)
    publication_rules.extend(verified_publication_overrides(source, rows, integer_aliases, overrides))
    proofs = _own_stack_proofs(source, integer_aliases, clears)
    dynamic_read_ranges, dynamic_read_range_source = resolve_dynamic_ranges(
        scan.dynamic_read, proofs["read"], validated_ranges(overrides.get("dynamic_read_ranges")),
        "own-stack read", fallback_full_stack=True,
    )
    dynamic_write_ranges, dynamic_write_range_source = resolve_dynamic_ranges(
        scan.dynamic_write, proofs["write"], validated_ranges(overrides.get("dynamic_write_ranges")),
        "own-stack write", fallback_full_stack=True,
    )
    dynamic_write_cells = {
        address for item in dynamic_write_ranges for address in range(item["start"], item["end"] + 1)
    }
    stable_expected: dict[int, Any] = {header["base"]: header["magic"] for header in headers}
    stable_expected.update({header["base"] + 1: header["abi"] for header in headers})
    stable = stable_cells(source, integer_aliases, stable_expected)
    # A cell peers may write is never a provider constant, however few literal
    # writes the owner's own source shows for it.
    external_write_cells = {
        address for item in validated_ranges(overrides.get("external_writable_ranges"))
        for address in range(item["start"], item["end"] + 1)
    }
    # A cell an entry clear zeroes and nothing writes again holds zero at the first
    # yield, so it is no more a constant than a cell a computed write can reach.
    fields = _synthesize_fields(
        scan, annotations, headers, stable,
        dynamic_write_cells | external_write_cells | clear_exposed_cells(program, integer_aliases),
        overrides,
    )
    external_readable_ranges = _extension_readable_ranges(
        headers, scan.write_values, validated_ranges(overrides.get("external_readable_ranges"))
    )
    return {
        "size": 512,
        "literal_reads": sorted(scan.reads),
        "literal_writes": sorted(scan.writes),
        "dynamic_read": scan.dynamic_read,
        "dynamic_write": scan.dynamic_write,
        "dynamic_read_ranges": dynamic_read_ranges,
        "dynamic_write_ranges": dynamic_write_ranges,
        "dynamic_read_proven_ranges": proofs["read"].ranges if scan.dynamic_read else [],
        "dynamic_write_proven_ranges": proofs["write"].ranges if scan.dynamic_write else [],
        "dynamic_read_range_source": dynamic_read_range_source,
        "dynamic_write_range_source": dynamic_write_range_source,
        "clears_all": scan.clears_all,
        "external_readable_ranges": external_readable_ranges,
        "external_writable_ranges": validated_ranges(overrides.get("external_writable_ranges")),
        "fields": [fields[address] for address in sorted(fields)],
    }, sorted(publication_rules, key=lambda item: (item["address"], item["kind"], item["description"]))


def restart_behavior(rows: list[list[str]], clears_all: bool) -> dict[str, str]:
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


def header_invariants(headers: list[dict[str, int]], own_stack: dict[str, Any]) -> list[dict[str, Any]]:
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
