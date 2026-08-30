#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from framework.commissioning_validators import (
    DEVICE_TARGET_VALIDATORS,
    DeviceTargetValidation,
    Obligation,
    ResultCollector,
    SCRIPT_TARGET_VALIDATORS,
    ScriptTargetValidation,
    ValidationBatch,
    build_binding,
    static_obligation,
    validate_capabilities,
    validate_dynamic_bindings,
    validate_device_port,
    validate_protocol_compatibility,
    validate_publication_fences,
    validate_runtime_constraints,
    validate_script_port,
    validate_stack_coverage,
)


fails = []


def capabilities(*, reads=(), writes=(), bindings=()):
    return {
        "properties_readable": list(reads),
        "properties_writable": list(writes),
        "slot_properties_readable": [],
        "slot_properties_writable": [],
        "property_bindings": [
            {"operand": operand, "property": property_name}
            for operand, property_name in bindings
        ],
    }


requirements = {
    "reads": ["r2"],
    "writes": ["Setting"],
    "slot_reads": [],
    "slot_writes": [],
}
mapping = {
    "kind": "script",
    "provider": "provider",
    "reference": "housing",
    "capabilities": capabilities(
        reads=("Pressure",), writes=("Setting",), bindings=(("r2", "Pressure"),)
    ),
}
capability_batch, resolved = validate_capabilities("d0", requirements, mapping)
if resolved["reads"] != ["Pressure"] or any(
    item.status != "PASS" for item in capability_batch.obligations
):
    fails.append("capability validation is not independently usable with minimal fixtures")


provider = {
    "source": "ic10/provider.ic10",
    "source_sha256": "provider-sha",
    "identity": {"service_id": "provider"},
    "contracts": {
        "provides": [{
            "protocol_id": "example.protocol",
            "base": 0,
            "magic": 314159,
            "abi": 1,
        }]
    },
    "behavior": {
        "publication_rules": [{
            "kind": "commit-last",
            "address": 5,
            "description": "generation LAST",
        }]
    },
    "own_stack": {
        "literal_reads": [3],
        "literal_writes": [2],
        "external_readable_ranges": [],
        "external_writable_ranges": [],
        "fields": [],
    },
}
stack = {
    "literal_reads": [2],
    "literal_writes": [3],
    "dynamic_read_ranges": [],
    "dynamic_write_ranges": [],
    "constraints": [{"address": 7, "equals": 42}],
}
stack_batch = validate_stack_coverage("d0", stack, provider)
if [item.status for item in stack_batch.obligations] != ["PASS", "PASS"]:
    fails.append("stack coverage validator rejected a minimal compatible provider")

constraint_batch = validate_runtime_constraints(
    "d0", stack["constraints"], provider, provider["behavior"]["publication_rules"]
)
if len(constraint_batch.obligations) != 1 or len(constraint_batch.observations()) != 1:
    fails.append("runtime constraint validation did not pair its result and observation")
elif constraint_batch.observations()[0].get("fences") != provider["behavior"]["publication_rules"]:
    fails.append("runtime constraint validation lost its publication fence")


port = {
    "port": "d0",
    "target": {"kind": "stack-protocol", "protocol_ids": ["example.protocol"]},
    "device_properties": requirements,
    "stack": stack,
}
accepted = [{
    "protocol_id": "example.protocol",
    "header_base": 0,
    "magic": 314159,
    "abi": 1,
    "publication_requirements": [{"kind": "commit-last", "address": 5}],
}]
compatibility = validate_protocol_compatibility(
    "d0", port["target"], provider["contracts"]["provides"], accepted
)
if compatibility.header != provider["contracts"]["provides"][0]:
    fails.append("protocol compatibility is not independently contract-derived")
else:
    publication = validate_publication_fences("d0", compatibility.accepted_header, provider)
    if publication.batch.obligations[0].status != "PASS" or not publication.fence_rules:
        fails.append("publication-fence validation is not independently contract-derived")

port_batch = validate_script_port(port, mapping, provider, accepted)
runtime_ids = {
    item.identifier for item in port_batch.obligations if item.category == "runtime"
}
if runtime_ids != {item["id"] for item in port_batch.observations()}:
    fails.append("script-port validation did not emit exactly one recipe per runtime result")
elif port_batch.observations()[0]["id"] != "d0.provider-observed":
    fails.append("script-port validation changed the stable observation ordering")


strategy_called = []


def custom_strategy(name, _target, _provider, _accepted):
    strategy_called.append(name)
    return ScriptTargetValidation(
        ValidationBatch((static_obligation(f"{name}.custom", "FAIL", "custom strategy"),)),
        False,
    )


SCRIPT_TARGET_VALIDATORS["test-target"] = custom_strategy
try:
    custom_port = {**port, "target": {"kind": "test-target"}}
    custom_batch = validate_script_port(custom_port, mapping, provider, [])
finally:
    del SCRIPT_TARGET_VALIDATORS["test-target"]
if strategy_called != ["d0"] or [item.identifier for item in custom_batch.obligations] != ["d0.custom"]:
    fails.append("new script target kinds cannot be supplied through the strategy table")


def custom_device_strategy(name, _target):
    strategy_called.append(f"device:{name}")
    return DeviceTargetValidation(
        ValidationBatch((static_obligation(f"{name}.custom-device", "FAIL", "custom strategy"),)),
        False,
    )


DEVICE_TARGET_VALIDATORS["test-device-target"] = custom_device_strategy
try:
    custom_device_port = {**port, "target": {"kind": "test-device-target"}}
    custom_device_batch = validate_device_port(custom_device_port, mapping)
finally:
    del DEVICE_TARGET_VALIDATORS["test-device-target"]
if strategy_called[-1:] != ["device:d0"] or [
    item.identifier for item in custom_device_batch.obligations
] != ["d0.custom-device"]:
    fails.append("new physical-device target kinds cannot be supplied through the strategy table")


dynamic_ports = {
    "d0": {
        "dynamic_property_sources": [{
            "source_port": "d2",
            "address": 7,
            "operand": "r2",
            "fence": None,
        }]
    }
}
dynamic_batch = validate_dynamic_bindings(dynamic_ports, {"d0": mapping})
if [item.identifier for item in dynamic_batch.obligations] != ["binding.d2.s7.r2"]:
    fails.append("dynamic-property binding validation changed its stable obligation ID")
elif dynamic_batch.observations()[0]["cells"] != [{"address": 7, "expected": "Pressure"}]:
    fails.append("dynamic-property binding validation lost the resolved LogicType")


collector = ResultCollector()
collector.add(constraint_batch)
try:
    Obligation("broken.runtime", "UNRESOLVED", "missing recipe", "runtime")
except ValueError:
    pass
else:
    fails.append("runtime obligations can be constructed without an observation recipe")


consumer = {
    "source": "ic10/consumer.ic10",
    "source_sha256": "consumer-sha",
    "identity": {"service_id": "consumer"},
}
binding = build_binding(
    {"consumer": "consumer", "ports": {"d0": mapping}},
    consumer,
    {"d0": {"service_id": "provider", "source": provider["source"], "source_sha256": "provider-sha"}},
    {"d0": port},
)
if len(binding["plan_id"]) != 24 or binding["target_ids"] != {"d0": "example.protocol"}:
    fails.append("binding identity generation is not independently deterministic")


if fails:
    print("Commissioning validator unit tests: FAIL")
    for failure in fails:
        print(" -", failure)
    raise SystemExit(1)
print("Commissioning validator unit tests: PASS")
print(" - focused protocol, capability, stack, runtime, binding, and collector behavior covered")
