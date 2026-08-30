#!/usr/bin/env python3
"""Exercise the canonical device-port wiring checks against synthetic maps."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import json

from framework.json_schema import SchemaValidationError, validate
from framework.script_wiring import check_wiring, inbound_edges

ROOT = _PROJECT_ROOT
SCHEMA = json.loads((ROOT / "schemas/script_wiring.schema.json").read_text())

PROVIDER = "ic10/test-family/provider_v1_0.ic10"
CONSUMER = "ic10/test-family/consumer_v1_0.ic10"
PORTS = {
    PROVIDER: {},
    CONSUMER: {
        "d0": {"kind": "stack-protocol", "reads": {0, 1, 9}, "writes": {10},
               "read_ranges": [], "write_ranges": [], "constraints": {0: 31410001, 1: 2}},
        "d1": {"kind": "physical-device", "reads": set(), "writes": set(),
               "read_ranges": [], "write_ranges": [], "constraints": {}},
    },
}
PUBLISHERS = {PROVIDER: [{"base": 0, "magic": 31410001, "abi": 2}], CONSUMER: []}
WIRING = {
    "$schema": "../schemas/script_wiring.schema.json",
    "format": "IC10_SCRIPT_WIRING_V1",
    "ports": {
        PROVIDER: {},
        CONSUMER: {
            "d0": {"kind": "script", "providers": [PROVIDER], "note": "test edge"},
            "d1": {"kind": "physical-device", "role": "Sensor"},
        },
    },
}

failures = 0


def expect(label, condition):
    global failures
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def failing(wiring=None, ports=None, publishers=None, migrated=frozenset()):
    return check_wiring(wiring or WIRING, ports or PORTS, publishers or PUBLISHERS, set(migrated))


validate(WIRING, SCHEMA)
expect("clean map has no failures", failing() == [])

bad_schema = deepcopy(WIRING)
bad_schema["ports"][CONSUMER]["d1"] = {"kind": "script", "providers": [PROVIDER]}
try:
    validate(bad_schema, SCHEMA)
    expect("script peer without a note is rejected by the schema", False)
except SchemaValidationError:
    pass

missing = deepcopy(WIRING)
del missing["ports"][CONSUMER]["d0"]
expect("uncovered port fails", any("no declared peer" in f for f in failing(missing)))

extra = deepcopy(WIRING)
extra["ports"][PROVIDER]["d3"] = {"kind": "physical-device", "role": "Sensor"}
expect("peer for an unused port fails", any("does not use" in f for f in failing(extra)))

orphan = dict(WIRING, ports={CONSUMER: WIRING["ports"][CONSUMER]})
expect("program without an entry fails", any("no wiring entry" in f for f in failing(orphan)))

unknown = deepcopy(WIRING)
unknown["ports"][CONSUMER]["d0"]["providers"] = ["ic10/test-family/ghost_v1_0.ic10"]
expect("unknown provider fails", any("not a deployable program" in f for f in failing(unknown)))

mismatched = deepcopy(WIRING)
mismatched["ports"][CONSUMER]["d1"] = {"kind": "script", "providers": [PROVIDER], "note": "wrong"}
expect("script peer on a physical-device port fails",
       any("wiring declares" in f for f in failing(mismatched)))

native_ports = deepcopy(PORTS)
native_ports[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={})
native_stack = deepcopy(WIRING)
native_stack["ports"][CONSUMER]["d0"] = {"kind": "physical-device", "role": "Sorter",
                                         "note": "device native stack"}
expect("noted device with a native stack on a stack port passes",
       failing(native_stack, ports=native_ports) == [])
del native_stack["ports"][CONSUMER]["d0"]["note"]
expect("unnoted physical peer on a stack-shaped port fails",
       any("needs a note" in f for f in failing(native_stack, ports=native_ports)))
native_stack["ports"][CONSUMER]["d0"]["note"] = "claimed device"
expect("physical peer on a magic-checking port fails",
       any("registered script header" in f for f in failing(native_stack)))

crowd = deepcopy(PUBLISHERS)
crowd["ic10/test-family/rival_v1_0.ic10"] = [{"base": 0, "magic": 31410001, "abi": 2}]
crowd_ports = deepcopy(PORTS)
crowd_ports["ic10/test-family/rival_v1_0.ic10"] = {}
crowd_wiring = deepcopy(WIRING)
crowd_wiring["ports"]["ic10/test-family/rival_v1_0.ic10"] = {}
expect("magic publisher omitted from the providers list fails",
       any("omits publisher" in f
           for f in failing(crowd_wiring, ports=crowd_ports, publishers=crowd)))

wrong_magic = deepcopy(PORTS)
wrong_magic[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={0: 31419999})
expect("magic the provider never publishes fails",
       any("does not publish" in f for f in failing(ports=wrong_magic)))

wrong_abi = deepcopy(PORTS)
wrong_abi[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={0: 31410001, 1: 3})
expect("ABI mismatch fails", any("does not publish" in f for f in failing(ports=wrong_abi)))

header_read = deepcopy(PORTS)
header_read[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], reads={0, 1, 3, 9})
expect("payload read of a migrated peer's header fails",
       any("header cells now" in f for f in failing(ports=header_read, migrated={PROVIDER})))
expect("unmigrated peer allows the same read", failing(ports=header_read) == [])

reviewed = deepcopy(WIRING)
reviewed["ports"][CONSUMER]["d0"]["header_reads"] = {"3": "SchemaId"}
validate(reviewed, SCHEMA)
expect("declared header read passes",
       failing(reviewed, ports=header_read, migrated={PROVIDER}) == [])

stale = deepcopy(reviewed)
stale["ports"][CONSUMER]["d0"]["header_reads"] = {"3": "SchemaId", "6": "TelemetryBase"}
expect("header_reads beyond what the port reads fails",
       any("never reads" in f for f in failing(stale, ports=header_read, migrated={PROVIDER})))

nonheader = deepcopy(WIRING)
nonheader["ports"][CONSUMER]["d0"]["header_reads"] = {"9": "Payload"}
expect("header_reads outside S2..S7 fails",
       any("are not header" in f for f in failing(nonheader)))

header_write = deepcopy(PORTS)
header_write[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], writes={5})
expect("write into a migrated peer's header always fails",
       any("only the owner" in f for f in failing(ports=header_write, migrated={PROVIDER})))
expect("reviewed reads never excuse a header write",
       any("only the owner" in f
           for f in failing(reviewed, ports=header_write, migrated={PROVIDER})))

envelope_write = deepcopy(PORTS)
envelope_write[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], writes={1})
expect("write to a migrated peer's S0/S1 identity cells fails",
       any("only the owner" in f for f in failing(ports=envelope_write, migrated={PROVIDER})))

ranged_write = deepcopy(PORTS)
ranged_write[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], write_ranges=[(3, 12)])
expect("dynamic write range over a migrated peer's envelope fails",
       any("only the owner" in f for f in failing(ports=ranged_write, migrated={PROVIDER})))
expect("unmigrated peer allows the same range", failing(ports=ranged_write) == [])

ranged_read = deepcopy(PORTS)
ranged_read[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], read_ranges=[(3, 3)])
expect("dynamic read range over a migrated peer's header fails",
       any("header cells now" in f for f in failing(ports=ranged_read, migrated={PROVIDER})))
expect("declared header read excuses the ranged read",
       failing(reviewed, ports=ranged_read, migrated={PROVIDER}) == [])

abi_only = deepcopy(PORTS)
abi_only[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={1: 2})
expect("ABI-only constraint matching the provider passes", failing(ports=abi_only) == [])
abi_only[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={1: 3})
expect("ABI-only constraint the provider never publishes fails",
       any("publishes no" in f for f in failing(ports=abi_only)))

malformed = deepcopy(WIRING)
malformed["ports"][CONSUMER]["d0"]["header_reads"] = {"S3": "SchemaId"}
expect("check flags a non-numeric header_reads key",
       any("are not header" in f for f in failing(malformed)))
edges = inbound_edges(malformed, PORTS, {PROVIDER})
expect("inbound edges skip malformed header_reads keys instead of crashing",
       edges and edges[0]["header_reads"] == {})

edges = inbound_edges(WIRING, PORTS, {PROVIDER})
expect("inbound edges name the consumer, port, cells, and ranges",
       edges == [{"consumer": CONSUMER, "port": "d0", "targets": [PROVIDER],
                  "reads": [0, 1, 9], "writes": [10],
                  "read_ranges": [], "write_ranges": [], "header_reads": {}}])
expect("no edges into an unreferenced family", inbound_edges(WIRING, PORTS, {CONSUMER}) == [])

if failures:
    raise SystemExit(1)
print("Script wiring model: PASS")
print(" - schema, coverage, provider existence, kind agreement, magic/ABI consistency,")
print("   migrated-header guard, reviewed header reads, and inbound-edge listing verified")
