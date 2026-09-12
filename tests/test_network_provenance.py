#!/usr/bin/env python3
"""Exercise the network write provenance walk behind validate_network_provenance.py (issue #174).

The walk reports, at every `putd`, where the reference register's value came
from on each path from the entry. The cases here pin what it must see: an
identity check establishing a reference and a `move` carrying it, a reload or
a failed check taking it back, a check through `rrN` against a magic held in a
register, a reference loaded off an identified port or a checked peer's cell,
and the untracked register nothing on the path loaded. Then the attribution
over a small tree, the declarations that cover what no check does, and the
tree itself: the Loader Router writing through a copy of a checked Store, the
Printer Capacity Client reloading a bank reference from its own cell, and the
Readiness program's capacity block as it stood before this issue, reading the
output Reservation's constant `S2` as an Endpoint reference.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import sys
import tempfile
from pathlib import Path

from framework.ic10_source import game_hash
from framework.identity_coverage import declared_identities
from framework.network_provenance import (
    UNTRACKED,
    ReferenceOrigins,
    attribute_network_writes,
    attributed_network_writes,
    filled_by_errors,
    origin_matches,
    validate_provenance,
    writing,
)
from framework.script_contracts import build_all

ROOT = _PROJECT_ROOT
failures = []


def ck(condition, message):
    if not condition:
        failures.append(message)


MAGIC = game_hash("Peer.v1")
OTHER = game_hash("Other.v1")
KNOWN = {(0, MAGIC), (0, OTHER)}


def arrivals(source, identities=None, private=frozenset(), known=KNOWN):
    """Per source line, the origin sets the reference arrives holding at each `putd`."""
    origins = ReferenceOrigins(source, identities, frozenset(private), None, known)
    sites = origins.run()
    return {origins.paths.line_numbers[index]: sets for index, sets in sites.items()}


def tokens(source, **kwargs):
    """Every origin token seen at any `putd` in `source`."""
    return {token for sets in arrivals(source, **kwargs).values() for held in sets for token in held}


def without(source, line):
    ck(f"{line}\n" in source, f"witness line {line!r} is not in the source")
    return source.replace(f"{line}\n", "", 1)


# --- an identity check establishes the reference; the reject edge does not -----------
CHECKED = f"""get r1 db 10
getd r0 r1 0
bne r0 HASH("Peer.v1") Bad
putd r1 8 1
j Done
Bad:
putd r1 9 -1
Done:
yield
"""
found = arrivals(CHECKED)
ck(found[4] == {frozenset({"own:10", f"checked:0:{MAGIC}"})}, f"the write past the check must see the identity: {found[4]}")
ck(found[7] == {frozenset({"own:10"})}, f"the reject block must not see it: {found[7]}")

# a beq's taken edge is its equality edge
BEQ = CHECKED.replace('bne r0 HASH("Peer.v1") Bad\nputd r1 8 1\nj Done\nBad:\nputd r1 9 -1\n',
                      'beq r0 HASH("Peer.v1") Good\nputd r1 9 -1\nj Done\nGood:\nputd r1 8 1\n')
found = arrivals(BEQ)
ck(found[7] == {frozenset({"own:10", f"checked:0:{MAGIC}"})}, f"beq's taken edge is the equality: {found[7]}")
ck(found[4] == {frozenset({"own:10"})}, f"beq's fallthrough is the rejection: {found[4]}")

# --- a move carries the established identity; a reload or a rewrite drops it ----------
COPY = f"""get r2 db 10
getd r0 r2 0
bne r0 HASH("Peer.v1") Done
move ra r2
putd ra 27 1
get r2 db 11
putd r2 8 1
Done:
yield
"""
found = arrivals(COPY)
ck(f"checked:0:{MAGIC}" in next(iter(found[5])), f"a copy of a checked reference is checked: {found[5]}")
ck(found[7] == {frozenset({"own:11"})}, f"a reload forgets the check: {found[7]}")
ck(f"checked:0:{MAGIC}" not in tokens(COPY.replace("putd ra 27 1", "add ra ra 0\nputd ra 27 1")),
   "a rewrite of the copy must forget the check")

# --- a check that fails on a later tick takes the establishment back -------------------
RECHECK = f"""move r14 0
get r1 db 10
Loop:
yield
getd r0 r1 0
bne r0 HASH("Peer.v1") Lost
move r14 1
putd r1 8 r14
j Loop
Lost:
putd r1 9 -1
j Loop
"""
found = arrivals(RECHECK)
ck(all(f"checked:0:{MAGIC}" in held for held in found[8]), f"the write after the check is covered every tick: {found[8]}")
ck(all(f"checked:0:{MAGIC}" not in held for held in found[11]),
   f"a check that fails after an earlier good tick leaves the reject block unchecked: {found[11]}")

# --- a check through rrN against a magic held in a register ---------------------------
INDIRECT = f"""alias console r1
alias renderer r2
get console db 8
get renderer db 9
move r10 HASH("Peer.v1")
move r11 HASH("Other.v1")
move r7 1
Validate:
blez rr7 Bad
getd r0 rr7 0
add r8 r7 9
bne r0 rr8 Bad
add r7 r7 1
ble r7 2 Validate
putd console 10 1
putd renderer 8 2
j Done
Bad:
putd renderer 8 -1
Done:
yield
"""
found = arrivals(INDIRECT)
ck(found[15] == {frozenset({"own:8", f"checked:0:{MAGIC}"})}, f"the first indirect check establishes r1: {found[15]}")
ck(found[16] == {frozenset({"own:9", f"checked:0:{OTHER}"})}, f"the second indirect check establishes r2: {found[16]}")
ck(all("checked" not in token for held in found[19] for token in held), f"Bad is reached by a failed check: {found[19]}")

# --- only a magic some program publishes establishes anything -------------------------
PAYLOAD = """get r1 db 10
getd r0 r1 16
bne r0 3 Done
putd r1 8 1
Done:
yield
"""
ck(tokens(PAYLOAD) == {"own:10"}, f"a payload check against 3 at S16 is not an identity: {tokens(PAYLOAD)}")
ck("checked:16:3" in tokens(PAYLOAD, known=None), "with no provider table every literal compare counts")

# --- where a reference is loaded from ---------------------------------------------------
LOADS = """get r1 d0 40
putd r1 8 1
get r2 db 10
putd r2 8 1
move r3 12
get r4 db r3
putd r4 8 1
get r5 db r9
putd r5 8 1
getd r6 r1 21
putd r6 8 1
l r7 d1 ReferenceId
putd r7 8 1
l r8 db ReferenceId
getd r10 r8 5
putd r10 8 1
get r11 db:0 r12
putd r11 8 1
putd r13 8 1
"""
identities = {"d0": {(0, MAGIC)}}
found = arrivals(LOADS, identities)
ck(found[2] == {frozenset({f"cell:{MAGIC}:40"})}, f"a cell of an identified port names the peer: {found[2]}")
ck(found[4] == {frozenset({"own:10"})}, f"an own cell: {found[4]}")
ck(found[7] == {frozenset({"own:*"})} and found[9] == {frozenset({"own:*"})},
   f"a register address is a scan, whatever the walk knows of the register: {found[7]} {found[9]}")
ck(found[11] == {frozenset({"ref:r1:21"})}, f"a cell of an unchecked reference names the register: {found[11]}")
ck(found[13] == {frozenset({"device:d1"})}, f"an unidentified port's device: {found[13]}")
ck(found[16] == {frozenset({"own:5"})}, f"a cell read through the housing's own reference is an own cell: {found[16]}")
ck(found[18] == {frozenset({"index:0:*"})}, f"a device-index read: {found[18]}")
ck(found[19] == {frozenset({UNTRACKED})}, f"a register nothing loaded arrives holding nothing: {found[19]}")
unidentified = arrivals(LOADS)
ck(unidentified[2] == {frozenset({"port:d0:40"})}, f"a cell of an unidentified port names the port: {unidentified[2]}")
ck(arrivals(LOADS, identities)[13] == {frozenset({"device:d1"})} and
   arrivals(LOADS, {"d1": {(0, OTHER)}})[13] == {frozenset({f"checked:0:{OTHER}"})},
   "an identified port's own ReferenceId is that identity")
CHAINED = f"""get r1 db 10
getd r0 r1 0
bne r0 HASH("Peer.v1") Done
getd r2 r1 21
putd r2 8 1
Done:
yield
"""
ck(tokens(CHAINED) == {f"cell:{MAGIC}:21"}, f"a cell of a checked reference names the identity: {tokens(CHAINED)}")

# --- a state machine loads the reference in one tick and writes through it in the next --
STATE_CELL = """get r0 db 0
beq r0 HASH("Peer.v1") Init
poke 20 0
Init:
poke 0 HASH("Peer.v1")
Loop:
yield
get r0 db 20
beq r0 1 Ready
get r2 db 10
blez r2 Loop
poke 20 1
j Loop
Ready:
putd r2 0 3
poke 20 0
j Loop
"""
ck(arrivals(STATE_CELL, private={20})[15] == {frozenset({"own:10"})},
   f"with the state cell private only the loaded reference reaches the write: {arrivals(STATE_CELL, private={20})[15]}")
ck(frozenset({UNTRACKED}) in arrivals(STATE_CELL)[15], "without the state cell the entry path reaches the write with nothing loaded")
# Over the guard's same-image edge a register holds what a fresh path could
# have left in it, here the loaded reference: a resume block only that edge
# reaches is attributed the way the block the fresh path reaches is.
RESUME = STATE_CELL.replace("beq r0 1 Ready\n", "beq r0 1 Ready\nbeq r0 2 Resume\n", 1).replace(
    "Ready:\n", "Resume:\nputd r2 1 4\nj Loop\nReady:\n", 1)
ck(arrivals(RESUME, private={20}).get(16) == {frozenset({"own:10"})},
   f"a resume block reached only over the same-image edge carries the fresh loads: {arrivals(RESUME, private={20})}")
ck(16 not in arrivals(without(RESUME, 'beq r0 HASH("Peer.v1") Init'), private={20}),
   "without the guard the resume block is unreachable")

# --- declarations ----------------------------------------------------------------------------
aliases = {"console": "r1"}
ck(origin_matches(f"cell:{MAGIC}:40", {"kind": "peer-cell", "identity": "Peer.v1", "cells": [40, 41]}, aliases), "peer-cell by identity and cell")
ck(not origin_matches(f"cell:{MAGIC}:42", {"kind": "peer-cell", "identity": "Peer.v1", "cells": [40, 41]}, aliases), "a cell outside the list does not match")
ck(origin_matches(f"cell:{MAGIC}:*", {"kind": "peer-cell", "identity": "Peer.v1", "cells": "any"}, aliases), "any covers an unresolved cell")
ck(not origin_matches(f"cell:{MAGIC}:*", {"kind": "peer-cell", "identity": "Peer.v1", "cells": [40]}, aliases), "a list does not cover an unresolved cell")
ck(not origin_matches(f"cell:{OTHER}:40", {"kind": "peer-cell", "identity": "Peer.v1", "cells": "any"}, aliases), "another identity does not match")
ck(origin_matches("own:10", {"kind": "own-cell", "cells": [10], "filled_by": "peer"}, aliases), "own-cell")
ck(origin_matches("ref:r1:21", {"kind": "reference-cell", "via": "console", "cells": [21]}, aliases), "reference-cell resolves the via alias")
ck(origin_matches("port:d1:15", {"kind": "port-cell", "port": "d1", "cells": [15]}, aliases), "port-cell")
ck(origin_matches("device:d1", {"kind": "port-device", "port": "d1"}, aliases), "port-device")
ck(origin_matches("index:0:*", {"kind": "index-cell", "index": 0, "cells": "any"}, aliases), "index-cell")

GOOD = {"reference": "r1", "origin": {"kind": "own-cell", "cells": [10], "filled_by": "peer"}, "targets": ["Peer"], "reason": "why"}
ck(validate_provenance([GOOD], {"r1"}) == [GOOD], "a well-formed declaration passes")
for broken, message in (
    ({**GOOD, "reference": "r2"}, "a declaration for a reference that writes nothing"),
    ({**GOOD, "origin": {"kind": "elsewhere"}}, "an unknown origin kind"),
    ({**GOOD, "origin": {"kind": "own-cell", "cells": [10]}}, "an own-cell origin without filled_by"),
    ({**GOOD, "origin": {"kind": "own-cell", "cells": [10], "filled_by": "someone"}}, "an unknown filler"),
    ({**GOOD, "origin": {"kind": "own-cell", "cells": [], "filled_by": "peer"}}, "an empty cell list"),
    ({**GOOD, "origin": {"kind": "peer-cell", "identity": "Peer.v1", "cells": [40], "port": "d0"}}, "a stray field"),
    ({**GOOD, "targets": []}, "no target and no device"),
    ({k: v for k, v in GOOD.items() if k != "reason"}, "no reason"),
):
    try:
        validate_provenance([broken], {"r1"})
        failures.append(f"{message} was accepted")
    except ValueError:
        pass

# --- who fills an own cell is held to the contracts -----------------------------------------
FILLER = {
    "own_stack": {
        "fields": [{"address": 9, "access": ["self-read", "self-write"]}, {"address": 10, "access": ["self-read"]}],
        "dynamic_write": False, "dynamic_write_ranges": [],
    },
}


def filled(cells, filled_by, peer=frozenset(), contract=FILLER):
    declaration = {"reference": "r1", "origin": {"kind": "own-cell", "cells": cells, "filled_by": filled_by}}
    return filled_by_errors(contract, declaration, frozenset(peer))


ck(filled([10], "peer", {10}) == [], "a cell a wired peer writes is filled by a peer")
ck(filled([10], "peer") != [], "a cell no peer writes is not filled by a peer")
ck(filled([9], "self") == [], "a cell only this program writes is filled by itself")
ck(filled([9], "self", {9}) != [] and filled([10], "self") != [], "a peer-written or never-written cell is not self-filled")
ck(filled([10], "operator") == [], "a cell nothing writes is operator-configured")
ck(filled([9], "operator") != [] and filled([10], "operator", {10}) != [], "a written cell is not operator-configured")
ck(filled("any", "self") != [], "a table origin needs a program that writes its stack dynamically")
table = {"own_stack": {**FILLER["own_stack"], "dynamic_write": True}}
ck(filled("any", "self", contract=table) == [] and filled("any", "peer", contract=table) != [],
   "a table origin is only ever the program's own")
ck(filled_by_errors(FILLER, {"reference": "r1", "origin": {"kind": "port-cell", "port": "d0", "cells": [1]}}, frozenset()) == [],
   "only an own-cell origin says who fills it")

# --- attribution over a small tree ----------------------------------------------------------


def contract(source_rel, provides, consumes, dependencies, private=()):
    return {
        "source": source_rel,
        "network_dependencies": dependencies,
        "contracts": {"provides": provides, "consumes": consumes},
        "own_stack": {"fields": [{"address": 0, "const": provides[0]["magic"]}] if provides else []},
    }


def dependency(reference, writes, provenance=None, dynamic=False):
    item = {"transport": "reference-id", "reference": reference, "literal_reads": [], "literal_writes": writes,
            "dynamic_read": False, "dynamic_write": dynamic, "constraints": [], "accepted": []}
    if provenance:
        item["provenance"] = provenance
    return item


PEER = [{"protocol_id": "ic10.stack.peer.v1", "base": 0, "contract": "Peer", "magic": MAGIC, "abi": 1}]
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    (root / "ic10").mkdir()
    (root / "ic10/writer.ic10").write_text(CHECKED)
    (root / "ic10/copier.ic10").write_text(COPY)
    (root / "ic10/loader.ic10").write_text("get r1 db 10\nputd r1 8 1\nget r2 d0 40\nputd r2 9 1\nputd r3 9 1\n")
    (root / "ic10/peer.ic10").write_text("poke 0 HASH(\"Peer.v1\")\nyield\n")
    # A register loaded off the checked port, then re-pointed at what the peer's S30 holds:
    # the read before the re-point reaches the peer, the reads after it reach the target the
    # declaration names, and a read at a computed cell is recorded under `*`.
    (root / "ic10/repointer.ic10").write_text(
        "l r1 d0 ReferenceId\ngetd r2 r1 20\ngetd r1 r1 30\nmove r5 6\ngetd r3 r1 5\ngetd r4 r1 r5\nyield\n")
    # A read through a register nothing loaded: recorded, never refused.
    (root / "ic10/reader.ic10").write_text("getd r0 r3 5\nyield\n")
    declaration = {"reference": "r1", "origin": {"kind": "own-cell", "cells": [10], "filled_by": "peer"},
                   "targets": ["Peer"], "reason": "the request names the peer"}
    accepted_peer = [{"port": "d0", "accepted": [{"header_base": 0, "magic": MAGIC, "contract": "Peer", "abi": 1}]}]
    repoint = {"reference": "r1", "origin": {"kind": "peer-cell", "identity": "Peer.v1", "cells": [30]},
               "targets": ["Other"], "reason": "the peer's S30 names the record's target"}
    contracts = {
        "peer": contract("ic10/peer.ic10", PEER, [], []),
        "repointer": contract("ic10/repointer.ic10", [], accepted_peer,
                              [{**dependency("r1", [], [repoint]), "literal_reads": [5, 20, 30], "dynamic_read": True}]),
        "reader": contract("ic10/reader.ic10", [], [], [{**dependency("r3", []), "literal_reads": [5]}]),
        "writer": contract("ic10/writer.ic10", [], [], [dependency("r1", [8, 9])]),
        "copier": contract("ic10/copier.ic10", [], [], [dependency("ra", [27]), dependency("r2", [8])]),
        "loader": contract("ic10/loader.ic10", [], [{"port": "d0", "accepted": [{"header_base": 0, "magic": MAGIC, "contract": "Peer", "abi": 1}]}],
                           [dependency("r1", [8], [declaration]), dependency("r2", [9]), dependency("r3", [9])]),
    }
    attribute_network_writes(contracts, root)
    writer = contracts["writer"]["network_dependencies"][0]
    ck(writer["targets"] == ["Peer"] and writer["unattributed"] == ["own:10"],
       f"the checked write is attributed and the reject block's is not: {writer}")
    copier = {item["reference"]: item for item in contracts["copier"]["network_dependencies"]}
    ck(copier["ra"]["targets"] == ["Peer"] and not copier["ra"]["unattributed"], f"a copy of a checked reference is attributed: {copier['ra']}")
    ck(copier["r2"]["targets"] == [] and copier["r2"]["unattributed"] == ["own:11"], f"a reload is not: {copier['r2']}")
    repointer = contracts["repointer"]["network_dependencies"][0]
    ck(repointer["site_targets"] == [
        {"cell": 5, "targets": ["Other"]}, {"cell": 20, "targets": ["Peer"]}, {"cell": 30, "targets": ["Peer"]},
        {"cell": "*", "targets": ["Other"]},
    ], f"each read site is attributed to what the register named there: {repointer['site_targets']}")
    ck(repointer["targets"] == ["Other", "Peer"] and repointer["unattributed"] == [] and not writing(repointer),
       f"a read-only reference's answer comes from its read sites: {repointer}")
    reader = contracts["reader"]["network_dependencies"][0]
    ck(reader["unattributed"] == [UNTRACKED] and reader["site_targets"] == [] and reader["targets"] == []
       and not writing(reader),
       f"a read nothing attributes is recorded on a read-only reference, which the write rule does not hold: {reader}")
    loader = {item["reference"]: item for item in contracts["loader"]["network_dependencies"]}
    ck(loader["r1"]["targets"] == ["Peer"] and not loader["r1"]["unattributed"], f"a declared origin attributes: {loader['r1']}")
    ck(loader["r2"]["unattributed"] == [f"cell:{MAGIC}:40"], f"a peer's cell needs a declaration: {loader['r2']}")
    ck(loader["r3"]["unattributed"] == [UNTRACKED], f"a register nothing loaded is untracked: {loader['r3']}")
    reached = attributed_network_writes(contracts)
    # Every cell a dependency writes counts against every target it reaches; a
    # dependency with an unattributed site is a failure in its own right.
    ck(reached == {MAGIC: {8, 9, 27}}, f"attributed writes reach the peer's cells: {reached}")
    contracts["copier"]["network_dependencies"][0]["dynamic_write"] = True
    ck(attributed_network_writes(contracts)[MAGIC] == set(range(512)), "a dynamic attributed write reaches every cell")
    stale = {**declaration, "origin": {"kind": "own-cell", "cells": [11], "filled_by": "peer"}}
    contracts["loader"]["network_dependencies"][0]["provenance"] = [stale]
    try:
        attribute_network_writes(contracts, root)
        failures.append("a declaration matching no access site load was accepted")
    except ValueError:
        pass

# --- the tree ------------------------------------------------------------------------------------
tree, index, _, _ = build_all(ROOT)
by_source = {item["source"]: item for item in tree.values()}
inventory = index["network_write_inventory"]
ck(inventory["unattributed_count"] == 0, f"the tree has unattributed network writes: {inventory['unattributed_count']}")
ck(inventory["writing_dependency_count"] >= 40 and inventory["declared_provenance_count"] >= 20,
   f"the inventory does not cover the tree: {inventory}")
router = {item["reference"]: item for item in by_source["ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10"]["network_dependencies"]}
ck(router["ra"]["targets"] == ["GenericCatalogStore"] and not router["ra"].get("provenance"),
   f"the Router's ra is attributed by the check on r2 it copies: {router['ra']}")
editor = {item["reference"]: item for item in by_source["ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10"]["network_dependencies"]}
ck(editor["renderer"]["targets"] == ["DiagnosticRenderer"] and not editor["renderer"].get("provenance"),
   f"the Mapping Editor's rrN service loop establishes the renderer: {editor['renderer']}")


def tree_tokens(path, source=None):
    item = by_source[path]
    identities = declared_identities(item)
    known = {(p["base"], p["magic"]) for c in tree.values() for p in c["contracts"]["provides"]}
    return tokens(source or (ROOT / path).read_text(), identities=identities, known=known)


CLIENT = "ic10/printer-directory/printer_capacity_client_v2_0.ic10"
client = {item["reference"]: item for item in by_source[CLIENT]["network_dependencies"]}
ck(client["r1"].get("provenance") and client["r1"]["provenance"][0]["origin"] == {"kind": "own-cell", "cells": [9], "filled_by": "self"},
   f"the Capacity Client declares the bank reference it reloads from S9: {client['r1'].get('provenance')}")
client_tokens = tree_tokens(CLIENT)
ck("own:9" in client_tokens and any(token.startswith("checked:0:") for token in client_tokens),
   f"Release writes through a reference the identity check in Reserve does not cover: {client_tokens}")

READINESS = "ic10/manufacturing/transform_candidate_readiness_v1_0.ic10"
before = (ROOT / READINESS).read_text().replace(
    "getd r0 r11 37\ngetd r13 r12 35\n",
    "getd r0 r11 2\ngetd r0 r0 14\nblez r0 Processor\nputd r0 2 2\ngetd r13 r12 33\nputd r0 3 r13\ngetd r0 r11 7\ngetd r13 r12 35\n", 1)
ck(before != (ROOT / READINESS).read_text(), "the Readiness witness did not rebuild the old capacity block")
ck("ref:r0:14" in tree_tokens(READINESS, before),
   f"before this issue Readiness wrote through cell 14 of what the output Reservation's S2 named: {tree_tokens(READINESS, before)}")
ck(all(not token.startswith("ref:r0:") for token in tree_tokens(READINESS)), "the fixed Readiness no longer writes through it")

if failures:
    for failure in failures:
        print("FAIL", failure)
    sys.exit(1)
print("Network provenance test PASS")
print(" - an identity check establishes a reference for the rest of the path, a move carries it, a reload or a failed check drops it")
print(" - a check through rrN against a register-held magic, and only a published magic, establishes")
print(" - loads name the identified peer's cell, the own cell, the unchecked reference, the port, or nothing")
print(" - declarations match by kind, identity, and cell; a stale one fails the build")
print(" - the Router's ra, the Mapping Editor's services, the Capacity Client's S9, and the old Readiness capacity block behave as recorded")
