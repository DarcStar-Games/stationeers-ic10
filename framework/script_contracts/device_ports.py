"""Extract device-port and network dependencies and verify consumer claims.

Per-port stack accesses, device-property usage, and literal header checks are
scanned from source; declared consumers must be enforced by those literal
checks before they are believed, and each port resolves to a typed target.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
from typing import Any

from framework.script_contracts.control_flow import (
    branch_rejects_before_success,
    control_flow_dominators,
    must_reach,
    paths_preserve_register,
)
from framework.script_contracts.dynamic_ranges import (
    RangeProof,
    dynamic_port_proofs,
    merge_ranges,
    resolve_dynamic_ranges,
    validated_ranges,
)
from framework.script_contracts.naming import protocol_id
from framework.script_contracts.parsing import (
    parse_program,
    resolve_integer,
    resolve_literal,
    resolve_port,
    row_nodes,
)
from framework.script_contracts.publication import verified_seqlock_consumer

DYNAMIC_PROPERTY_RE = re.compile(r"^(?:r(?:1[0-7]|[0-9])|ra|sp)$")


def external_equality_checks(
    source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int]
) -> dict[str, dict[int, set[Any]]]:
    program = parse_program(source)
    nodes = row_nodes(program)
    labels = {entry["label"]: index for index, entry in enumerate(program) if entry["label"]}
    _, _, successors, _ = control_flow_dominators(program)
    checks: dict[str, dict[int, set[Any]]] = defaultdict(lambda: defaultdict(set))
    for index, row in enumerate(rows):
        if len(row) < 4 or row[0] != "get":
            continue
        port = resolve_port(row[2], aliases)
        cell = resolve_integer(row[3], integer_aliases)
        if port is None or cell is None or not 0 <= cell <= 511:
            continue
        register = row[1]
        for later_index, later in enumerate(rows[index + 1:index + 6], index + 1):
            if len(later) >= 3 and later[0] == "bne" and later[1] == register:
                expected = resolve_literal(later[2], integer_aliases)
                read_node = nodes[index]
                compare_node = nodes[later_index]
                fallthrough_node = compare_node + 1 if compare_node + 1 < len(program) else None
                if (
                    expected is not None
                    and fallthrough_node is not None
                    and must_reach(read_node, compare_node, successors)
                    and paths_preserve_register(read_node, compare_node, register, program, successors)
                    and branch_rejects_before_success(
                        later, compare_node, fallthrough_node, {read_node}, program,
                        side_effect_barriers=True,
                    )
                ):
                    checks[port][cell].add(expected)
                break
            if len(later) >= 2 and later[1] == register and later[0] not in {"beq", "bne", "beqz", "bnez"}:
                break
    return checks


def network_dependencies(
    source: str, rows: list[list[str]], integer_aliases: dict[str, int], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    program = parse_program(source)
    nodes = row_nodes(program)
    _, _, successors, _ = control_flow_dominators(program)
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
            address = resolve_integer(row[3], integer_aliases)
            target["dynamic_read"] |= address is None
            if address is not None:
                target["literal_reads"].add(address)
            register = row[1]
        elif row[0] == "putd" and len(row) >= 4:
            target = ensure(row[1], "reference-id")
            address = resolve_integer(row[2], integer_aliases)
            target["dynamic_write"] |= address is None
            if address is not None:
                target["literal_writes"].add(address)
        elif row[0] == "get" and len(row) >= 4 and row[2].startswith("db:"):
            target = ensure(row[2], "device-index")
            address = resolve_integer(row[3], integer_aliases)
            target["dynamic_read"] |= address is None
            if address is not None:
                target["literal_reads"].add(address)
            register = row[1]
        else:
            continue
        if register is None:
            continue
        read_node = nodes[index]
        check_start_node = read_node
        for later_index, later in enumerate(rows[index + 1:index + 5], index + 1):
            if len(later) >= 3 and later[1] == register and later[0] in {"bne", "blt", "bgt"}:
                value = resolve_literal(later[2], integer_aliases)
                compare_node = nodes[later_index]
                verified = (
                    value is not None
                    and address is not None
                    and must_reach(check_start_node, compare_node, successors)
                    and paths_preserve_register(
                        check_start_node, compare_node, register, program, successors
                    )
                    and branch_rejects_before_success(
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
                "protocol_id": protocol_id(declaration["magic"], abi),
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


def _optional_ports(source: str) -> set[str]:
    """Ports the leading comment block explicitly declares optional."""
    comments = "\n".join(line for line in source.splitlines()[:6] if line.lstrip().startswith("#"))
    optional_ports = set()
    port_mentions = list(re.finditer(r"\bd[0-5]\b", comments))
    for index, mention in enumerate(port_mentions):
        end = port_mentions[index + 1].start() if index + 1 < len(port_mentions) else len(comments)
        clause = comments[mention.start():end]
        if "optional" in clause.lower():
            optional_ports.add(mention.group())
    return optional_ports


def _scan_port_accesses(rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int], ensure) -> None:
    """Record every stack, property, and slot access each instruction makes on a port."""
    for row in rows:
        if row[0] == "alias":
            continue
        referenced = {resolve_port(token, aliases) for token in row}
        for port in referenced - {None}:
            ensure(port)
        op = row[0]
        if op == "get" and len(row) >= 4:
            port = resolve_port(row[2], aliases)
            if port:
                address = resolve_integer(row[3], integer_aliases)
                target = ensure(port)["stack"]
                target["dynamic_read"] |= address is None
                if address is not None:
                    target["literal_reads"].add(address)
        elif op == "put" and len(row) >= 4:
            port = resolve_port(row[1], aliases)
            if port:
                address = resolve_integer(row[2], integer_aliases)
                target = ensure(port)["stack"]
                target["dynamic_write"] |= address is None
                if address is not None:
                    target["literal_writes"].add(address)
        elif op in {"l", "lr"} and len(row) >= 4:
            port = resolve_port(row[2], aliases)
            if port:
                ensure(port)["device_properties"]["reads"].add(row[3])
        elif op in {"s", "sr"} and len(row) >= 4:
            port = resolve_port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["writes"].add(row[2])
        elif op == "ls" and len(row) >= 5:
            port = resolve_port(row[2], aliases)
            if port:
                slot = resolve_integer(row[3], integer_aliases)
                ensure(port)["device_properties"]["slot_reads"].add((slot if slot is not None else "dynamic", row[4]))
        elif op == "ss" and len(row) >= 5:
            port = resolve_port(row[1], aliases)
            if port:
                slot = resolve_integer(row[2], integer_aliases)
                ensure(port)["device_properties"]["slot_writes"].add((slot if slot is not None else "dynamic", row[3]))
        elif op == "bdnvl" and len(row) >= 3:
            port = resolve_port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["reads"].add(row[2])
        elif op == "bdnvs" and len(row) >= 3:
            port = resolve_port(row[1], aliases)
            if port:
                ensure(port)["device_properties"]["writes"].add(row[2])


def _finalize_port(
    port: str, item: dict[str, Any], optional_ports: set[str], overrides: dict[str, Any],
    proofs: dict[tuple[str, str], RangeProof],
) -> None:
    """Sort the scanned sets, verify dynamic-property provenance, and resolve ranges."""
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
        proof = proofs.get((port, direction), RangeProof())
        stack[ranges_key], stack[source_key] = resolve_dynamic_ranges(
            stack[dynamic_key], proof, declared_ranges, f"{port} {direction}"
        )


def analyze_device_ports(source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int], overrides: dict[str, Any]) -> list[dict[str, Any]]:
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

    _scan_port_accesses(rows, aliases, integer_aliases, ensure)
    for port, cells in external_equality_checks(source, rows, aliases, integer_aliases).items():
        target = ensure(port)["stack"]["constraints"]
        for address, values in sorted(cells.items()):
            for value in sorted(values, key=lambda item: (type(item).__name__, str(item))):
                target.append({"address": address, "equals": value})
    for port, declared in overrides.get("ports", {}).items():
        target = ensure(port)["stack"]
        target["dynamic_read_ranges"] = validated_ranges(declared.get("dynamic_read_ranges"))
        target["dynamic_write_ranges"] = validated_ranges(declared.get("dynamic_write_ranges"))
        if "role" in declared:
            ensure(port)["role"] = declared["role"]
        if "requirement" in declared:
            ensure(port)["requirement"] = declared["requirement"]
    proofs = dynamic_port_proofs(source, aliases, integer_aliases)
    optional_ports = _optional_ports(source)
    for port, item in state.items():
        _finalize_port(port, item, optional_ports, overrides, proofs)
    return [state[port] for port in sorted(state)]


def verify_declared_consumers(source: str, rows: list[list[str]], aliases: dict[str, str], integer_aliases: dict[str, int], declared: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = external_equality_checks(source, rows, aliases, integer_aliases)
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
                    and resolve_port(row[2], aliases) == port
                    and resolve_integer(row[3], integer_aliases) == address
                )
                if publication["kind"] == "commit-last" and not checks[port][address] and publication_reads < 2:
                    raise ValueError(
                        f"declared commit-last consumer {requirement} neither checks nor double-reads publication cell S{address}"
                    )
                if publication["kind"] == "seqlock" and not verified_seqlock_consumer(
                    source, rows, aliases, integer_aliases, port, address
                ):
                    raise ValueError(
                        f"declared seqlock consumer {requirement} does not parity-check and re-read S{address}"
                    )
            accepted.append({
                "protocol_id": protocol_id(magic, abi),
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


def access_interface_id(stack: dict[str, Any], assumptions: dict[str, Any]) -> str:
    signature = json.dumps(
        {"stack": stack, "assumptions": assumptions}, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"ic10.interface.access.{hashlib.sha256(signature).hexdigest()[:16]}"


def access_provider_obligations(stack: dict[str, Any], assumptions: dict[str, Any]) -> dict[str, Any]:
    readable = merge_ranges(
        [{"start": address, "end": address} for address in stack["literal_reads"]]
        + stack["dynamic_read_ranges"]
    )
    writable = merge_ranges(
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


def port_target(port: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
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
