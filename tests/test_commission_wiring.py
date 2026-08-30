#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from pathlib import Path
from tempfile import TemporaryDirectory
import json

import framework.commissioning as commissioning
from framework.commissioning import apply_evidence, build_plan, load_wiring, overall_status
import tools.commission_wiring as cli
import tools.live_commission as live

R = _PROJECT_ROOT
fails = []


def caps(read=(), write=(), slot_read=(), slot_write=(), bindings=None):
    return {
        "properties_readable": list(read),
        "properties_writable": list(write),
        "slot_properties_readable": list(slot_read),
        "slot_properties_writable": list(slot_write),
        "property_bindings": [
            {"operand": operand, "property": property_name}
            for operand, property_name in sorted((bindings or {}).items())
        ],
    }


def script(provider, reference, capabilities=None):
    return {"kind": "script", "provider": provider, "reference": reference, "capabilities": capabilities or caps()}


def device(device_type, reference, capabilities):
    return {"kind": "physical-device", "device_type": device_type, "reference": reference, "capabilities": capabilities}


def wiring(consumer, ports, label="test"):
    return {
        "$schema": "https://github.com/DarcStar-Games/stationeers-ic10/schemas/commissioning_wiring.schema.json",
        "format": "IC10_COMMISSIONING_WIRING_V1",
        "consumer": consumer,
        "label": label,
        "ports": ports,
    }


# Literal-header dependency: PI Runtime consumes the generic persistent Config Host.
pi = wiring("ic10.script.controller.pi.runtime", {
    "d0": device("Pressure Sensor", "process input", caps(read=["Pressure"], bindings={"r12": "Pressure"})),
    "d1": device("Volume Pump", "process output", caps(write=["Setting"], bindings={"r13": "Setting"})),
    "d2": script(
        "ic10.script.generic.persistent.config.host", "config host housing",
        caps(read=["ReferenceId"]),
    ),
})
pi_plan = build_plan(pi, R)
if overall_status(pi_plan) != "UNRESOLVED":
    fails.append(f"compatible literal-header wiring should await field evidence: {overall_status(pi_plan)}")
if any(item["status"] == "FAIL" for item in pi_plan["results"]):
    fails.append("compatible literal-header wiring has a static failure")
header = next(item for item in pi_plan["observations"] if item["id"] == "d2.provider-observed")
if header.get("cells") != [{"address": 0, "expected": 31415928}, {"address": 1, "expected": 1}]:
    fails.append(f"literal provider header instructions were not contract-derived: {header.get('cells')}")
if header.get("capabilities", {}).get("reads") != ["ReferenceId"]:
    fails.append("script-provider housing capabilities were omitted from runtime instructions")
for port_name, direction, expected in (("d0", "reads", "Pressure"), ("d1", "writes", "Setting")):
    observation = next(item for item in pi_plan["observations"] if item["id"] == f"{port_name}.device-observed")
    properties = observation.get("capabilities", {}).get(direction, [])
    if properties != [expected] or any(value.startswith("r") for value in properties):
        fails.append(f"{port_name} dynamic LogicType was not resolved to {expected}")
if next(item for item in pi_plan["observations"] if item["id"] == "d1.device-observed")["capabilities"]["reads"]:
    fails.append("bdnvs incorrectly produced a readable-property requirement")
for obligation_id, address, expected in (
    ("binding.d2.s107.r12", 107, "Pressure"),
    ("binding.d2.s108.r13", 108, "Setting"),
):
    observation = next((item for item in pi_plan["observations"] if item["id"] == obligation_id), None)
    if not observation or observation["tool"] != "snapshot-probe":
        fails.append(f"{obligation_id} did not produce a fenced runtime observation")
    elif observation.get("cells") != [{"address": address, "expected": expected}]:
        fails.append(f"{obligation_id} did not preserve its concrete LogicType expectation")
    elif [item["address"] for item in observation.get("fences", [])] != [5]:
        fails.append(f"{obligation_id} did not use the Config Host generation fence")

unbound_pi = json.loads(json.dumps(pi))
unbound_pi["ports"]["d0"]["capabilities"]["property_bindings"] = []
unbound_plan = build_plan(unbound_pi, R)
if not any(item["id"] == "d0.property-bindings" and item["status"] == "FAIL" for item in unbound_plan["results"]):
    fails.append("unbound dynamic LogicType operand did not fail closed")

conflicting_bindings = wiring("ic10.script.gas.mixer.utility.controller", {
    "d0": device(
        "Pipe Analyzer", "input one",
        caps(read=["Temperature", "RatioOxygen"], bindings={"r2": "RatioOxygen"}),
    ),
    "d2": device(
        "Pipe Analyzer", "mixture output",
        caps(
            read=["Pressure", "TotalMoles", "RatioNitrogen", "RatioVolatiles"],
            bindings={"r2": "RatioNitrogen", "r4": "RatioVolatiles"},
        ),
    ),
})
conflicting_plan = build_plan(conflicting_bindings, R)
if not any(
    item["id"] == "binding.d4.s13.r2" and item["status"] == "FAIL"
    for item in conflicting_plan["results"]
):
    fails.append("conflicting bindings for one runtime LogicType source did not fail closed")

shared_cell_contracts = commissioning.load_contracts(R)
shared_cell_pi = next(
    item for item in shared_cell_contracts
    if item["identity"]["service_id"] == "ic10.script.controller.pi.runtime"
)
next(item for item in shared_cell_pi["device_ports"] if item["port"] == "d1")[
    "dynamic_property_sources"
][0]["address"] = 107
original_load_contracts = commissioning.load_contracts
commissioning.load_contracts = lambda _root: shared_cell_contracts
try:
    shared_cell_plan = build_plan(pi, R)
finally:
    commissioning.load_contracts = original_load_contracts
if not any(
    item["id"] == "binding.d2.s107" and item["status"] == "FAIL"
    for item in shared_cell_plan["results"]
):
    fails.append("incompatible LogicTypes sharing one runtime source cell did not fail closed")

swapped = json.loads(json.dumps(pi))
swapped["ports"]["d2"]["provider"] = "ic10.script.generic.config.editor"
swapped_plan = build_plan(swapped, R)
if overall_status(swapped_plan) != "FAIL" or not any(item["id"] == "d2.protocol" and item["status"] == "FAIL" for item in swapped_plan["results"]):
    fails.append("incompatible literal-header provider did not fail at the port/protocol obligation")

# Access-only interfaces: Transform Driver d0/d1 have no identifying header contract.
transform = wiring("ic10/manufacturing/transform_job_driver_v2_0.ic10", {
    "d0": script("ic10.script.manufacturing.candidate.selector", "candidate selector"),
    "d1": script("ic10.script.transform.candidate.executor", "candidate executor"),
    "d2": device("IC Housing", "transform directory", caps(read=["ReferenceId"])),
})
transform_plan = build_plan(transform, R)
if overall_status(transform_plan) != "UNRESOLVED" or any(item["status"] == "FAIL" for item in transform_plan["results"]):
    fails.append("compatible access-only wiring did not pass static checks and await observation")
if not any(item["tool"] == "manual-wiring-check" for item in transform_plan["observations"]):
    fails.append("access-only wiring was presented as automatically identifiable")

transform_swapped = json.loads(json.dumps(transform))
transform_swapped["ports"]["d0"]["provider"], transform_swapped["ports"]["d1"]["provider"] = (
    transform_swapped["ports"]["d1"]["provider"], transform_swapped["ports"]["d0"]["provider"],
)
swapped_access_plan = build_plan(transform_swapped, R)
if overall_status(swapped_access_plan) != "FAIL" or not any(
    item["status"] == "FAIL" and item["id"].startswith(("d0.stack-", "d1.stack-"))
    for item in swapped_access_plan["results"]
):
    fails.append("swapped access-only providers did not fail with a range/direction diagnostic")

# Provider cells annotated external-read/write are part of the canonical access surface.
grant_guard = wiring("ic10.script.pressure.transfer.grant.guard", {
    "d0": script(
        "ic10.script.controller.pressure.transfer.runtime", "pressure transfer runtime",
        caps(read=["ReferenceId"]),
    ),
    "d1": script(
        "ic10.script.pressure.grid.reservation.planner", "reservation planner",
        caps(read=["ReferenceId"]),
    ),
})
grant_plan = build_plan(grant_guard, R)
if any(item["status"] == "FAIL" for item in grant_plan["results"]):
    fails.append("external-read/write field annotations were omitted from provider compatibility")
if not any(item["id"] == "d0.stack-read" and item["status"] == "PASS" for item in grant_plan["results"]):
    fails.append("Pressure Transfer staged grant fields were not accepted as externally readable")

# Repeated equality checks for one address need separate value-bound evidence obligations.
larre = wiring("ic10.script.larre.storage.reserved.move.client", {
    "d0": script("ic10.script.larre.item.storage.endpoint", "LArRE endpoint", caps(read=["ReferenceId"])),
    "d1": script("ic10.script.resource.reservation", "storage reservation"),
    "d2": script("ic10.script.resource.reservation", "external reservation"),
})
larre_plan = build_plan(larre, R)
if any(item["status"] == "FAIL" for item in larre_plan["results"]):
    fails.append("documented LArRE endpoint wiring has a static failure")
for port_name in ("d1", "d2"):
    prefix = f"{port_name}.constraint.s16.value."
    matching_results = [item for item in larre_plan["results"] if item["id"].startswith(prefix)]
    matching_observations = [item for item in larre_plan["observations"] if item["id"].startswith(prefix)]
    if len(matching_results) != 2 or len(matching_observations) != 2:
        fails.append(f"{prefix} did not produce two distinct evidence obligations")
    elif len({item["id"] for item in matching_results}) != 2:
        fails.append(f"{prefix} produced colliding evidence IDs")
    elif {item["cells"][0]["expected"] for item in matching_observations} != {1, 2}:
        fails.append(f"{prefix} did not preserve both required values")

# Contract publication rules select the Snapshot Probe and its exact fence cell.
link_adapter = wiring("ic10.script.pressure.resource.link.adapter", {
    "d0": script(
        "ic10.script.controller.pressure.transfer.runtime", "pressure transfer runtime",
        caps(read=["ReferenceId"]),
    ),
    "d1": script("ic10.script.resource.reservation", "source reservation", caps(read=["ReferenceId"])),
    "d2": script("ic10.script.resource.reservation", "sink reservation", caps(read=["ReferenceId"])),
})
link_plan = build_plan(link_adapter, R)
fenced = next((item for item in link_plan["observations"] if item["id"] == "d1.constraint.s33"), None)
if not fenced or fenced["tool"] != "snapshot-probe":
    fails.append("fenced runtime constraint did not select the Snapshot Probe")
elif fenced.get("fences") != [{
    "kind": "commit-last", "address": 12,
    "description": "semantic mirror generation LAST", "source": "verified-inline-order",
}]:
    fails.append(f"fenced runtime constraint omitted the contract fence: {fenced.get('fences')}")

# Physical-device ports require explicit readable/writable LogicType declarations.
editor = wiring("ic10.script.generic.config.editor", {
    name: device("Logic Memory", f"button {name}", caps(read=["Setting"]))
    for name in ("d0", "d1", "d2")
})
editor_plan = build_plan(editor, R)
if overall_status(editor_plan) != "UNRESOLVED" or any(item["status"] == "FAIL" for item in editor_plan["results"]):
    fails.append("compatible physical-device declarations did not await actual observation")
if any(item.get("capabilities", {}).get("reads") != ["Setting"] for item in editor_plan["observations"]):
    fails.append("physical-device observations omitted contract-derived LogicType requirements")
bad_device = json.loads(json.dumps(editor))
bad_device["ports"]["d1"]["capabilities"]["properties_readable"] = []
bad_device_plan = build_plan(bad_device, R)
if not any(item["id"] == "d1.properties-read" and item["status"] == "FAIL" for item in bad_device_plan["results"]):
    fails.append("unsupported physical-device property did not fail closed")

# Schema/CLI/session integration: evidence is append-only and bound to exact contract/interface IDs.
with TemporaryDirectory() as td:
    map_path = Path(td) / "pi.json"
    session_path = Path(td) / "session.json"
    map_path.write_text(json.dumps(pi))
    try:
        loaded = load_wiring(map_path, R)
    except ValueError as error:
        fails.append(f"valid wiring map failed schema validation: {error}")
        loaded = pi
    live.write_session(session_path, live.new_session())
    runtime_ids = [item["id"] for item in build_plan(loaded, R)["results"] if item["category"] == "runtime"]
    for obligation in runtime_ids:
        rc = cli.main([
            "record", "--map", str(map_path), "--session", str(session_path),
            "--obligation", obligation, "--status", "PASS", "--observed", "matched in game",
        ])
        if rc:
            fails.append(f"record CLI rejected runtime obligation {obligation}")
    session = live.read_session(session_path)
    evidenced = apply_evidence(build_plan(loaded, R), session)
    if overall_status(evidenced) != "PASS":
        fails.append(f"recorded compatible wiring did not close: {overall_status(evidenced)}")
    plan_id = evidenced["binding"]["plan_id"]
    session["wiring_results"][plan_id]["binding"]["target_ids"]["d2"] = "changed"
    if overall_status(apply_evidence(build_plan(loaded, R), session)) != "FAIL":
        fails.append("mismatched contract/interface evidence binding was accepted")
    session = live.read_session(session_path)
    first_id = runtime_ids[0]
    session["wiring_results"][plan_id]["runs"][first_id][-1]["status"] = "UNKNOWN"
    if overall_status(apply_evidence(build_plan(loaded, R), session)) != "FAIL":
        fails.append("invalid recorded evidence status was accepted")

if fails:
    print("Contract commissioning tests: FAIL")
    for failure in fails:
        print(" -", failure)
    raise SystemExit(1)
print("Contract commissioning tests: PASS")
print(" - literal-header, access-only, and physical-device wiring covered end to end")
print(" - external fields, repeated constraints, fencing, and physical capabilities are contract-derived")
print(" - dynamic LogicTypes are source-observed; swapped providers and unsupported properties fail closed")
print(" - runtime evidence is framework-, contract-, interface-, and wiring-bound")
