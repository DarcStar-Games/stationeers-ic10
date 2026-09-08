#!/usr/bin/env python3
"""Exercise the identity-check path walk behind validate_identity_coverage.py (issue #109).

The walk reports an access to a declared consumer port on a path from the
entry that never took the port's identity check. The cases here pin what it
must see through -- a state register or a private state cell armed after the
check and dispatched on next tick, a generation snapshot or a bounds guard
taken before the check, a subroutine that rejects through `ra` -- and what it
must not: the same shapes with the check bypassed, a reject path that echoes
the pin, a read held across a write or a `yield`, a check inherited over a
reflash guard. The tree cases rebuild the two defects issue #109 was opened on
and the ones this walk found.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import json
import sys

import framework.register_seeding as register_seeding
from framework.identity_coverage import declared_identities, unchecked_accesses
from framework.register_seeding import PRIVATE_STATE_CELLS

ROOT = _PROJECT_ROOT
D0 = {"d0": {(0, 1234)}}
failures = []


def ck(condition, message):
    if not condition:
        failures.append(message)


def unchecked(source, identities=D0, private=frozenset(), pins=None):
    return {item.port for item in unchecked_accesses(source, identities, frozenset(private), pins)}


def without(source, line):
    ck(f"{line}\n" in source, f"witness line {line!r} is not in the source")
    return source.replace(f"{line}\n", "", 1)


def tree(path):
    """A tree program's source and what its contract declares it consumes."""
    contract = json.loads((ROOT / "contracts" / path[len("ic10/"):-len(".ic10")]).with_suffix(".contract.json").read_text())
    pins = {token: tuple(item["pins"]) for token, item in contract.get("register_ports", {}).items()}
    return (ROOT / path).read_text(), declared_identities(contract), frozenset(PRIVATE_STATE_CELLS.get(path, {})), pins


# --- a state register armed after the check gates the accesses of later ticks ---------
STATE_MACHINE = """move r14 0
Loop:
yield
beqz r14 New
get r0 d0 11
bne r0 r13 Loop
get r1 d0 8
poke 8 r1
move r14 0
j Loop
New:
get r13 db 14
beqz r13 Loop
get r0 d0 0
bne r0 1234 Loop
put d0 14 r13
move r14 1
j Loop
"""
ck(unchecked(STATE_MACHINE) == set(), f"the wait state is reached only after New checked the pin: {unchecked(STATE_MACHINE)}")
ck(unchecked(without(STATE_MACHINE, "move r14 0")) == {"d0"},
   f"an unseeded state register dispatches the entry into the wait state unchecked: {unchecked(without(STATE_MACHINE, 'move r14 0'))}")
bypassed = STATE_MACHINE.replace("beqz r13 Loop\n", "beqz r13 Loop\nbgtz r13 Armed\n", 1).replace(
    "put d0 14 r13\n", "Armed:\nput d0 14 r13\n", 1)
ck(unchecked(bypassed) == {"d0"}, f"a branch around the check reaches the write unchecked: {unchecked(bypassed)}")

rechecked = STATE_MACHINE.replace("get r0 d0 11\nbne r0 r13 Loop\n",
                                  "get r0 d0 0\nbne r0 1234 Lost\nget r0 d0 11\nbne r0 r13 Loop\n", 1) + "Lost:\nget r1 d0 8\npoke 8 r1\nj Loop\n"
ck(unchecked(rechecked) == {"d0"},
   f"a check that fails in the armed state takes the establishment back, so its reject block acts unchecked: {unchecked(rechecked)}")
ck(unchecked(rechecked.replace("Lost:\nget r1 d0 8\npoke 8 r1\n", "Lost:\npoke 8 -1\n", 1)) == set(),
   f"the same reject block publishing only its own status is clean")

# Widening joins the arrivals at one instruction, and the loop head is reached by
# the unchecked entry and by every checked, armed state. Partitioned by the ports
# a path has established, the join keeps both; walked with every arrival widened
# the proof must still hold, and the bypass must still be found.
cap = register_seeding.ENVIRONMENT_CAP
register_seeding.ENVIRONMENT_CAP = 1
try:
    ck(unchecked(STATE_MACHINE) == set(), f"widening at every arrival must not merge the entry with the armed states: {unchecked(STATE_MACHINE)}")
    ck(unchecked(bypassed) == {"d0"}, f"widening at every arrival must not lose the bypass: {unchecked(bypassed)}")
finally:
    register_seeding.ENVIRONMENT_CAP = cap

# --- a state cell the program alone writes gates exactly as a register does ----------
STATE_CELL = """poke 20 0
Loop:
yield
get r0 db 20
beq r0 1 Wait
get r0 d0 0
bne r0 1234 Loop
put d0 14 1
poke 20 1
j Loop
Wait:
get r0 d0 11
beqz r0 Loop
poke 20 0
j Loop
"""
ck(unchecked(STATE_CELL, private={20}) == set(), f"a private state cell gates the wait state: {unchecked(STATE_CELL, private={20})}")
ck(unchecked(STATE_CELL) == {"d0"}, f"a cell a peer may write gates nothing: {unchecked(STATE_CELL)}")

# --- a read before the check is settled by the check or by a guard that rejects the same way
PROLOGUE = """Loop:
yield
get r14 d0 12
blez r14 Bad
get r0 d0 0
bne r0 1234 Bad
get r1 d0 8
poke 8 r1
get r0 d0 12
bne r0 r14 Loop
poke 9 r14
j Loop
Bad:
poke 8 -1
j Loop
"""
ck(unchecked(PROLOGUE) == set(), f"a generation snapshot before the check is a prologue read: {unchecked(PROLOGUE)}")
published = PROLOGUE.replace("blez r14 Bad\n", "blez r14 Bad\npoke 9 r14\n", 1)
ck(unchecked(published) == {"d0"}, f"a pre-check read written out before the check is a finding: {unchecked(published)}")
held = PROLOGUE.replace("blez r14 Bad\n", "blez r14 Bad\nyield\n", 1)
ck(unchecked(held) == {"d0"}, f"a pre-check read held across a yield is a finding: {unchecked(held)}")
elsewhere = PROLOGUE.replace("blez r14 Bad\n", "blez r14 Other\n", 1) + "Other:\npoke 9 r14\nj Loop\n"
ck(unchecked(elsewhere) == {"d0"}, f"a guard that rejects somewhere the check does not is not settled: {unchecked(elsewhere)}")

# --- a subroutine that rejects through ra settles at the caller's return -------------
SUBROUTINE = """Loop:
yield
jal Grant
j Loop
Grant:
get r14 d2 13
blez r14 ra
get r0 d2 0
bne r0 1234 ra
get r2 d2 9
poke 9 r2
j ra
"""
D2 = {"d2": {(0, 1234)}}
ck(unchecked(SUBROUTINE, D2) == set(), f"a guard returning through ra rejects as the check does: {unchecked(SUBROUTINE, D2)}")
ck(unchecked(without(SUBROUTINE, "bne r0 1234 ra"), D2) == {"d2"},
   f"without the check the subroutine acts on the pin: {unchecked(without(SUBROUTINE, 'bne r0 1234 ra'), D2)}")

# --- a reject path that reads the pin has not checked it -----------------------------
ECHO = """Loop:
yield
get r15 db 20
get r0 d0 0
bne r0 1234 Bad
get r1 d0 8
poke 8 r1
poke 22 1
j Publish
Bad:
poke 22 -1
Publish:
get r0 d0 17
poke 17 r0
poke 21 r15
j Loop
"""
ck(unchecked(ECHO) == {"d0"}, f"the reject path echoes a cell of whatever is wired: {unchecked(ECHO)}")
silent = ECHO.replace("Bad:\npoke 22 -1\n", "Bad:\npoke 22 -1\npoke 21 r15\nj Loop\n", 1)
ck(unchecked(silent) == set(), f"a reject path that publishes only its own status is clean: {unchecked(silent)}")

# --- a check the previous image passed proves nothing about the pin -------------------
GUARDED = """get r0 db 0
beq r0 HASH("IdentityCoverageFixture.v1") Loop
clr db
poke 0 HASH("IdentityCoverageFixture.v1")
move r14 0
Loop:
yield
beqz r14 New
get r0 d0 11
bne r0 r13 Loop
poke 8 r0
move r14 0
j Loop
New:
get r0 d0 0
bne r0 1234 Loop
move r13 7
move r14 1
j Loop
"""
ck(unchecked(GUARDED) == {"d0"}, f"over the guard's skip edge the wait state trusts a check the last image passed: {unchecked(GUARDED)}")
reseeded = GUARDED.replace('beq r0 HASH("IdentityCoverageFixture.v1") Loop\n', 'beq r0 HASH("IdentityCoverageFixture.v1") Seed\n', 1).replace(
    "move r14 0\nLoop:\n", "Seed:\nmove r14 0\nLoop:\n", 1)
ck(unchecked(reseeded) == set(), f"a guard that reseeds the state on both edges reaches the wait state only through New: {unchecked(reseeded)}")

# --- the tree: the two defects the issue was opened on, rebuilt ----------------------
EXECUTOR = tree("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10")
ck(unchecked(*EXECUTOR) == set(), f"the Store Command Executor checks its Store on every path: {unchecked(*EXECUTOR)}")
check = 'get r0 d0 0\nbne r0 HASH("GenericJobStore.v1") Loop\n'
resume = "get r0 db 31\nbgtz r0 StoreWait\n"
ck(check + resume in EXECUTOR[0], "the Executor's check no longer sits above its resume test")
below = (EXECUTOR[0].replace(check + resume, resume + check, 1), *EXECUTOR[1:])
ck(unchecked(*below) == {"d0"}, f"the check below the resume test leaves StoreWait unchecked: {unchecked(*below)}")
fast_path = (EXECUTOR[0].replace("beq r0 1 Loop\n", "bne r0 1 Init\n" + resume + "j Loop\n", 1), *EXECUTOR[1:])
ck(fast_path[0] != EXECUTOR[0] and unchecked(*fast_path) == {"d0"},
   f"a boot fast-path into StoreWait over the same-image edge bypasses the loop's check: {unchecked(*fast_path)}")

PLANNER = tree("ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10")
ck(unchecked(*PLANNER) == set(), f"the Dependency Planner checks its controller at the loop head: {unchecked(*PLANNER)}")
check = 'get r0 d1 0\nbne r0 HASH("ExistingDependencyPlanController.v1") Loop\n'
fork = "get r15 db 25\nget r0 db 26\nbne r15 r0 Cleanup\n"
ck(check + fork in PLANNER[0], "the Planner's check no longer sits above the Cleanup fork")
sibling = (PLANNER[0].replace(check + fork, fork + check, 1), *PLANNER[1:])
ck(unchecked(*sibling) == {"d1"}, f"the check below the Cleanup fork leaves Cleanup's Existing call unchecked: {unchecked(*sibling)}")

BUILDER = tree("ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10")
ck(unchecked(*BUILDER) == set(),
   f"the Plan Builder's Path and Wait blocks run only once New has checked both peers: {unchecked(*BUILDER)}")
ck(unchecked(without(BUILDER[0], 'bne r0 HASH("PressureGridPathAllocator.v1") Reject'), *BUILDER[1:]) == {"d1"},
   "without the Allocator check every Path block access is unchecked")

# --- the tree: what this walk found ---------------------------------------------------
SELECTOR = tree("ic10/generic-jobs/generic_job_selector_v3_0.ic10")
ck(unchecked(*SELECTOR) == set(), f"the Job Selector's reject path no longer reads its Store: {unchecked(*SELECTOR)}")
echoing = (SELECTOR[0].replace("Bad:\npoke 22 -1\npoke 21 r15\nj Loop\n", "Bad:\npoke 22 -1\nj Publish\n", 1), *SELECTOR[1:])
ck(echoing[0] != SELECTOR[0] and unchecked(*echoing) == {"d0"},
   f"the Selector's Bad path through Publish echoed S17 of whatever was wired: {unchecked(*echoing)}")

SEQUENCER = tree("ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10")
ck(unchecked(*SEQUENCER) == set(), f"the Sequencer checks its Config Host before publishing its ReferenceId: {unchecked(*SEQUENCER)}")
check = 'get r0 d3 0\nbne r0 HASH("GenericPersistentConfigHost.v1") ConfigBad\n'
publish = "l r0 d3 ReferenceId\nsne sp r0 r13\nmove r13 r0\npoke 116 r0\n"
ck(check + publish in SEQUENCER[0], "the Sequencer's check no longer precedes its host ReferenceId publication")
late = (SEQUENCER[0].replace(check + publish, publish + check, 1), *SEQUENCER[1:])
ck(unchecked(*late) == {"d3"}, f"publishing the host ReferenceId before the check is a finding: {unchecked(*late)}")

ENDPOINT = tree("ic10/material-grid/material_import_slot_endpoint_v1_0.ic10")
ck(unchecked(*ENDPOINT) == set(), f"the import-slot endpoint publishes its view's ReferenceId after checking it: {unchecked(*ENDPOINT)}")
at_boot = (ENDPOINT[0].replace("poke 14 0\n", "l r0 d1 ReferenceId\npoke 14 r0\n", 1)
           .replace('Bad\nl r0 d1 ReferenceId\npoke 14 r0\n', "Bad\n", 1), *ENDPOINT[1:])
ck(at_boot[0] != ENDPOINT[0] and unchecked(*at_boot) == {"d1"},
   f"publishing the pin's ReferenceId at boot precedes every check: {unchecked(*at_boot)}")

if failures:
    print("IC10 identity-check coverage: FAIL")
    for failure in failures:
        print(" -", failure)
    sys.exit(1)
print("IC10 identity-check coverage: PASS")
print(" - an access on a path that never passed the port's identity check is reported, a reflash guard's same-image edge included")
print(" - a state register or private state cell armed after the check gates the accesses of later ticks")
print(" - a read before the check is settled by the check or the rejection it takes, and becomes a finding at a write or a yield")
print(" - widening is partitioned by the ports a path has established, so the Plan Builder proves and a bypass survives a cap of one")
print(" - the Executor, Planner, Selector, Sequencer, and import-slot endpoint fail exactly with their fixes reverted")
