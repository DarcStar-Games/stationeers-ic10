#!/usr/bin/env python3
"""Exercise the boot-path register walk behind validate_register_seeding.py (issue #168).

The walk reports a register read on a path from the entry before that path has
written it. The cases here pin what it must see through -- a state register
seeded at boot and dispatched on, a state cell the program alone writes, an
`rrN` load loop, an ordering guard that decides a later equality, a loop
counter that would otherwise widen a state guard away -- and what it must not
see through: the same shapes with the seed removed. The fixture under
`tests/ic10/` is the shape the issue was opened on, a reflash guard whose clear
path never seeds the register the loop compares.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import sys

from framework.register_seeding import (
    FRESH,
    SAME_IMAGE,
    Range,
    decide,
    exact,
    join_environments,
    peer_written_cells,
    refine,
    unseeded_reads,
)

ROOT = _PROJECT_ROOT
failures = []


def ck(condition, message):
    if not condition:
        failures.append(message)


def reads(source, private=frozenset()):
    return {(item.edge, item.register) for item in unseeded_reads(source, frozenset(private))}


def fresh(source, private=frozenset()):
    return {register for edge, register in reads(source, private) if edge == FRESH}


def without(source, line):
    ck(f"{line}\n" in source, f"witness line {line!r} is not in the source")
    return source.replace(f"{line}\n", "", 1)


# --- the fixture: a reflash guard whose clear path never seeds the echo register ------
FIXTURE = (ROOT / "tests/ic10/reflash_guard_unseeded_fixture_v1_0.ic10").read_text()
found = reads(FIXTURE)
ck((FRESH, "r15") in found, f"the fixture's r15 is not reported on the fresh path: {found}")
ck(not {register for edge, register in found if register != "r15"},
   f"the fixture reports registers other than r15: {found}")
seeded = FIXTURE.replace("clr db\n", "clr db\nmove r15 0\n", 1)
ck(reads(seeded) == {(SAME_IMAGE, "r15")},
   f"seeding r15 on the clear path should leave only the same-image carry: {reads(seeded)}")
unguarded = FIXTURE.replace('get r0 db 0\nbeq r0 HASH("ReflashGuardUnseededFixture.v1") Header\n', "", 1)
ck(reads(unguarded) == {(FRESH, "r15")},
   f"without a guard every path is a fresh housing: {reads(unguarded)}")

# --- a state register seeded at boot prunes the blocks the entry path cannot take -----
STATE_MACHINE = """move r14 0
Loop:
yield
beqz r14 New
get r0 d0 24
bne r0 r5 Fail
bge r8 r7 Done
add r8 r8 1
j Loop
New:
get r5 db 14
get r7 db 15
move r8 0
move r14 1
j Loop
Done:
poke 8 r8
Fail:
move r14 0
j Loop
"""
ck(fresh(STATE_MACHINE) == set(), f"a seeded state register should prune every other state: {fresh(STATE_MACHINE)}")
ck(fresh(without(STATE_MACHINE, "move r14 0")) >= {"r5", "r7", "r8"},
   f"an unseeded state register reaches every state: {fresh(without(STATE_MACHINE, 'move r14 0'))}")
ck(fresh(without(STATE_MACHINE, "move r8 0")) == {"r8"},
   f"a register the taken state never seeds is reported: {fresh(without(STATE_MACHINE, 'move r8 0'))}")

# --- a state cell the program alone writes prunes exactly as a register does ----------
STATE_CELL = """poke 20 0
Loop:
yield
get r0 db 20
beq r0 1 Wait
get r2 db 14
put d0 10 r2
poke 20 1
j Loop
Wait:
get r0 d0 11
beqz r0 Loop
put d0 12 r2
poke 20 0
j Loop
"""
ck(fresh(STATE_CELL, {20}) == set(), f"a private state cell should prune: {fresh(STATE_CELL, {20})}")
ck(fresh(STATE_CELL) == {"r2"}, f"a cell a peer may write proves nothing: {fresh(STATE_CELL)}")
ck(fresh(without(STATE_CELL, "poke 20 0"), {20}) == {"r2"},
   f"an unseeded state cell proves nothing: {fresh(without(STATE_CELL, 'poke 20 0'), {20})}")
CLEARED_CELL = "clr db\n" + STATE_CELL.replace("poke 20 0\n", "", 1)
ck(fresh(CLEARED_CELL, {20}) == set(), f"a boot clear zeroes a private cell: {fresh(CLEARED_CELL, {20})}")

# --- an rrN load loop writes the registers its index names ---------------------------
INDIRECT = """Loop:
yield
move r0 1
move ra 96
Load:
get rr0 d0 ra
bnan rr0 Bad
add ra ra 1
add r0 r0 1
ble r0 3 Load
beqz r1 Loop
add r4 r2 r3
poke 8 r4
Bad:
j Loop
"""
ck(fresh(INDIRECT) == set(), f"a literal-indexed rrN loop seeds its registers: {fresh(INDIRECT)}")
unknown_index = INDIRECT.replace("move r0 1\n", "get r0 db 8\n", 1)
ck(fresh(unknown_index) == {"r1", "r2", "r3"},
   f"a write through an unknown index is credited to no register, and the read right behind it"
   f" is of the register it just wrote: {fresh(unknown_index)}")
any_register = INDIRECT.replace("bnan rr0 Bad\n", "add ra ra 1\nbnan rr0 Bad\n", 1).replace("move r0 1\n", "get r0 db 8\n", 1)
ck(fresh(any_register) >= {"r1", "r2", "r3", "r9", "r15"},
   f"an rrN read through an unknown index, once anything moved, may be of any register: {fresh(any_register)}")

# --- an ordering guard decides a later equality against a cleared cell ---------------
KEYED = """get r0 db 0
beq r0 HASH("KeyedFixture.v1") Header
clr db
Header:
poke 0 HASH("KeyedFixture.v1")
Loop:
yield
get r0 db 35
blez r0 Bad
get sp db 11
beq r0 sp Resume
poke 11 r0
move r4 7
j Loop
Resume:
bne r0 r4 Bad
poke 9 r4
Bad:
j Loop
"""
ck(reads(KEYED, {11}) == {(SAME_IMAGE, "r4")},
   f"a positive key never matches the cleared cell, so r4 carries only over the guard: {reads(KEYED, {11})}")
ck(fresh(without(KEYED, "blez r0 Bad"), {11}) == {"r4"},
   f"without the sign guard a zero key resumes over an unseeded cursor: {fresh(without(KEYED, 'blez r0 Bad'), {11})}")
ck(fresh(KEYED) == {"r4"}, f"the key cell proves nothing unless it is private: {fresh(KEYED)}")

# --- a counter bounded by a peer's number must not widen a state guard away ----------
COUNTED = """Loop:
yield
get r10 d0 8
move r6 -1
move r13 0
Scan:
bge r13 r10 Done
get r14 d0 r13
bltz r6 Choose
bgt r14 r7 Choose
j Next
Choose:
move r6 r13
move r7 r14
Next:
add r13 r13 1
j Scan
Done:
poke 8 r6
j Loop
"""
ck(fresh(COUNTED) == set(), f"the first pass always chooses, so r7 is written before read: {fresh(COUNTED)}")
ck(fresh(without(COUNTED, "move r6 -1")) == {"r6", "r7"},
   f"an unseeded chooser reads the comparison register: {fresh(without(COUNTED, 'move r6 -1'))}")

# --- the interval arithmetic: NaN never lets a comparison hold, only fail -------------
positive_or_nan = refine("ble", Range(), exact(0), False)
ck(positive_or_nan == Range(0, None, True, False, True), f"blez fallthrough: {positive_or_nan}")
ck(decide("beq", positive_or_nan, exact(0)) is False, "a positive-or-NaN value never equals zero")
ck(decide("bgt", positive_or_nan, exact(0)) is None, "a value that may be NaN cannot be shown greater")
ck(decide("bgt", refine("bgt", Range(), exact(0), True), exact(0)) is True, "bgtz taken: strictly positive")
ck(decide("bne", positive_or_nan, exact(0)) is True, "bne holds for NaN as for every positive value")
ck(refine("beq", Range(), exact(3), True) == exact(3), "beq taken pins the value")
ck(refine("blt", exact(5), exact(3), True) is None, "5 < 3 has no edge")
ck(join_environments({"r1": exact(1), "r2": exact(2)}, {"r1": exact(4), "r2": exact(2)})
   == {"r1": Range(1, 4, False, False, False), "r2": exact(2)}, "join widens what differs and keeps what agrees")

# --- peer-written cells come from the wiring map and the peers' port contracts -------
CONTRACTS = {
    "a.json": {"source": "ic10/x/a.ic10", "device_ports": [
        {"port": "d0", "stack": {"literal_writes": [10, 11], "dynamic_write": False,
                                 "dynamic_write_ranges": [{"start": 16, "end": 17}]}}],
        "own_stack": {"external_writable_ranges": []}},
    "b.json": {"source": "ic10/x/b.ic10", "device_ports": [],
               "own_stack": {"external_writable_ranges": [{"start": 40, "end": 41}]}},
    "c.json": {"source": "ic10/x/c.ic10", "device_ports": [],
               "own_stack": {"external_writable_ranges": []}},
}
WIRING = {"ports": {
    "ic10/x/a.ic10": {"d0": {"kind": "script", "providers": ["ic10/x/b.ic10"]}},
    "ic10/x/b.ic10": {},
}}
written = peer_written_cells(CONTRACTS, WIRING)
ck(written["ic10/x/b.ic10"] == frozenset({10, 11, 16, 17, 40, 41}),
   f"b takes a's port writes and its own declared mailbox: {sorted(written['ic10/x/b.ic10'])}")
ck(written["ic10/x/a.ic10"] == frozenset(), f"nothing points at a: {sorted(written['ic10/x/a.ic10'])}")
ck(len(written["ic10/x/c.ic10"]) == 512, "a program with no wiring entry has every cell peer-written")

# --- the shape the issue was opened on, in the tree ----------------------------------
BUILDER = (ROOT / "ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10").read_text()
ck(fresh(BUILDER) == set(), f"the singlehop builder seeds every register it reads: {fresh(BUILDER)}")
ck("move r13 0\nmove r14 1\n" in BUILDER, "the builder's New block no longer seeds r13 before arming the state")
unseeded_builder = BUILDER.replace("move r13 0\nmove r14 1\n", "move r14 1\n", 1)
ck(fresh(unseeded_builder) == {"r13"},
   f"the builder without its allocation-token seed waits on whatever r13 held: {fresh(unseeded_builder)}")
ENUMERATOR = (ROOT / "ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10").read_text()
ck(reads(ENUMERATOR, {11}) == {(SAME_IMAGE, f"r{n}") for n in (4, 5, 6, 7, 8)},
   f"the enumerator's cursors carry only over its same-image edge: {reads(ENUMERATOR, {11})}")

if failures:
    print("IC10 register seeding: FAIL")
    for failure in failures:
        print(" -", failure)
    sys.exit(1)
print("IC10 register seeding: PASS")
print(" - a register read before any write on a fresh-housing path is reported; the same read only over a reflash guard's same-image edge is a carry")
print(" - a state register or private state cell seeded at boot prunes the states the entry path cannot take, and loses nothing to widening")
print(" - rrN resolves through its index, an ordering guard decides a later equality, and NaN never lets a comparison hold")
print(" - the fixture and the singlehop builder fail exactly without their seeds")
