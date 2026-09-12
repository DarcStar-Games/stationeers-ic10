#!/usr/bin/env python3
"""Exercise the canonical device-port wiring checks against synthetic maps."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import json

from framework.json_schema import SchemaValidationError, validate
from framework.script_contracts import compatibility_errors
from framework.script_wiring import (
    check_wiring, cited_cells, inbound_edges, port_index, stack_surfaces,
)

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
# Wide enough that the structural cases below turn on what they mean to test; the
# surface rule itself is exercised against NARROW.
SURFACES = {
    PROVIDER: {"published": frozenset(range(16)), "accepted": frozenset(range(16))},
    CONSUMER: {"published": frozenset(), "accepted": frozenset()},
}
NARROW = {
    PROVIDER: {"published": frozenset({0, 1, 9}), "accepted": frozenset({10})},
    CONSUMER: {"published": frozenset(), "accepted": frozenset()},
}
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


def failing(wiring=None, ports=None, publishers=None, migrated=frozenset(), surfaces=None):
    return check_wiring(wiring or WIRING, ports or PORTS, publishers or PUBLISHERS,
                        set(migrated), surfaces or SURFACES)


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

named = {PROVIDER: [{"base": 0, "magic": 31410001, "abi": 2, "contract": "TestProvider"}],
         CONSUMER: []}
expect("a note that does not name the pinned identity fails",
       any("never says so" in f for f in failing(publishers=named)))
told = deepcopy(WIRING)
told["ports"][CONSUMER]["d0"]["note"] = 'peer named by d0 S0 magic check (TestProvider.v2)'
expect("naming the identity in the note passes", failing(told, publishers=named) == [])
expect("a numeric block header exempts the note", failing() == [])

# A note's cells are held to the port: every `S<n>` it names, alone or in a range,
# must be a cell the port reads or writes, literally or through a declared range.
expect("cited cells are read as S<n> and as ranges, with S0 left out",
       cited_cells("S3, S5..S7, S9-S10, S12..14, S0 magic, line 40, -2 status")
       == {3, 5, 6, 7, 9, 10, 12, 13, 14})
cited = deepcopy(WIRING)
cited["ports"][CONSUMER]["d0"]["note"] = "writes S10 token; reads S9 status and S1 ABI"
expect("a note naming only cells the port touches passes", failing(cited) == [])
cited["ports"][CONSUMER]["d0"]["note"] = "writes S10 token; reads S8 status"
expect("a note naming a cell the port never touches fails",
       any("cites S[8]" in f for f in failing(cited)))
cited["ports"][CONSUMER]["d0"]["note"] = "mailbox S9..S10"
expect("a cited range inside the port's cells passes", failing(cited) == [])
cited["ports"][CONSUMER]["d0"]["note"] = "mailbox S8-S11"
expect("a cited range reaching past the port's cells reports the cells outside it",
       any("cites S[8, 11]" in f for f in failing(cited)))
cited["ports"][CONSUMER]["d0"]["note"] = "peer named by S0 magic check; reads 9, writes 10"
identity_only = deepcopy(PORTS)
identity_only[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], reads={9})
expect("S0 and bare numbers are not citations", failing(cited, ports=identity_only) == [])
walked = deepcopy(PORTS)
walked[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], read_ranges=[(11, 13)])
cited["ports"][CONSUMER]["d0"]["note"] = "walks the record at S11..S13 by register"
expect("a declared dynamic range covers the cells a note cites in it",
       failing(cited, ports=walked) == [])
cited["ports"][CONSUMER]["d0"]["note"] = "walks the record at S11..S14 by register"
expect("a cited range one cell past the declared range fails",
       any("cites S[14]" in f for f in failing(cited, ports=walked)))
physical_note = deepcopy(WIRING)
physical_note["ports"][CONSUMER]["d1"]["note"] = "Pressure, Temperature; no S5 here"
expect("a physical-device note is not held to stack cells", failing(physical_note) == [])

wrong_magic = deepcopy(PORTS)
wrong_magic[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={0: 31419999})
expect("magic the provider never publishes fails",
       any("does not publish" in f for f in failing(ports=wrong_magic)))

# The ABI is folded into the S0 identity, so a wrong ABI is a wrong magic and is
# caught by the case above. A port carrying a separate S1 constraint no longer exists:
# validate_service_identity.py rejects the source construct that would produce one, so
# the wiring layer simply ignores it rather than treating it as a second identity gate.
stray_abi = deepcopy(PORTS)
stray_abi[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={0: 31410001, 1: 3})
expect("a stray S1 constraint neither gates nor breaks the edge", failing(ports=stray_abi) == [])

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
abi_only[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], constraints={1: 3})
expect("an S1-only constraint identifies nothing, so the edge stays unconstrained here",
       failing(ports=abi_only) == [])

surface = stack_surfaces({"any-key": {"source": PROVIDER, "own_stack": {
    "literal_reads": [32], "literal_writes": [0, 1],
    "dynamic_read_ranges": [{"start": 40, "end": 41}],
    "dynamic_write_ranges": [{"start": 16, "end": 18}],
    "external_readable_ranges": [{"start": 60, "end": 60}],
    "external_writable_ranges": [{"start": 70, "end": 70}],
    "fields": [{"address": 80, "access": ["external-read"]},
               {"address": 81, "access": ["external-write"]}],
}}})[PROVIDER]
expect("a peer may read what the owner writes or declares readable",
       sorted(surface["published"]) == [0, 1, 16, 17, 18, 60, 80])
expect("a peer may write what the owner reads or declares writable",
       sorted(surface["accepted"]) == [32, 40, 41, 70, 81])

expect("a port touching only what the provider offers passes",
       failing(surfaces=NARROW) == [])

unpublished = deepcopy(PORTS)
unpublished[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], reads={0, 1, 9, 11})
expect("reading a cell the provider never writes fails",
       any("nor declares them externally readable" in f
           for f in failing(ports=unpublished, surfaces=NARROW)))

unaccepted = deepcopy(PORTS)
unaccepted[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], writes={10, 12})
expect("writing a cell the provider never reads fails",
       any("nor declares them externally writable" in f
           for f in failing(ports=unaccepted, surfaces=NARROW)))

ranged_surface = deepcopy(PORTS)
ranged_surface[CONSUMER]["d0"] = dict(PORTS[CONSUMER]["d0"], read_ranges=[(9, 11)])
expect("a dynamic range reaching past the provider's surface fails",
       any("nor declares them externally readable" in f
           for f in failing(ports=ranged_surface, surfaces=NARROW)))

declared = {PROVIDER: {"published": NARROW[PROVIDER]["published"] | {11},
                       "accepted": NARROW[PROVIDER]["accepted"]},
            CONSUMER: NARROW[CONSUMER]}
expect("a reviewed readable declaration covers a cell the provider never writes",
       failing(ports=unpublished, surfaces=declared) == [])

RIVAL = "ic10/test-family/rival_v1_0.ic10"
any_of_ports = deepcopy(PORTS)
any_of_ports[RIVAL] = {}
any_of_wiring = deepcopy(WIRING)
any_of_wiring["ports"][RIVAL] = {}
any_of_wiring["ports"][CONSUMER]["d0"]["providers"] = [RIVAL, PROVIDER]
any_of_publishers = dict(PUBLISHERS, **{RIVAL: [{"base": 0, "magic": 31410001, "abi": 2}]})
any_of_surfaces = dict(NARROW, **{RIVAL: {"published": frozenset(), "accepted": frozenset()}})
expect("any-of providers pass on the one that offers the cells",
       failing(any_of_wiring, ports=any_of_ports, publishers=any_of_publishers,
               surfaces=any_of_surfaces) == [])
any_of_surfaces[PROVIDER] = {"published": frozenset(), "accepted": frozenset()}
expect("a port matching no declared provider reports each of them",
       sum("nor declares them" in f
           for f in failing(any_of_wiring, ports=any_of_ports, publishers=any_of_publishers,
                            surfaces=any_of_surfaces)) == 4)

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


# The declared-consumer-edge check and the wiring check compare against one
# surface (#155): a consumer writing into its provider's read window, or reading
# its write window, with no envelope declared, gets the same verdict from both.
def contract(source, own_stack, ports=(), consumes=(), provides=()):
    return {"source": source, "own_stack": own_stack, "device_ports": list(ports),
            "network_dependencies": [],
            "contracts": {"provides": list(provides), "consumes": list(consumes)},
            "behavior": {"publication_rules": []}}


WINDOWED = contract(PROVIDER, {
    "literal_reads": [], "literal_writes": [0, 1],
    "dynamic_read_ranges": [{"start": 40, "end": 41}],
    "dynamic_write_ranges": [{"start": 16, "end": 18}],
    "external_readable_ranges": [], "external_writable_ranges": [], "fields": [],
}, provides=[{"protocol_id": "ic10.stack.31410001.abi2", "base": 0}])
EDGE = {"format": "IC10_SCRIPT_WIRING_V1", "ports": {
    PROVIDER: {}, CONSUMER: {"d0": {"kind": "script", "providers": [PROVIDER], "note": "test edge"}},
}}


def verdicts(read, write):
    consumer = contract(CONSUMER, WINDOWED["own_stack"], ports=[{
        "port": "d0", "target": {"kind": "stack-protocol"},
        "stack": {"literal_reads": [0, 1, read], "literal_writes": [write],
                  "dynamic_read": False, "dynamic_write": False,
                  "dynamic_read_ranges": [], "dynamic_write_ranges": [],
                  "constraints": [{"address": 0, "equals": 31410001}, {"address": 1, "equals": 2}]},
    }], consumes=[{"port": "d0", "accepted": [
        {"protocol_id": "ic10.stack.31410001.abi2", "header_base": 0, "publication_requirements": []}]}])
    documents = {PROVIDER: WINDOWED, CONSUMER: consumer}
    declared = compatibility_errors(list(documents.values()))
    wired = check_wiring(EDGE, port_index(documents), PUBLISHERS, set(), stack_surfaces(documents))
    return bool(declared), bool(wired)


expect("a write into the read window and a read of the write window pass both checks",
       verdicts(read=16, write=40) == (False, False))
expect("a write one cell past the read window fails both checks", verdicts(read=16, write=42) == (True, True))
expect("a read one cell past the write window fails both checks", verdicts(read=19, write=40) == (True, True))

if failures:
    raise SystemExit(1)
print("Script wiring model: PASS")
print(" - schema, coverage, provider existence, kind agreement, S0 identity consistency,")
print("   migrated-header guard, reviewed header reads, and inbound-edge listing verified")
print(" - a port's cells are compared against every declared provider's published/accepted")
print("   surface, any-of across providers, with reviewed envelopes as the escape hatch")
print(" - the declared-consumer-edge check gives a windowed access the same verdict")
print(" - a note must name the contract identity its port pins, so the reviewed evidence")
print("   cannot keep citing cell shape for an edge the source names outright")
print(" - every cell a note names is one its port reads or writes, literally or through")
print("   a declared range, so the prose cannot keep a numbering the source has left")
