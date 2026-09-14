#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from framework.validation_suite import suite_entries
from pathlib import Path
import sys
R=_PROJECT_ROOT
result=Validation(R)
need=result.contains
ordered=result.ordered
registered={entry.path for entry in suite_entries(R)}

need('framework/fault_injection.py','inject_every_boundary','deepcopy','recover','check')
need('tests/test_fault_injection.py','ic10/power-grid/power_dispatch_plan_store_v1_0.ic10','allowed_transition','internal_token','LArRE')
for path in ('validation/validators/validate_fault_injection_contracts.py','tests/test_fault_injection.py'):
 result.check(path in registered,'fault-injection suite entry is not registered',path=path)
# Whole-item migration publishes destination generation before source record removal.
ordered('ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10','putd r2 15 r0','putd r1 9 r0')
# LArRE client persists origin/quantity before issuing the Storage Service request generation.
ordered('ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10','poke 11 r3','poke 13 r6','put d0 31 r9')
# Dependency Plan Store makes a record inactive before mutating the remaining payload.
ordered('ic10/dependency-planning/dependency_plan_store_v2_0.ic10','poke r0 0','Write:','poke r0 r3','jal End')
# Gateway replay identity must remain deterministic externalToken*5+lane.
ordered('ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10','mul r0 r15 128','add r0 r0 r7','put d0 23 r0')
# Power Plan Store boot must invalidate an interrupted odd COMMIT before restoring even sequence.
ordered('ic10/power-grid/power_dispatch_plan_store_v1_0.ic10','and r1 r0 1','poke 28 0','poke 29 0','add r0 r0 1','poke 27 r0')
# New POWER reservations are committed before old release; allocator authority is published last.
ordered('ic10/power-grid/power_reservation_allocator_v1_0.ic10','poke 8 0','WaitC:','WaitR:','Publish:','poke 10 1')
# Executors are gated by allocator active flag and exact PlanGeneration.
result.ordered('ic10/power-grid/power_load_executor_v1_0.ic10','get r0 d1 10','get r0 d1 8','get r0 d1 9','Write:','sd r3 On r4',after='Set:',rule='post-anchor order')
result.ordered('ic10/power-grid/power_link_executor_v1_0.ic10','get r0 d1 10','get r0 d1 8','get r0 d1 9','Write:','sd r3 Setting r4','sd r3 On r5',after='Set:',rule='post-anchor order')
# Transform Runtime snapshots the output Reservation, switches the furnace on, and publishes its state last;
# a served token leaves the published status alone, and an interrupted acceptance or fault is resumed (issue #165).
ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','poke 11 r0','poke 12 r0','s d0 Activate 1','poke 13 0','poke 19 3')
ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','get r0 db 20','beq r0 2 Accept','bgt r0 2 Fault','beq r15 r0 Loop','Accept:','poke 20 2','poke 21 r15')
ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','s d0 Activate 0','poke 20 1','poke 19 0',rule='completion publishes status before state')
result.ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','s d0 Activate 0','get r0 db 21','put d3 23 r0','poke 19 0','poke 20 -1',after='Fault:',rule='fault notices the served token, then publishes state before status')
# The Allocator's echo of the token is the commit: WaitAlloc takes the echo and a non-negative status, never a
# status value an outage can consume, and WaitInput mirrors the completed epoch once delivery reads 2 (#204).
result.ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','get r0 d3 16','bne r0 r15 Loop','get r0 d3 22','bltz r0 Fault','poke 19 2','poke 20 3',after='WaitAlloc:',rule='WaitAlloc commits on the echo')
result.ordered('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','bne r0 r15 Fault','get r0 d3 22','bltz r0 Fault','bne r0 2 Loop','get r0 d3 15','blez r0 Fault','poke 22 r0','get r0 d4 36',after='WaitInput:',rule='WaitInput mirrors the completed epoch once delivery reads 2')
result.excludes('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','bne r0 1 Loop','get r0 d3 14',rule='no wait on an Allocator status or epoch cell an outage can consume')
# Item 10 documentation must be present and marked complete.
need('docs/INTERRUPTION_FAULT_INJECTION.md','Catalog migration','Directory mutation','LArRE','POWER replacement','Generic Job lifecycle','Transform Runtime')
need('ROADMAP.md','10. Broad interruption and fault-injection suite — COMPLETE','Items **1–11 are implemented and automatically validated**','Item **12 is ACTIVE**')
need('docs/COMPLETED_MILESTONES.md','10. Broad interruption and fault-injection suite — COMPLETE')
raise SystemExit(result.finish('Fault-injection contracts',[
 'reusable cut-at-every-boundary harness is part of the release suite',
 'catalog/LArRE/dependency/Gateway/POWER publication order is statically fenced',
 'POWER Plan Store reflash recovery invalidates torn plans before restoring readability',
 'Transform Runtime snapshots, activates, then publishes state; a served token keeps its status and an interrupted acceptance or fault resumes; the Allocator echo is its commit and no wait needs a status an outage can consume']))
