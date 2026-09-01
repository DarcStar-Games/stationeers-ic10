"""Assemble contracts and the cross-program registries from the analysis phases.

`build_contract` runs every phase over one source file; `build_all` loads the
authoritative declarations, builds every contract, and derives the protocol
registry, protocol definitions, structural interfaces, and index from them.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import json
from typing import Any

from framework.script_contracts.device_ports import (
    access_provider_obligations,
    analyze_device_ports,
    network_dependencies,
    port_target,
    verify_declared_consumers,
)
from framework.script_contracts.naming import protocol_id, protocol_name, revision, service_id
from framework.script_contracts.own_stack import (
    analyze_own_stack,
    header_invariants,
    restart_behavior,
    verify_declared_headers,
)
from framework.script_contracts.parsing import collect_aliases, parse_rows
from framework.script_contracts.value_bounds import declared_coverage_errors
from framework.protocol_headers import load_headers
from framework.source_metadata import deployable_scripts, load_manifest, resolve_script_metadata

FORMAT = "IC10_SCRIPT_CONTRACT_V2"
INDEX_FORMAT = "IC10_SCRIPT_CONTRACT_INDEX_V1"
PROTOCOL_FORMAT = "IC10_STACK_PROTOCOL_REGISTRY_V1"
PROTOCOL_DEFINITION_FORMAT = "IC10_PROTOCOL_DEFINITION_V1"
SUPPLEMENTAL_REFS = {
    "input-profile-catalog": "data/input_profiles.json#",
    "resource-profile-catalog": "data/resource_profiles.json#",
    "transform-catalog": "data/resource_transforms.json#",
}


def generated_artifact_paths(root: Path, pattern: str) -> set[Path]:
    return set((Path(root) / "contracts").rglob(pattern))


def verify_override_source(path: Path, override: dict[str, Any]) -> None:
    actual_sha256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if override.get("source_sha256") != actual_sha256:
        raise ValueError(
            f"contract override source fingerprint mismatch for {path}; "
            "re-review dynamic ranges and semantic exceptions before updating source_sha256"
        )


def build_contract(path: Path, root: Path, manifest: dict[str, Any], declared_headers: list[dict[str, int]], declared_consumers: list[dict[str, Any]], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    rows = parse_rows(source)
    port_aliases, integer_aliases = collect_aliases(rows)
    metadata = resolve_script_metadata(path, manifest, root)
    rel = path.relative_to(root).as_posix()
    service = service_id(path)
    overrides = overrides or {}
    headers = verify_declared_headers(rows, integer_aliases, declared_headers)
    consumes = verify_declared_consumers(source, rows, port_aliases, integer_aliases, declared_consumers)
    ports = analyze_device_ports(source, rows, port_aliases, integer_aliases, overrides)
    for port in ports:
        port["target"] = port_target(port, consumes)
    own_stack, publication_rules = analyze_own_stack(source, rows, integer_aliases, headers, overrides)
    declared_ranges = {
        (port["port"], direction): port["stack"][f"dynamic_{direction}_ranges"]
        for port in ports for direction in ("read", "write")
    } | {
        ("db", direction): own_stack[f"dynamic_{direction}_ranges"] for direction in ("read", "write")
    }
    coverage_errors = declared_coverage_errors(source, port_aliases, integer_aliases, declared_ranges)
    if coverage_errors:
        raise ValueError(f"{rel}: " + "; ".join(coverage_errors))
    provides = [{
        "protocol_id": protocol_id(header["magic"], header["abi"], header.get("contract")),
        **header,
        "source": "literal-own-stack-header",
    } for header in headers]
    invariants = header_invariants(headers, own_stack) + overrides.get("invariants", [])
    return {
        "$schema": "../../schemas/script_contract_v2.schema.json",
        "format": FORMAT,
        "source": rel,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "identity": {
            "service_id": service,
            "implementation_revision": revision(path),
            "deployment_family": metadata["deployment_family"],
            "deployment_class": metadata["deployment_class"],
            "layer": metadata["layer"],
            "purpose": metadata["purpose"],
        },
        "device_ports": ports,
        "network_dependencies": network_dependencies(source, rows, integer_aliases, overrides),
        "own_stack": {**own_stack, "headers": headers},
        "behavior": {
            "publication_rules": publication_rules,
            "restart": restart_behavior(rows, own_stack["clears_all"]),
            "invariants": invariants,
        },
        "contracts": {"provides": provides, "consumes": consumes},
        "extraction": {
            "mode": "static-v2",
            "limitations": [
                "Unproved dynamic own-stack addresses fail closed to the full 512-cell stack.",
                "An address the branches around it bound whole is source-derived; other reviewed bounds are source-fingerprinted overrides.",
                "Provided and consumed protocols require authoritative declarations verified against source literals.",
                "Field semantics not represented by source comments or literals remain in supplemental canonical data.",
            ],
        },
    }


def _load_declarations(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load the authoritative override, protocol-definition, and header declarations."""
    override_path = root / "data" / "script_contract_overrides.json"
    override_data = json.loads(override_path.read_text()) if override_path.exists() else {"scripts": {}}
    if override_data.get("format") != "IC10_SCRIPT_CONTRACT_OVERRIDES_V1":
        raise ValueError("unsupported script contract override format")
    definitions_data = json.loads((root / "data" / "script_contract_protocol_definitions.json").read_text())
    if definitions_data.get("format") != "IC10_PROTOCOL_DEFINITIONS_V1":
        raise ValueError("unsupported script contract protocol definition format")
    declared_headers, declared_consumers = load_headers(root)
    return (override_data.get("scripts", {}), definitions_data.get("protocols", {}),
            declared_headers, declared_consumers)


def _build_contracts(
    root: Path, script_overrides: dict[str, Any],
    declared_headers: dict[str, Any], declared_consumers: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Build every deployable contract, enforcing declaration coverage first."""
    manifest = load_manifest(root)
    source_paths = {source.relative_to(root).as_posix() for source in deployable_scripts(root)}
    if set(declared_headers) != source_paths:
        raise ValueError(f"protocol header coverage mismatch: missing={sorted(source_paths-set(declared_headers))}, stale={sorted(set(declared_headers)-source_paths)}")
    if set(declared_consumers) != source_paths:
        raise ValueError(f"protocol consumer coverage mismatch: missing={sorted(source_paths-set(declared_consumers))}, stale={sorted(set(declared_consumers)-source_paths)}")
    contracts: dict[str, dict[str, Any]] = {}
    for source in deployable_scripts(root):
        source_rel = source.relative_to(root).as_posix()
        override = script_overrides.get(source_rel)
        if override:
            verify_override_source(source, override)
        contract = build_contract(source, root, manifest, declared_headers[source_rel], declared_consumers[source_rel], override)
        family = contract["identity"]["deployment_family"]
        rel = f"contracts/{family}/{source.stem}.contract.json"
        if rel in contracts:
            raise ValueError(f"duplicate contract path: {rel}")
        contracts[rel] = contract
    stale_overrides = sorted(set(script_overrides) - {contract["source"] for contract in contracts.values()})
    if stale_overrides:
        raise ValueError(f"contract overrides reference missing scripts: {stale_overrides}")
    return contracts


def _protocol_registry(
    contracts: dict[str, dict[str, Any]], definitions: dict[str, Any],
    by_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Derive the protocol registry from every contract's provides/consumes edges."""
    providers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    consumers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    headers: dict[str, tuple[int, int, str | None]] = {}
    for contract in contracts.values():
        for provided in contract["contracts"]["provides"]:
            pid = provided["protocol_id"]
            headers[pid] = (provided["magic"], provided["abi"], provided.get("contract"))
            providers[pid].append({"source": contract["source"], "header_base": provided["base"]})
        for requirement in contract["contracts"]["consumes"]:
            for accepted in requirement["accepted"]:
                pid = accepted["protocol_id"]
                headers[pid] = (accepted["magic"], accepted["abi"], accepted.get("contract"))
                consumers[pid].append({"source": contract["source"], "endpoint": {"kind": "device-port", "value": requirement["port"]}, "header_base": accepted["header_base"]})
        for dependency in contract["network_dependencies"]:
            for accepted in dependency["accepted"]:
                pid = accepted["protocol_id"]
                headers[pid] = (accepted["magic"], accepted["abi"], accepted.get("contract"))
                consumers[pid].append({"source": contract["source"], "endpoint": {"kind": "network-reference", "value": dependency["reference"]}, "header_base": accepted["header_base"]})
    unknown_definitions = sorted(set(definitions) - set(headers))
    if unknown_definitions:
        raise ValueError(f"protocol definitions have no provider or consumer: {unknown_definitions}")
    protocol_registry = {
        "format": PROTOCOL_FORMAT,
        "protocols": [{
            "protocol_id": pid,
            "transport": "ic-housing-stack",
            **({"contract": headers[pid][2]} if headers[pid][2] else {}),
            "magic": headers[pid][0],
            "abi": headers[pid][1],
            "name": protocol_name(pid, headers[pid][1], sorted(item["source"] for item in providers[pid]), definitions, headers[pid][2]),
            "definition_ref": f"contracts/protocols/{pid}.protocol.json",
            "canonical_refs": sorted(set(definitions.get(pid, {}).get("definition_refs", [])) | {
                SUPPLEMENTAL_REFS[by_source[item["source"]]["identity"]["deployment_family"]]
                for item in providers[pid]
                if by_source[item["source"]]["identity"]["deployment_family"] in SUPPLEMENTAL_REFS
            }),
            "providers": sorted(providers[pid], key=lambda item: (item["source"], item["header_base"])),
            "consumers": sorted(consumers[pid], key=lambda item: (item["source"], item["endpoint"]["kind"], item["endpoint"]["value"], item["header_base"])),
        } for pid in sorted(headers)],
    }
    return protocol_registry


def _protocol_definitions(protocol_registry: dict[str, Any], by_source: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Expand each registered protocol into its canonical definition document."""
    protocol_definitions: dict[str, dict[str, Any]] = {}
    for protocol in protocol_registry["protocols"]:
        provider_interfaces = []
        for provider in protocol["providers"]:
            contract = by_source[provider["source"]]
            own = contract["own_stack"]
            provider_interfaces.append({
                **provider,
                "readable_ranges": own["external_readable_ranges"],
                "writable_ranges": own["external_writable_ranges"],
                "fields": own["fields"],
                "behavior": contract["behavior"],
            })
        consumer_interfaces = []
        for consumer in protocol["consumers"]:
            contract = by_source[consumer["source"]]
            endpoint = consumer["endpoint"]
            if endpoint["kind"] == "device-port":
                access = next(item["stack"] for item in contract["device_ports"] if item["port"] == endpoint["value"])
                interface = {
                    "literal_reads": access["literal_reads"],
                    "literal_writes": access["literal_writes"],
                    "dynamic_read_ranges": access["dynamic_read_ranges"],
                    "dynamic_write_ranges": access["dynamic_write_ranges"],
                    "dynamic_read_range_source": access["dynamic_read_range_source"],
                    "dynamic_write_range_source": access["dynamic_write_range_source"],
                    "constraints": [{"address": item["address"], "operator": "equals", "value": item["equals"]} for item in access["constraints"]],
                    "publication_requirements": next(
                        accepted["publication_requirements"]
                        for requirement in contract["contracts"]["consumes"]
                        if requirement["port"] == endpoint["value"]
                        for accepted in requirement["accepted"]
                        if accepted["protocol_id"] == protocol["protocol_id"] and accepted["header_base"] == consumer["header_base"]
                    ),
                }
            else:
                access = next(item for item in contract["network_dependencies"] if item["reference"] == endpoint["value"])
                interface = {
                    "literal_reads": access["literal_reads"],
                    "literal_writes": access["literal_writes"],
                    "dynamic_read_ranges": [],
                    "dynamic_write_ranges": [],
                    "dynamic_read_range_source": "none",
                    "dynamic_write_range_source": "none",
                    "constraints": access["constraints"],
                    "publication_requirements": [],
                }
            consumer_interfaces.append({**consumer, **interface})
        rel = protocol["definition_ref"]
        protocol_definitions[rel] = {
            "$schema": "../../schemas/protocol_definition.schema.json",
            "format": PROTOCOL_DEFINITION_FORMAT,
            "protocol_id": protocol["protocol_id"],
            "name": protocol["name"],
            "transport": protocol["transport"],
            **({"contract": protocol["contract"]} if "contract" in protocol else {}),
            "magic": protocol["magic"],
            "abi": protocol["abi"],
            "header_bases": sorted({item["header_base"] for item in protocol["providers"] + protocol["consumers"]}),
            "canonical_refs": protocol["canonical_refs"],
            "provider_interfaces": provider_interfaces,
            "consumer_interfaces": consumer_interfaces,
        }
    return protocol_definitions


def _interface_definitions(contracts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Collect the structural access-only interfaces every stack-interface port names."""
    interface_definitions: dict[str, dict[str, Any]] = {}
    for contract in contracts.values():
        for port in contract["device_ports"]:
            target = port["target"]
            if target["kind"] != "stack-interface":
                continue
            interface_id = target["interface_id"]
            definition = interface_definitions.setdefault(interface_id, {
                "stack": port["stack"],
                "assumptions": target["assumptions"],
                "provider_obligations": access_provider_obligations(port["stack"], target["assumptions"]),
                "consumers": [],
            })
            if definition["stack"] != port["stack"] or definition["assumptions"] != target["assumptions"]:
                raise ValueError(f"structural interface hash collision: {interface_id}")
            definition["consumers"].append({"source": contract["source"], "port": port["port"]})
    for definition in interface_definitions.values():
        definition["consumers"].sort(key=lambda item: (item["source"], item["port"]))
    return interface_definitions


def _contract_index(contracts: dict[str, dict[str, Any]], interface_definitions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize contracts, interfaces, and the dynamic own-stack surface in one index."""
    own_stack_range_inventory = []
    for contract in sorted(contracts.values(), key=lambda item: item["source"]):
        own = contract["own_stack"]
        if not own["dynamic_read"] and not own["dynamic_write"]:
            continue
        own_stack_range_inventory.append({
            "source": contract["source"],
            "read": {
                "dynamic": own["dynamic_read"],
                "ranges": own["dynamic_read_ranges"],
                "proven_ranges": own["dynamic_read_proven_ranges"],
                "provenance": own["dynamic_read_range_source"],
            },
            "write": {
                "dynamic": own["dynamic_write"],
                "ranges": own["dynamic_write_ranges"],
                "proven_ranges": own["dynamic_write_proven_ranges"],
                "provenance": own["dynamic_write_range_source"],
            },
        })
    index = {
        "format": INDEX_FORMAT,
        "contract_count": len(contracts),
        "own_stack_range_inventory": {
            "dynamic_script_count": len(own_stack_range_inventory),
            "source_proven_surface_count": sum(
                bool(item[direction]["proven_ranges"])
                for item in own_stack_range_inventory for direction in ("read", "write")
            ),
            "unresolved_fallback_count": sum(
                item[direction]["provenance"] == "conservative-full-stack"
                for item in own_stack_range_inventory for direction in ("read", "write")
            ),
            "scripts": own_stack_range_inventory,
        },
        "interfaces": {key: interface_definitions[key] for key in sorted(interface_definitions)},
        "contracts": [{
            "source": contract["source"],
            "contract": rel,
            "service_id": contract["identity"]["service_id"],
            "provides": [item["protocol_id"] for item in contract["contracts"]["provides"]],
            "consumes": sorted(
                {accepted["protocol_id"] for item in contract["contracts"]["consumes"] for accepted in item["accepted"]}
                | {accepted["protocol_id"] for item in contract["network_dependencies"] for accepted in item["accepted"]}
            ),
        } for rel, contract in sorted(contracts.items())],
    }
    return index


def build_all(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    root = Path(root)
    script_overrides, definitions, declared_headers, declared_consumers = _load_declarations(root)
    contracts = _build_contracts(root, script_overrides, declared_headers, declared_consumers)
    by_source = {contract["source"]: contract for contract in contracts.values()}
    protocol_registry = _protocol_registry(contracts, definitions, by_source)
    protocol_definitions = _protocol_definitions(protocol_registry, by_source)
    interface_definitions = _interface_definitions(contracts)
    index = _contract_index(contracts, interface_definitions)
    return contracts, index, protocol_registry, protocol_definitions


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False, allow_nan=False) + "\n"
