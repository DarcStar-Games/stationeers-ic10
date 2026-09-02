#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import math
import sys

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


def pipeline(inventory_changes=False, output_changes=False):
    """Run the production target-to-Store path with only leaf services stubbed."""
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
        src("ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10"),
        {"d0": host, "d1": Device(216, producer.stack),
         "d2": Device(220, demand.stack), "d3": Device(221, ingress.stack)},
        self_ref=222,
    )
    evaluator.run(1)
    actors = [evaluator, ingress, producer, demand, future_view, live_gateway,
              live_executor, live_store, live_plan, resolver, requirement,
              inventory_leaf, claim]
    run_round_robin(actors, 500)
    return live_store, evaluator


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
print(" - production evaluator-to-Store flow revalidates demand and output metadata at mutation time")
