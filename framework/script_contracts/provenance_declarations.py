"""The shape of a reviewed `network_provenance` declaration (issue #174).

A declaration says where a network write's reference register is loaded from
and which contracts a ReferenceId in that place names. The walk that holds it
to the source lives in `framework.network_provenance`; this module is only the
vocabulary, so the contract build can check a declaration's shape without
importing the walk.
"""
from __future__ import annotations

from typing import Any

# origin kind -> the fields it takes besides `kind`
ORIGIN_KINDS = {
    "peer-cell": ("identity", "cells"),
    "own-cell": ("cells", "filled_by"),
    "reference-cell": ("via", "cells"),
    "port-cell": ("port", "cells"),
    "port-device": ("port",),
    "index-cell": ("index", "cells"),
}
# Who puts a ReferenceId in one of the program's own cells: the program itself
# (a reference it checked and stored), a wired peer or network writer (a
# request cell), or the operator at commissioning (a configured service
# reference nothing in the tree writes). `validate_network_provenance.py`
# holds each to the contracts.
FILLED_BY = ("self", "peer", "operator")


def validate_provenance(declarations: list[dict[str, Any]], references: set[str]) -> list[dict[str, Any]]:
    """Check the shape of a program's `network_provenance` declarations.

    `references` are the reference operands the program writes through; a
    declaration for anything else is stale.
    """
    for declaration in declarations:
        reference = declaration.get("reference")
        if reference not in references:
            raise ValueError(f"network provenance declaration names a reference with no network write: {declaration}")
        origin = declaration.get("origin")
        if not isinstance(origin, dict) or origin.get("kind") not in ORIGIN_KINDS:
            raise ValueError(f"network provenance declaration has no recognized origin kind: {declaration}")
        fields = ORIGIN_KINDS[origin["kind"]]
        if set(origin) != {"kind", *fields}:
            raise ValueError(f"network provenance origin {origin['kind']} takes exactly {fields}: {declaration}")
        cells = origin.get("cells", "any")
        if cells != "any" and not (
            isinstance(cells, list) and cells
            and all(isinstance(cell, int) and 0 <= cell <= 511 for cell in cells)
        ):
            raise ValueError(f"network provenance origin cells must be 'any' or a list of stack addresses: {declaration}")
        if origin["kind"] == "own-cell" and origin["filled_by"] not in FILLED_BY:
            raise ValueError(f"network provenance own-cell origin must say who fills it, one of {FILLED_BY}: {declaration}")
        targets = declaration.get("targets")
        if not isinstance(targets, list) or not all(isinstance(target, str) and target for target in targets):
            raise ValueError(f"network provenance declaration needs a list of target contracts: {declaration}")
        if not targets and not declaration.get("device"):
            raise ValueError(f"network provenance declaration names no target contract and no device: {declaration}")
        if not isinstance(declaration.get("reason"), str) or not declaration["reason"]:
            raise ValueError(f"network provenance declaration has no reason: {declaration}")
    return declarations
