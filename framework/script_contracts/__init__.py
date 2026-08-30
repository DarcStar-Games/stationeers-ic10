"""Extract deterministic machine-readable contracts from deployable IC10 programs.

The analysis lives in focused phase modules -- parsing, control_flow,
dynamic_ranges, address_forms, value_bounds, publication, own_stack,
device_ports, naming, assembly, checks -- and this facade re-exports the stable
public API unchanged.
"""
from framework.script_contracts.assembly import (
    FORMAT,
    INDEX_FORMAT,
    PROTOCOL_DEFINITION_FORMAT,
    PROTOCOL_FORMAT,
    build_all,
    build_contract,
    generated_artifact_paths,
    json_text,
    verify_override_source,
)
from framework.script_contracts.checks import compatibility_errors, invariant_errors
from framework.script_contracts.device_ports import (
    DYNAMIC_PROPERTY_RE,
    access_interface_id,
    access_provider_obligations,
)
from framework.script_contracts.dynamic_ranges import ranges_overlap
from framework.script_contracts.parsing import PORTS

__all__ = [
    "DYNAMIC_PROPERTY_RE",
    "FORMAT",
    "INDEX_FORMAT",
    "PORTS",
    "PROTOCOL_DEFINITION_FORMAT",
    "PROTOCOL_FORMAT",
    "access_interface_id",
    "access_provider_obligations",
    "build_all",
    "build_contract",
    "compatibility_errors",
    "generated_artifact_paths",
    "invariant_errors",
    "json_text",
    "ranges_overlap",
    "verify_override_source",
]
