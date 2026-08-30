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
ordered('ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10','mul r0 r15 5','add r0 r0 r6','put d0 23 r0')
# Power Plan Store boot must invalidate an interrupted odd COMMIT before restoring even sequence.
ordered('ic10/power-grid/power_dispatch_plan_store_v1_0.ic10','and r1 r0 1','poke 28 0','poke 29 0','add r0 r0 1','poke 27 r0')
# New POWER reservations are committed before old release; allocator authority is published last.
ordered('ic10/power-grid/power_reservation_allocator_v1_0.ic10','poke 8 0','WaitC:','WaitR:','Publish:','poke 10 1')
# Executors are gated by allocator active flag and exact PlanGeneration.
result.ordered('ic10/power-grid/power_load_executor_v1_0.ic10','get r0 d1 10','get r0 d1 8','get r0 d1 9','Write:','sd r3 On r4',after='Set:',rule='post-anchor order')
result.ordered('ic10/power-grid/power_link_executor_v1_0.ic10','get r0 d1 10','get r0 d1 8','get r0 d1 9','Write:','sd r3 Setting r4','sd r3 On r5',after='Set:',rule='post-anchor order')
# Item 10 documentation must be present and marked complete.
need('docs/INTERRUPTION_FAULT_INJECTION.md','Catalog migration','Directory mutation','LArRE','POWER replacement','Generic Job lifecycle')
need('ROADMAP.md','10. Broad interruption and fault-injection suite — COMPLETE','Items **1–11 are implemented and automatically validated**','Item **12 is ACTIVE**')
need('docs/COMPLETED_MILESTONES.md','10. Broad interruption and fault-injection suite — COMPLETE')
raise SystemExit(result.finish('Fault-injection contracts',[
 'reusable cut-at-every-boundary harness is part of the release suite',
 'catalog/LArRE/dependency/Gateway/POWER publication order is statically fenced',
 'POWER Plan Store reflash recovery invalidates torn plans before restoring readability']))
