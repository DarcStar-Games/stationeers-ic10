"""Cross-contract invariant and provider/consumer compatibility validation."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from framework.script_contracts.dynamic_ranges import expanded_ranges


def invariant_errors(contract: dict[str, Any]) -> list[str]:
    """Evaluate every machine-readable invariant declared by one contract."""
    constants = {
        field["address"]: field["const"] for field in contract["own_stack"]["fields"] if "const" in field
    }
    errors = []
    dynamic_writes = expanded_ranges(contract["own_stack"]["dynamic_write_ranges"])
    for invariant in contract["behavior"]["invariants"]:
        if invariant["kind"] == "cell-equals":
            if invariant["address"] in dynamic_writes:
                errors.append(
                    f"{contract['source']}: invariant {invariant['id']} is not proven across dynamic writes"
                )
                continue
            actual = constants.get(invariant["address"])
            if actual != invariant["equals"]:
                errors.append(
                    f"{contract['source']}: invariant {invariant['id']} expected S{invariant['address']}="
                    f"{invariant['equals']!r}, got {actual!r}"
                )
    return errors


def compatibility_errors(contracts: list[dict[str, Any]]) -> list[str]:
    """Return provider/consumer header, cell, and access-direction incompatibilities."""
    providers: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for contract in contracts:
        for provided in contract["contracts"]["provides"]:
            providers[(provided["protocol_id"], provided["base"])].append(contract)
    errors = []
    for consumer in contracts:
        ports = {item["port"]: item for item in consumer["device_ports"]}
        for requirement in consumer["contracts"]["consumes"]:
            port = ports.get(requirement["port"])
            if port is None:
                errors.append(f"{consumer['source']}: consumed protocol uses undeclared {requirement['port']}")
                continue
            for accepted in requirement["accepted"]:
                key = (accepted["protocol_id"], accepted["header_base"])
                candidates = providers.get(key, [])
                if not candidates:
                    errors.append(f"{consumer['source']} {requirement['port']}: no provider for {key[0]} at S{key[1]}")
                    continue
                failures = []
                for provider in candidates:
                    own = provider["own_stack"]
                    readable = set(own["literal_writes"]) | expanded_ranges(own["external_readable_ranges"])
                    writable = set(own["literal_reads"]) | expanded_ranges(own["external_writable_ranges"])
                    for field in own["fields"]:
                        if "external-read" in field["access"]:
                            readable.add(field["address"])
                        if "external-write" in field["access"]:
                            writable.add(field["address"])
                    requested_reads = set(port["stack"]["literal_reads"]) | expanded_ranges(port["stack"]["dynamic_read_ranges"])
                    requested_writes = set(port["stack"]["literal_writes"]) | expanded_ranges(port["stack"]["dynamic_write_ranges"])
                    missing_reads = requested_reads - readable
                    missing_writes = requested_writes - writable
                    constants = {field["address"]: field["const"] for field in own["fields"] if "const" in field}
                    wrong_values = [
                        (constraint["address"], constraint["equals"], constants[constraint["address"]])
                        for constraint in port["stack"]["constraints"]
                        if constraint["address"] in constants and constants[constraint["address"]] != constraint["equals"]
                    ]
                    provider_rules = {(item["kind"], item["address"]) for item in provider["behavior"]["publication_rules"]}
                    missing_publication = [
                        item for item in accepted.get("publication_requirements", [])
                        if (item["kind"], item["address"]) not in provider_rules
                    ]
                    unresolved = []
                    if port["stack"]["dynamic_read"] and not port["stack"]["dynamic_read_ranges"]:
                        unresolved.append("consumer dynamic read has no declared range")
                    if port["stack"]["dynamic_write"] and not port["stack"]["dynamic_write_ranges"]:
                        unresolved.append("consumer dynamic write has no declared range")
                    if not missing_reads and not missing_writes and not wrong_values and not missing_publication and not unresolved:
                        break
                    failures.append((provider["source"], sorted(missing_reads), sorted(missing_writes), wrong_values, missing_publication, unresolved))
                else:
                    detail = "; ".join(f"{source}: unreadable={reads}, unwritable={writes}, unequal={values}, publication={publication}, unresolved={unresolved}" for source, reads, writes, values, publication, unresolved in failures)
                    errors.append(f"{consumer['source']} {requirement['port']}: {key[0]} at S{key[1]} has no value/direction-compatible provider ({detail})")
        for dependency in consumer["network_dependencies"]:
            for accepted in dependency["accepted"]:
                key = (accepted["protocol_id"], accepted["header_base"])
                candidates = providers.get(key, [])
                if not candidates:
                    errors.append(f"{consumer['source']} network {dependency['reference']}: no provider for {key[0]} at S{key[1]}")
                    continue
                requested_reads = set(dependency["literal_reads"])
                requested_writes = set(dependency["literal_writes"])
                if not any(
                    not (requested_reads - (set(provider["own_stack"]["literal_writes"]) | expanded_ranges(provider["own_stack"]["external_readable_ranges"])))
                    and not (requested_writes - (set(provider["own_stack"]["literal_reads"]) | expanded_ranges(provider["own_stack"]["external_writable_ranges"])))
                    for provider in candidates
                ):
                    errors.append(f"{consumer['source']} network {dependency['reference']}: {key[0]} at S{key[1]} has no access-compatible provider")
    return errors
