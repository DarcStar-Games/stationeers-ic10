"""Validate player-supplied wiring against generated IC10 script contracts."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import re

from framework.json_schema import validate

FORMAT = "IC10_COMMISSIONING_WIRING_V1"
EVIDENCE_STATUSES = {"PASS", "FAIL", "BLOCKED"}
DYNAMIC_PROPERTY = re.compile(r"^(?:r(?:1[0-7]|[0-9])|ra|sp)$")


def load_wiring(path: Path, root: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    schema = json.loads((Path(root) / "schemas/commissioning_wiring.schema.json").read_text())
    validate(value, schema)
    return value


def wiring_sha256(wiring: dict[str, Any]) -> str:
    canonical = json.dumps(wiring, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def load_contracts(root: Path) -> list[dict[str, Any]]:
    index = json.loads((Path(root) / "contracts/index.json").read_text())
    return [json.loads((Path(root) / item["contract"]).read_text()) for item in index["contracts"]]


def resolve_contract(selector: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [
        contract for contract in contracts
        if selector in {
            contract["source"],
            contract["identity"]["service_id"],
            contract["source"].replace("ic10/", "contracts/").replace(".ic10", ".contract.json"),
        }
    ]
    if len(matches) != 1:
        detail = "not found" if not matches else "ambiguous"
        raise ValueError(f"contract selector {selector!r} is {detail}")
    return matches[0]


def contract_identity(contract: dict[str, Any]) -> dict[str, str]:
    return {
        "service_id": contract["identity"]["service_id"],
        "source": contract["source"],
        "source_sha256": contract["source_sha256"],
    }


def _expanded(ranges: list[dict[str, int]]) -> set[int]:
    return {cell for item in ranges for cell in range(item["start"], item["end"] + 1)}


def _requested_cells(stack: dict[str, Any], direction: str) -> set[int]:
    return set(stack[f"literal_{direction}s"]) | _expanded(stack[f"dynamic_{direction}_ranges"])


def _provider_cells(contract: dict[str, Any], direction: str) -> set[int]:
    own = contract["own_stack"]
    if direction == "read":
        cells = set(own["literal_writes"]) | _expanded(own["external_readable_ranges"])
        access = "external-read"
    else:
        cells = set(own["literal_reads"]) | _expanded(own["external_writable_ranges"])
        access = "external-write"
    cells.update(field["address"] for field in own["fields"] if access in field["access"])
    return cells


def _result(obligation_id: str, status: str, message: str, category: str = "static") -> dict[str, str]:
    return {"id": obligation_id, "status": status, "category": category, "message": message}


def _missing_ranges(cells: set[int]) -> str:
    if not cells:
        return ""
    ordered = sorted(cells)
    ranges: list[list[int]] = []
    for cell in ordered:
        if ranges and cell == ranges[-1][1] + 1:
            ranges[-1][1] = cell
        else:
            ranges.append([cell, cell])
    return ", ".join(str(start) if start == end else f"{start}..{end}" for start, end in ranges)


def _field_constants(contract: dict[str, Any]) -> dict[int, Any]:
    constants = {field["address"]: field["const"] for field in contract["own_stack"]["fields"] if "const" in field}
    for protocol in contract["contracts"]["provides"]:
        constants.setdefault(protocol["base"], protocol["magic"])
        constants.setdefault(protocol["base"] + 1, protocol["abi"])
    return constants


def _fencing(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return "none declared by the provider contract"
    return "; ".join(f"{item['kind']} S{item['address']}: {item['description']}" for item in rules)


def _observation(
    obligation_id: str,
    port: str,
    tool: str,
    summary: str,
    *,
    cells: list[dict[str, Any]] | None = None,
    capabilities: dict[str, Any] | None = None,
    fences: list[dict[str, Any]] | None = None,
    fencing: str = "none",
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": obligation_id,
        "port": port,
        "tool": tool,
        "summary": summary,
        "fencing": fencing,
    }
    if cells:
        value["cells"] = cells
    if capabilities and any(capabilities.values()):
        value["capabilities"] = capabilities
    if fences:
        value["fences"] = fences
    return value


def _validate_script_port(
    port: dict[str, Any], mapping: dict[str, Any], provider: dict[str, Any], accepted_protocols: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    name = port["port"]
    target = port["target"]
    results: list[dict[str, str]] = []
    observations: list[dict[str, Any]] = []
    if target["kind"] == "physical-device":
        return [_result(f"{name}.target-kind", "FAIL", "physical-device port cannot map to a script")], []

    provider_protocols = provider["contracts"]["provides"]
    provided = {item["protocol_id"] for item in provider_protocols}
    compatible_headers: list[tuple[dict[str, Any], dict[str, Any]]] = []
    fence_rules: list[dict[str, Any]] = []
    if target["kind"] == "stack-protocol":
        accepted = set(target["protocol_ids"])
        accepted_headers = {
            (item["protocol_id"], item["header_base"], item["magic"], item["abi"]): item
            for item in accepted_protocols
        }
        compatible_headers = [
            (item, accepted_headers[(item["protocol_id"], item["base"], item["magic"], item["abi"])])
            for item in provider_protocols
            if (item["protocol_id"], item["base"], item["magic"], item["abi"]) in accepted_headers
        ]
        if not compatible_headers:
            results.append(_result(
                f"{name}.protocol", "FAIL",
                f"provider offers {sorted(provided) or ['no protocol']} without a matching header base; expected one of {sorted(accepted)}",
            ))
        else:
            header, accepted_header = compatible_headers[0]
            results.append(_result(
                f"{name}.protocol", "PASS", f"provider declares {header['protocol_id']} at S{header['base']}"
            ))
            required_rules = {
                (item["kind"], item["address"]): item
                for item in accepted_header.get("publication_requirements", [])
            }
            provider_rules = {
                (item["kind"], item["address"]): item
                for item in provider["behavior"].get("publication_rules", [])
            }
            missing_rules = sorted(set(required_rules) - set(provider_rules))
            results.append(_result(
                f"{name}.publication", "FAIL" if missing_rules else "PASS",
                f"provider lacks publication rules {missing_rules}"
                if missing_rules else f"provider satisfies {len(required_rules)} required publication fence(s)",
            ))
            fence_rules = [provider_rules[key] for key in required_rules if key in provider_rules]
    else:
        results.append(_result(
            f"{name}.interface", "PASS",
            f"provider is statically checked against {target['interface_id']}",
        ))
        fence_rules = provider["behavior"].get("publication_rules", [])

    capability_results, capabilities = _capability_results(name, port["device_properties"], mapping)
    results.extend(capability_results)

    for direction in ("read", "write"):
        requested = _requested_cells(port["stack"], direction)
        available = _provider_cells(provider, direction)
        missing = requested - available
        results.append(_result(
            f"{name}.stack-{direction}",
            "FAIL" if missing else "PASS",
            f"provider lacks {direction} access at {_missing_ranges(missing)}"
            if missing else f"provider covers {len(requested)} requested {direction} cell(s)",
        ))

    constants = _field_constants(provider)
    constraints_by_address: dict[int, list[Any]] = {}
    for constraint in port["stack"]["constraints"]:
        constraints_by_address.setdefault(constraint["address"], []).append(constraint["equals"])
    runtime_constraints: list[tuple[str, dict[str, Any]]] = []
    for address, unsorted_values in sorted(constraints_by_address.items()):
        expected_values = sorted(set(unsorted_values), key=lambda value: (type(value).__name__, str(value)))
        for expected in expected_values:
            obligation_id = f"{name}.constraint.s{address}"
            if len(expected_values) > 1:
                identity = json.dumps(
                    {"type": type(expected).__name__, "value": expected},
                    sort_keys=True, separators=(",", ":"),
                ).encode()
                obligation_id += f".value.{hashlib.sha256(identity).hexdigest()[:8]}"
            if address in constants and constants[address] != expected:
                results.append(_result(
                    obligation_id, "FAIL", f"provider constant is {constants[address]!r}; expected {expected!r}"
                ))
            elif address in constants:
                results.append(_result(
                    obligation_id, "PASS", f"provider source fixes S{address} to required value {expected!r}"
                ))
            else:
                results.append(_result(
                    obligation_id, "UNRESOLVED", f"observe S{address} == {expected!r}", "runtime"
                ))
                runtime_constraints.append((obligation_id, {"address": address, "expected": expected}))

    identity_id = f"{name}.provider-observed"
    capability_note = " and exercise its declared LogicType/slot capabilities" if any(capabilities.values()) else ""
    results.append(_result(
        identity_id, "UNRESOLVED",
        f"confirm screw {name} ({mapping['reference']}) is the declared provider in game{capability_note}", "runtime",
    ))
    if target["kind"] == "stack-protocol":
        header_cells = []
        if compatible_headers:
            item, _ = compatible_headers[0]
            header_cells = [
                {"address": item["base"], "expected": item["magic"]},
                {"address": item["base"] + 1, "expected": item["abi"]},
            ]
        observations.append(_observation(
            identity_id, name, "snapshot-probe",
            "Capture the declared provider header and any listed housing capabilities on the mapped screw; PASS only when every expectation matches.",
            cells=header_cells, capabilities=capabilities, fencing="none; literal protocol header",
        ))
    else:
        observations.append(_observation(
            identity_id, name, "manual-wiring-check",
            "Access-only interfaces have no identifying header; confirm the screw-to-housing wire, recorded ReferenceId, and listed capabilities.",
            capabilities=capabilities,
            fencing="not available until framework self-identification is standardized",
        ))
    for obligation_id, cell in runtime_constraints:
        tool = "snapshot-probe" if fence_rules else "stack-cell-monitor"
        observations.append(_observation(
            obligation_id, name, tool,
            "Capture the contract-derived cell with its publication fence and compare it with the accepted value."
            if fence_rules else "Read the contract-derived cell and compare it with the accepted value.",
            cells=[cell], fences=fence_rules, fencing=_fencing(fence_rules),
        ))
    return results, observations


def _slot_key(value: dict[str, Any]) -> tuple[Any, str]:
    return value["slot"], value["property"]


def _property_bindings(mapping: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    bindings: dict[str, str] = {}
    duplicates: set[str] = set()
    for item in mapping["capabilities"]["property_bindings"]:
        if item["operand"] in bindings:
            duplicates.add(item["operand"])
        bindings[item["operand"]] = item["property"]
    return bindings, duplicates


def _resolved_device_properties(
    requirements: dict[str, Any], mapping: dict[str, Any]
) -> tuple[dict[str, Any], set[str], set[str]]:
    bindings, duplicates = _property_bindings(mapping)
    missing: set[str] = set()

    def resolve(property_name: str) -> str | None:
        if not DYNAMIC_PROPERTY.fullmatch(property_name):
            return property_name
        if property_name not in bindings:
            missing.add(property_name)
            return None
        return bindings[property_name]

    resolved = {"reads": [], "writes": [], "slot_reads": [], "slot_writes": []}
    for direction in ("reads", "writes"):
        resolved[direction] = [value for item in requirements[direction] if (value := resolve(item)) is not None]
    for direction in ("slot_reads", "slot_writes"):
        for item in requirements[direction]:
            property_name = resolve(item["property"])
            if property_name is not None:
                resolved[direction].append({"slot": item["slot"], "property": property_name})
    return resolved, missing, duplicates


def _capability_results(
    name: str, requirements: dict[str, Any], mapping: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    capabilities = mapping["capabilities"]
    resolved, missing_bindings, duplicate_bindings = _resolved_device_properties(requirements, mapping)
    checks = (
        ("properties-read", resolved["reads"], capabilities["properties_readable"], lambda value: value),
        ("properties-write", resolved["writes"], capabilities["properties_writable"], lambda value: value),
        ("slots-read", resolved["slot_reads"], capabilities["slot_properties_readable"], _slot_key),
        ("slots-write", resolved["slot_writes"], capabilities["slot_properties_writable"], _slot_key),
    )
    results = [_result(
        f"{name}.property-bindings", "FAIL" if missing_bindings or duplicate_bindings else "PASS",
        f"dynamic LogicType operands lack concrete bindings: {sorted(missing_bindings)}"
        if missing_bindings else f"dynamic LogicType operands have duplicate bindings: {sorted(duplicate_bindings)}"
        if duplicate_bindings else "dynamic LogicType operands are concretely bound",
    )]
    for suffix, requested, supplied, key in checks:
        missing = {key(value) for value in requested} - {key(value) for value in supplied}
        results.append(_result(
            f"{name}.{suffix}", "FAIL" if missing else "PASS",
            f"declared target lacks {sorted(missing, key=str)}" if missing else f"declared target supports required {suffix}",
        ))
    return results, resolved


def _validate_device_port(
    port: dict[str, Any], mapping: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    name = port["port"]
    if port["target"]["kind"] != "physical-device":
        return [_result(f"{name}.target-kind", "FAIL", "stack port cannot map to a physical device")], []
    results, capabilities = _capability_results(name, port["device_properties"], mapping)
    identity_id = f"{name}.device-observed"
    results.append(_result(
        identity_id, "UNRESOLVED",
        f"confirm {mapping['reference']} is a {mapping['device_type']} with the declared capabilities", "runtime",
    ))
    observations = [_observation(
        identity_id, name, "manual-device-check",
        "Exercise the listed LogicType and slot assumptions on the connected device; do not treat the declaration as proof.",
        capabilities=capabilities,
    )]
    return results, observations


def build_plan(wiring: dict[str, Any], root: Path) -> dict[str, Any]:
    contracts = load_contracts(root)
    consumer = resolve_contract(wiring["consumer"], contracts)
    contract_ports = {port["port"]: port for port in consumer["device_ports"]}
    results: list[dict[str, str]] = []
    observations: list[dict[str, Any]] = []
    provider_identities: dict[str, dict[str, str]] = {}
    consumed_protocols = {
        item["port"]: item["accepted"] for item in consumer["contracts"]["consumes"]
    }

    for name, port in contract_ports.items():
        mapping = wiring["ports"].get(name)
        if mapping is None:
            status = "FAIL" if port["requirement"] == "required" else "PASS"
            results.append(_result(f"{name}.mapping", status, f"{port['requirement']} port is not mapped"))
            continue
        if mapping["kind"] == "script":
            try:
                provider = resolve_contract(mapping["provider"], contracts)
            except ValueError as error:
                results.append(_result(f"{name}.provider", "FAIL", str(error)))
                continue
            provider_identities[name] = contract_identity(provider)
            port_results, port_observations = _validate_script_port(
                port, mapping, provider, consumed_protocols.get(name, [])
            )
        else:
            port_results, port_observations = _validate_device_port(port, mapping)
        results.extend(port_results)
        observations.extend(port_observations)

    for name in sorted(set(wiring["ports"]) - set(contract_ports)):
        results.append(_result(f"{name}.mapping", "FAIL", "consumer contract does not use this port"))

    dynamic_bindings: dict[tuple[str, int, str], dict[str, Any]] = {}
    for target_port, port in contract_ports.items():
        mapping = wiring["ports"].get(target_port)
        if mapping is None:
            continue
        bindings, duplicates = _property_bindings(mapping)
        for source in port.get("dynamic_property_sources", []):
            operand = source["operand"]
            if operand not in bindings or operand in duplicates:
                continue
            key = source["source_port"], source["address"], operand
            entry = dynamic_bindings.setdefault(key, {
                "source": source,
                "fences": set(),
                "properties": set(),
                "target_ports": set(),
            })
            entry["fences"].add(json.dumps(source.get("fence"), sort_keys=True))
            entry["properties"].add(bindings[operand])
            entry["target_ports"].add(target_port)

    source_cells: dict[tuple[str, int], list[tuple[str, int, str]]] = {}
    for key in dynamic_bindings:
        source_cells.setdefault(key[:2], []).append(key)
    conflicted_bindings: set[tuple[str, int, str]] = set()
    for (source_port, address), keys in sorted(source_cells.items()):
        if len(keys) == 1:
            continue
        properties = {
            property_name
            for key in keys
            for property_name in dynamic_bindings[key]["properties"]
        }
        fences = {
            fence
            for key in keys
            for fence in dynamic_bindings[key]["fences"]
        }
        if len(properties) <= 1 and len(fences) <= 1:
            continue
        conflicted_bindings.update(keys)
        details = []
        if len(properties) > 1:
            details.append(f"conflicting properties {sorted(properties)}")
        if len(fences) > 1:
            details.append("conflicting fence declarations")
        results.append(_result(
            f"binding.{source_port}.s{address}", "FAIL",
            f"one runtime source cell has {' and '.join(details)}",
        ))

    for (source_port, address, operand), entry in sorted(dynamic_bindings.items()):
        if (source_port, address, operand) in conflicted_bindings:
            continue
        obligation_id = f"binding.{source_port}.s{address}.{operand}"
        properties = entry["properties"]
        targets = sorted(entry["target_ports"])
        if len(entry["fences"]) != 1:
            results.append(_result(
                obligation_id, "FAIL",
                f"targets {targets} declare conflicting fences for one runtime operand",
            ))
            continue
        if len(properties) != 1:
            results.append(_result(
                obligation_id, "FAIL",
                f"targets {targets} bind one runtime operand to conflicting properties {sorted(properties)}",
            ))
            continue
        property_name = next(iter(properties))
        source = entry["source"]
        fence = source.get("fence")
        results.append(_result(
            obligation_id, "UNRESOLVED",
            f"observe {source_port} S{address} == LogicType {property_name!r} for {operand} used by {targets}",
            "runtime",
        ))
        observations.append(_observation(
            obligation_id, source_port, "snapshot-probe" if fence else "stack-cell-monitor",
            f"Capture the configured LogicType that populates {operand} for {targets}; PASS only when it is {property_name}.",
            cells=[{"address": address, "expected": property_name}],
            fences=[fence] if fence else None,
            fencing=_fencing([fence] if fence else []),
        ))

    binding = {
        "wiring_sha256": wiring_sha256(wiring),
        "consumer_contract": contract_identity(consumer),
        "provider_contracts": provider_identities,
        "target_ids": {
            name: (
                port["target"].get("interface_id")
                or ",".join(port["target"].get("protocol_ids", []))
                or "physical-device"
            )
            for name, port in contract_ports.items() if name in wiring["ports"]
        },
    }
    binding["plan_id"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    return {
        "format": "IC10_COMMISSIONING_PLAN_V1",
        "label": wiring.get("label", ""),
        "binding": binding,
        "results": results,
        "observations": observations,
    }


def apply_evidence(plan: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    entry = session.get("wiring_results", {}).get(plan["binding"]["plan_id"], {})
    runs = entry.get("runs", {})
    output = {**plan, "results": [dict(item) for item in plan["results"]]}
    if entry and entry.get("binding") != plan["binding"]:
        output["results"].append(_result(
            "evidence-binding", "FAIL",
            "recorded evidence does not match the current contract/interface binding",
        ))
        return output
    valid_ids = {item["id"] for item in output["results"] if item["category"] == "runtime"}
    for item in output["results"]:
        history = runs.get(item["id"], [])
        if item["id"] in valid_ids and history:
            latest = history[-1]
            if not isinstance(latest, dict) or latest.get("status") not in EVIDENCE_STATUSES:
                item["status"] = "FAIL"
                item["message"] = "recorded evidence has an invalid status"
                continue
            item["status"] = latest["status"]
            item["message"] = str(latest.get("observed", ""))
            item["evidence_recorded_at"] = str(latest.get("recorded_at", ""))
    return output


def overall_status(plan: dict[str, Any]) -> str:
    statuses = {item["status"] for item in plan["results"]}
    if "FAIL" in statuses or "BLOCKED" in statuses:
        return "FAIL"
    if "UNRESOLVED" in statuses:
        return "UNRESOLVED"
    return "PASS"
