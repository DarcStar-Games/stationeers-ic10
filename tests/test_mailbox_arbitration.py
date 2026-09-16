#!/usr/bin/env python3
"""Mailbox arbitration: the reviewed-declaration checks, and the race they exist to prevent."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from copy import deepcopy
import json
import sys

from framework.ic10_harness import Device, IC10, run_round_robin, without_lines
from framework.json_schema import SchemaValidationError, validate
from framework.request_blocking import (
    PortTokens,
    RequestBlocking,
    own_response_cells,
    port_tokens,
    token_cells,
)
from framework.script_wiring import (
    arbitration_failures,
    contended_pairs,
    dedicated_closure,
    serialized_tree,
    writer_edges,
)

R = _PROJECT_ROOT
fails = []


def ck(value, message):
    if not value:
        fails.append(message)


def src(path):
    return (R / path).read_text()


# --- The declaration checks, against a synthetic map -------------------------------
#
# ROOT posts to A and B; A and B both post to P on the same cells; P posts to Q.
ROOT_P = "ic10/test-family/root_v1_0.ic10"
A = "ic10/test-family/alpha_v1_0.ic10"
B = "ic10/test-family/beta_v1_0.ic10"
P = "ic10/test-family/provider_v1_0.ic10"
Q = "ic10/test-family/downstream_v1_0.ic10"
DOC = "docs/TEST.md"


def port(writes=(), reads=()):
    return {"kind": "stack-interface", "reads": set(reads), "writes": set(writes),
            "read_ranges": [], "write_ranges": [], "constraints": {}}


def edge(provider):
    return {"kind": "script", "providers": [provider], "note": "test edge"}


PORTS = {
    ROOT_P: {"d0": port({10}), "d1": port({10})},
    A: {"d0": port({10, 11}, {12})},
    B: {"d0": port({10, 11}, {12})},
    P: {"d0": port({8})},
    Q: {},
}
WIRING = {
    "$schema": "../schemas/script_wiring.schema.json",
    "format": "IC10_SCRIPT_WIRING_V1",
    "ports": {
        ROOT_P: {"d0": edge(A), "d1": edge(B)},
        A: {"d0": edge(P)},
        B: {"d0": edge(P)},
        P: {"d0": edge(Q)},
        Q: {},
    },
}
CLASSES = {name: "conditional-resident" for name in PORTS}
TEXTS = {ROOT_P: "put d0 10 r1\n", DOC: f"{P} and {Q}"}


def text(path):
    return TEXTS.get(path, "")


def failing(declarations, wiring=WIRING, ports=PORTS, classes=CLASSES, source=text, blocking=None):
    return arbitration_failures(wiring, ports, declarations, classes, source, blocking)


def mentions(failures, fragment):
    return any(fragment in failure for failure in failures)


ck(mentions(failing({}), f"{P}: 2 programs write overlapping request cells"),
   "two writers on one mailbox without a declaration passed")

serial = {P: {"arbitration": "serial", "writers": [A, B], "serialized_by": ROOT_P, "note": "n"}}
ck(failing(serial) == [], f"serial group under its root failed: {failing(serial)}")

# Take ROOT's edge to B away: B now posts from its own loop.
loose_wiring = deepcopy(WIRING)
del loose_wiring["ports"][ROOT_P]["d1"]
loose_ports = deepcopy(PORTS)
del loose_ports[ROOT_P]["d1"]
ck(mentions(failing(serial, loose_wiring, loose_ports), "does not reach"),
   "a writer the root does not reach was accepted as serial")

# A root reaching a writer through a register-indexed port is no exception: the
# contract resolves `dr<n>` to its pins, so the edge is in the map or the group
# is not serial. The old `unmapped` escape hatch is refused as a stray key.
unmapped = deepcopy(serial)
unmapped[P]["unmapped"] = [B]
ck(mentions(failing(unmapped, loose_wiring, loose_ports), "does not take ['unmapped']"),
   "a serial group listed an unmapped writer and the claim was not refused")

stale = deepcopy(serial)
stale[P]["writers"] = [A]
ck(mentions(failing(stale), "differ from the wiring map"), "a stale writer list passed")

no_root = {P: {"arbitration": "serial", "writers": [A, B], "note": "n"}}
ck(mentions(failing(no_root), "names no serialized_by"), "a serial group without a root passed")

laned_ports = deepcopy(PORTS)
laned_ports[B]["d0"]["writes"] = {20, 21}
ck(failing({}, ports=laned_ports) == [], "laned writers were asked for a declaration")
ck(mentions(failing(serial, ports=laned_ports), "laned writers"),
   "a declaration on a laned mailbox was not reported stale")

single_wiring = deepcopy(WIRING)
del single_wiring["ports"][B]["d0"]
single_ports = deepcopy(PORTS)
del single_ports[B]["d0"]
alternatives = {P: {"arbitration": "alternatives", "writers": [A], "note": "n"}}
ck(mentions(failing(alternatives, single_wiring, single_ports), "one writer"),
   "a declaration on a single-writer mailbox was not reported stale")
reselect = {P: {"arbitration": "reselect", "writers": [A], "note": "n"}}
ck(failing(reselect, single_wiring, single_ports) == [],
   "reselect was refused on a single-writer surface")

dedicated = {P: {
    "arbitration": "dedicated", "writers": [A, B], "note": "n",
    "instances": [{"writers": [A], "documented_in": DOC}, {"writers": [B], "documented_in": DOC}],
}}
ck(failing(dedicated) == [], f"dedicated instances named in their document failed: {failing(dedicated)}")
ck(dedicated_closure(writer_edges(WIRING, PORTS), dedicated, P) == {P, Q},
   "the closure of a dedicated instance did not include the mailbox it writes downstream")
ck(mentions(failing(dedicated, source=lambda path: P if path == DOC else text(path)), f"does not name ['{Q}']"),
   "a document naming the instance but not its downstream mailbox passed")
stopped = deepcopy(dedicated)
stopped[Q] = {"arbitration": "reselect", "writers": [P], "note": "n"}
ck(dedicated_closure(writer_edges(WIRING, PORTS), stopped, P) == {P},
   "a reselect surface did not stop the closure")
ck(failing(stopped, source=lambda path: P if path == DOC else text(path)) == [],
   "a document need not name a reselect surface, but was asked to")
partial = deepcopy(dedicated)
partial[P]["instances"] = [{"writers": [A], "documented_in": DOC}, {"writers": [A], "documented_in": DOC}]
failures = failing(partial)
ck(mentions(failures, "repeats writers") and mentions(failures, f"no instance claims writers ['{B}']"),
   "instances that repeat one writer and omit another passed")
unserialized = deepcopy(dedicated)
unserialized[P]["instances"] = [{"writers": [A, B], "documented_in": DOC}, {"writers": [A], "documented_in": DOC}]
ck(mentions(failing(unserialized), "instance 1 has 2 writers and names no serialized_by"),
   "a shared instance without a root passed")
ck(mentions(failing({P: {"arbitration": "dedicated", "writers": [A, B], "note": "n"}}), "names no instances"),
   "dedicated without instances passed")

operator = {P: {"arbitration": "operator", "writers": [A, B], "note": "n"}}
ck(mentions(failing(operator), "2 resident writers"), "operator arbitration with two resident tools passed")
ck(failing(operator, classes={**CLASSES, B: "on-demand"}) == [],
   "operator arbitration with one resident writer failed")

shaped = {P: {"arbitration": "alternatives", "writers": [A, B], "serialized_by": ROOT_P, "note": "n"}}
ck(mentions(failing(shaped), "does not take ['serialized_by']"),
   "serial fields on an alternatives entry passed")
ck(mentions(failing({Q: {"arbitration": "reselect", "writers": [P], "note": "n"},
                     "ic10/test-family/ghost_v1_0.ic10": {"arbitration": "reselect", "writers": [P], "note": "n"}}),
            "no wiring entry"),
   "a declaration for a program outside the map passed")

SCHEMA = json.loads((R / "schemas/mailbox_arbitration.schema.json").read_text())
try:
    validate({"$schema": "../schemas/mailbox_arbitration.schema.json",
              "format": "IC10_MAILBOX_ARBITRATION_V1",
              "mailboxes": {P: {"arbitration": "serial", "writers": [A, B]}}}, SCHEMA)
    ck(False, "the schema accepted an entry without a note")
except SchemaValidationError:
    pass

# --- The waiting half of a serial claim (#146) ------------------------------------
#
# The map puts every writer under the root; the walk proves each program on the
# tree reads a peer's response token before it posts to another peer or replies.
PEERS = {"d0": PortTokens(frozenset({10}), frozenset({11})), "d1": PortTokens(frozenset({10}), frozenset({11}))}
OWN_REPLY = frozenset({9})
ACCEPT = "Loop:\nyield\nget r15 db 8\nget r0 db 9\nbeq r15 r0 Loop\n"


def unblocked(source, ports=PEERS, private=frozenset(), register_ports=None):
    return sorted((item.port, item.line_number, item.offence, item.offence_line)
                  for item in RequestBlocking(source, ports, OWN_REPLY, private, register_ports).findings())


WAITS = ACCEPT + ("put d0 12 r15\nput d0 10 r15\nWaitA:\nyield\nget r0 d0 11\nbne r0 r15 WaitA\n"
                  "put d1 10 r15\nWaitB:\nyield\nget r0 d1 11\nbne r0 r15 WaitB\npoke 9 r15\nj Loop\n")
ck(unblocked(WAITS) == [], f"a caller that waits on each post before the next passed nothing: {unblocked(WAITS)}")
PARALLEL = ACCEPT + ("put d0 10 r15\nput d1 10 r15\nWaitA:\nyield\nget r0 d0 11\nbne r0 r15 WaitA\n"
                     "WaitB:\nyield\nget r0 d1 11\nbne r0 r15 WaitB\npoke 9 r15\nj Loop\n")
ck(unblocked(PARALLEL) == [("d0", 6, "posts to d1", 7)],
   f"posting to two peers before waiting on either was not reported once, at the second post: {unblocked(PARALLEL)}")
EARLY_REPLY = ACCEPT + "put d0 10 r15\npoke 9 r15\nWaitA:\nyield\nget r0 d0 11\nbne r0 r15 WaitA\nj Loop\n"
ck(unblocked(EARLY_REPLY) == [("d0", 6, "replies to its own caller", 7)],
   f"replying with a request in flight was not reported: {unblocked(EARLY_REPLY)}")
HALTS = ACCEPT + "put d0 10 r15\nhcf\n"
ck(unblocked(HALTS) == [("d0", 6, "halts", 7)], f"halting with a request in flight was not reported: {unblocked(HALTS)}")

# A post that arms a private state cell and returns to the loop head is followed
# to the block the head dispatches to on the next tick; without the cell the
# accept block and the reply are reachable with the request pending.
STATE_MACHINE = ("poke 20 0\nLoop:\nyield\nget r0 db 20\nbeq r0 1 WaitA\nbeq r0 2 WaitB\nget r15 db 8\nget r0 db 9\n"
                 "beq r15 r0 Loop\nput d0 10 r15\npoke 20 1\nj Loop\nWaitA:\nget r15 db 8\nget r0 d0 11\nbne r0 r15 Loop\n"
                 "put d1 10 r15\npoke 20 2\nj Loop\nWaitB:\nget r15 db 8\nget r0 d1 11\nbne r0 r15 Loop\npoke 9 r15\n"
                 "poke 20 0\nj Loop\n")
ck(unblocked(STATE_MACHINE, private=frozenset({20})) == [],
   f"a state machine dispatching on a private cell was not followed to its wait: {unblocked(STATE_MACHINE, private=frozenset({20}))}")
ck(unblocked(STATE_MACHINE) == [("d0", 10, "replies to its own caller", 24), ("d1", 17, "posts to d0", 10)],
   f"the same machine with the cell unknown did not reach the reply and the accept block while pending: {unblocked(STATE_MACHINE)}")
# Returning to the loop head with no state to route the next tick back to a wait
# is not refused as such; what fails is what the next request then does.
NEXT_REQUEST = ACCEPT + "get r0 db 12\nbeqz r0 First\nput d1 10 r15\nj Loop\nFirst:\nput d0 10 r15\nj Loop\n"
ck(unblocked(NEXT_REQUEST) == [("d0", 11, "posts to d1", 8), ("d1", 8, "posts to d0", 11)],
   f"a caller that never waits and serves the next request elsewhere passed: {unblocked(NEXT_REQUEST)}")
# The wait is the compare's equality edge, not the read: a caller whose mismatch
# edge posts elsewhere is reported, one that replies on the match is not, and a
# token read into a register that is overwritten before any compare leaves the
# post pending.
MISMATCH = ACCEPT + ("put d0 10 r15\nget r0 d0 11\nbne r0 r15 Other\npoke 9 r15\nj Loop\nOther:\nput d1 10 r15\n"
                     "WaitB:\nyield\nget r0 d1 11\nbne r0 r15 WaitB\nj Loop\n")
ck(unblocked(MISMATCH) == [("d0", 6, "posts to d1", 12)],
   f"a caller posting elsewhere on its mismatch edge was not reported, or its match edge was: {unblocked(MISMATCH)}")
MATCHED = ACCEPT + "put d0 10 r15\nWaitA:\nyield\nget r0 d0 11\nbeq r0 r15 Done\nj WaitA\nDone:\npoke 9 r15\nj Loop\n"
ck(unblocked(MATCHED) == [], f"a wait taken through beq was not read as the match: {unblocked(MATCHED)}")
CLOBBERED = ACCEPT + "put d0 10 r15\nget r0 d0 11\nmove r0 1\nbne r0 r15 Loop\npoke 9 r15\nj Loop\n"
ck(unblocked(CLOBBERED) == [("d0", 6, "replies to its own caller", 10)],
   f"a token read that was overwritten before its compare counted as the wait: {unblocked(CLOBBERED)}")
LITERAL = ACCEPT + "put d0 10 r15\nWaitA:\nyield\nget r0 d0 11\nbeq r0 0 WaitA\npoke 9 r15\nj Loop\n"
ck(unblocked(LITERAL) == [("d0", 6, "replies to its own caller", 11)],
   f"a compare of the token against a literal counted as the match: {unblocked(LITERAL)}")
# A second post to the same peer replaces the program's own request and strands
# nobody; the token is not this check's business.
REPOST = ACCEPT + "put d0 10 r15\nput d0 10 r15\nWaitA:\nyield\nget r0 d0 11\nbne r0 r15 WaitA\npoke 9 r15\nj Loop\n"
ck(unblocked(REPOST) == [], f"a second post to the same peer was reported: {unblocked(REPOST)}")

# A register-indexed port is the pins its register can hold; a wait on the same
# set answers a post on it, and an unresolved one is no port at all.
INDEXED = ACCEPT + "get r9 db 12\nput dr9 10 r15\nWait:\nyield\nget r0 dr9 11\nbne r0 r15 Wait\npoke 9 r15\nj Loop\n"
indexed = RequestBlocking(INDEXED, PEERS, OWN_REPLY, register_ports={"dr9": ("d0", "d1")})
ck(indexed.posts == 1 and indexed.findings() == [], "a post and wait through dr9 did not pair up")
ck(RequestBlocking(INDEXED, PEERS, OWN_REPLY).posts == 0, "an unresolved dr9 was read as a port")
MIXED = ACCEPT + "get r9 db 12\nput dr9 10 r15\nput d0 10 r15\nWait:\nyield\nget r0 dr9 11\nbne r0 r15 Wait\npoke 9 r15\nj Loop\n"
ck(unblocked(MIXED, register_ports={"dr9": ("d0", "d1")}) == [("d0/d1", 7, "posts to d0", 8)],
   f"a post on one pin of dr9's set was not told from the post on the set: {unblocked(MIXED, register_ports={'dr9': ('d0', 'd1')})}")

# A register-addressed write is a post only where the contract's proven write
# range for the port reaches a request cell.
DYNAMIC = ACCEPT + "move r1 10\nput d0 r1 r15\npoke 9 r15\nj Loop\n"
ck(unblocked(DYNAMIC) == [], f"a register-addressed write on a port whose range stays below the token was a post: {unblocked(DYNAMIC)}")
reaching = {"d0": PortTokens(frozenset({10}), frozenset({11}), True)}
ck(unblocked(DYNAMIC, reaching) == [("d0", 7, "replies to its own caller", 8)],
   f"a register-addressed write whose range reaches the token was not a post: {unblocked(DYNAMIC, reaching)}")

# Token cells come from the reviewed layouts behind the contracts: a
# LIVE_CURRENT producer answers at its current token.
LAYOUT = {"own_stack": {"fields": [
    {"address": 8, "role": "request_token"}, {"address": 9, "role": "response_token"},
    {"address": 10, "role": "current_token"}, {"address": 11, "role": "state"}, {"address": 0}]}}
ck(token_cells(LAYOUT) == (frozenset({8}), frozenset({9, 10})), "token roles were not read from the layout")
ck(own_response_cells(LAYOUT) == frozenset({9, 10}), "a program's answering cells are its response and current tokens")
CALLER = {"device_ports": [
    {"port": "d0", "stack": {"dynamic_write": True, "dynamic_write_ranges": [{"start": 4, "end": 8}]}},
    {"port": "d1", "stack": {"dynamic_write": False, "dynamic_write_ranges": []}}]}
CALLER_WIRING = {"ports": {"ic10/x/caller.ic10": {
    "d0": {"kind": "script", "providers": ["ic10/x/peer.ic10"]},
    "d1": {"kind": "script", "providers": ["ic10/x/peer.ic10", "ic10/x/unknown.ic10"]},
    "d2": {"kind": "device", "device": "Pump"}}}}
tokens = port_tokens("ic10/x/caller.ic10", CALLER, CALLER_WIRING, {"ic10/x/peer.ic10": LAYOUT})
ck(tokens == {"d0": PortTokens(frozenset({8}), frozenset({9, 10}), True),
              "d1": PortTokens(frozenset({8}), frozenset({9, 10}), False)},
   f"port tokens did not follow the wiring to the peer's layout, with the write range reaching d0's token: {tokens}")

# The tree a serial claim rests on is the root and every hop down to a writer;
# the check runs on those and its findings name the group they break.
ck(serialized_tree(writer_edges(WIRING, PORTS), ROOT_P, [A, B]) == {ROOT_P, A, B},
   "the serialized tree did not stop at the writers")
asked = []


def blocking(path):
    asked.append(path)
    return ["posts to d0 at line 6 `put d0 10 r1` and posts to d1 at line 7 `put d1 10 r1`"] if path == A else []


found = failing(serial, blocking=blocking)
ck(found == [f"{A}: posts to d0 at line 6 `put d0 10 r1` and posts to d1 at line 7 `put d1 10 r1`;"
             f" {P}'s serial group is serialized by {ROOT_P} through it, which needs every post on the tree"
             " answered before the next"],
   f"a writer that does not wait did not fail its serial group: {found}")
ck(sorted(asked) == sorted([ROOT_P, A, B]), f"the walk ran on programs off the tree or missed one on it: {asked}")
ck(failing(serial, blocking=lambda path: []) == [], "a tree whose every program waits failed")

# On the tree: the Dispatch Sweep posts to the Flow Builder and returns to its
# loop head, which dispatches on S20 to the block that waits; with that dispatch
# removed the next tick asks the Sink Selector with the Flow Builder's request
# in flight. The Single-Hop Builder holds one Allocator COMMIT at a time behind
# its wait state; with that state's dispatch removed a directory generation
# change replies to the Plan Builder with the COMMIT outstanding, which is what
# the shipped Builder did before #146.
SWEEP = src("ic10/power-grid/power_dispatch_sweep_v1_0.ic10")
SWEEP_PEERS = {"d0": PortTokens(frozenset({13}), frozenset({14})), "d1": PortTokens(frozenset({15}), frozenset({16})),
               "d2": PortTokens(frozenset({10}), frozenset({11}))}


def sweep_unblocked(source):
    return sorted((item.port, item.offence, item.offence_text)
                  for item in RequestBlocking(source, SWEEP_PEERS, frozenset({9}), frozenset({20})).findings())


ck(sweep_unblocked(SWEEP) == [], f"the Sweep does not wait on each post: {sweep_unblocked(SWEEP)}")
ck(sweep_unblocked(without_lines(SWEEP, "beq r0 2 WaitFlow")) == [
    ("d1", "posts to d0", "put d0 13 r15"), ("d1", "replies to its own caller", "poke 9 r15")],
   "the Sweep without its WaitFlow dispatch did not post to the Sink Selector with the Flow Builder's request in flight")
BUILDER = src("ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10")
BUILDER_PEERS = {"d0": PortTokens(frozenset({14}), frozenset({15})), "d1": PortTokens(frozenset({18}), frozenset({9}))}


def builder_unblocked(source):
    return sorted((item.port, item.code_text, item.offence, item.offence_text)
                  for item in RequestBlocking(source, BUILDER_PEERS, frozenset({11})).findings())


ck(builder_unblocked(BUILDER) == [], f"the Single-Hop Builder does not wait on its Allocator request: {builder_unblocked(BUILDER)}")
ck("put d1 18 r13\nmove r14 2\nj Loop\n" in BUILDER and "beqz r14 New\nbeq r14 2 Wait\n" in BUILDER,
   "the Builder no longer arms its wait state at the post and dispatches on it first")
ck(builder_unblocked(without_lines(BUILDER, "beq r14 2 Wait")) == [("d1", "put d1 18 r13", "replies to its own caller", "poke 11 r15")],
   "the Builder without its wait dispatch did not reply with the Allocator's COMMIT outstanding")

# --- The race, on the production programs ------------------------------------------
#
# Two independent loops posting to one Claim View instance: the stock-target Future
# View asks once per active matching job, the Plan Builder asks once for a plan. The
# Claim View answers the token it finds when it polls, so whichever request landed
# second before that poll is served and the other caller waits for a response that
# never comes. A second Claim View instance, the deployment the arbitration
# declares, serves both.


def boot(path, screws=None, ref=999):
    vm = IC10(src(path), screws, self_ref=ref)
    vm.run(1)
    return vm


def stub(magic, token_in, token_out, replies, ref):
    lines = [f'poke 0 HASH("{magic}")', "Loop:", "yield", f"get r15 db {token_in}",
             f"get r0 db {token_out}", "beq r15 r0 Loop"]
    lines += [f"poke {cell} {value}" for cell, value in replies]
    lines += [f"poke {token_out} r15", "j Loop"]
    vm = IC10("\n".join(lines) + "\n", self_ref=ref)
    vm.run(1)
    return vm


def device(vm):
    return Device(vm.self_ref, vm.stack, {"ReferenceId": vm.self_ref})


def publish(store, token, job_type, identity, quantity, priority=0):
    slot = int(store.stack.get(23, 1)) - 1
    base = 32 + 8 * slot
    for offset, value in enumerate((job_type, 0, identity, 1, 1, quantity, priority), 1):
        store.stack[base + offset] = value
    store.stack.update({11: 1, 12: slot, 19: token})
    store.run(1)


RESOURCE = 999
FUTURE_TOKEN = 66
BUILDER_TOKEN = 55


def claim_topology(instances):
    store = boot("ic10/generic-jobs/generic_job_store_v1_0.ic10", ref=300)
    for job in range(3):
        publish(store, 100 + job, 2, RESOURCE, 5)
    plan = boot("ic10/dependency-planning/dependency_plan_store_v2_0.ic10", ref=301)
    validity = stub("DependencyChildValidity.v1", 15, 16, [(17, 1)], 302)
    creator = stub("DependencyChildCreator.v2", 22, 23, [(24, 1), (25, 41), (27, 10)], 303)
    views = [boot("ic10/dependency-planning/dependency_claim_view_v1_0.ic10",
                  {"d0": device(plan), "d1": device(validity)}, ref=310 + index)
             for index in range(instances)]
    builder = boot("ic10/dependency-planning/dependency_plan_builder_v2_0.ic10",
                   {"d0": device(views[0]), "d1": device(creator)}, ref=320)
    future = boot("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10",
                  {"d0": device(store), "d1": device(views[-1]), "d2": device(plan)}, ref=321)
    builder.stack.update({19: 7, 20: 2, 21: 1, 22: RESOURCE, 23: 1, 24: 1, 25: RESOURCE, 26: 4,
                          30: BUILDER_TOKEN})
    future.stack.update({15: RESOURCE, 16: 2, 17: RESOURCE, 18: 2, 19: FUTURE_TOKEN})
    run_round_robin([future, builder, *views, store, plan, validity, creator], 400)
    return builder, future


def claim_completed(builder, future):
    return (builder.stack.get(31) == BUILDER_TOKEN) + (future.stack.get(20) == FUTURE_TOKEN)


shared_builder, shared_future = claim_topology(1)
ck(claim_completed(shared_builder, shared_future) == 1,
   "one Claim View serving the Future View's loop and the Plan Builder did not strand exactly one of them")
own_builder, own_future = claim_topology(2)
ck(claim_completed(own_builder, own_future) == 2,
   "a Claim View per caller did not answer both")
ck(own_builder.stack.get(32) == 1 and own_builder.stack.get(33) == 41 and own_builder.stack.get(35) == 0,
   "the Plan Builder's answer did not carry its own child creation")
ck(own_future.stack.get(21) == 1 and own_future.stack.get(22) == 30,
   "the Future View's answer did not carry its own three-root sum")

# The same shape on the Item Producer Resolver, the mailbox docs/STOCK_TARGET_INGRESS.md
# once said Producer View was the only writer of: Child Creator posts there too.
IRON = -1301215609
PRODUCER_TOKEN = 77
CREATOR_TOKEN = 88


def resolver_topology(instances):
    resolvers = [boot("ic10/dependency-planning/item_producer_resolver_v1_0.ic10", ref=400 + index)
                 for index in range(instances)]
    requirement = [stub("JobRequirementView.v1", 19, 20,
                        [(21, 1), (22, 0), (23, 1), (24, IRON), (25, 2)], 410 + index)
                   for index in range(2)]
    ancestry = stub("DependencyAncestryGuard.v1", 15, 16, [(17, 1)], 412)
    gateway = stub("GenericJobCommandGateway.v5", 48, 49, [(50, 1), (51, 42), (52, 3)], 413)
    producer = boot("ic10/manufacturing-ingress/stock_target_producer_view_v1_0.ic10",
                    {"d0": device(resolvers[0]), "d1": device(requirement[0])}, ref=420)
    creator = boot("ic10/dependency-planning/dependency_child_creator_v2_0.ic10",
                   {"d0": device(resolvers[-1]), "d1": device(requirement[1]),
                    "d2": device(ancestry), "d3": device(gateway)}, ref=421)
    producer.stack.update({15: IRON, 18: PRODUCER_TOKEN})
    creator.stack.update({14: 7, 15: 1, 16: 0, 17: 1, 18: 1, 19: 0, 20: IRON, 21: 6, 22: CREATOR_TOKEN})
    run_round_robin([producer, creator, *resolvers, *requirement, ancestry, gateway], 60)
    return producer, creator


def resolver_completed(producer, creator):
    return (producer.stack.get(19) == PRODUCER_TOKEN) + (creator.stack.get(23) == CREATOR_TOKEN)


shared_producer, shared_creator = resolver_topology(1)
ck(resolver_completed(shared_producer, shared_creator) == 1,
   "one Item Producer Resolver serving Producer View and Child Creator did not strand exactly one of them")
own_producer, own_creator = resolver_topology(2)
ck(resolver_completed(own_producer, own_creator) == 2,
   "a Resolver per caller did not answer both")
ck(own_producer.stack.get(20) == 1 and own_producer.stack.get(21) == 1
   and own_producer.stack.get(23) == "HASH:SmeltIron" and own_producer.stack.get(26) == 2,
   "Producer View's answer did not carry its own producer resolution")
ck(own_creator.stack.get(24) == 1 and own_creator.stack.get(25) == 42 and own_creator.stack.get(27) == 6,
   "Child Creator's answer did not carry its own child")

if fails:
    print("Mailbox arbitration: FAIL")
    for failure in fails:
        print(" -", failure)
    sys.exit(1)

print("Mailbox arbitration: PASS")
print(" - a contended mailbox needs a declaration; laned and single-writer mailboxes refuse one")
print(" - serial groups must sit downstream of their root, with dr-port edges named and checked")
print(" - every program on a serialized tree reads a peer's response token before it posts elsewhere or replies,"
      " followed through a private state cell's dispatch; the Sweep and the Single-Hop Builder fail without theirs")
print(" - dedicated instances partition the writers and are named, with their closure, in the cited document")
print(" - one Claim View shared by the Future View's loop and the Plan Builder strands one caller; one per caller answers both")
print(" - one Item Producer Resolver shared by Producer View and Child Creator strands one caller; one per caller answers both")
