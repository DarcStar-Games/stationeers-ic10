#!/usr/bin/env python3
"""Focused failure tests for script contract schema and compatibility validation."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.ic10_source import game_hash

from copy import deepcopy
import json
import tempfile

from framework.json_schema import SchemaValidationError, validate
from framework.ic10_source import parse_ic10
from framework.script_contracts import (
    access_interface_id,
    access_provider_obligations,
    build_all,
    compatibility_errors,
    generated_artifact_paths,
    invariant_errors,
    ranges_overlap,
    verify_override_source,
)
from framework.script_contracts.address_forms import dynamic_access_bases
from framework.script_contracts.control_flow import writes_register
from framework.script_contracts.device_ports import (
    analyze_device_ports,
    network_dependencies,
    verify_declared_consumers,
)
from framework.script_contracts.dynamic_ranges import validated_ranges
from framework.script_contracts.own_stack import (
    analyze_own_stack,
    header_invariants,
    restart_behavior,
    verify_declared_headers,
)
from framework.script_contracts.parsing import collect_aliases, parse_rows
from framework.script_contracts.publication import (
    source_semantics,
    verified_publication_overrides,
    verified_seqlock_consumer,
)
from framework.script_contracts.value_bounds import (
    declared_coverage_errors,
    dynamic_access_cells,
)
from framework.source_metadata import deployable_scripts

ROOT = _PROJECT_ROOT
fails = []


def ck(condition, message):
    if not condition:
        fails.append(message)


parser_fixture = parse_ic10(
    '# heading\n\nStart: # entry\nalias Port d0\ndefine Limit 3\n'
    'move r0, Limit # normalized\nbad-label:\nStart:\n'
)
ck(len(parser_fixture.lines) == 8 and parser_fixture.lines[0].raw_text == '# heading'
   and parser_fixture.lines[1].code_text == '',
   "canonical parser did not retain comments, blank lines, and physical source text")
ck([(label.name, label.line.number, label.row_index, label.instruction_index)
    for label in parser_fixture.labels] == [('Start', 3, 0, 0), ('Start', 8, 4, 2)],
   "canonical parser did not resolve label row and executable indices")
ck([(directive.kind, directive.name, directive.value, directive.row.line.number)
    for directive in parser_fixture.directives]
   == [('alias', 'Port', 'd0', 4), ('define', 'Limit', '3', 5)],
   "canonical parser did not retain alias/define directives and source lines")
ck(parser_fixture.instructions[0].opcode == 'move'
   and parser_fixture.instructions[0].operands == ('r0', 'Limit')
   and parser_fixture.instructions[0].line.code_text == 'move r0, Limit',
   "canonical parser did not normalize comma-separated operands")
ck([(item.code, item.line_number, item.related_line_number)
    for item in parser_fixture.diagnostics]
   == [('malformed-label', 7, None), ('duplicate-label', 8, 3)],
   "canonical parser diagnostics did not identify malformed and duplicate labels")
quoted_fixture = parse_ic10('define Key HASH("A B,#C") # trailing comment\n')
ck(quoted_fixture.lines[0].code_text == 'define Key HASH("A B,#C")'
   and quoted_fixture.lines[0].comment_text == 'trailing comment'
   and quoted_fixture.directives[0].value == 'HASH("A B,#C")',
   "canonical parser split quoted spaces, commas, or comment markers")
quoted_annotations, quoted_rules = source_semantics(
    'poke 8 HASH("Identity#V1") # generation last\nyield\n', {}
)
ck(quoted_annotations[8]["descriptions"] == ["generation last"]
   and quoted_rules[0]["description"] == "generation last",
   "contract semantics reparsed a quoted hash comment marker")


contracts, index, protocols, protocol_definitions = build_all(ROOT)
documents = list(contracts.values())
schema = json.loads((ROOT / "schemas/script_contract_v2.schema.json").read_text())
legacy_schema = json.loads((ROOT / "schemas/script_contract.schema.json").read_text())
try:
    for document in documents:
        validate(document, schema)
except SchemaValidationError as error:
    fails.append(f"valid generated document rejected: {error}")
ck(all(document["format"] == "IC10_SCRIPT_CONTRACT_V2" and
       document["extraction"]["mode"] == "static-v2" and
       document["$schema"] == "../../schemas/script_contract_v2.schema.json"
       for document in documents),
   "generated contracts did not advertise the breaking V2 schema")
ck(schema["$id"].endswith("/script_contract_v2.schema.json") and
   schema["properties"]["$schema"]["const"] == "../../schemas/script_contract_v2.schema.json",
   "V2 schema does not have a distinct canonical identity")
ck(legacy_schema["properties"]["format"]["const"] == "IC10_SCRIPT_CONTRACT_V1" and
   legacy_schema["properties"]["extraction"]["properties"]["mode"]["const"] == "static-v1",
   "unversioned V1 schema was not preserved")

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
        if field.get("const") == game_hash("ControllerPressureTransfer"):
            field["const"] = game_hash("ControllerPressureDomain")
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
pi_input = next(item for item in pi_runtime["device_ports"] if item["port"] == "d0")
pi_output = next(item for item in pi_runtime["device_ports"] if item["port"] == "d1")
ck(pi_input["dynamic_property_sources"] == [{
       "operand": "r12", "source_port": "d2", "address": 107,
       "fence": {
           "address": 51, "kind": "generation",
           "description": "Config Host generation must be positive and unchanged around the LogicType read.",
       },
   }], "PI input LogicType lacks its fenced Config Host provenance")
ck(pi_output["device_properties"]["reads"] == [] and
   pi_output["device_properties"]["writes"] == ["r13"],
   "bdnvs was not classified as a writable-property requirement")
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
own_inventory = index["own_stack_range_inventory"]
ck(own_inventory["dynamic_script_count"] == sum(
       document["own_stack"]["dynamic_read"] or document["own_stack"]["dynamic_write"]
       for document in documents
   ), "own-stack range inventory does not cover every dynamic script")
ck(own_inventory["unresolved_fallback_count"] == sum(
       document["own_stack"][f"dynamic_{direction}_range_source"] == "conservative-full-stack"
       for document in documents for direction in ("read", "write")
   ) > 0, "own-stack range inventory does not explicitly report unresolved fallbacks")
proven_own_reads = {
    item["source"]: item["read"]["proven_ranges"]
    for item in own_inventory["scripts"] if item["read"]["proven_ranges"]
}
ck(proven_own_reads.get("ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10") ==
   [{"start": 56, "end": 62}],
   "bounded Generic Job gateway own-stack loop is absent from proven occupancy")
ck(proven_own_reads.get("ic10/resource-grid-core/resource_reservation_v1_0.ic10") ==
   [{"start": 28, "end": 31}],
   "bounded Resource Reservation own-stack loop is absent from proven occupancy")
ck(sum(len(document["behavior"]["invariants"]) for document in documents) > 0 and
   not any(invariant_errors(document) for document in documents),
   "generated machine-readable invariants are absent or false")

payload_rows = parse_rows("poke 8 31415999\npoke 9 1\n")
_, payload_aliases = collect_aliases(payload_rows)
ck(verify_declared_headers(payload_rows, payload_aliases, []) == [],
   "undeclared payload values were inferred as a protocol header")
try:
    verify_declared_headers(payload_rows, payload_aliases, [{"base": 8, "magic": game_hash("TransformCandidateReadiness.v1"), "abi": 1}])
    fails.append("incorrect authoritative protocol header was accepted")
except ValueError:
    pass

dynamic_source = "move ra 96\nget r0 d0 ra\n"
dynamic_rows = parse_rows(dynamic_source)
dynamic_ports, dynamic_aliases = collect_aliases(dynamic_rows)
try:
    analyze_device_ports(dynamic_source, dynamic_rows, dynamic_ports, dynamic_aliases, {
        "ports": {"d0": {"dynamic_read_ranges": [[0, 0]]}}
    })
    fails.append("source-derived dynamic range accepted an incorrect override")
except ValueError:
    pass
derived_port = analyze_device_ports(dynamic_source, dynamic_rows, dynamic_ports, dynamic_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(derived_port["stack"]["dynamic_read_range_source"] == "source-derived",
   "literal-seeded dynamic access was not marked source-derived")

bypassed_seed = "j Access\nmove ra 96\nAccess:\nget r0 d0 ra\n"
bypassed_rows = parse_rows(bypassed_seed)
bypassed_ports, bypassed_aliases = collect_aliases(bypassed_rows)
bypassed = analyze_device_ports(bypassed_seed, bypassed_rows, bypassed_ports, bypassed_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(bypassed["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a register seed that does not dominate its access was accepted as source-derived")

backedge_source = "move ra 96\nLoop:\nget r0 d0 ra\nadd ra ra 1\nj Loop\n"
backedge_rows = parse_rows(backedge_source)
backedge_ports, backedge_aliases = collect_aliases(backedge_rows)
backedge = analyze_device_ports(backedge_source, backedge_rows, backedge_ports, backedge_aliases, {
    "ports": {"d0": {"dynamic_read_ranges": [[96, 96]]}}
})[0]
ck(backedge["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a label-targeted backedge was accepted as a singleton source-derived range")

bypassed_counter_source = (
    "move ra 96\nj Loop\nmove rc 0\nLoop:\nget r0 d0 ra\n"
    "add ra ra 1\nadd rc rc 1\nble rc 3 Loop\n"
)
bypassed_counter_rows = parse_rows(bypassed_counter_source)
bypassed_counter_ports, bypassed_counter_aliases = collect_aliases(bypassed_counter_rows)
bypassed_counter = analyze_device_ports(
    bypassed_counter_source, bypassed_counter_rows, bypassed_counter_ports, bypassed_counter_aliases,
    {"ports": {"d0": {"dynamic_read_ranges": [[96, 99]]}}},
)[0]
ck(bypassed_counter["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a non-dominating loop counter seed was accepted as source-derived")

reentered_loop_source = (
    "move ra 96\nmove rc 0\nLoop:\nget r0 d0 ra\n"
    "add ra ra 1\nadd rc rc 1\nble rc 3 Loop\nj Loop\n"
)
reentered_loop_rows = parse_rows(reentered_loop_source)
reentered_loop_ports, reentered_loop_aliases = collect_aliases(reentered_loop_rows)
reentered_loop = analyze_device_ports(
    reentered_loop_source, reentered_loop_rows, reentered_loop_ports, reentered_loop_aliases,
    {"ports": {"d0": {"dynamic_read_ranges": [[96, 99]]}}},
)[0]
ck(reentered_loop["stack"]["dynamic_read_range_source"] == "source-fingerprinted-exception",
   "a bounded loop with post-bound re-entry was accepted as source-derived")

conditional_clear = parse_rows("get r0 db 0\nbne r0 1 Reset\nyield\nReset:\nclr db\n")
ck(restart_behavior(conditional_clear, True)["mode"] == "conditional-reset",
   "a conditional recovery clear was mislabeled as cleared-on-init")
ck(restart_behavior(parse_rows("clr db\nyield\n"), True)["mode"] == "cleared-on-init",
   "an unconditional entry-path clear was not recognized")

dynamic_header_source = "poke 0 31415999\npoke 1 1\nmove ra 0\npoke ra 5\n"
dynamic_header_rows = parse_rows(dynamic_header_source)
_, dynamic_header_aliases = collect_aliases(dynamic_header_rows)
dynamic_header, _ = analyze_own_stack(
    dynamic_header_source, dynamic_header_rows, dynamic_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
dynamic_header_fields = {field["address"]: field for field in dynamic_header["fields"]}
ck("const" not in dynamic_header_fields[0] and dynamic_header_fields[1].get("const") == 1,
   "dynamic write coverage did not suppress only the affected header constant")

bounded_own_source = (
    "poke 0 31415999\npoke 1 1\nmove ra 96\nmove rc 0\nLoop:\n"
    "get r0 db ra\npoke ra r0\nadd ra ra 1\nadd rc rc 1\nble rc 3 Loop\n"
)
bounded_own_rows = parse_rows(bounded_own_source)
_, bounded_own_aliases = collect_aliases(bounded_own_rows)
bounded_own, _ = analyze_own_stack(
    bounded_own_source, bounded_own_rows, bounded_own_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(bounded_own["dynamic_read_ranges"] == [{"start": 96, "end": 99}] and
   bounded_own["dynamic_write_ranges"] == [{"start": 96, "end": 99}] and
   bounded_own["dynamic_read_proven_ranges"] == [{"start": 96, "end": 99}] and
   bounded_own["dynamic_write_proven_ranges"] == [{"start": 96, "end": 99}] and
   bounded_own["dynamic_read_range_source"] == "source-derived" and
   bounded_own["dynamic_write_range_source"] == "source-derived",
   "bounded own-stack table reads/writes were not derived from the shared strict loop proof")
ck({item["address"] for item in header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], bounded_own
   )} == {0, 1}, "non-overlapping bounded writes did not restore header invariants")
ck(all("const" in field for field in bounded_own["fields"] if field["address"] in {0, 1}),
   "non-overlapping bounded writes suppressed header constants")

ck(not writes_register(["bge", "r6", "r12", "Done"], "r6")
   and not writes_register(["sd", "r5", "On", "r1"], "r5")
   and not writes_register(["clr", "d0"], "d0")
   and writes_register(["add", "r0", "r0", "32"], "r0")
   and writes_register(["pop", "r3"], "r3")
   and writes_register(["push", "r3"], "sp"),
   "instruction signatures did not decide which mnemonics assign their first operand")

record_loop_source = (
    "move r6 0\nRecord:\nbge r6 r12 Done\nmul r0 r6 3\nadd r0 r0 32\n"
    "get r1 d1 r0\nadd r0 r0 2\nget r2 d1 r0\nadd r6 r6 1\nj Record\nDone:\nyield\n"
)
record_loop_rows = parse_rows(record_loop_source)
record_loop_ports, record_loop_aliases = collect_aliases(record_loop_rows)
ck([item[:3] for item in dynamic_access_bases(record_loop_source, record_loop_ports, record_loop_aliases)] ==
   [("d1", "read", 32), ("d1", "read", 34)],
   "a strided record loop did not reduce to its first-pass base addresses")
ck([(item[0], item[1], sorted(item[2])) for item in
    dynamic_access_cells(record_loop_source, record_loop_ports, record_loop_aliases)] ==
   [("d1", "read", [32]), ("d1", "read", [34])],
   "a loop counted against an unbounded peer count claimed more than its first pass")
ck(len(declared_coverage_errors(record_loop_source, record_loop_ports, record_loop_aliases,
                                {("d1", "read"): [{"start": 16, "end": 31}]})) == 2,
   "a declared range that omits the record base was accepted")
ck(not declared_coverage_errors(record_loop_source, record_loop_ports, record_loop_aliases,
                                {("d1", "read"): [{"start": 32, "end": 49}]}),
   "the record window the loop actually reaches was rejected")

# The same loop, with the count validated the way a fail-closed consumer does:
# six legs of three cells reach S32..S49, so a two-leg window is short.
guarded_loop_source = record_loop_source.replace(
    "move r6 0\n", "blt r12 0 Done\nbgt r12 6 Done\nmove r6 0\n"
)
guarded_loop_rows = parse_rows(guarded_loop_source)
guarded_loop_ports, guarded_loop_aliases = collect_aliases(guarded_loop_rows)
ck([(item[0], item[1], sorted(item[2])) for item in
    dynamic_access_cells(guarded_loop_source, guarded_loop_ports, guarded_loop_aliases)] ==
   [("d1", "read", [32, 35, 38, 41, 44, 47]), ("d1", "read", [34, 37, 40, 43, 46, 49])],
   "a validated record count did not bound the far end of the loop it counts")
ck(sorted(int(cell[1:]) for cell in
          " ".join(declared_coverage_errors(
              guarded_loop_source, guarded_loop_ports, guarded_loop_aliases,
              {("d1", "read"): [{"start": 32, "end": 37}]})).replace(",", " ").split()
          if cell.startswith("S")) == [38, 40, 41, 43, 44, 46, 47, 49],
   "a window anchored right but cut short was accepted")
ck(not declared_coverage_errors(guarded_loop_source, guarded_loop_ports, guarded_loop_aliases,
                                {("d1", "read"): [{"start": 32, "end": 49}]}),
   "the full record window a validated count reaches was rejected")

# A bottom test counts a loop out just as well, and bounds an address register
# advanced beside the counter rather than compared against anything itself.
staging_source = (
    "move r3 128\nmove r4 16\nCopy:\nget r0 db r4\npoke r3 r0\n"
    "add r3 r3 1\nadd r4 r4 1\nble r4 23 Copy\n"
)
staging_rows = parse_rows(staging_source)
staging_ports, staging_aliases = collect_aliases(staging_rows)
ck([(item[0], item[1], min(item[2]), max(item[2])) for item in
    dynamic_access_cells(staging_source, staging_ports, staging_aliases)] ==
   [("db", "read", 16, 23), ("db", "write", 128, 135)],
   "a bottom-tested staging loop was not counted out by its own exit test")

# Dropping the call and return edges leaves blocks with fewer predecessors than
# they have, which over-states what dominates them: both bounds stand down.
subroutine_source = staging_source + "jal Helper\nj Copy\nHelper:\nj ra\n"
subroutine_rows = parse_rows(subroutine_source)
subroutine_ports, subroutine_aliases = collect_aliases(subroutine_rows)
ck([(item[0], item[1], sorted(item[2])) for item in
    dynamic_access_cells(subroutine_source, subroutine_ports, subroutine_aliases)] ==
   [("db", "read", [16]), ("db", "write", [128])],
   "an unmodeled transfer did not stand the branch bounds down to the base rule")

peer_based_source = "get r5 d0 24\nadd r0 r5 25\nget r1 d0 r0\n"
peer_based_rows = parse_rows(peer_based_source)
peer_based_ports, peer_based_aliases = collect_aliases(peer_based_rows)
ck(not dynamic_access_bases(peer_based_source, peer_based_ports, peer_based_aliases)
   and not dynamic_access_cells(peer_based_source, peer_based_ports, peer_based_aliases)
   and not declared_coverage_errors(peer_based_source, peer_based_ports, peer_based_aliases,
                                    {("d0", "read"): [{"start": 400, "end": 401}]}),
   "an address offset by an unbounded peer value was given cells it cannot be held to")

own_table_source = "move ra 96\nTable:\nget r0 db ra\npoke ra r0\nadd ra ra 1\nblt ra 100 Table\n"
own_table_rows = parse_rows(own_table_source)
own_table_ports, own_table_aliases = collect_aliases(own_table_rows)
ck([item[:3] for item in dynamic_access_bases(own_table_source, own_table_ports, own_table_aliases)] ==
   [("db", "read", 96), ("db", "write", 96)],
   "own-stack table accesses were not reduced to their base cell")
ck([(item[0], item[1], sorted(item[2])) for item in
    dynamic_access_cells(own_table_source, own_table_ports, own_table_aliases)] ==
   [("db", "read", [96, 97, 98, 99]), ("db", "write", [96, 97, 98, 99])],
   "the own-stack table loop was not bounded by its literal exit test")

conflicting_header_source = bounded_own_source.replace(
    "poke 1 1\n", "poke 1 1\npoke 0 0\n"
)
conflicting_header_rows = parse_rows(conflicting_header_source)
_, conflicting_header_aliases = collect_aliases(conflicting_header_rows)
conflicting_header, _ = analyze_own_stack(
    conflicting_header_source, conflicting_header_rows, conflicting_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
conflicting_header_fields = {field["address"]: field for field in conflicting_header["fields"]}
ck("const" not in conflicting_header_fields[0] and not header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], conflicting_header
   ), "conflicting literal header write produced a false constant or invariant")

conditional_header_source = (
    "beqz r5 Ready\npoke 0 31415999\npoke 1 1\nReady:\nyield\n"
)
conditional_header_rows = parse_rows(conditional_header_source)
_, conditional_header_aliases = collect_aliases(conditional_header_rows)
conditional_header, _ = analyze_own_stack(
    conditional_header_source, conditional_header_rows, conditional_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(not header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], conditional_header
   ), "conditionally skipped header initialization produced a false invariant")

delayed_header_source = "yield\npoke 0 31415999\npoke 1 1\n"
delayed_header_rows = parse_rows(delayed_header_source)
_, delayed_header_aliases = collect_aliases(delayed_header_rows)
delayed_header, _ = analyze_own_stack(
    delayed_header_source, delayed_header_rows, delayed_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(not header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], delayed_header
   ), "header initialization after the first yield produced a false invariant")

both_branches_header_source = (
    "beqz r5 Alternate\npoke 0 31415999\npoke 1 1\nj Ready\n"
    "Alternate:\npoke 0 31415999\npoke 1 1\nReady:\nyield\n"
)
both_branches_header_rows = parse_rows(both_branches_header_source)
_, both_branches_header_aliases = collect_aliases(both_branches_header_rows)
both_branches_header, _ = analyze_own_stack(
    both_branches_header_source, both_branches_header_rows, both_branches_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck({item["address"] for item in header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], both_branches_header
   )} == {0, 1}, "same-value initialization on every branch was not proven")

called_header_source = (
    "poke 0 31415999\npoke 1 1\njal Helper\nyield\nHelper:\nj ra\n"
)
called_header_rows = parse_rows(called_header_source)
_, called_header_aliases = collect_aliases(called_header_rows)
called_header, _ = analyze_own_stack(
    called_header_source, called_header_rows, called_header_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck({item["address"] for item in header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], called_header
   )} == {0, 1}, "local subroutine call suppressed guaranteed header initialization")

header_after_call_source = (
    "jal Helper\npoke 0 31415999\npoke 1 1\nyield\nHelper:\nj ra\n"
)
header_after_call_rows = parse_rows(header_after_call_source)
_, header_after_call_aliases = collect_aliases(header_after_call_rows)
header_after_call, _ = analyze_own_stack(
    header_after_call_source, header_after_call_rows, header_after_call_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck({item["address"] for item in header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], header_after_call
   )} == {0, 1}, "a non-observable subroutine call was mistaken for a loop boundary")

yielding_call_source = (
    "jal Helper\npoke 0 31415999\npoke 1 1\nyield\nHelper:\nyield\nj ra\n"
)
yielding_call_rows = parse_rows(yielding_call_source)
_, yielding_call_aliases = collect_aliases(yielding_call_rows)
yielding_call, _ = analyze_own_stack(
    yielding_call_source, yielding_call_rows, yielding_call_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(not header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], yielding_call
   ), "a callee yield before header initialization produced a false invariant")

conditional_return_source = (
    "beqz r5 ra\npoke 0 31415999\npoke 1 1\nyield\n"
)
conditional_return_rows = parse_rows(conditional_return_source)
_, conditional_return_aliases = collect_aliases(conditional_return_rows)
conditional_return, _ = analyze_own_stack(
    conditional_return_source, conditional_return_rows, conditional_return_aliases,
    [{"base": 0, "magic": 31415999, "abi": 1}], {},
)
ck(not header_invariants(
       [{"base": 0, "magic": 31415999, "abi": 1}], conditional_return
   ), "a conditional termination before header initialization produced a false invariant")

unsafe_call_sources = {
    "nested call": (
        "jal Outer\npoke 0 31415999\npoke 1 1\nyield\n"
        "Outer:\njal Inner\nj ra\nInner:\nj ra\n"
    ),
    "clobbered return address": (
        "jal Helper\npoke 0 31415999\npoke 1 1\nyield\n"
        "Helper:\nmove ra 0\nj ra\n"
    ),
}
for case, unsafe_call_source in unsafe_call_sources.items():
    unsafe_call_rows = parse_rows(unsafe_call_source)
    _, unsafe_call_aliases = collect_aliases(unsafe_call_rows)
    unsafe_call, _ = analyze_own_stack(
        unsafe_call_source, unsafe_call_rows, unsafe_call_aliases,
        [{"base": 0, "magic": 31415999, "abi": 1}], {},
    )
    ck(not header_invariants(
           [{"base": 0, "magic": 31415999, "abi": 1}], unsafe_call
       ), f"{case} used an unsound abstract return stack for header initialization")

stack_pointer_sources = {
    "push": "move sp 96\npush 0\nget r0 db sp\n",
    "pop": "move sp 97\npop r0\nget r1 db sp\n",
}
for operation, stack_pointer_source in stack_pointer_sources.items():
    stack_pointer_rows = parse_rows(stack_pointer_source)
    _, stack_pointer_aliases = collect_aliases(stack_pointer_rows)
    stack_pointer_access, _ = analyze_own_stack(
        stack_pointer_source, stack_pointer_rows, stack_pointer_aliases, [], {},
    )
    ck(stack_pointer_access["dynamic_read_proven_ranges"] == [],
       f"implicit {operation} mutation of sp produced a false source-proven range")

strided_source = (
    "move ra 96\nmove rc 0\nLoop:\npoke ra 1\n"
    "add ra ra 2\nadd rc rc 1\nble rc 3 Loop\n"
)
strided_rows = parse_rows(strided_source)
_, strided_aliases = collect_aliases(strided_rows)
strided, _ = analyze_own_stack(strided_source, strided_rows, strided_aliases, [], {})
ck(strided["dynamic_write_ranges"] == [
       {"start": 96, "end": 96}, {"start": 98, "end": 98},
       {"start": 100, "end": 100}, {"start": 102, "end": 102},
   ] and strided["dynamic_write_proven_ranges"] == strided["dynamic_write_ranges"],
   "non-unit stride was not represented as exact source-proven cells")

own_negative_sources = {
    "branch bypass": "beqz r5 Seed\nj Access\nSeed:\nmove ra 96\nAccess:\npoke ra 1\n",
    "multiple mutations": (
        "move ra 96\nmove rc 0\nLoop:\npoke ra 1\nadd ra ra 1\nadd ra ra 1\n"
        "add rc rc 1\nble rc 3 Loop\n"
    ),
    "branch-dependent update": (
        "move ra 96\nmove rc 0\nLoop:\npoke ra 1\nbeqz r5 SkipCounter\nadd rc rc 1\n"
        "SkipCounter:\nadd ra ra 1\nble rc 3 Loop\n"
    ),
    "non-dominating counter seed": (
        "move ra 96\nj Loop\nmove rc 0\nLoop:\npoke ra 1\nadd ra ra 1\n"
        "add rc rc 1\nble rc 3 Loop\n"
    ),
    "unbounded loop": "move ra 96\nLoop:\npoke ra 1\nadd ra ra 1\nj Loop\n",
}
for case, own_source in own_negative_sources.items():
    own_rows = parse_rows(own_source)
    _, own_aliases = collect_aliases(own_rows)
    unresolved, _ = analyze_own_stack(own_source, own_rows, own_aliases, [], {})
    ck(unresolved["dynamic_write_ranges"] == [{"start": 0, "end": 511}] and
       unresolved["dynamic_write_range_source"] == "conservative-full-stack",
       f"{case} own-stack address did not fail closed")

exception_source = "move ra 96\nLoop:\npoke ra 1\nadd ra ra 1\nj Loop\n"
exception_rows = parse_rows(exception_source)
_, exception_aliases = collect_aliases(exception_rows)
exception, _ = analyze_own_stack(
    exception_source, exception_rows, exception_aliases, [], {"dynamic_write_ranges": [[96, 111]]},
)
ck(exception["dynamic_write_range_source"] == "source-fingerprinted-exception" and
   exception["dynamic_write_ranges"] == [{"start": 96, "end": 111}],
   "reviewed own-stack range exception was not distinguished from source proof and fallback")
try:
    analyze_own_stack(
        bounded_own_source, bounded_own_rows, bounded_own_aliases, [],
        {"dynamic_write_ranges": [[96, 98]]},
    )
    fails.append("own-stack override omitted a statically reachable cell")
except ValueError:
    pass
partially_proven_source = bounded_own_source + "poke r5 1\n"
partially_proven_rows = parse_rows(partially_proven_source)
_, partially_proven_aliases = collect_aliases(partially_proven_rows)
try:
    analyze_own_stack(
        partially_proven_source, partially_proven_rows, partially_proven_aliases, [],
        {"dynamic_write_ranges": [[96, 98]]},
    )
    fails.append("own-stack exception omitted a cell from its source-proven subset")
except ValueError:
    pass

try:
    source_semantics("poke 12 1 # publication LAST\npoke 10 2\n", {})
    fails.append("commit-last annotation was accepted before a later payload write")
except ValueError:
    pass

verified_seqlock_source = "get r0 db 2\nadd r0 r0 1\npoke 2 r0\npoke 3 5\nadd r0 r0 1\npoke 2 r0\n"
verified_seqlock = verified_publication_overrides(
    verified_seqlock_source, parse_rows(verified_seqlock_source),
    {}, {"publication_rules": [{
        "kind": "seqlock", "address": 2, "verification": "paired-sequence", "description": "odd/even",
    }]},
)
ck(verified_seqlock and verified_seqlock[0]["source"] == "source-fingerprinted-paired-sequence",
   "a structurally verified seqlock publication was not represented")
try:
    invalid_seqlock_source = "get r0 db 2\npoke 2 r0\npoke 3 5\npoke 2 r0\n"
    verified_publication_overrides(
        invalid_seqlock_source, parse_rows(invalid_seqlock_source), {},
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
    verified_publication_overrides(
        unlinked_seqlock_source, parse_rows(unlinked_seqlock_source), {},
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
    verified_publication_overrides(
        split_seqlock_source, parse_rows(split_seqlock_source), {},
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
    verified_publication_overrides(
        yielding_seqlock_source, parse_rows(yielding_seqlock_source), {},
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
    verified_publication_overrides(
        early_exit_seqlock_source, parse_rows(early_exit_seqlock_source), {},
        {"publication_rules": [{
            "kind": "seqlock", "address": 2, "verification": "paired-sequence",
            "description": "early exit",
        }]},
    )
    fails.append("a provider path that cannot reach the even sequence write was accepted")
except ValueError:
    pass
try:
    source_semantics("poke 12 1 # publication LAST\nj Late\nLate:\npoke 10 2\nyield\n", {})
    fails.append("commit-last annotation escaped validation through a jump target")
except ValueError:
    pass
try:
    rejoined_checks_source = (
        "get r0 d0 8\nbne r0 31415999 BadMagic\nj Abi\nBadMagic:\nj Abi\nAbi:\n"
        "get r1 d0 9\nbne r1 1 BadAbi\nj Done\nBadAbi:\nj Done\nDone:\nyield\n"
    )
    rejoined_checks_rows = parse_rows(rejoined_checks_source)
    rejoined_checks_ports, rejoined_checks_aliases = collect_aliases(rejoined_checks_rows)
    verify_declared_consumers(
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
    skipped_network_rows = parse_rows(skipped_network_checks_source)
    _, skipped_network_aliases = collect_aliases(skipped_network_rows)
    network_dependencies(
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
consumer_rows = parse_rows(consumer_source)
consumer_ports, consumer_aliases = collect_aliases(consumer_rows)
ck(verify_declared_consumers(consumer_source, consumer_rows, consumer_ports, consumer_aliases, []) == [],
   "undeclared payload equality checks were inferred as a consumed protocol")
try:
    verify_declared_consumers(consumer_source, consumer_rows, consumer_ports, consumer_aliases, [{
        "port": "d0", "accepted": [{"header_base": 8, "magic": game_hash("TransformCandidateReadiness.v1"), "abi": 1}]
    }])
    fails.append("incorrect authoritative consumed protocol was accepted")
except ValueError:
    pass
try:
    skipped_checks_source = (
        "get r0 d0 8\nj Abi\nbne r0 31415999 Bad\nAbi:\nget r1 d0 9\n"
        "j Done\nbne r1 1 Bad\nDone:\nyield\nBad:\nyield\n"
    )
    skipped_checks_rows = parse_rows(skipped_checks_source)
    skipped_checks_ports, skipped_checks_aliases = collect_aliases(skipped_checks_rows)
    verify_declared_consumers(
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
fake_fence_rows = parse_rows(fake_fence_source)
fake_fence_ports, fake_fence_aliases = collect_aliases(fake_fence_rows)
ck(not verified_seqlock_consumer(
    fake_fence_source, fake_fence_rows, fake_fence_ports, fake_fence_aliases, "d0", 2
),
   "a seqlock consumer that overwrites its first snapshot and self-compares was accepted")

noop_retry_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Accept\nget r2 d0 2\n"
    "bne r2 r0 Accept\nAccept:\nget r3 d0 5\n"
)
noop_retry_rows = parse_rows(noop_retry_source)
noop_retry_ports, noop_retry_aliases = collect_aliases(noop_retry_rows)
ck(not verified_seqlock_consumer(
    noop_retry_source, noop_retry_rows, noop_retry_ports, noop_retry_aliases, "d0", 2
), "a seqlock consumer whose retry target equals its success continuation was accepted")

unreachable_reread_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Retry\nj Done\nSecond:\n"
    "get r2 d0 2\nbne r2 r0 Retry\nDone:\nyield\nRetry:\nyield\n"
)
unreachable_reread_rows = parse_rows(unreachable_reread_source)
unreachable_reread_ports, unreachable_reread_aliases = collect_aliases(unreachable_reread_rows)
ck(not verified_seqlock_consumer(
    unreachable_reread_source, unreachable_reread_rows,
    unreachable_reread_ports, unreachable_reread_aliases, "d0", 2
), "a seqlock consumer with an unreachable second read was accepted")

rejoined_retry_source = (
    "get r0 d0 2\nand r1 r0 1\nbnez r1 Retry\nEven:\nget r2 d0 2\n"
    "bne r2 r0 Retry\nj Done\nRetry:\nj Even\nDone:\nyield\n"
)
rejoined_retry_rows = parse_rows(rejoined_retry_source)
rejoined_retry_ports, rejoined_retry_aliases = collect_aliases(rejoined_retry_rows)
ck(not verified_seqlock_consumer(
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
    validated_ranges([[8, 7]])
    fails.append("inverted stack range was accepted")
except ValueError:
    pass
try:
    validated_ranges([[0, 10], [5, 15]])
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
