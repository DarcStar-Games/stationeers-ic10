"""Validate, prove, and resolve the stack cell ranges dynamic addresses can reach.

Range lists are validated and merged here, and the resolver arbitrates between
source-derived proofs, fingerprinted overrides, and the conservative full-stack
fallback -- failing closed on any disagreement.

The proof itself is `framework.script_contracts.value_bounds`, which derives
what the branches around an access permit and says whether that is all of it.
A range is source-derived only where every access in its class was proven
whole, so one address nothing counts out leaves the whole class to review; that
is the same standard the literal-seeded linear loop proof this replaced held,
reached by asking the one analysis rather than a second one beside it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from framework.script_contracts.parsing import parse_program, resolve_integer, resolve_port
from framework.script_contracts.value_bounds import ValueBounds


@dataclass
class RangeProof:
    """What the branch bounds established for one class of dynamic accesses."""

    total: int = 0
    proved_accesses: int = 0
    ranges: list[dict[str, int]] = field(default_factory=list)

    @property
    def all_proven(self) -> bool:
        return self.total > 0 and self.proved_accesses == self.total


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


def dynamic_range_proofs(
    source: str, integer_aliases: dict[str, int], accesses: list[tuple[int, Any, str]]
) -> dict[Any, RangeProof]:
    """Bound classified dynamic accesses by the branches around each of them."""
    analyzer = ValueBounds(source, integer_aliases)
    proofs: dict[Any, RangeProof] = defaultdict(RangeProof)
    for index, key, address_token in accesses:
        proof = proofs[key]
        proof.total += 1
        cells, whole = analyzer.access_bounds(index, address_token)
        if not whole or cells is None:
            continue
        proof.proved_accesses += 1
        proof.ranges.extend({"start": cell, "end": cell} for cell in sorted(cells))
    for proof in proofs.values():
        proof.ranges = merge_ranges(proof.ranges)
    return proofs


def dynamic_port_proofs(
    source: str, aliases: dict[str, str], integer_aliases: dict[str, int]
) -> dict[tuple[str, str], RangeProof]:
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
    dynamic: bool, proof: RangeProof, declared_ranges: list[dict[str, int]], context: str,
    fallback_full_stack: bool = False,
) -> tuple[list[dict[str, int]], str]:
    """Publish one range list and say where it came from, failing closed on drift.

    A declaration has to contain every proven cell whether or not the proof was
    complete, because a window that omits one is not describing the access. Past
    that, a declaration wider than a complete proof is a reviewer being
    deliberately conservative rather than a disagreement -- a record window
    named whole where the program reads six cells of every eight -- and it
    stands, with the proof holding its floor and the source fingerprint holding
    it to this revision. Only an undeclared surface publishes the proof itself.
    """
    if not dynamic:
        if declared_ranges:
            raise ValueError(f"{context} declares ranges without a dynamic access")
        return [], "none"
    inferred_cells = expanded_ranges(proof.ranges)
    declared_cells = expanded_ranges(declared_ranges)
    if declared_ranges and not inferred_cells <= declared_cells:
        raise ValueError(
            f"{context} range {declared_ranges} omits source-proven cells "
            f"{sorted(inferred_cells-declared_cells)}"
        )
    if proof.all_proven and (not declared_ranges or declared_cells == inferred_cells):
        return proof.ranges, "source-derived"
    if declared_ranges:
        return declared_ranges, "source-fingerprinted-exception"
    if fallback_full_stack:
        return [{"start": 0, "end": 511}], "conservative-full-stack"
    return [], "source-fingerprinted-exception"
