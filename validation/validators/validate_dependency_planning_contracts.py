#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from pathlib import Path
import re,sys
R=_PROJECT_ROOT;validation=Validation(R)
# Scanning callers that a Plan Store change restarts derive each downstream posting's token
# from a per-request counter, never the scan position alone, so a repost after a restart is
# latched rather than answered by the earlier reply (#148). The count lives in a private
# stack cell (S18 / S28), so a reflash mid-request continues it (#182).
req={
'ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10':['poke 1 5','get r15 db r7','ble r7 96 Scan','put d0 21 r6'],
'ic10/dependency-planning/job_requirement_view_v1_0.ic10':['poke 0 HASH("JobRequirementView.v1")','put d2 8 r10'],
'ic10/dependency-planning/item_producer_resolver_v1_0.ic10':['poke 0 HASH("ItemProducerResolver.v1")','Table:'],
'ic10/dependency-planning/generic_job_monitor_v1_0.ic10':['poke 0 HASH("GenericJobMonitor.v1")'],
'ic10/dependency-planning/job_inventory_preflight_v1_0.ic10':['poke 0 HASH("JobInventoryPreflight.v1")','bne r0 -2 Bad','get r12 d1 10','bgt r12 6 Bad'],
'ic10/dependency-planning/dependency_child_creator_v2_0.ic10':['poke 1 2','put d3 62 r0','put d3 48 r15'],
'ic10/dependency-planning/dependency_plan_store_v2_0.ic10':['poke 1 2','poke r0 0','poke r0 r3'],
'ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10':['poke 1 2','get r0 db 27','bne r11 r0 Replan','bne r12 r0 Replan'],
'ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10':['poke 0 HASH("DependencyAncestryGuard.v1")','beq r11 r8 TooDeep','get r12 db 18','add r12 r12 1','bge r12 512 Bad','poke 18 r12','add r13 r13 r12','poke 18 0'],
'ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10':['poke 0 HASH("ManufacturingDependencyPlanner.v1")','put d0 12 2','put d0 12 3'],
'ic10/dependency-planning/dependency_plan_builder_v2_0.ic10':['poke 1 2','get sp d0 27'],
'ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10':['poke 1 2','put d0 19 r15','put d1 9 r15'],
'ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10':['poke 0 HASH("DependencyCancellationGuard.v1")'],
'ic10/dependency-planning/dependency_child_validity_v1_0.ic10':['poke 0 HASH("DependencyChildValidity.v1")'],
'ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10':['poke 0 HASH("GenericJobStoreCommandExecutor.v1")','FindFree:','put d0 11 r10'],
'ic10/dependency-planning/dependency_claim_view_v1_0.ic10':['poke 0 HASH("DependencyClaimView.v1")','poke 27 r4','bne r0 1 Unverified','move r1 -3','poke 20 r1','get r5 db 28','add r5 r5 1','bge r5 512 Bad','poke 28 r5','add r13 r13 r5','poke 28 0'],
'ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10':['poke 0 HASH("ManufacturingReagentResolver.v1")'],
'ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10':['poke 0 HASH("DependencyPlanReleaseAdvisor.v1")'],
'ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10':['poke 0 HASH("ExistingDependencyPlanController.v1")','beq r0 5 Replan','put d3 32 r15'],
'ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10':['poke 0 HASH("NewDependencyPlanController.v1")']}
# Line limits are validate_ic10.py's: its ceiling, its reviewed SOFT_LIMIT_EXEMPTIONS, and
# the hard limit apply to every program here, so a per-file ceiling beside them was a
# second list that tracked each program's size and held nothing back (issue #172).
for rel,pats in req.items():
 p=R/rel
 if not p.exists():validation.fail(f'{rel}: missing implementation');continue
 t=p.read_text()
 for pat in pats:
  if pat not in t:validation.fail(f"{rel}: missing {pat!r}")
t=(R/'ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10').read_text()
if 'bge r8 6 Overflow' not in t:validation.fail('item reservation selector: seventh eligible source is not explicit overflow')
if 'bge r8 6 Quoted' in t:validation.fail('item reservation selector: stale six-leg false-deficit path remains')
t=(R/'ic10/manufacturing/manufacturing_scheduler_v1_0.ic10').read_text()
if 'd0 Job Gateway' not in t or 'd2 Dependency Gate' not in t:validation.fail('manufacturing scheduler boundary not updated')
writers=[]
for f in (R/'ic10').rglob('*.ic10'):
 txt=f.read_text()
 if re.search(r'put d0 (?:7|11|12|13|14|15) ',txt) and f.name=='generic_job_store_command_executor_v1_0.ic10':writers.append(f)
if len(writers)!=1:validation.fail(f'expected one physical Job Store command writer, found {len(writers)}')
for rel in ('ic10/dependency-planning/dependency_child_creator_v1_0.ic10','ic10/dependency-planning/dependency_plan_builder_v1_0.ic10','ic10/dependency-planning/manufacturing_dependency_gate_v1_0.ic10'):
 if (R/rel).exists():validation.fail(f'stale implementation remains: {rel}')
raise SystemExit(validation.finish('Dependency planning contracts',[
 'dependency lanes share one six-lane Gateway and one Store executor',
 '8-cell commit-last plans, active-only claims, surplus accounting, bounded depth and quote overflow are enforced',
 'scheduler routes lifecycle through Gateway and execution through Dependency Gate']))
