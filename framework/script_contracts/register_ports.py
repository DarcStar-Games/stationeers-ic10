"""Resolve register-indexed device ports (`dr<n>`) to the pins they can address.

A `put dr9 14 r2` writes whichever pin `r9` names when the instruction runs, so
the pin is a fact about the register's values and not about the operand. Left
unresolved, every access through the register is invisible to the contract:
the wiring map has no port to key on, no peer's surface is compared against
the cells written, and a program can write a peer's header cells for years
without a validator noticing (issue #163). So a register-indexed port is
resolved the way a computed stack address is. `value_bounds` derives what the
branches around each access let the register hold; where that derivation is
whole at every access the pins are source-derived, and where it is not -- a
register read back from the program's own stack, say -- a reviewed
`register_ports` override in `data/script_contract_overrides.json` names the
pins, fingerprinted to the source and required to contain every pin the proof
did establish. A `dr<n>` with neither does not build.
"""
from __future__ import annotations

from typing import Any

from framework.script_contracts.parsing import (
    PORTS,
    RegisterPorts,
    parse_program,
    register_port,
)
from framework.script_contracts.value_bounds import ValueBounds


def validated_pins(token: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(set(value)) != len(value):
        raise ValueError(f"register_ports {token}: expected a non-empty list of distinct pins, got {value!r}")
    unknown = sorted(pin for pin in value if pin not in PORTS)
    if unknown:
        raise ValueError(f"register_ports {token}: {unknown} are not device pins d0..d5")
    return tuple(sorted(value))


def analyze_register_ports(
    source: str, integer_aliases: dict[str, int], declared: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Per `dr<n>` operand in `source`: the register, the pins it can name, and why.

    `declared` is the program's `register_ports` override (`{"dr9": ["d1", "d2"]}`).
    Raises when a declaration names an operand the source never uses, omits a
    pin the branches prove the register can hold, or is missing for an operand
    the branches do not bound at every access.
    """
    program = parse_program(source)
    uses: dict[str, list[int]] = {}
    for index, entry in enumerate(program):
        for token in entry["row"]:
            if register_port(token) is not None:
                uses.setdefault(token, []).append(index)
    declared = declared or {}
    stale = sorted(set(declared) - set(uses))
    if stale:
        raise ValueError(f"register_ports declares {stale}, which the source never addresses")
    if not uses:
        return {}
    analyzer = ValueBounds(source, integer_aliases)
    resolved: dict[str, dict[str, Any]] = {}
    for token in sorted(uses):
        register = register_port(token)
        assert register is not None
        proven: set[int] = set()
        whole = True
        for index in uses[token]:
            values, closed = analyzer.values(index, register, analyzer.sites(index))
            if values is None:
                whole = False
                continue
            proven |= {int(value) for value in values}
            whole = whole and closed
        outside = sorted(value for value in proven if not 0 <= value < len(PORTS))
        if outside:
            raise ValueError(
                f"{token}: the branches let {register} hold {outside}, which name no device pin")
        proven_pins = tuple(f"d{value}" for value in sorted(proven))
        pins = declared.get(token)
        if pins is not None:
            pins = validated_pins(token, pins)
            missing = sorted(set(proven_pins) - set(pins))
            if missing:
                raise ValueError(
                    f"{token}: register_ports {list(pins)} omits source-proven pins {missing}")
        if whole and (pins is None or pins == proven_pins):
            pins, provenance = proven_pins, "source-derived"
        elif pins is not None:
            provenance = "source-fingerprinted-exception"
        else:
            raise ValueError(
                f"{token}: the branches do not bound {register} at every access; declare a"
                " reviewed register_ports entry naming the pins it can hold")
        resolved[token] = {
            "register": register,
            "pins": list(pins),
            "proven_pins": list(proven_pins),
            "source": provenance,
        }
    return resolved


def register_port_pins(resolved: dict[str, dict[str, Any]]) -> RegisterPorts:
    """The `{"dr9": ("d1", "d2")}` view the access scans consume."""
    return {token: tuple(item["pins"]) for token, item in resolved.items()}
