#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import sys

from framework.ic10_harness import Device, IC10, run_round_robin

R = _PROJECT_ROOT
fails = []


def ck(value, message):
    if not value:
        fails.append(message)


def src(path):
    return (R / path).read_text()


# The panel stages four coherent Resolver snapshots. Commit is a rising edge,
# and a held switch cannot publish another request after the first response.
resolver = Device(100, {0: "HASH:GenericInputResolver.v1", 11: 1})
ingress_mailbox = Device(101, {0: "HASH:OperatorOrderJobIngress.v1", 20: 0})
commit = Device(102, {}, {"Setting": 0})
editor = IC10(src("ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10"),
              {"d0": resolver, "d1": ingress_mailbox, "d2": commit}, self_ref=103)
editor.run(1)
for generation, ordinal, value in (
    (1, 1, 321), (2, 2, 4), (3, 3, 10), (4, 4, 7),
):
    resolver.stack.update({12: generation, 13: ordinal, 14: value})
    editor.run(1)
ck([editor.stack.get(cell) for cell in range(40, 44)] == [321, 4, 10, 7],
   "panel did not stage family/ordinal/quantity/priority")
commit.props["Setting"] = 1
editor.run(2)
token = int(ingress_mailbox.stack.get(19, 0))
ck(token == 1 and [ingress_mailbox.stack.get(cell) for cell in range(15, 19)] == [321, 4, 10, 7],
   "commit edge did not publish one complete order request")
ingress_mailbox.stack.update({20: token, 21: 1, 22: 44, 23: 2})
editor.run(2)
ck(ingress_mailbox.stack.get(19) == token, "held commit switch republished an order")
commit.props["Setting"] = 0
editor.run(1)
commit.props["Setting"] = 1
editor.run(2)
ck(ingress_mailbox.stack.get(19) == token + 1,
   "release and re-commit did not publish a fresh request identity")


def boot_store():
    vm = IC10(src("ic10/generic-jobs/generic_job_store_v1_0.ic10"))
    vm.run(1)
    return vm


def pipeline(family=321, reflash=False, prime_lane_e=False,
             prime_v4_executor=False, prime_v4_gateway=False):
    lookup = IC10("""
poke 0 HASH("RecipeCatalogLookup.v3")
Loop:
yield
get r15 db 15
get r0 db 16
beq r15 r0 Loop
get r0 db 12
bne r0 321 Missing
poke 8 1
poke 9 8
poke 10 777
poke 11 2
j Reply
Missing:
poke 8 -3
poke 9 0
poke 10 0
poke 11 0
Reply:
poke 16 r15
j Loop
""")
    profile = IC10("""
poke 0 HASH("RecipeExecutionProfileView.v1")
Loop:
yield
get r0 db 10
beqz r0 Loop
poke 11 321
poke 12 2
poke 13 3
poke 15 1
poke 49 r0
j Loop
""")
    for leaf in (lookup, profile):
        leaf.run(1)
    recipe = IC10(src("ic10/manufacturing-ingress/operator_order_recipe_view_v1_0.ic10"), {
        "d0": Device(110, lookup.stack), "d1": Device(111, profile.stack),
    }, self_ref=112)
    recipe.run(1)
    # A replaced Ingress must advance from the View's old response identity,
    # rather than accepting stale success from an earlier commissioning session.
    recipe.stack.update({20: 1, 21: 1, 22: 999, 23: 9, 24: 9})
    store = boot_store()
    plan = IC10(src("ic10/dependency-planning/dependency_plan_store_v2_0.ic10"))
    plan.run(1)
    store_device = Device(113, store.stack)
    plan_device = Device(114, plan.stack)
    executor = IC10(src("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10"), {
        "d0": store_device, "d1": plan_device,
    }, self_ref=115)
    executor.run(1)
    if prime_v4_executor:
        # ABI4 encoded client token 37, command 2 as executor token 224.
        executor.stack.update({24: 224, 25: 1, 26: 99, 27: 0})
    gateway = IC10(src("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10"), {
        "d0": Device(115, executor.stack),
    }, self_ref=116)
    if prime_v4_gateway:
        # Supported upgrade path: every ABI4 lane is quiescent before replacement.
        gateway.stack.update({
            0: "HASH:GenericJobCommandGateway.v4", 1: 4,
            8: 7, 19: 7, 32: 8, 33: 8, 48: 9, 49: 9,
            64: 10, 65: 10, 80: 11, 81: 11, 24: 0,
        })
    gateway.run(1)
    if prime_lane_e:
        gateway.stack.update({
            85: 0, 86: 0, 87: 2, 88: 1, 89: 666,
            90: 1, 91: 1, 92: 1, 93: 0, 80: 1,
        })
        run_round_robin([gateway, executor, store], 50)
    ingress_devices = {
        "d0": Device(116, gateway.stack), "d1": Device(112, recipe.stack),
        "d2": store_device, "d3": plan_device,
    }
    ingress = IC10(src("ic10/manufacturing-ingress/operator_order_job_ingress_v1_0.ic10"),
                   ingress_devices, self_ref=117)
    ingress.run(1)
    ingress.stack.update({15: family, 16: 4, 17: 10, 18: 7, 19: 1})
    front = [ingress, recipe, lookup, profile]
    if reflash:
        run_round_robin(front, 20)
        ck(ingress.stack.get(30, 0) > 0, "order did not reach restart-safe Gateway staging")
        resumed = IC10(src("ic10/manufacturing-ingress/operator_order_job_ingress_v1_0.ic10"),
                       ingress_devices, self_ref=117)
        resumed.stack.update(ingress.stack)
        ingress = resumed
    run_round_robin([ingress, recipe, gateway, executor, store, plan, lookup, profile], 100)
    return store, ingress


store, ingress = pipeline(reflash=True, prime_lane_e=True)
ck(store.stack.get(23) == 3, "lane E and same-token lane F did not publish distinct roots")
ck([store.stack.get(cell) for cell in range(41, 48)] == [2, 2, 777, 3, 1, 10, 7],
   "published PRINT intent lost recipe metadata, quantity, or priority")
ck(ingress.stack.get(20) == 1 and ingress.stack.get(21) == 1 and ingress.stack.get(22) == 2,
   "successful order did not return its exact response identity")

upgrade_store, upgrade_ingress = pipeline(
    prime_v4_executor=True, prime_v4_gateway=True,
)
ck(upgrade_store.stack.get(23) == 2 and upgrade_ingress.stack.get(22) == 1,
   "ABI5 lane-F request collided with a persisted ABI4 executor replay token")

missing_store, missing_ingress = pipeline(family=999)
ck(missing_store.stack.get(23) == 1, "unknown recipe family published an unsatisfiable job")
ck(missing_ingress.stack.get(20) == 1 and missing_ingress.stack.get(21) == -3,
   "unknown recipe did not return the distinguishable not-found status")

# A same-stack Editor reflash must reassert a pending token even when the first
# downstream publication was interrupted. It must also retain the consumed edge.
resume_mailbox = Device(118, {0: "HASH:OperatorOrderJobIngress.v1", 19: 0, 20: 0})
resume_switch = Device(119, {}, {"Setting": 1})
resumed_editor = IC10(src("ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10"), {
    "d0": resolver, "d1": resume_mailbox, "d2": resume_switch,
}, self_ref=120)
resumed_editor.stack.update({
    0: "HASH:OperatorOrderEditor.v1", 1: 1, 26: 15, 28: 0, 30: 1,
    40: 321, 41: 4, 42: 10, 43: 7,
})
resumed_editor.run(2)
ck(resume_mailbox.stack.get(19) == 1 and resumed_editor.stack.get(28) == 1,
   "Editor reflash did not reassert an unsent pending commit and consume its edge")
resume_mailbox.stack.update({20: 1, 21: 1, 22: 45, 23: 3})
resumed_editor.run(2)
ck(resume_mailbox.stack.get(19) == 1 and resumed_editor.stack.get(30) == 0,
   "held commit republished after the resumed Editor request completed")

wrong_mailbox = Device(121, {0: "HASH:UnrelatedService.v1", 19: 77})
guarded_editor = IC10(src("ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10"), {
    "d0": resolver, "d1": wrong_mailbox, "d2": resume_switch,
}, self_ref=122)
guarded_editor.stack.update({
    0: "HASH:OperatorOrderEditor.v1", 1: 1, 28: 0, 30: 1,
})
guarded_editor.run(2)
ck(wrong_mailbox.stack.get(19) == 77 and guarded_editor.stack.get(28) == 0,
   "Editor replay wrote to or consumed an edge against an unverified peer")

if fails:
    print("Operator-order ingress: FAIL")
    for failure in fails:
        print(" -", failure)
    sys.exit(1)

print("Operator-order ingress: PASS")
print(" - staged shared-input values publish once per commit edge")
print(" - Recipe Lookup/Profile metadata reaches one ordinary PRINT root intact")
print(" - publisher reflash is idempotent and unknown recipes fail closed")
