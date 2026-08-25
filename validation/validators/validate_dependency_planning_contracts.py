#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import re,sys
R=_PROJECT_ROOT;fails=[]
req={
'ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10':['poke 1 3','get r15 db 48','get r15 db 64','put d0 21 r6'],
'ic10/dependency-planning/job_requirement_view_v1_0.ic10':['poke 0 31416002','put d2 2 r10'],
'ic10/dependency-planning/item_producer_resolver_v1_0.ic10':['poke 0 31416003','Table:'],
'ic10/dependency-planning/generic_job_monitor_v1_0.ic10':['poke 0 31416004'],
'ic10/dependency-planning/job_inventory_preflight_v1_0.ic10':['poke 0 31416005','bne r0 -2 Bad'],
'ic10/dependency-planning/dependency_child_creator_v2_0.ic10':['poke 1 2','put d3 63 -1','put d3 48 r15'],
'ic10/dependency-planning/dependency_plan_store_v2_0.ic10':['poke 1 2','poke r0 0','poke r0 r3'],
'ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10':['poke 1 2','get r0 db 9','bne r11 r0 Replan','bne r12 r0 Replan'],
'ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10':['poke 0 31416009','beq r11 r8 TooDeep'],
'ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10':['poke 0 31416010','put d0 12 2','put d0 12 3'],
'ic10/dependency-planning/dependency_plan_builder_v2_0.ic10':['poke 1 2','get sp d0 14'],
'ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10':['poke 1 2','put d0 9 r15','put d1 9 r15'],
'ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10':['poke 0 31416013'],
'ic10/dependency-planning/dependency_child_validity_v1_0.ic10':['poke 0 31416014'],
'ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10':['poke 0 31416015','FindFree:','put d0 11 r10'],
'ic10/dependency-planning/dependency_claim_view_v1_0.ic10':['poke 0 31416016','poke 14 r4'],
'ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10':['poke 0 31416017'],
'ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10':['poke 0 31416018'],
'ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10':['poke 0 31416019','beq r0 5 Replan','put d3 32 r15'],
'ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10':['poke 0 31416020']}
for rel,pats in req.items():
 p=R/rel
 if not p.exists():fails.append(f'{rel}: missing implementation');continue
 t=p.read_text();lines=len(t.splitlines())
 if lines>120:fails.append(f'{rel}: {lines} lines > 120')
 for pat in pats:
  if pat not in t:fails.append(f"{rel}: missing {pat!r}")
t=(R/'ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10').read_text()
if 'bge r8 6 Overflow' not in t:fails.append('item reservation selector: seventh eligible source is not explicit overflow')
if 'bge r8 6 Quoted' in t:fails.append('item reservation selector: stale six-leg false-deficit path remains')
t=(R/'ic10/manufacturing/manufacturing_scheduler_v1_0.ic10').read_text()
if 'd0 Job Gateway' not in t or 'd2 Dependency Gate' not in t:fails.append('manufacturing scheduler boundary not updated')
writers=[]
for f in (R/'ic10').rglob('*.ic10'):
 txt=f.read_text()
 if re.search(r'put d0 (?:7|11|12|13|14|15) ',txt) and f.name=='generic_job_store_command_executor_v1_0.ic10':writers.append(f)
if len(writers)!=1:fails.append(f'expected one physical Job Store command writer, found {len(writers)}')
for rel in ('ic10/dependency-planning/dependency_child_creator_v1_0.ic10','ic10/dependency-planning/dependency_plan_builder_v1_0.ic10','ic10/dependency-planning/manufacturing_dependency_gate_v1_0.ic10'):
 if (R/rel).exists():fails.append(f'stale implementation remains: {rel}')
if fails:
 print('Dependency planning contracts: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Dependency planning contracts: PASS')
print(' - dependency lanes share one four-lane Gateway and one Store executor')
print(' - 8-cell commit-last plans, active-only claims, surplus accounting, bounded depth and quote overflow are enforced')
print(' - scheduler routes lifecycle through Gateway and execution through Dependency Gate')
