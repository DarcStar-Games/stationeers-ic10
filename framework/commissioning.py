"""Validate player-supplied wiring against generated IC10 script contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
import json

from framework.commissioning_validators import (
    ResultCollector,
    ValidationBatch,
    build_binding,
    contract_identity,
    static_obligation,
    validate_device_port,
    validate_dynamic_bindings,
    validate_missing_mapping,
    validate_script_port,
    validate_unknown_mappings,
)
from framework.json_schema import validate


FORMAT = "IC10_COMMISSIONING_WIRING_V1"
EVIDENCE_STATUSES = {"PASS", "FAIL", "BLOCKED"}


def load_wiring(path: Path, root: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    schema = json.loads((Path(root) / "schemas/commissioning_wiring.schema.json").read_text())
    validate(value, schema)
    return value


def load_contracts(root: Path) -> list[dict[str, Any]]:
    index = json.loads((Path(root) / "contracts/index.json").read_text())
    return [json.loads((Path(root) / item["contract"]).read_text()) for item in index["contracts"]]


def resolve_contract(selector: str, contracts: list[dict[str, Any]]) -> dict[str, Any]:
    matches = [
        contract
        for contract in contracts
        if selector
        in {
            contract["source"],
            contract["identity"]["service_id"],
            contract["source"].replace("ic10/", "contracts/").replace(".ic10", ".contract.json"),
        }
    ]
    if len(matches) != 1:
        detail = "not found" if not matches else "ambiguous"
        raise ValueError(f"contract selector {selector!r} is {detail}")
    return matches[0]


@dataclass(frozen=True)
class MappingValidation:
    batch: ValidationBatch
    provider_identity: dict[str, str] | None = None


MappingStrategy = Callable[
    ["PlanBuildingContext", str, dict[str, Any], dict[str, Any]], MappingValidation
]


def _validate_script_mapping(
    context: "PlanBuildingContext",
    name: str,
    port: dict[str, Any],
    mapping: dict[str, Any],
) -> MappingValidation:
    try:
        provider = resolve_contract(mapping["provider"], context.contracts)
    except ValueError as error:
        return MappingValidation(ValidationBatch((
            static_obligation(f"{name}.provider", "FAIL", str(error)),
        )))
    return MappingValidation(
        validate_script_port(port, mapping, provider, context.consumed_protocols.get(name, [])),
        contract_identity(provider),
    )


def _validate_device_mapping(
    _context: "PlanBuildingContext",
    _name: str,
    port: dict[str, Any],
    mapping: dict[str, Any],
) -> MappingValidation:
    return MappingValidation(validate_device_port(port, mapping))


MAPPING_STRATEGIES: dict[str, MappingStrategy] = {
    "script": _validate_script_mapping,
    "physical-device": _validate_device_mapping,
}


@dataclass
class PlanBuildingContext:
    """Mutable orchestration state; validation rules remain pure and independently testable."""

    wiring: dict[str, Any]
    contracts: list[dict[str, Any]]
    consumer: dict[str, Any]
    contract_ports: dict[str, dict[str, Any]]
    consumed_protocols: dict[str, list[dict[str, Any]]]
    collector: ResultCollector = field(default_factory=ResultCollector)
    provider_identities: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def create(cls, wiring: dict[str, Any], root: Path) -> "PlanBuildingContext":
        contracts = load_contracts(root)
        consumer = resolve_contract(wiring["consumer"], contracts)
        return cls(
            wiring=wiring,
            contracts=contracts,
            consumer=consumer,
            contract_ports={port["port"]: port for port in consumer["device_ports"]},
            consumed_protocols={
                item["port"]: item["accepted"] for item in consumer["contracts"]["consumes"]
            },
        )

    def validate_ports(self) -> None:
        for name, port in self.contract_ports.items():
            mapping = self.wiring["ports"].get(name)
            if mapping is None:
                self.collector.add(validate_missing_mapping(name, port))
                continue
            strategy = MAPPING_STRATEGIES.get(mapping["kind"])
            if strategy is None:
                self.collector.add(ValidationBatch((static_obligation(
                    f"{name}.mapping-kind",
                    "FAIL",
                    f"unsupported mapping kind {mapping['kind']!r}",
                ),)))
                continue
            validation = strategy(self, name, port, mapping)
            self.collector.add(validation.batch)
            if validation.provider_identity is not None:
                self.provider_identities[name] = validation.provider_identity

        self.collector.add(validate_unknown_mappings(self.wiring["ports"], self.contract_ports))
        self.collector.add(validate_dynamic_bindings(self.contract_ports, self.wiring["ports"]))

    def plan(self) -> dict[str, Any]:
        binding = build_binding(
            self.wiring, self.consumer, self.provider_identities, self.contract_ports
        )
        return {
            "format": "IC10_COMMISSIONING_PLAN_V1",
            "label": self.wiring.get("label", ""),
            "binding": binding,
            "results": self.collector.results,
            "observations": self.collector.observations,
        }


def build_plan(wiring: dict[str, Any], root: Path) -> dict[str, Any]:
    context = PlanBuildingContext.create(wiring, root)
    context.validate_ports()
    return context.plan()


def _result(obligation_id: str, status: str, message: str, category: str = "static") -> dict[str, str]:
    return {"id": obligation_id, "status": status, "category": category, "message": message}


def apply_evidence(plan: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    entry = session.get("wiring_results", {}).get(plan["binding"]["plan_id"], {})
    runs = entry.get("runs", {})
    output = {**plan, "results": [dict(item) for item in plan["results"]]}
    if entry and entry.get("binding") != plan["binding"]:
        output["results"].append(_result(
            "evidence-binding",
            "FAIL",
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
