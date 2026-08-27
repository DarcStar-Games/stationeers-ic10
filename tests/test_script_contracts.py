#!/usr/bin/env python3
"""Focused failure tests for script contract schema and compatibility validation."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import json
import tempfile

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import (
    _aliases,
    _device_ports,
    _instructions,
    _network_dependencies,
    _own_stack,
    _ranges,
    _restart_behavior,
    _source_semantics,
    _verified_publication_overrides,
    _verified_seqlock_consumer,
    _verify_declared_consumers,
    _verify_declared_headers,
    access_interface_id,
    access_provider_obligations,
    build_all,
    compatibility_errors,
    generated_artifact_paths,
    invariant_errors,
    ranges_overlap,
    verify_override_source,
)
from framework.source_metadata import deployable_scripts

ROOT = _PROJECT_ROOT
fails = []


def ck(condition, message):
    if not condition:
        fails.append(message)


contracts, index, protocols, protocol_definitions = build_all(ROOT)
documents = list(contracts.values())
schema = json.loads((ROOT / "schemas/script_contract.schema.json").read_text())
try:
    for document in documents:
        validate(document, schema)
except SchemaValidationError as error:
    fails.append(f"valid generated document rejected: {error}")

bad_port = deepcopy(documents[0])
bad_port["device_ports"] = [{
    "port": "d6", "role": "bad", "aliases": [], "requirement": "required",
    "device_properties": {"reads": [], "writes": [], "slot_reads": [], "slot_writes": []},
    "stack": {"literal_reads": [], "literal_writes": [], "dynamic_read": False, "dynamic_write": False,
              "dynamic_read_ranges": [], "dynamic_write_ranges": [], "dynamic_read_range_source": "none",
              "dynamic_write_range_source": "none", "constraints": []},
    "target": {"kind": "physical-device", "verification": "device-properties",
               "assumptions": {"properties_read": [], "properties_written": [],
                               "slot_properties_read": [], "slot_properties_written": []}},
}]
try:
    validate(bad_port, schema)
    fails.append("schema accepted invalid d6 port")
except SchemaValidationError:
    pass

missing_provider = deepcopy(documents)
pi = next(item for item in missing_provider if item["source"].endswith("controller_pi_runtime_v1_1.ic10"))
pi["contracts"]["consumes"][0]["accepted"][0].update({
    "protocol_id": "ic10.stack.99999999.abi1", "magic": 99999999,
})
ck(any("no provider" in error for error in compatibility_errors(missing_provider)),
   "missing protocol provider was not rejected")

wrong_base = deepcopy(documents)
pi = next(item for item in wrong_base if item["source"].endswith("controller_pi_runtime_v1_1.ic10"))
pi["contracts"]["consumes"][0]["accepted"][0]["header_base"] = 32
ck(any("no provider" in error for error in compatibility_errors(wrong_base)),
   "wrong protocol header base was not rejected")

wrong_direction = deepcopy(documents)
host = next(item for item in wrong_direction if item["source"].endswith("generic_persistent_config_host_v1_1.ic10"))
host["own_stack"]["literal_writes"].remove(9)
host["own_stack"]["external_readable_ranges"] = []
field = next(item for item in host["own_stack"]["fields"] if item["address"] == 9)
field["access"] = [access for access in field["access"] if access != "external-read"]
ck(any("value/direction-compatible" in error for error in compatibility_errors(wrong_direction)),
   "provider access-direction mismatch was not rejected")

out_of_range = deepcopy(documents)
pi = next(item for item in out_of_range if item["source"].endswith("controller_pi_runtime_v1_1.ic10"))
config_port = next(item for item in pi["device_ports"] if item["port"] == "d2")
config_port["stack"]["dynamic_read_ranges"] = [{"start": 511, "end": 511}]
ck(any("unreadable=[511]" in error for error in compatibility_errors(out_of_range)),
   "dynamic provider access incorrectly authorized an out-of-range PI config read")

wrong_schema = deepcopy(documents)
for provider in wrong_schema:
    for field in provider["own_stack"]["fields"]:
        if field.get("const") == 'HASH("ControllerPressureTransfer")':
            field["const"] = 'HASH("ControllerPressureDomain")'
ck(any("unequal=" in error for error in compatibility_errors(wrong_schema)),
   "consumer schema/controller discriminator mismatch was not rejected")

ck(index["contract_count"] == len(documents) == len(deployable_scripts(ROOT)),
   "contract inventory does not cover production scripts")
ck(any(item["header_base"] == 96 for protocol in protocols["protocols"] for item in protocol["providers"]),
   "nonzero telemetry header bases were not inventoried")
ck(len(protocol_definitions) == len(protocols["protocols"]),
   "not every registered protocol has a canonical generated definition")
ck(all(field["value_type"] in {"number", "integer", "enum", "hash", "reference-id", "boolean"} for definition in protocol_definitions.values()
       for provider in definition["provider_interfaces"] for field in provider["fields"]),
   "canonical protocol fields lack machine-readable value types")
all_fields = [field for document in documents for field in document["own_stack"]["fields"]]
ck(sum("description" in field for field in all_fields) >= 100,
   "source-backed field descriptions are not broadly represented")
ck(sum(len(document["behavior"]["publication_rules"]) for document in documents) >= 20,
   "source-backed publication rules are not broadly represented")
ck(all("target" in port for document in documents for port in document["device_ports"]),
   "a device port lacks an explicit target contract or device assumption")
interfaces = [port["target"] for document in documents for port in document["device_ports"]
              if port["target"]["kind"] == "stack-interface"]
ck(all(item["definition_ref"] == f"contracts/index.json#/interfaces/{item['interface_id']}" for item in interfaces),
   "an access-only interface does not resolve to its canonical definition")
ck(all(
    port["target"]["interface_id"] == access_interface_id(port["stack"], port["target"]["assumptions"])
    for document in documents for port in document["device_ports"]
    if port["target"]["kind"] == "stack-interface"
), "an access-only interface identity is not derived from its structural contract")
ck(len({item["interface_id"] for item in interfaces}) < len(interfaces),
   "equivalent access-only interfaces do not share an identity")
ck(all(interface_id in index["interfaces"] for interface_id in {item["interface_id"] for item in interfaces}),
   "an access-only interface is missing from the canonical interface registry")
ck(all(
    port["target"]["provider_resolution"] == "deployment-supplied"
    and index["interfaces"][port["target"]["interface_id"]]["provider_obligations"]
        == access_provider_obligations(port["stack"], port["target"]["assumptions"])
    for document in documents for port in document["device_ports"]
    if port["target"]["kind"] == "stack-interface"
), "an access-only interface lacks explicit commissioning-time provider obligations")
constrained_access_port = next(
    port for document in documents for port in document["device_ports"]
    if port["target"]["kind"] == "stack-interface" and port["stack"]["constraints"]
)
ck(
    index["interfaces"][constrained_access_port["target"]["interface_id"]]["provider_obligations"]["constraints"]
    == constrained_access_port["stack"]["constraints"],
    "an access-only interface omits required equality values from its provider obligations",
)
bad_interface_document = deepcopy(next(
    document for document in documents
    if any(port["target"]["kind"] == "stack-interface" for port in document["device_ports"])
))
next(
    port["target"] for port in bad_interface_document["device_ports"]
    if port["target"]["kind"] == "stack-interface"
).pop("provider_resolution")
try:
    validate(bad_interface_document, schema)
    fails.append("schema accepted an access-only interface without provider resolution")
except SchemaValidationError:
    pass
ck(all(protocol["name"] != protocol["protocol_id"] for protocol in protocols["protocols"]),
   "a protocol definition still uses its opaque ID as its display name")
ck(any("data/resource_profiles.json#" in protocol["canonical_refs"] for protocol in protocols["protocols"]),
   "resource profile canonical data is not linked from protocol definitions")
directory = next(item for item in documents if item["source"].endswith("controller_directory_adapter_v4_0.ic10"))
telemetry = next(item for item in directory["network_dependencies"] if item["reference"] == "r1")
ck(telemetry["literal_reads"] == [96, 97, 99] and {item["abi"] for item in telemetry["accepted"]} == {1, 2},
   "Controller Directory telemetry discovery contract is incomplete")
monitor = next(item for item in documents if item["source"].endswith("stack_cell_monitor_v1_0.ic10"))
ck({item["port"]: item["requirement"] for item in monitor["device_ports"]} ==
   {"d0": "required", "d1": "required", "d2": "optional"},
   "optional port inference escaped its documented port clause")
vending = next(item for item in documents if item["source"].endswith("material_vending_inventory_v1_0.ic10"))
vending_port = next(item for item in vending["device_ports"] if item["port"] == "d0")
ck({item["property"] for item in vending_port["device_properties"]["slot_reads"]} ==
   {"Occupied", "OccupantHash", "Quantity", "MaxQuantity"},
   "slot-property device assumptions are incomplete")
catalog_store = next(item for item in documents if item["source"].endswith("generic_catalog_store_v3_0.ic10"))
ck("default" not in next(field for field in catalog_store["own_stack"]["fields"] if field["address"] == 27),
   "runtime catalog commit was mislabeled as a boot default")
pi_runtime = next(item for item in documents if item["source"].endswith("controller_pi_runtime_v1_1.ic10"))
pi_config = next(item for item in pi_runtime["device_ports"] if item["port"] == "d2")["stack"]
ck(pi_config["dynamic_read_ranges"] == [{"start": 96, "end": 109}] and
   pi_config["dynamic_read_range_source"] == "source-derived",
   "PI config range was not derived from its literal-seeded source loop")
for persistent_store_name in ("power_dispatch_plan_store_v1_0.ic10", "generic_job_store_v1_0.ic10"):
    persistent_store = next(item for item in documents if item["source"].endswith(persistent_store_name))
    ck(persistent_store["behavior"]["restart"]["mode"] == "conditional-reset",
       f"{persistent_store_name} persistence was mislabeled as an unconditional clear")
    ck(any(rule["kind"] == "seqlock" for rule in persistent_store["behavior"]["publication_rules"]),
       f"{persistent_store_name} seqlock publication is absent")
ck(all((not document["own_stack"]["dynamic_read"] or document["own_stack"]["dynamic_read_ranges"]) and
       (not document["own_stack"]["dynamic_write"] or document["own_stack"]["dynamic_write_ranges"])
       for document in documents),
   "a dynamic own-stack access lacks a conservative occupied range")
ck(sum(len(document["behavior"]["invariants"]) for document in documents) > 0 and
   not any(invariant_errors(document) for document in documents),
   "generated machine-readable invariants are absent or false")

payload_rows = _instructions("poke 8 31415999\npoke 9 1\n")
_, payload_aliases = _aliases(payload_rows)
ck(_verify_declared_headers(payload_rows, payload_aliases, []) == [],
   "undeclared payload values were inferred as a protocol header")
try:
    _verify_declared_headers(payload_rows, payload_aliases, [{"base": 8, "magic": 31415998, "abi": 1}])
    fails.append("incorrect authoritative protocol header was accepted")
except ValueError:
    pass

dynamic_source = "move ra 96\nget r0 d0 ra\n"
dynamic_rows = _instructions(dynamic_source)
dynamic_ports, dynamic_aliases = _aliases(dynamic_rows)
try:
    _device_ports(dynamic_source, dynamic_rows, dynamic_ports, dynamic_aliases, {
        "ports": {"d0": {"dynamic_read_ranges": [[0, 0]]}}
    })
    fails.append("source-derived dynamic range accepted an incorrect override")
except ValueError:
    pass
derived_port = _device_ports(dynamic_source, dynamic_rows, dynamic_ports, dynamic_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(derived_port["stack"]["dynamic_read_range_source"] == "source-derived",
   "literal-seeded dynamic access was not marked source-derived")

bypassed_seed = "j Access\nmove ra 96\nAccess:\nget r0 d0 ra\n"
bypassed_rows = _instructions(bypassed_seed)
bypassed_ports, bypassed_aliases = _aliases(bypassed_rows)
bypassed = _device_ports(bypassed_seed, bypassed_rows, bypassed_ports, bypassed_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(bypassed["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a register seed that does not dominate its access was accepted as source-derived")

backedge_source = "move ra 96\nLoop:\nget r0 d0 ra\nadd ra ra 1\nj Loop\n"
backedge_rows = _instructions(backedge_source)
backedge_ports, backedge_aliases = _aliases(backedge_rows)
backedge = _device_ports(backedge_source, backedge_rows, backedge_ports, backedge_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(backedge["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a label-targeted backedge was accepted as a singleton source-derived range")

bypassed_counter_source = (
    "move ra 96\nj Loop\nmove rc 0\nLoop:\nget r0 d0 ra\n"
    "add ra ra 1\nadd rc rc 1\nble rc 3 Loop\n"
)
bypassed_counter_rows = _instructions(bypassed_counter_source)
bypassed_counter_ports, bypassed_counter_aliases = _aliases(bypassed_counter_rows)
bypassed_counter = _device_ports(
    bypassed_counter_source, bypassed_counter_rows, bypassed_counter_ports, bypassed_counter_aliases,
    {"ports": {"d0": {"dynamic_read_ranges": [[96, 99]]}}},
)[0]
ck(bypassed_counter["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a non-dominating loop counter seed was accepted as source-derived")

reentered_loop_source = (
    "move ra 96\nmove rc 0\nLoop:\nget r0 d0 ra\n"
    "add ra ra 1\nadd rc rc 1\nble rc 3 Loop\nj Loop\n"
)
reentered_loop_rows = _instructions(reentered_loop_source)
reentered_loop_ports, reentered_loop_aliases = _aliases(reentered_loop_rows)
reentered_loop = _device_ports(
    reentered_loop_source, reentered_loop_rows, reentered_loop_ports, reentered_loop_aliases,
    {"ports": {"d0": {"dynamic_read_ranges": [[96, 99]]}}},
)[0]
ck(reentered_loop["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a bounded loop with post-bound re-entry was accepted as source-derived")

conditional_clear = _instructions("get r0 db 0\nbne r0 1 Reset\nyield\nReset:\nclr db\n")
ck(_restart_behavior(conditional_clear, True)["mode"] == "conditional-reset",
   "a conditional recovery clear was mislabeled as cleared-on-init")
ck(_restart_behavior(_instructions("clr db\nyield\n"), True)["mode"] == "cleared-on-init",
   "an unconditional entry-path clear was not recognized")

dynamic_header_source = "poke 0 31415999\npoke 1 1\nmove ra 0\npoke ra 5\n"
dynamic_header_rows = _instructions(dynamic_header_source)
_, dynamic_header_aliases = _aliases(dynamic_header_rows)
dynamic_header, _ = _own_stack(
    dynamic_header_source, dynamic_header_rows, dynamic_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(not any("const" in field for field in dynamic_header["fields"] if field["address"] in {0, 1}),
   "a protocol header covered by a dynamic write was presented as constant")

try:
    _source_semantics("poke 12 1 # publication LAST\npoke 10 2\n", {})
    fails.append("commit-last annotation was accepted before a later payload write")
except ValueError:
    pass

verified_seqlock_source = "get r0 db 2\nadd r0 r0 1\npoke 2 r0\npoke 3 5\nadd r0 r0 1\npoke 2 r0\n"
verified_seqlock = _verified_publication_overrides(
    verified_seqlock_source, _instructions(verified_seqlock_source),
    {}, {"publication_rules": [{
        "kind": "seqlock", "address": 2, "verification": "paired-sequence", "description": "odd/even",
    }]},
)
ck(verified_seqlock and verified_seqlock[0]["source"] == "source-fingerprinted-paired-sequence",
   "a structurally verified seqlock publication was not represented")
try:
    invalid_seqlock_source = "get r0 db 2\npoke 2 r0\npoke 3 5\npoke 2 r0\n"
    _verified_publication_overrides(
        invalid_seqlock_source, _instructions(invalid_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence", "description": "invalid",
        }]},
    )
    fails.append("a seqlock without odd/even increment writes was accepted")
except ValueError:
    pass
try:
    unlinked_seqlock_source = (
        "get r9 db 2\nmove r0 0\nadd r0 r0 1\npoke 2 r0\n"
        "poke 3 5\nmove r0 0\nadd r0 r0 1\npoke 2 r0\n"
    )
    _verified_publication_overrides(
        unlinked_seqlock_source, _instructions(unlinked_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence", "description": "unlinked",
        }]},
    )
    fails.append("independent constant increments were accepted as a verified seqlock")
except ValueError:
    pass
try:
    split_seqlock_source = (
        "get r0 db 2\nbeqz r5 First\nj Second\nFirst:\nadd r0 r0 1\npoke 2 r0\n"
        "poke 3 5\nj Done\nSecond:\nget r0 db 2\npoke 4 6\nadd r0 r0 1\npoke 2 r0\nDone:\nyield\n"
    )
    _verified_publication_overrides(
        split_seqlock_source, _instructions(split_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence",
            "description": "mutually exclusive",
        }]},
    )
    fails.append("mutually exclusive sequence writes were accepted as a verified seqlock")
except ValueError:
    pass
try:
    yielding_seqlock_source = (
        "get r0 db 2\nadd r0 r0 1\npoke 2 r0\njal Pause\npoke 3 5\n"
        "add r0 r0 1\npoke 2 r0\nj Done\nPause:\nyield\nj ra\nDone:\nyield\n"
    )
    _verified_publication_overrides(
        yielding_seqlock_source, _instructions(yielding_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence",
            "description": "cross-yield",
        }]},
    )
    fails.append("a seqlock publication path crossing yield was accepted")
except ValueError:
    pass
try:
    early_exit_seqlock_source = (
        "get r0 db 2\nadd r0 r0 1\npoke 2 r0\nbeqz r5 Good\nj End\nGood:\n"
        "poke 3 5\nadd r0 r0 1\npoke 2 r0\nEnd:\nj End\n"
    )
    _verified_publication_overrides(
        early_exit_seqlock_source, _instructions(early_exit_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence",
            "description": "early exit",
        }]},
    )
    fails.append("a provider path that cannot reach the even sequence write was accepted")
except ValueError:
    pass
try:
    _source_semantics("poke 12 1 # publication LAST\nj Late\nLate:\npoke 10 2\nyield\n", {})
    fails.append("commit-last annotation escaped validation through a jump target")
except ValueError:
    pass
try:
    rejoined_checks_source = (
        "get r0 d0 8\nbne r0 31415999 BadMagic\nj Abi\nBadMagic:\nj Abi\nAbi:\n"
        "get r1 d0 9\nbne r1 1 BadAbi\nj Done\nBadAbi:\nj Done\nDone:\nyield\n"
    )
    rejoined_checks_rows = _instructions(rejoined_checks_source)
    rejoined_checks_ports, rejoined_checks_aliases = _aliases(rejoined_checks_rows)
    _verify_declared_consumers(
        rejoined_checks_source, rejoined_checks_rows,
        rejoined_checks_ports, rejoined_checks_aliases,
        [{"port": "d0", "accepted": [{
            "header_base": 8, "magic": 31415999, "abi": 1,
        }]}],
    )
    fails.append("header failure branches that rejoin success were accepted")
except ValueError:
    pass

try:
    skipped_network_checks_source = (
        "getd r0 r1 0\nj Abi\nbne r0 31415999 Bad\nAbi:\ngetd r0 r1 1\n"
        "j Done\nbne r0 1 Bad\nDone:\nyield\nBad:\nyield\n"
    )
    skipped_network_rows = _instructions(skipped_network_checks_source)
    _, skipped_network_aliases = _aliases(skipped_network_rows)
    _network_dependencies(
        skipped_network_checks_source, skipped_network_rows, skipped_network_aliases,
        {"network_protocols": [{
            "reference": "r1", "header_base": 0, "magic": 31415999,
            "abi_min": 1, "abi_max": 1,
        }]},
    )
    fails.append("unreachable network protocol checks were accepted")
except ValueError:
    pass

broken_invariant = deepcopy(next(item for item in documents if item["behavior"]["invariants"]))
broken_invariant["behavior"]["invariants"][0]["equals"] = -999
ck(invariant_errors(broken_invariant), "false machine-readable invariant was not rejected")
dynamic_invariant = deepcopy(next(item for item in documents if item["behavior"]["invariants"]))
dynamic_invariant["own_stack"]["dynamic_write"] = True
dynamic_invariant["own_stack"]["dynamic_write_ranges"] = [{"start": 0, "end": 511}]
ck(any("not proven across dynamic writes" in error for error in invariant_errors(dynamic_invariant)),
   "an invariant covered by dynamic writes was accepted")

consumer_source = "get r0 d0 8\nbne r0 31415999 Bad\nget r0 d0 9\nbne r0 1 Bad\n"
consumer_rows = _instructions(consumer_source)
consumer_ports, consumer_aliases = _aliases(consumer_rows)
ck(_verify_declared_consumers(consumer_source, consumer_rows, consumer_ports, consumer_aliases, []) == [],
   "undeclared payload equality checks were inferred as a consumed protocol")
try:
    _verify_declared_consumers(consumer_source, consumer_rows, consumer_ports, consumer_aliases, [{
        "port": "d0", "accepted": [{"header_base": 8, "magic": 31415998, "abi": 1}]
    }])
    fails.append("incorrect authoritative consumed protocol was accepted")
except ValueError:
    pass
try:
    skipped_checks_source = (
        "get r0 d0 8\nj Abi\nbne r0 31415999 Bad\nAbi:\nget r1 d0 9\n"
        "j Done\nbne r1 1 Bad\nDone:\nyield\nBad:\nyield\n"
    )
    skipped_checks_rows = _instructions(skipped_checks_source)
    skipped_checks_ports, skipped_checks_aliases = _aliases(skipped_checks_rows)
    _verify_declared_consumers(
        skipped_checks_source, skipped_checks_rows, skipped_checks_ports, skipped_checks_aliases,
        [{"port": "d0", "accepted": [{
            "header_base": 8, "magic": 31415999, "abi": 1,
        }]}],
    )
    fails.append("unreachable header comparisons were accepted as authoritative checks")
except ValueError:
    pass

fake_fence_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Retry\nget r0 d0 2\nbeq r0 r0 Stable\n"
)
fake_fence_rows = _instructions(fake_fence_source)
fake_fence_ports, fake_fence_aliases = _aliases(fake_fence_rows)
ck(not _verified_seqlock_consumer(
    fake_fence_source, fake_fence_rows, fake_fence_ports, fake_fence_aliases, "d0", 2
),
   "a seqlock consumer that overwrites its first snapshot and self-compares was accepted")

noop_retry_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Accept\nget r2 d0 2\n"
    "bne r2 r0 Accept\nAccept:\nget r3 d0 5\n"
)
noop_retry_rows = _instructions(noop_retry_source)
noop_retry_ports, noop_retry_aliases = _aliases(noop_retry_rows)
ck(not _verified_seqlock_consumer(
    noop_retry_source, noop_retry_rows, noop_retry_ports, noop_retry_aliases, "d0", 2
), "a seqlock consumer whose retry target equals its success continuation was accepted")

unreachable_reread_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Retry\nj Done\nSecond:\n"
    "get r2 d0 2\nbne r2 r0 Retry\nDone:\nyield\nRetry:\nyield\n"
)
unreachable_reread_rows = _instructions(unreachable_reread_source)
unreachable_reread_ports, unreachable_reread_aliases = _aliases(unreachable_reread_rows)
ck(not _verified_seqlock_consumer(
    unreachable_reread_source, unreachable_reread_rows,
    unreachable_reread_ports, unreachable_reread_aliases, "d0", 2
), "a seqlock consumer with an unreachable second read was accepted")

rejoined_retry_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Retry\nEven:\nget r2 d0 2\n"
    "bne r2 r0 Retry\nj Done\nRetry:\nj Even\nDone:\nyield\n"
)
rejoined_retry_rows = _instructions(rejoined_retry_source)
rejoined_retry_ports, rejoined_retry_aliases = _aliases(rejoined_retry_rows)
ck(not _verified_seqlock_consumer(
    rejoined_retry_source, rejoined_retry_rows,
    rejoined_retry_ports, rejoined_retry_aliases, "d0", 2
), "a seqlock retry branch that rejoins without refreshing the first read was accepted")

publication_drift = deepcopy(documents)
required = next(
    (accepted, consumer)
    for consumer in publication_drift
    for requirement in consumer["contracts"]["consumes"]
    for accepted in requirement["accepted"]
    if accepted["publication_requirements"]
)
accepted, _ = required
for provider in publication_drift:
    if any(item["protocol_id"] == accepted["protocol_id"] and item["base"] == accepted["header_base"] for item in provider["contracts"]["provides"]):
        provider["behavior"]["publication_rules"] = []
ck(any("publication=" in error for error in compatibility_errors(publication_drift)),
   "publication-rule mismatch was not rejected")

try:
    validate("abcd", {"type": "string", "maxLength": 3})
    fails.append("maxLength was not enforced")
except SchemaValidationError:
    pass
try:
    validate("ok", {"type": "string", "notImplemented": True})
    fails.append("unsupported JSON Schema keyword was silently ignored")
except SchemaValidationError:
    pass
try:
    _ranges([[8, 7]])
    fails.append("inverted stack range was accepted")
except ValueError:
    pass
try:
    _ranges([[0, 10], [5, 15]])
    fails.append("overlapping stack ranges were accepted")
except ValueError:
    pass
ck(ranges_overlap([{"start": 0, "end": 10}, {"start": 5, "end": 15}]),
   "overlapping generated ranges are not detected")

try:
    validate(5, {"$defs": {"number": {"type": "integer"}}, "$ref": "#/$defs/number", "maximum": 3})
    fails.append("JSON Schema sibling keyword next to $ref was ignored")
except SchemaValidationError:
    pass

with tempfile.TemporaryDirectory() as directory_name:
    nested = _ProjectPath(directory_name) / "contracts" / "family" / "stale" / "orphan.contract.json"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}")
    ck(nested in generated_artifact_paths(_ProjectPath(directory_name), "*.contract.json"),
       "nested orphan contracts are not discovered")
    source = _ProjectPath(directory_name) / "dynamic.ic10"
    source.write_text("move ra 96\nget r0 d0 ra\n")
    import hashlib
    override = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    verify_override_source(source, override)
    source.write_text("move ra 97\nget r0 d0 ra\n")
    try:
        verify_override_source(source, override)
        fails.append("dynamic-range override did not detect source arithmetic drift")
    except ValueError:
        pass

if fails:
    print("Script contract tests: FAIL")
    for failure in fails:
        print(" -", failure)
    raise SystemExit(1)
print("Script contract tests: PASS")
print(" - JSON Schema, overlap, authoritative-header, and source-fingerprint failures are enforced")
print(" - missing providers, wrong layouts, publication rules, and access direction fail compatibility")
print(" - all deployable scripts, explicit port targets, and semantic protocol definitions are inventoried")
