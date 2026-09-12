#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import math
import sys

from framework.async_request import posting_token
from framework.fault_injection import Step, inject_every_boundary
from framework.ic10_harness import Device, IC10, run_round_robin

R = _PROJECT_ROOT
fails = []


def ck(value, message):
    if not value:
        fails.append(message)


def src(path):
    return (R / path).read_text()


def batches(target, stock, future, hysteresis, output_per_batch):
    deficit = target - stock - future
    return 0 if deficit <= hysteresis else math.ceil(deficit / output_per_batch)


ck(batches(50, 50, 0, 5, 1) == 0, "sufficient stock ordered work")
ck(batches(50, 46, 0, 5, 1) == 0, "hysteresis band ordered work")
ck(batches(50, 44, 0, 5, 1) == 6, "exact deficit did not refill to target")
ck(batches(50, 30, 16, 3, 2) == 2, "future output was not subtracted")

# Run the production Config Policy through an executable disabled-record commit.
config_host = Device(490, {
    0: "HASH:GenericPersistentConfigHost.v1", 13: 4, 20: 0, 52: 1, 53: 0,
    128: 0, 129: 10, 130: 1, 131: 9,
})
config_policy = IC10(
    src("ic10/manufacturing-ingress/stock_target_config_policy_v1_0.ic10"),
    {"d0": config_host}, self_ref=491,
)
config_policy.run(3)
ck(config_host.stack.get(20) == 1 and config_host.stack.get(21) == 5,
   "production Config Policy did not accept a disabled stock target")
ck(all(config_host.stack.get(cell) == 0 for cell in range(128, 132)),
   "production Config Policy did not canonicalize a disabled target")

# An insufficient selector quote is usable only when every contributing
# endpoint says its quantity is exact. A lower-bound endpoint must surface as
# ambiguity so the evaluator cannot turn an unknown stock level into a job.
selector_stub = IC10("""
poke 0 HASH("ItemResourceReservationSelector.v1")
Loop:
yield
get r15 db 15
get r0 db 16
beq r15 r0 Loop
poke 8 -2
poke 9 6
poke 10 1
poke 32 501
poke 34 1
poke 16 r15
j Loop
""")
selector_stub.run(1)
lower_bound_endpoint = Device(501, {11: 8, 12: 1}, {"ReferenceId": 501})
inventory = IC10(
    src("ic10/manufacturing-ingress/stock_target_inventory_view_v1_0.ic10"),
    {"d0": Device(500, selector_stub.stack), "x0": lower_bound_endpoint}, self_ref=502,
)
inventory.run(1)
inventory.stack.update({15: 321, 16: 10, 18: 7, 22: 400})
run_round_robin([inventory, selector_stub], 30)
ck(inventory.stack.get(19) == 7 and inventory.stack.get(20) == 2,
   "lower-bound inventory was treated as an exact deficit")
ck(selector_stub.stack.get(15) == 401,
   "Inventory View selector token was derived from a collision-prone outer token")

# The selector's leg count is a peer-published value bounded at six by the
# selector's own contract; the Inventory View bounds it again before walking
# the quote table, because a count of seven would read S50 and S52, past the
# table, and sum whatever sat there as a seventh leg.


def without_guard(path, *lines):
    text = src(path)
    for line in lines:
        ck(line + "\n" in text, f"{path} lost its count guard `{line}`")
        text = text.replace(line + "\n", "")
    return text


def seven_leg_quote(source):
    stub = IC10(
        'poke 0 HASH("ItemResourceReservationSelector.v1")\nLoop:\nyield\nget r15 db 15\n'
        "get r0 db 16\nbeq r15 r0 Loop\npoke 8 -2\npoke 9 6\npoke 10 7\npoke 16 r15\nj Loop\n"
    )
    stub.run(1)
    for leg in range(7):
        stub.stack[32 + 3 * leg] = 511 + leg
        stub.stack[34 + 3 * leg] = 1
    legs = {f"x{leg}": Device(511 + leg, {11: 0, 12: 1}, {"ReferenceId": 511 + leg})
            for leg in range(7)}
    view = IC10(source, {"d0": Device(510, stub.stack), **legs}, self_ref=509)
    view.run(1)
    view.stack.update({15: 321, 16: 10, 18: 7, 22: 400})
    run_round_robin([view, stub], 30)
    return view.stack.get(20)


inventory_view = "ic10/manufacturing-ingress/stock_target_inventory_view_v1_0.ic10"
ck(seven_leg_quote(without_guard(inventory_view, "blt r7 0 Bad", "bgt r7 6 Bad")) == 1,
   "witness: the unguarded Inventory View did not accept a seven-leg quote as exact")
ck(seven_leg_quote(src(inventory_view)) == -1,
   "Inventory View walked a quote past the six-leg table the selector publishes")


def boot_store():
    vm = IC10(src("ic10/generic-jobs/generic_job_store_v1_0.ic10"))
    vm.run(1)
    return vm


def publish(store, token, job_type, identity, quantity, priority=0):
    slot = int(store.stack.get(23, 1)) - 1
    base = 32 + 8 * slot
    for offset, value in enumerate((job_type, 0, identity, 1, 1, quantity, priority), 1):
        store.stack[base + offset] = value
    store.stack.update({11: 1, 12: slot, 19: token})
    store.run(1)
    return int(store.stack.get(10, 0))


# Lane E atomically publishes one root against both observed Store sequences.
store = boot_store()
plan = IC10(src("ic10/dependency-planning/dependency_plan_store_v2_0.ic10"))
plan.run(1)
sdev = Device(100, store.stack, {"ReferenceId": 100})
pdev = Device(101, plan.stack, {"ReferenceId": 101})
executor = IC10(
    src("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10"),
    {"d0": sdev, "d1": pdev}, self_ref=102,
)
executor.run(1)
edev = Device(102, executor.stack, {"ReferenceId": 102})
gateway = IC10(
    src("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10"),
    {"d0": edev}, self_ref=103,
)
gateway.run(1)
job_seq = int(store.stack.get(16, 0))
plan_seq = int(plan.stack.get(40, 0))
gateway.stack.update({
    85: job_seq, 86: plan_seq, 87: 2, 88: 0, 89: 777,
    90: 1, 91: 1, 92: 6, 93: 9, 80: 10,
})
run_round_robin([gateway, executor, store], 50)
ck(gateway.stack.get(81) == 10 and gateway.stack.get(82) == 1,
   "lane E root publication did not acknowledge")
ck(gateway.stack.get(83) == 1 and gateway.stack.get(84) == 0,
   "lane E returned the wrong root identity or slot")
ck(store.stack.get(33) == 2 and store.stack.get(35) == 777 and store.stack.get(38) == 6,
   "lane E staged the wrong immutable root intent")

# A second target evaluated against the same snapshots loses the atomic race.
next_id = int(store.stack.get(23, 0))
gateway.stack.update({80: 11})
run_round_robin([gateway, executor, store], 40)
ck(gateway.stack.get(81) == 11 and gateway.stack.get(82) != 1,
   "stale target snapshots double-published a root")
ck(int(store.stack.get(23, 0)) == next_id, "stale root request consumed a JobId")

# Reflash after Gateway staging reissues the same internal token exactly once.
store2 = boot_store()
plan2 = IC10(src("ic10/dependency-planning/dependency_plan_store_v2_0.ic10"))
plan2.run(1)
executor2 = IC10(
    src("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10"),
    {"d0": Device(110, store2.stack), "d1": Device(111, plan2.stack)}, self_ref=112,
)
executor2.run(1)
edev2 = Device(112, executor2.stack)
gateway2 = IC10(src("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10"),
                {"d0": edev2}, self_ref=113)
gateway2.run(1)
gateway2.stack.update({85: 0, 86: 0, 87: 2, 88: 0, 89: 888,
                       90: 1, 91: 1, 92: 2, 93: 1, 80: 20})
gateway2.run(2)
resumed = IC10(src("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10"),
               {"d0": edev2}, self_ref=113)
resumed.stack.update(gateway2.stack)
resumed.run(1)
run_round_robin([resumed, executor2, store2], 50)
ck(resumed.stack.get(81) == 20 and resumed.stack.get(82) == 1,
   "Gateway reflash stranded an in-flight root")
ck(int(store2.stack.get(23, 0)) == 2, "Gateway replay duplicated an in-flight root")

# Future View counts roots at full output and children only at unclaimed surplus.
store3 = boot_store()
publish(store3, 1, 2, 999, 4)
publish(store3, 2, 2, 999, 5)
claim_stub = IC10("""
poke 0 HASH("DependencyClaimView.v1")
Loop:
yield
get r15 db 18
get r0 db 19
beq r15 r0 Loop
get r0 db 17
bne r0 2 Root
poke 20 1
poke 21 2
poke 22 10
poke 25 321
poke 27 7
j Reply
Root:
poke 20 -2
Reply:
poke 19 r15
j Loop
""")
claim_stub.run(1)
future = IC10(
    src("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10"),
    {"d0": Device(120, store3.stack), "d1": Device(121, claim_stub.stack),
     "d2": Device(122, {0: "HASH:DependencyPlanStore.v2", 40: 0})}, self_ref=123,
)
future.run(1)
future.stack.update({15: 321, 16: 2, 17: 999, 18: 2, 19: 30})
run_round_robin([future, claim_stub], 100)
ck(future.stack.get(20) == 30 and future.stack.get(21) == 1,
   "future-output scan did not complete")
ck(future.stack.get(22) == 11, "future-output scan double-counted claimed child output")

# A job is a root only when the real Claim View proves no active claim names it.
# A plan record that names the job as a child but whose child cannot be validated
# is not a root: Claim View answers -3 rather than the no-record -2, and the scan
# reports itself ambiguous instead of counting the full requested output (#122).
RESOURCE = 999


def validity_stub(*replies):
    lines = ['poke 0 HASH("DependencyChildValidity.v1")', "Loop:", "yield",
             "get r15 db 15", "get r0 db 16", "beq r15 r0 Loop"]
    lines += [f"poke {cell} {value}" for cell, value in replies]
    lines += ["poke 16 r15", "j Loop"]
    vm = IC10("\n".join(lines) + "\n", self_ref=132)
    vm.run(1)
    return vm


def claim_over(store, validity, child_record):
    """A real Plan Store, holding one record naming the Store's first job as a child when asked,
    and a real Claim View over it and `validity`."""
    plan = IC10(src("ic10/dependency-planning/dependency_plan_store_v2_0.ic10"), self_ref=131)
    plan.run(1)
    if child_record:
        # [ParentJobId, ChildJobId, ResourceType, RequiredTotal, BaselineKnown, FutureQty, fpA, fpB]
        record = (9, int(store.stack[32]), RESOURCE, 6, 2, 8, 0, 0)
        plan.stack.update({128 + offset: value for offset, value in enumerate(record)})
    claim = IC10(src("ic10/dependency-planning/dependency_claim_view_v1_0.ic10"),
                 {"d0": Device(131, plan.stack), "d1": Device(132, validity.stack)}, self_ref=133)
    claim.run(1)
    return plan, claim


def claim_scan(child_record, validity, token, store=None, behind=()):
    """Real Job Store, Plan Store, Claim View, and Future View. Child Validity is a stub unless
    `store` already holds the job and `behind` runs the Monitor and Requirement View under a
    real Child Validity."""
    if store is None:
        store = boot_store()
        publish(store, 1, 2, RESOURCE, 5)
    plan, claim = claim_over(store, validity, child_record)
    future = IC10(src("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10"),
                  {"d0": Device(130, store.stack), "d1": Device(133, claim.stack),
                   "d2": Device(131, plan.stack)}, self_ref=134)
    future.run(1)
    future.stack.update({15: RESOURCE, 16: 2, 17: RESOURCE, 18: 2, 19: token})
    run_round_robin([future, claim, validity, *behind, plan, store], 120)
    return claim, future


claim, future = claim_scan(False, validity_stub((17, 1)), 40)
ck(future.stack.get(20) == 40 and future.stack.get(21) == 1 and future.stack.get(22) == 10,
   "a job no plan record names was not counted as a root at full output")
ck(claim.stack.get(20) == -2, "Claim View did not report a proven absence as -2")
claim, future = claim_scan(True, validity_stub((17, 1), (19, 2), (20, 1), (23, RESOURCE)), 41)
ck(future.stack.get(20) == 41 and future.stack.get(21) == 1 and future.stack.get(22) == 4,
   "a validated child was not counted at FutureQty minus the other parents' claims")
claim, future = claim_scan(True, validity_stub((17, 1), (19, 7), (20, 1), (23, RESOURCE)), 42)
ck(claim.stack.get(20) == -2, "a validated terminal child was not reported as no active claim")
for status in (-1, -2, -3):
    claim, future = claim_scan(True, validity_stub((17, status)), 50 + status)
    ck(claim.stack.get(20) == -3,
       f"Claim View collapsed an unverifiable child (Child Validity {status}) into the no-record answer")
    ck(future.stack.get(20) == 50 + status and future.stack.get(21) == -3,
       f"Future View did not report an unverifiable child (Child Validity {status}) as ambiguous")
    ck(future.stack.get(22, 0) == 0,
       f"Future View counted root output for an unverifiable child (Child Validity {status})")


# The stubs above encode what the Claim View reads of Child Validity. The real chain has to
# agree with it: the Monitor publishes State and JobGeneration at S22 and S23, Child Validity
# copies them to its S19 and S20 and publishes the child's ResourceType at S23, and the Claim
# View republishes that ResourceType at S25 for the Future View's check. The Monitor used to
# publish State one cell lower, and the Claim View read the child's JobGeneration as its
# ResourceType, so every live child failed the Future View's check (#193).
def set_state(store, token, slot, new_state):
    base = 288 + 7 * slot
    generation = int(store.stack.get(base + 2 + 3 * int(store.stack.get(base, 0)), 0))
    store.stack.update({11: 2, 12: slot, 13: generation, 14: new_state, 15: 0, 19: token})
    store.run(1)


def real_validity(child_edges, promised_resource):
    """A real Monitor and Child Validity over a Job Store whose only job walked `child_edges`;
    the Requirement View behind them reports `promised_resource` as the child's output."""
    store = boot_store()
    publish(store, 1, 2, RESOURCE, 5)
    for token, new_state in enumerate(child_edges, 2):
        set_state(store, token, 0, new_state)
    monitor = IC10(src("ic10/dependency-planning/generic_job_monitor_v1_0.ic10"),
                   {"d0": Device(130, store.stack)}, self_ref=135)
    monitor.run(1)
    requirement = IC10("\n".join([
        'poke 0 HASH("JobRequirementView.v1")', "Loop:", "yield", "get r15 db 19", "get r0 db 20",
        "beq r15 r0 Loop", "poke 21 1", "poke 22 0", "poke 23 1", f"poke 24 {promised_resource}",
        "poke 25 1", "poke 20 r15", "j Loop"]) + "\n", self_ref=136)
    requirement.run(1)
    validity = IC10(src("ic10/dependency-planning/dependency_child_validity_v1_0.ic10"),
                    {"d0": Device(135, monitor.stack), "d1": Device(136, requirement.stack)}, self_ref=132)
    validity.run(1)
    return store, validity, [monitor, requirement]


store, validity, behind = real_validity([], RESOURCE)
claim, future = claim_scan(True, validity, 43, store=store, behind=behind)
ck(validity.stack.get(17) == 1 and tuple(validity.stack.get(c) for c in (19, 20, 23)) == (1, 1, RESOURCE),
   "Child Validity did not publish the child's State, JobGeneration, and ResourceType at S19, S20, S23")
ck(claim.stack.get(20) == 1 and claim.stack.get(24) == 1 and claim.stack.get(25) == RESOURCE,
   "the Claim View did not republish the live child's ResourceType at S25")
ck(future.stack.get(20) == 43 and future.stack.get(21) == 1 and future.stack.get(22) == 4,
   "the Future View did not count the live child the real chain validated")
store, validity, behind = real_validity([], RESOURCE + 1)
claim, future = claim_scan(True, validity, 44, store=store, behind=behind)
ck(validity.stack.get(17) == -3 and claim.stack.get(20) == -3 and future.stack.get(21) == -3,
   "a live child that no longer promises the ResourceType was counted")
# The Future View skips a COMPLETE job itself; the Plan Builder asks the Claim View directly.
store, validity, behind = real_validity([2, 3, 4, 5, 6, 7], RESOURCE)
plan, claim = claim_over(store, validity, True)
claim.stack.update({15: RESOURCE, 16: 1, 17: 0, 18: 45})
run_round_robin([claim, validity, *behind, plan], 120)
ck(validity.stack.get(17) == 1 and validity.stack.get(19) == 7 and claim.stack.get(19) == 45
   and claim.stack.get(20) == -2,
   "a COMPLETE child the real chain validated was offered for reuse")


# A Plan Store change after Child Validity has answered restarts the Claim View's
# scan, and the restart posts for the same record again. The token used to be
# derived from the record's address, so the repost carried the token Child Validity
# had already answered: its gate saw request and response equal and never latched,
# the Claim View's wait passed on its first poll, and the Claim View consumed the
# reply from before the change. Each posting under one request now carries a
# counter, so the repost is served on its own (#148). Child Validity here answers
# valid once and invalid afterwards, and counts its requests in S30.
def counting_validity(first, later):
    lines = ['poke 0 HASH("DependencyChildValidity.v1")', "Loop:", "yield", "get r15 db 15",
             "get r0 db 16", "beq r15 r0 Loop", "get r0 db 30", "add r0 r0 1", "poke 30 r0",
             f"poke 17 {later}", "bgt r0 1 Answer", f"poke 17 {first}", "poke 19 2",
             f"poke 20 {RESOURCE}", "Answer:", "poke 16 r15", "j Loop"]
    vm = IC10("\n".join(lines) + "\n", self_ref=142)
    vm.run(1)
    return vm


def claim_plan():
    """A Plan Store holding one record: parent 9 plans child 3 for RESOURCE."""
    return Device(141, {0: "HASH:DependencyPlanStore.v2", 40: 0,
                        128: 9, 129: 3, 130: RESOURCE, 131: 6, 132: 2, 133: 8, 134: 0, 135: 0})


def restarted_claim_scan(source, validity, token):
    """One plan record naming child 3; the Plan Store moves by one mutation after the first reply."""
    plan = claim_plan()
    claim = IC10(source, {"d0": plan, "d1": Device(142, validity.stack)}, self_ref=143)
    claim.run(1)
    claim.stack.update({15: RESOURCE, 16: 1, 17: 0, 18: token})
    for _ in range(40):
        run_round_robin([claim, validity], 1)
        if validity.stack.get(30) == 1:
            break
    first_token = validity.stack.get(15)
    plan.stack[40] += 2
    run_round_robin([claim, validity], 60)
    return claim, first_token


claim_view = "ic10/dependency-planning/dependency_claim_view_v1_0.ic10"
COUNTED_POST = ("get r5 db 28\nadd r5 r5 1\nbge r5 512 Bad\npoke 28 r5\nput d1 13 r9\nput d1 14 r2\n"
                "mul r13 r15 512\nadd r13 r13 r5\n")
POSITIONAL_POST = "put d1 13 r9\nput d1 14 r2\nmul r13 r15 512\nadd r13 r13 r7\nadd r13 r13 1\n"
ck(COUNTED_POST in src(claim_view), "the Claim View's posting counter is not where the test expects")
validity = counting_validity(1, -1)
claim, first_token = restarted_claim_scan(src(claim_view), validity, 7)
ck(first_token == posting_token(7, 1) and validity.stack.get(15) == posting_token(7, 2),
   "the Claim View's postings under one request did not carry the first and second posting tokens")
ck(validity.stack.get(30) == 2, "Child Validity did not latch the Claim View's posting after the restart")
ck(claim.stack.get(19) == 7 and claim.stack.get(20) == -3,
   "the Claim View did not answer from Child Validity's reply to the restarted posting")
claim.stack[18] = 8
run_round_robin([claim, validity], 60)
ck(claim.stack.get(19) == 8 and validity.stack.get(15) == posting_token(8, 1),
   "the Claim View's posting counter did not restart with the next request")
validity = counting_validity(1, -1)
claim, first_token = restarted_claim_scan(src(claim_view).replace(COUNTED_POST, POSITIONAL_POST), validity, 7)
ck(first_token == 3713 and validity.stack.get(30) == 1 and claim.stack.get(20) == 1,
   "witness: under the positional token the restarted Claim View did not consume the earlier reply")

# A Claim View reflashed while serving a request finds its posting count in S28, so the
# image that resumes the request posts the next token rather than the first one again.
# The campaign cuts the service of one request after every Claim View instruction,
# reflashes a fresh image over the same stack, and runs it to the answer: Child Validity
# latches exactly one more posting unless the request was already answered, the answer
# follows its last reply, and the count is cleared. A count kept in a register (#181) or
# a token derived from the position (before it) repeats the first token after every cut
# between Child Validity's first reply and the answer, and inherits that reply (#182).
class ClaimScan:
    def __init__(self, source):
        self.source = source
        self.validity = counting_validity(1, -1)
        self.claim = IC10(source, {"d0": claim_plan(), "d1": Device(142, self.validity.stack)}, self_ref=143)
        self.claim.run(1)
        self.claim.stack.update({15: RESOURCE, 16: 1, 17: 0, 18: 7})

    def step(self):
        if self.claim.run(1, instruction_quantum=1) == "yield":
            self.validity.run_tick()

    def answered(self):
        return self.claim.stack.get(19) == 7

    def latched(self):
        return int(self.validity.stack.get(30, 0))

    def reflash(self, cut):
        self.before = (self.latched(), self.answered())
        fresh = IC10(self.source, self.claim.screws, self_ref=143)
        fresh.stack = self.claim.stack
        fresh.run(1)
        self.claim = fresh
        run_round_robin([self.claim, self.validity], 60)
        return self


def reflash_every_instruction(source):
    """Per cut: (latched before, answered before, latched after, status after, S28 after)."""
    reference = ClaimScan(source)
    steps = []
    while not reference.answered():
        reference.step()
        steps.append(Step(f"instruction {len(steps) + 1}", ClaimScan.step))
    outcomes = []

    def record(scan, cut):
        outcomes.append(scan.before + (scan.latched(), scan.claim.stack.get(20), scan.claim.stack.get(28)))

    inject_every_boundary(ClaimScan(source), steps, ClaimScan.reflash, record)
    return outcomes


def register_counter(source):
    """The Claim View as #181 left it: the count in r5, seeded at boot and reset at the reply."""
    for old, new in (("poke 2 0\nLoop:\n", "poke 2 0\nmove r5 0\nLoop:\n"), ("beq r15 r0 Reply\n", "beq r15 r0 Loop\n"),
                     ("get r5 db 28\nadd r5 r5 1\nbge r5 512 Bad\npoke 28 r5\n", "add r5 r5 1\nbge r5 512 Bad\n"),
                     ("poke 19 r15\npoke 28 0\nj Loop\n", "move r5 0\npoke 19 r15\nj Loop\n")):
        ck(source.count(old) == 1, f"the Claim View does not hold {old.splitlines()[0]!r} exactly once")
        source = source.replace(old, new)
    return source


outcomes = reflash_every_instruction(src(claim_view))
ck(len(outcomes) > 100 and any(o[:2] == (1, False) for o in outcomes),
   "the reflash campaign never cut between Child Validity's first reply and the Claim View's answer")
ck(all(after == latched + (0 if answered else 1) and status == (1 if after == 1 else -3) and count == 0
       for latched, answered, after, status, count in outcomes),
   "a Claim View reflashed mid-request repeated a token, answered from the wrong reply, or kept its count")
for name, witness in (("register", register_counter(src(claim_view))),
                      ("positional", src(claim_view).replace(COUNTED_POST, POSITIONAL_POST))):
    inherited = [o for o in reflash_every_instruction(witness) if o[:2] == (1, False)]
    ck(inherited and all(o[2:4] == (1, 1) for o in inherited),
       f"witness: the {name} counter did not inherit the first reply after a reflash between it and the answer")

# A housing whose S28 holds another program's state, with no request in flight: the idle
# tick clears the cell before the first request, which counts from 1.
validity = counting_validity(1, -1)
claim = IC10(src(claim_view), {"d0": claim_plan(), "d1": Device(142, validity.stack)}, self_ref=143)
claim.stack[28] = 300
claim.run(1)
run_round_robin([claim, validity], 1)
ck(claim.stack.get(28) == 0, "the idle Claim View did not clear a posting count left on its housing")
claim.stack.update({15: RESOURCE, 16: 1, 17: 0, 18: 7})
run_round_robin([claim, validity], 60)
ck(validity.stack.get(15) == posting_token(7, 1) and claim.stack.get(20) == 1,
   "the first request on a housing that held a stale count did not count from 1")

# The Future View restarts the same way on a Plan Store change and reposts the same
# job to the Claim View; the repost is latched and answered too.
store4 = boot_store()
publish(store4, 1, 2, RESOURCE, 4)
counting_claim = IC10("\n".join([
    'poke 0 HASH("DependencyClaimView.v1")', "Loop:", "yield", "get r15 db 18", "get r0 db 19",
    "beq r15 r0 Loop", "get r0 db 30", "add r0 r0 1", "poke 30 r0", "poke 20 -2", "poke 19 r15",
    "j Loop"]) + "\n", self_ref=151)
counting_claim.run(1)
plan4 = Device(152, {0: "HASH:DependencyPlanStore.v2", 40: 0})
future = IC10(src("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10"),
              {"d0": Device(150, store4.stack), "d1": Device(151, counting_claim.stack), "d2": plan4},
              self_ref=153)
future.run(1)
future.stack.update({15: RESOURCE, 16: 2, 17: RESOURCE, 18: 2, 19: 30})
for _ in range(40):
    run_round_robin([future, counting_claim], 1)
    if counting_claim.stack.get(30) == 1:
        break
plan4.stack[40] += 2
run_round_robin([future, counting_claim], 80)
ck(counting_claim.stack.get(30) == 2 and counting_claim.stack.get(18) == posting_token(30, 2),
   "the Claim View did not latch the Future View's posting after the restart")
ck(future.stack.get(20) == 30 and future.stack.get(21) == 1 and future.stack.get(22) == 8
   and future.stack.get(24) == 2,
   "the restarted Future View did not complete against the moved Plan Store sequence")
# Reflashed between the Claim View's reply and its own answer, the Future View continues
# its count from S25 and the Claim View latches the posting the fresh image makes.
future.stack[19] = 31
for _ in range(40):
    run_round_robin([future, counting_claim], 1)
    if counting_claim.stack.get(30) == 3:
        break
fresh = IC10(src("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10"), future.screws, self_ref=153)
fresh.stack = future.stack
fresh.run(1)
run_round_robin([fresh, counting_claim], 80)
ck(counting_claim.stack.get(30) == 4 and counting_claim.stack.get(18) == posting_token(31, 2),
   "the Claim View did not latch the posting of a Future View reflashed mid-request")
ck(fresh.stack.get(20) == 31 and fresh.stack.get(21) == 1 and fresh.stack.get(25) == 0,
   "the reflashed Future View did not answer its request and clear its count")


def build_pipeline(inventory_changes=False, output_changes=False, evaluator_source=None):
    """Build the production target-to-Store path with only leaf services stubbed."""
    host = Device(200, {
        0: "HASH:GenericPersistentConfigHost.v1", 8: 1,
        12: "HASH:CFG1|ManufacturingStockTarget|1|2|255|255|0|0", 51: 7,
        96: 321, 97: 10, 98: 1, 99: 5,
        **{cell: 0 for cell in range(100, 112)},
    })
    resolver = IC10("""
poke 0 HASH("ItemProducerResolver.v1")
Loop:
yield
get r15 db 9
get r0 db 10
beq r15 r0 Loop
poke 11 1
poke 12 2
poke 13 777
poke 10 r15
j Loop
""")
    requirement_output = """
mod r0 r15 3
bne r0 2 Stable
move r1 3
j Output
Stable:
move r1 2
Output:
""" if output_changes else "move r1 2\n"
    requirement = IC10(f"""
poke 0 HASH("JobRequirementView.v1")
Loop:
yield
get r15 db 19
get r0 db 20
beq r15 r0 Loop
{requirement_output}poke 21 1
poke 22 0
poke 23 1
poke 24 321
poke 25 r1
poke 20 r15
j Loop
""")
    inventory_reply = """
get r0 db 30
add r0 r0 1
poke 30 r0
bgt r0 1 Full
poke 21 0
j InventoryReply
Full:
poke 21 10
InventoryReply:
""" if inventory_changes else "poke 21 0\n"
    inventory_leaf = IC10(f"""
poke 0 HASH("StockTargetInventoryView.v1")
Loop:
yield
get r15 db 18
get r0 db 19
beq r15 r0 Loop
{inventory_reply}poke 20 1
poke 19 r15
j Loop
""")
    claim = IC10("""
poke 0 HASH("DependencyClaimView.v1")
Loop:
yield
get r15 db 18
get r0 db 19
beq r15 r0 Loop
poke 20 -2
poke 19 r15
j Loop
""")
    for leaf in (resolver, requirement, inventory_leaf, claim):
        leaf.run(1)

    live_store = boot_store()
    live_plan = IC10(src("ic10/dependency-planning/dependency_plan_store_v2_0.ic10"))
    live_plan.run(1)
    store_device = Device(210, live_store.stack)
    plan_device = Device(211, live_plan.stack)
    live_executor = IC10(
        src("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10"),
        {"d0": store_device, "d1": plan_device}, self_ref=212,
    )
    live_executor.run(1)
    live_gateway = IC10(
        src("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10"),
        {"d0": Device(212, live_executor.stack)}, self_ref=213,
    )
    live_gateway.run(1)
    producer = IC10(
        src("ic10/manufacturing-ingress/stock_target_producer_view_v1_0.ic10"),
        {"d0": Device(214, resolver.stack), "d1": Device(215, requirement.stack)},
        self_ref=216,
    )
    producer.run(1)
    future_view = IC10(
        src("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10"),
        {"d0": store_device, "d1": Device(217, claim.stack), "d2": plan_device},
        self_ref=218,
    )
    future_view.run(1)
    demand = IC10(
        src("ic10/manufacturing-ingress/stock_target_demand_view_v1_0.ic10"),
        {"d0": Device(219, inventory_leaf.stack), "d1": Device(218, future_view.stack)},
        self_ref=220,
    )
    demand.run(1)
    ingress = IC10(
        src("ic10/manufacturing-ingress/stock_target_job_ingress_v1_0.ic10"),
        {"d0": Device(213, live_gateway.stack), "d1": Device(216, producer.stack),
         "d2": Device(220, demand.stack), "d3": host}, self_ref=221,
    )
    ingress.run(1)
    evaluator = IC10(
        evaluator_source or src("ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10"),
        {"d0": host, "d1": Device(216, producer.stack),
         "d2": Device(220, demand.stack), "d3": Device(221, ingress.stack)},
        self_ref=222,
    )
    evaluator.run(1)
    actors = [evaluator, ingress, producer, demand, future_view, live_gateway,
              live_executor, live_store, live_plan, resolver, requirement,
              inventory_leaf, claim]
    return {"actors": actors, "store": live_store, "evaluator": evaluator,
            "ingress": ingress, "producer": producer, "demand": demand}


def pipeline(**kwargs):
    """Run the production target-to-Store path to completion."""
    built = build_pipeline(**kwargs)
    run_round_robin(built["actors"], 500)
    return built["store"], built["evaluator"]


# The complete production chain creates exactly one root with the fresh deficit.
pipeline_store, pipeline_evaluator = pipeline()
ck(pipeline_store.stack.get(23) == 2,
   "production evaluator-to-Store pipeline did not create exactly one root")
ck(pipeline_store.stack.get(33) == 2 and pipeline_store.stack.get(35) == 777,
   "production pipeline published the wrong root identity")
ck(pipeline_store.stack.get(38) == 5 and pipeline_store.stack.get(39) == 5,
   "production pipeline published the wrong batch quantity or priority")
ck(pipeline_evaluator.stack.get(8) in (0, 1),
   "production evaluator did not remain healthy after publication")

# Mutation-time demand and producer metadata must still match the evaluated proof.
stale_inventory_store, _ = pipeline(inventory_changes=True)
ck(stale_inventory_store.stack.get(23) == 1,
   "inventory becoming sufficient before mutation still published a root")
changed_output_store, _ = pipeline(output_changes=True)
ck(changed_output_store.stack.get(23) == 1,
   "changed output-per-batch metadata still published a root")


# The Demand View holds one request. An Evaluator reflashed while the Ingress
# sits between its lane-B reply and the Demand View's latch used to start a
# fresh evaluation at once and could post into that mailbox in the same tick,
# displacing the Ingress's token: the Demand View served the Evaluator, the
# Ingress waited forever for its reply, and the Evaluator then waited forever
# on the Ingress. The Evaluator now starts no evaluation until the Ingress is
# idle (S25 == S26), so the reflash waits instead of racing (#145).
def reflash_during_ingress(evaluator_source):
    built = build_pipeline(evaluator_source=evaluator_source)
    evaluator, ingress, producer, demand = (built[key] for key in
                                           ("evaluator", "ingress", "producer", "demand"))
    others = built["actors"][4:]
    # Run until the Ingress holds its lane-B reply and will post to the Demand View next.
    for _ in range(200):
        run_round_robin(built["actors"], 1)
        token = ingress.stack.get(25)
        if token and token != ingress.stack.get(26) and producer.stack.get(34) == token:
            break
    else:
        ck(False, "pipeline never reached the Ingress's window before its Demand View post")
        return built, 0, False
    # Reflash the Evaluator over its own stack: same image, so it boots straight to Loop.
    fresh = IC10(evaluator_source, evaluator.screws, self_ref=evaluator.self_ref)
    fresh.stack = evaluator.stack
    fresh.run(1)
    # With the Ingress held, let the fresh Evaluator reach the point of posting to the
    # Demand View: its lane-A reply is ready. A guarded Evaluator never gets there.
    for _ in range(20):
        run_round_robin([fresh, producer, *others], 1)
        if producer.stack.get(19) == fresh.stack.get(30) and fresh.stack.get(30) != token:
            break
    # One tick: the Ingress posts, the Evaluator's slice runs, then the Demand View latches.
    run_round_robin([ingress, fresh, demand, producer, *others], 1)
    displaced = demand.stack.get(23) != 3 * token + 2
    run_round_robin([fresh, ingress, producer, demand, *others], 500)
    built["evaluator"] = fresh
    return built, token, displaced


guarded, guarded_token, guarded_displaced = reflash_during_ingress(
    src("ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10"))
ck(not guarded_displaced,
   "a reflashed Evaluator posted into the Demand View beside the Ingress's request")
ck(guarded["ingress"].stack.get(26) == guarded_token and guarded["ingress"].stack.get(27) == 1,
   "the Ingress did not complete its request after the Evaluator reflash")
ck(guarded["store"].stack.get(23) == 2,
   "the Evaluator reflash lost the root or published a duplicate")
ck(guarded["evaluator"].stack.get(8) == 0,
   "the reflashed Evaluator did not complete an evaluation once the Ingress was idle")
# The same program without its idle check is the race: the Ingress never gets its
# reply, and the root it was about to publish never reaches the Store.
unguarded_source = src("ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10")
ck("bne r0 r1 Loop\n" in unguarded_source, "the Evaluator's idle check is not where the test expects")
unguarded, unguarded_token, unguarded_displaced = reflash_during_ingress(
    unguarded_source.replace("bne r0 r1 Loop\n", ""))
ck(unguarded_displaced and unguarded["ingress"].stack.get(26) != unguarded_token
   and unguarded["store"].stack.get(23) == 1,
   "without the idle check the Evaluator reflash did not strand the Ingress")

if fails:
    print("Stock-target ingress: FAIL")
    for failure in fails:
        print(" -", failure)
    sys.exit(1)

print("Stock-target ingress: PASS")
print(" - sufficient stock, hysteresis, deficit refill, and future-output subtraction")
print(" - production Config Policy canonicalizes disabled stock-target records")
print(" - lane E atomically rejects stale Job/Plan snapshots and survives Gateway reflash")
print(" - active root output and only unclaimed child surplus contribute to stock targets")
print(" - a job counts as a root only when the real Claim View proves no active claim names it;"
      " an unverifiable child makes the scan ambiguous")
print(" - the real Monitor, Child Validity, and Claim View agree on their cells: a live child's"
      " ResourceType reaches the Future View and a COMPLETE child is not reused")
print(" - production evaluator-to-Store flow revalidates demand and output metadata at mutation time")
print(" - an Evaluator reflashed mid-Ingress waits for it instead of displacing its Demand View request")
print(" - the Inventory View bounds the selector leg count at six before walking the quote table")
print(" - a scan the Plan Store restarts posts again under a new token; the callee latches and answers the repost")
print(" - a Claim View or Future View reflashed mid-request continues its posting count from the stack,"
      " so the callee latches the posting the fresh image makes")
