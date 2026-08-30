"""Pure validation building blocks for commissioning plans."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import hashlib
import json
import re


DYNAMIC_PROPERTY = re.compile(r"^(?:r(?:1[0-7]|[0-9])|ra|sp)$")


def obligation_id(*parts: object) -> str:
    """Build a stable, human-readable obligation identifier."""
    return ".".join(str(part) for part in parts)


def _result(identifier: str, status: str, message: str, category: str = "static") -> dict[str, str]:
    return {"id": identifier, "status": status, "category": category, "message": message}


def _observation(
    identifier: str,
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
        "id": identifier,
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


@dataclass(frozen=True)
class Obligation:
    """One plan result and its evidence recipe, when runtime evidence is required."""

    identifier: str
    status: str
    message: str
    category: str = "static"
    observation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        needs_observation = self.category == "runtime"
        if needs_observation != (self.observation is not None):
            raise ValueError(f"runtime obligation {self.identifier!r} must have exactly one observation")
        if self.observation is not None and self.observation.get("id") != self.identifier:
            raise ValueError(f"observation ID does not match obligation {self.identifier!r}")

    def as_result(self) -> dict[str, str]:
        return _result(self.identifier, self.status, self.message, self.category)


@dataclass(frozen=True)
class ValidationBatch:
    """Ordered validation results with an explicit serialized observation order."""

    obligations: tuple[Obligation, ...] = ()
    observation_order: tuple[str, ...] | None = None

    def observations(self) -> list[dict[str, Any]]:
        paired = {
            item.identifier: item.observation
            for item in self.obligations
            if item.observation is not None
        }
        order = self.observation_order
        if order is None:
            order = tuple(item.identifier for item in self.obligations if item.observation is not None)
        if len(order) != len(set(order)) or set(order) != set(paired):
            raise ValueError("observation order must name every runtime obligation exactly once")
        return [paired[identifier] for identifier in order]


@dataclass
class ResultCollector:
    """Collect results while enforcing stable, one-to-one runtime evidence recipes."""

    results: list[dict[str, str]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    _identifiers: set[str] = field(default_factory=set)

    def add(self, batch: ValidationBatch) -> None:
        identifiers = [item.identifier for item in batch.obligations]
        duplicates = self._identifiers.intersection(identifiers)
        if len(identifiers) != len(set(identifiers)) or duplicates:
            raise ValueError(f"duplicate commissioning obligation IDs: {sorted(duplicates or set(identifiers))}")
        observations = batch.observations()
        self.results.extend(item.as_result() for item in batch.obligations)
        self.observations.extend(observations)
        self._identifiers.update(identifiers)


def static_obligation(identifier: str, status: str, message: str) -> Obligation:
    return Obligation(identifier, status, message)


def runtime_obligation(
    identifier: str, message: str, observation: dict[str, Any]
) -> Obligation:
    return Obligation(identifier, "UNRESOLVED", message, "runtime", observation)


def contract_identity(contract: dict[str, Any]) -> dict[str, str]:
    return {
        "service_id": contract["identity"]["service_id"],
        "source": contract["source"],
        "source_sha256": contract["source_sha256"],
    }


def wiring_sha256(wiring: dict[str, Any]) -> str:
    canonical = json.dumps(wiring, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


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


def _missing_ranges(cells: set[int]) -> str:
    if not cells:
        return ""
    ranges: list[list[int]] = []
    for cell in sorted(cells):
        if ranges and cell == ranges[-1][1] + 1:
            ranges[-1][1] = cell
        else:
            ranges.append([cell, cell])
    return ", ".join(str(start) if start == end else f"{start}..{end}" for start, end in ranges)


def _field_constants(contract: dict[str, Any]) -> dict[int, Any]:
    constants = {
        field["address"]: field["const"]
        for field in contract["own_stack"]["fields"]
        if "const" in field
    }
    for protocol in contract["contracts"]["provides"]:
        constants.setdefault(protocol["base"], protocol["magic"])
        constants.setdefault(protocol["base"] + 1, protocol["abi"])
    return constants


def _fencing(rules: list[dict[str, Any]]) -> str:
    if not rules:
        return "none declared by the provider contract"
    return "; ".join(f"{item['kind']} S{item['address']}: {item['description']}" for item in rules)


def _slot_key(value: dict[str, Any]) -> tuple[Any, str]:
    return value["slot"], value["property"]


def property_bindings(mapping: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    bindings: dict[str, str] = {}
    duplicates: set[str] = set()
    for item in mapping["capabilities"]["property_bindings"]:
        if item["operand"] in bindings:
            duplicates.add(item["operand"])
        bindings[item["operand"]] = item["property"]
    return bindings, duplicates


def resolved_device_properties(
    requirements: dict[str, Any], mapping: dict[str, Any]
) -> tuple[dict[str, Any], set[str], set[str]]:
    bindings, duplicates = property_bindings(mapping)
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
        resolved[direction] = [
            value for item in requirements[direction] if (value := resolve(item)) is not None
        ]
    for direction in ("slot_reads", "slot_writes"):
        for item in requirements[direction]:
            property_name = resolve(item["property"])
            if property_name is not None:
                resolved[direction].append({"slot": item["slot"], "property": property_name})
    return resolved, missing, duplicates


def validate_capabilities(
    name: str, requirements: dict[str, Any], mapping: dict[str, Any]
) -> tuple[ValidationBatch, dict[str, Any]]:
    capabilities = mapping["capabilities"]
    resolved, missing_bindings, duplicate_bindings = resolved_device_properties(requirements, mapping)
    checks: tuple[tuple[str, list[Any], list[Any], Callable[[Any], Any]], ...] = (
        ("properties-read", resolved["reads"], capabilities["properties_readable"], lambda value: value),
        ("properties-write", resolved["writes"], capabilities["properties_writable"], lambda value: value),
        ("slots-read", resolved["slot_reads"], capabilities["slot_properties_readable"], _slot_key),
        ("slots-write", resolved["slot_writes"], capabilities["slot_properties_writable"], _slot_key),
    )
    obligations = [static_obligation(
        obligation_id(name, "property-bindings"),
        "FAIL" if missing_bindings or duplicate_bindings else "PASS",
        f"dynamic LogicType operands lack concrete bindings: {sorted(missing_bindings)}"
        if missing_bindings else f"dynamic LogicType operands have duplicate bindings: {sorted(duplicate_bindings)}"
        if duplicate_bindings else "dynamic LogicType operands are concretely bound",
    )]
    for suffix, requested, supplied, key in checks:
        missing = {key(value) for value in requested} - {key(value) for value in supplied}
        obligations.append(static_obligation(
            obligation_id(name, suffix),
            "FAIL" if missing else "PASS",
            f"declared target lacks {sorted(missing, key=str)}"
            if missing else f"declared target supports required {suffix}",
        ))
    return ValidationBatch(tuple(obligations)), resolved


def validate_stack_coverage(name: str, stack: dict[str, Any], provider: dict[str, Any]) -> ValidationBatch:
    obligations = []
    for direction in ("read", "write"):
        requested = _requested_cells(stack, direction)
        missing = requested - _provider_cells(provider, direction)
        obligations.append(static_obligation(
            obligation_id(name, f"stack-{direction}"),
            "FAIL" if missing else "PASS",
            f"provider lacks {direction} access at {_missing_ranges(missing)}"
            if missing else f"provider covers {len(requested)} requested {direction} cell(s)",
        ))
    return ValidationBatch(tuple(obligations))


def validate_runtime_constraints(
    name: str,
    constraints: list[dict[str, Any]],
    provider: dict[str, Any],
    fence_rules: list[dict[str, Any]],
) -> ValidationBatch:
    constants = _field_constants(provider)
    constraints_by_address: dict[int, list[Any]] = {}
    for constraint in constraints:
        constraints_by_address.setdefault(constraint["address"], []).append(constraint["equals"])
    obligations = []
    for address, unsorted_values in sorted(constraints_by_address.items()):
        expected_values = sorted(set(unsorted_values), key=lambda value: (type(value).__name__, str(value)))
        for expected in expected_values:
            identifier = obligation_id(name, "constraint", f"s{address}")
            if len(expected_values) > 1:
                identity = json.dumps(
                    {"type": type(expected).__name__, "value": expected},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                identifier += f".value.{hashlib.sha256(identity).hexdigest()[:8]}"
            if address in constants:
                actual = constants[address]
                obligations.append(static_obligation(
                    identifier,
                    "PASS" if actual == expected else "FAIL",
                    f"provider source fixes S{address} to required value {expected!r}"
                    if actual == expected else f"provider constant is {actual!r}; expected {expected!r}",
                ))
                continue
            tool = "snapshot-probe" if fence_rules else "stack-cell-monitor"
            observation = _observation(
                identifier,
                name,
                tool,
                "Capture the contract-derived cell with its publication fence and compare it with the accepted value."
                if fence_rules else "Read the contract-derived cell and compare it with the accepted value.",
                cells=[{"address": address, "expected": expected}],
                fences=fence_rules,
                fencing=_fencing(fence_rules),
            )
            obligations.append(runtime_obligation(
                identifier, f"observe S{address} == {expected!r}", observation
            ))
    return ValidationBatch(tuple(obligations))


@dataclass(frozen=True)
class ScriptTargetValidation:
    batch: ValidationBatch
    compatible: bool
    fence_rules: tuple[dict[str, Any], ...] = ()
    header_cells: tuple[dict[str, Any], ...] = ()
    identity_tool: str = ""
    identity_summary: str = ""
    identity_fencing: str = "none"


@dataclass(frozen=True)
class ProtocolCompatibility:
    batch: ValidationBatch
    header: dict[str, Any] | None = None
    accepted_header: dict[str, Any] | None = None


@dataclass(frozen=True)
class PublicationValidation:
    batch: ValidationBatch
    fence_rules: tuple[dict[str, Any], ...] = ()


def validate_protocol_compatibility(
    name: str,
    target: dict[str, Any],
    provider_protocols: list[dict[str, Any]],
    accepted_protocols: list[dict[str, Any]],
) -> ProtocolCompatibility:
    """Match a provider header against the consumer's exact accepted headers."""
    provided = {item["protocol_id"] for item in provider_protocols}
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
        return ProtocolCompatibility(ValidationBatch((static_obligation(
            obligation_id(name, "protocol"),
            "FAIL",
            f"provider offers {sorted(provided) or ['no protocol']} without a matching header base; expected one of {sorted(accepted)}",
        ),)))
    header, accepted_header = compatible_headers[0]
    return ProtocolCompatibility(
        ValidationBatch((static_obligation(
            obligation_id(name, "protocol"),
            "PASS",
            f"provider declares {header['protocol_id']} at S{header['base']}",
        ),)),
        header,
        accepted_header,
    )


def validate_publication_fences(
    name: str, accepted_header: dict[str, Any], provider: dict[str, Any]
) -> PublicationValidation:
    """Check the publication rules required by one compatible protocol header."""
    required_rules = {
        (item["kind"], item["address"]): item
        for item in accepted_header.get("publication_requirements", [])
    }
    provider_rules = {
        (item["kind"], item["address"]): item
        for item in provider["behavior"].get("publication_rules", [])
    }
    missing_rules = sorted(set(required_rules) - set(provider_rules))
    batch = ValidationBatch((static_obligation(
        obligation_id(name, "publication"),
        "FAIL" if missing_rules else "PASS",
        f"provider lacks publication rules {missing_rules}"
        if missing_rules else f"provider satisfies {len(required_rules)} required publication fence(s)",
    ),))
    fences = tuple(provider_rules[key] for key in required_rules if key in provider_rules)
    return PublicationValidation(batch, fences)


def _validate_stack_protocol_target(
    name: str,
    target: dict[str, Any],
    provider: dict[str, Any],
    accepted_protocols: list[dict[str, Any]],
) -> ScriptTargetValidation:
    provider_protocols = provider["contracts"]["provides"]
    compatibility = validate_protocol_compatibility(
        name, target, provider_protocols, accepted_protocols
    )
    if compatibility.header is None or compatibility.accepted_header is None:
        return ScriptTargetValidation(
            compatibility.batch,
            True,
            identity_tool="snapshot-probe",
            identity_summary="Capture the declared provider header and any listed housing capabilities on the mapped screw; PASS only when every expectation matches.",
            identity_fencing="none; literal protocol header",
        )
    header = compatibility.header
    publication = validate_publication_fences(name, compatibility.accepted_header, provider)
    cells = (
        {"address": header["base"], "expected": header["magic"]},
        {"address": header["base"] + 1, "expected": header["abi"]},
    )
    return ScriptTargetValidation(
        ValidationBatch(compatibility.batch.obligations + publication.batch.obligations),
        True,
        publication.fence_rules,
        cells,
        "snapshot-probe",
        "Capture the declared provider header and any listed housing capabilities on the mapped screw; PASS only when every expectation matches.",
        "none; literal protocol header",
    )


def _validate_stack_interface_target(
    name: str,
    target: dict[str, Any],
    provider: dict[str, Any],
    _accepted_protocols: list[dict[str, Any]],
) -> ScriptTargetValidation:
    return ScriptTargetValidation(
        ValidationBatch((static_obligation(
            obligation_id(name, "interface"),
            "PASS",
            f"provider is statically checked against {target['interface_id']}",
        ),)),
        True,
        tuple(provider["behavior"].get("publication_rules", [])),
        identity_tool="manual-wiring-check",
        identity_summary="Access-only interfaces have no identifying header; confirm the screw-to-housing wire, recorded ReferenceId, and listed capabilities.",
        identity_fencing="not available until framework self-identification is standardized",
    )


def _reject_physical_device_script(
    name: str,
    _target: dict[str, Any],
    _provider: dict[str, Any],
    _accepted_protocols: list[dict[str, Any]],
) -> ScriptTargetValidation:
    return ScriptTargetValidation(
        ValidationBatch((static_obligation(
            obligation_id(name, "target-kind"), "FAIL", "physical-device port cannot map to a script"
        ),)),
        False,
    )


SCRIPT_TARGET_VALIDATORS: dict[
    str,
    Callable[[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]], ScriptTargetValidation],
] = {
    "stack-protocol": _validate_stack_protocol_target,
    "stack-interface": _validate_stack_interface_target,
    "physical-device": _reject_physical_device_script,
}


@dataclass(frozen=True)
class DeviceTargetValidation:
    batch: ValidationBatch = ValidationBatch()
    compatible: bool = True


def _validate_physical_device_target(
    _name: str, _target: dict[str, Any]
) -> DeviceTargetValidation:
    return DeviceTargetValidation()


def _reject_stack_target_device(
    name: str, _target: dict[str, Any]
) -> DeviceTargetValidation:
    return DeviceTargetValidation(
        ValidationBatch((static_obligation(
            obligation_id(name, "target-kind"),
            "FAIL",
            "stack port cannot map to a physical device",
        ),)),
        False,
    )


DEVICE_TARGET_VALIDATORS: dict[
    str, Callable[[str, dict[str, Any]], DeviceTargetValidation]
] = {
    "physical-device": _validate_physical_device_target,
    "stack-protocol": _reject_stack_target_device,
    "stack-interface": _reject_stack_target_device,
}


def validate_script_port(
    port: dict[str, Any],
    mapping: dict[str, Any],
    provider: dict[str, Any],
    accepted_protocols: list[dict[str, Any]],
) -> ValidationBatch:
    name = port["port"]
    target = port["target"]
    strategy = SCRIPT_TARGET_VALIDATORS.get(target["kind"])
    if strategy is None:
        return ValidationBatch((static_obligation(
            obligation_id(name, "target-kind"), "FAIL", f"unsupported script target kind {target['kind']!r}"
        ),))
    target_validation = strategy(name, target, provider, accepted_protocols)
    if not target_validation.compatible:
        return target_validation.batch

    capability_batch, capabilities = validate_capabilities(name, port["device_properties"], mapping)
    stack_batch = validate_stack_coverage(name, port["stack"], provider)
    constraint_batch = validate_runtime_constraints(
        name, port["stack"]["constraints"], provider, list(target_validation.fence_rules)
    )
    identity = obligation_id(name, "provider-observed")
    capability_note = " and exercise its declared LogicType/slot capabilities" if any(capabilities.values()) else ""
    identity_observation = _observation(
        identity,
        name,
        target_validation.identity_tool,
        target_validation.identity_summary,
        cells=list(target_validation.header_cells),
        capabilities=capabilities,
        fencing=target_validation.identity_fencing,
    )
    identity_obligation = runtime_obligation(
        identity,
        f"confirm screw {name} ({mapping['reference']}) is the declared provider in game{capability_note}",
        identity_observation,
    )
    obligations = (
        target_validation.batch.obligations
        + capability_batch.obligations
        + stack_batch.obligations
        + constraint_batch.obligations
        + (identity_obligation,)
    )
    observation_order = (identity,) + tuple(
        item.identifier for item in constraint_batch.obligations if item.observation is not None
    )
    return ValidationBatch(obligations, observation_order)


def validate_device_port(port: dict[str, Any], mapping: dict[str, Any]) -> ValidationBatch:
    name = port["port"]
    target = port["target"]
    strategy = DEVICE_TARGET_VALIDATORS.get(target["kind"])
    if strategy is None:
        return ValidationBatch((static_obligation(
            obligation_id(name, "target-kind"),
            "FAIL",
            f"unsupported physical-device target kind {target['kind']!r}",
        ),))
    target_validation = strategy(name, target)
    if not target_validation.compatible:
        return target_validation.batch
    capability_batch, capabilities = validate_capabilities(name, port["device_properties"], mapping)
    identity = obligation_id(name, "device-observed")
    observation = _observation(
        identity,
        name,
        "manual-device-check",
        "Exercise the listed LogicType and slot assumptions on the connected device; do not treat the declaration as proof.",
        capabilities=capabilities,
    )
    observed = runtime_obligation(
        identity,
        f"confirm {mapping['reference']} is a {mapping['device_type']} with the declared capabilities",
        observation,
    )
    return ValidationBatch(capability_batch.obligations + (observed,))


def validate_missing_mapping(name: str, port: dict[str, Any]) -> ValidationBatch:
    status = "FAIL" if port["requirement"] == "required" else "PASS"
    return ValidationBatch((static_obligation(
        obligation_id(name, "mapping"), status, f"{port['requirement']} port is not mapped"
    ),))


def validate_unknown_mappings(
    wiring_ports: dict[str, Any], contract_ports: dict[str, dict[str, Any]]
) -> ValidationBatch:
    return ValidationBatch(tuple(
        static_obligation(
            obligation_id(name, "mapping"), "FAIL", "consumer contract does not use this port"
        )
        for name in sorted(set(wiring_ports) - set(contract_ports))
    ))


def validate_dynamic_bindings(
    contract_ports: dict[str, dict[str, Any]], wiring_ports: dict[str, Any]
) -> ValidationBatch:
    dynamic_bindings: dict[tuple[str, int, str], dict[str, Any]] = {}
    for target_port, port in contract_ports.items():
        mapping = wiring_ports.get(target_port)
        if mapping is None:
            continue
        bindings, duplicates = property_bindings(mapping)
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
    obligations = []
    for (source_port, address), keys in sorted(source_cells.items()):
        if len(keys) == 1:
            continue
        properties = {
            property_name for key in keys for property_name in dynamic_bindings[key]["properties"]
        }
        fences = {fence for key in keys for fence in dynamic_bindings[key]["fences"]}
        if len(properties) <= 1 and len(fences) <= 1:
            continue
        conflicted_bindings.update(keys)
        details = []
        if len(properties) > 1:
            details.append(f"conflicting properties {sorted(properties)}")
        if len(fences) > 1:
            details.append("conflicting fence declarations")
        obligations.append(static_obligation(
            obligation_id("binding", source_port, f"s{address}"),
            "FAIL",
            f"one runtime source cell has {' and '.join(details)}",
        ))

    for (source_port, address, operand), entry in sorted(dynamic_bindings.items()):
        if (source_port, address, operand) in conflicted_bindings:
            continue
        identifier = obligation_id("binding", source_port, f"s{address}", operand)
        properties = entry["properties"]
        targets = sorted(entry["target_ports"])
        if len(entry["fences"]) != 1:
            obligations.append(static_obligation(
                identifier, "FAIL", f"targets {targets} declare conflicting fences for one runtime operand"
            ))
            continue
        if len(properties) != 1:
            obligations.append(static_obligation(
                identifier,
                "FAIL",
                f"targets {targets} bind one runtime operand to conflicting properties {sorted(properties)}",
            ))
            continue
        property_name = next(iter(properties))
        source = entry["source"]
        fence = source.get("fence")
        observation = _observation(
            identifier,
            source_port,
            "snapshot-probe" if fence else "stack-cell-monitor",
            f"Capture the configured LogicType that populates {operand} for {targets}; PASS only when it is {property_name}.",
            cells=[{"address": address, "expected": property_name}],
            fences=[fence] if fence else None,
            fencing=_fencing([fence] if fence else []),
        )
        obligations.append(runtime_obligation(
            identifier,
            f"observe {source_port} S{address} == LogicType {property_name!r} for {operand} used by {targets}",
            observation,
        ))
    return ValidationBatch(tuple(obligations))


def build_binding(
    wiring: dict[str, Any],
    consumer: dict[str, Any],
    provider_identities: dict[str, dict[str, str]],
    contract_ports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
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
            for name, port in contract_ports.items()
            if name in wiring["ports"]
        },
    }
    binding["plan_id"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    return binding
