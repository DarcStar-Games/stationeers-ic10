#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys,re
R=_PROJECT_ROOT;fails=[]
def need(path,*tokens):
 t=(R/path).read_text()
 for tok in tokens:
  if tok not in t:fails.append(f'{path}: missing {tok!r}')
# Catalog semantics.
D=json.loads((R/'data/resource_profiles.json').read_text())
if D.get('resource_classes',{}).get('POWER')!=4:fails.append('ResourceClass.POWER != 4')
if D.get('resource_classes',{}).get('ENERGY')!=5:fails.append('ResourceClass.ENERGY != 5')
if D.get('units',{}).get('WATT')!=4:fails.append('Unit.WATT != 4')
if D.get('units',{}).get('JOULE')!=5:fails.append('Unit.JOULE != 5')
pp=[p for p in D['profiles'] if p['resource_class'] in (4,5)]
if len(pp)!=2:fails.append('expected exactly POWER + ENERGY electrical profiles')
M=json.loads((R/'data/resource_profile_catalog_manifest.json').read_text())
parts={x['partition_key']:x for x in M['partitions']}
for cls,name in [(4,'ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10'),(5,'ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10')]:
 if cls not in parts or name not in parts[cls]['loaders']:fails.append(f'missing generated ResourceClass {cls} loader')
# Endpoint/Reservation direction contract: Endpoint S5/S6 -> Reservation S6/S7.
need('ic10/power-grid/power_producer_endpoint_v1_0.ic10','poke 2 4','poke 5 r3','poke 35 1','poke 38 r8','poke 39 r9')
need('ic10/power-grid/power_consumer_endpoint_v1_0.ic10','poke 6 r3','poke 35 2','get r4 db 50','beq r4 2 Shed')
need('ic10/power-grid/power_battery_endpoint_v1_0.ic10','poke 5 r9','poke 6 r10','poke 35 3','get r0 db 23','get r13 db 50','beq r13 5 Hold')
need('ic10/resource-grid-core/resource_reservation_v1_0.ic10','get r5 d0 5','get r6 d0 6','poke 6 r5','poke 7 r6','poke 28 r0','poke 31 r0')
need('ic10/power-grid/power_source_selector_v1_0.ic10','getd r11 r10 6','add r13 r13 r4','getd r0 r10 28')
need('ic10/power-grid/power_sink_selector_v1_0.ic10','getd r11 r10 7','slt r12 r9 5000000','seq r12 r12 0')
# Generic links + transformer overhead.
need('ic10/power-grid/power_static_link_v1_0.ic10','poke 0 31415953','poke 4 4','poke 6 1')
need('ic10/power-grid/power_transformer_link_v1_0.ic10','poke 6 2','bdnvl d0 RequiredPower ReqReady','poke 14 r5')
need('ic10/power-grid/power_link_selector_v1_0.ic10','HASH("DirectorySchema.ResourceLink.v1")','getd r13 r1 14','add r13 r13 r4')
# Directory and bounded coherent plan.
need('ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10','HASH("DirectorySchema.PowerReservation.v1")','poke 10 3','poke 11 64','getd r0 r1 17','get r13 db 8','1000000','5000000')
need('ic10/power-grid/power_dispatch_plan_store_v1_0.ic10','poke 0 31416028','bge r2 8 Full','add r3 r3 1','poke 3 r0','poke 2 r3')
need('ic10/power-grid/power_plan_validator_v1_0.ic10','bgt r3 8 Bad','getd r0 r7 12','getd r0 r8 12','getd r0 r6 12','getd r0 r6 14')
need('ic10/power-grid/power_reservation_committer_v1_0.ic10','getd r0 r7 17','bne r0 r12 Bad','add sp sp r5','putd r7 14 sp','putd r8 15 ra','putd r7 17 r12')
need('ic10/power-grid/power_reservation_allocator_v1_0.ic10','poke 2 0','WaitV:','WaitC:','WaitR:','CleanupNew:','WaitCleanup:','poke 2 r0','poke 3 r0','poke 4 1')
need('ic10/power-grid/power_load_executor_v1_0.ic10','Set:','get r0 d1 4','get r0 d1 2','get r0 d1 3','Write:','sd r3 On r4','getd r5 r1 17','getd r5 r1 18','getd r5 r1 19')
need('ic10/power-grid/power_link_executor_v1_0.ic10','Set:','get r0 d1 4','get r0 d1 2','get r0 d1 3','Write:','getd r0 r14 17','getd r0 r15 17','getd r0 r14 19','getd r0 r15 19','sd r3 Setting r4','sd r3 On r5','bne r0 2 Scan')
# POWER jobs and Gateway lane D.
need('ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10','poke 1 3','get r15 db 64','move r6 4','move r7 64','move r8 68')
need('ic10/generic-jobs/generic_job_selector_v3_0.ic10','poke 1 3','get r10 db 18','bne r5 r10 Next','beq r2 7 Next','bge r2 11 Next')
if (R/'239_power_job_selector_v1_0.ic10').exists():fails.append('duplicate POWER Job selector must not exist')
need('ic10/power-jobs/power_policy_target_resolver_v1_0.ic10','HASH("DirectorySchema.PowerReservation.v1")','getd r5 r7 28')
need('ic10/power-jobs/power_job_policy_apply_v1_0.ic10','bne r10 4 Bad','bne r11 r6 Bad','putd r13 50 r4','putd r13 51 r7')
need('ic10/power-jobs/power_job_policy_verify_v1_0.ic10','getd r0 r6 50','getd r0 r6 51','NeedExportZero:','NeedImportZero:')
need('ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10','put d0 68 2','put d0 64 r15','add r3 r3 1','poke 9 r3')
need('ic10/power-jobs/power_job_prepare_v1_0.ic10','beq r4 1 ToPlanning','beq r4 4 Resolve','beq r0 -2 WaitResource','move r11 8','move r11 11','move r10 -1','put d1 10 r8','put d2 16 r7','move r11 5')
need('ic10/power-jobs/power_job_finalize_v1_0.ic10','beq r4 5 Resolve','beqz r0 Pending','move r12 11','move r10 -1','put d1 10 r8','put d2 10 r7','put d2 11 r6','move r12 6','move r12 7')
need('ic10/power-jobs/power_job_scheduler_v1_0.ic10','put d0 18 4','put d0 2 r0','put d0 3 r15','poke 22 r0','seq r1 r7 5','seq r0 r7 6','select r9 r1 2 1')
# Schema registry.
S=json.loads((R/'data/directory_schemas.json').read_text())
ps=[s for s in S['schemas'] if s['schema_id']=='DirectorySchema.PowerReservation']
if len(ps)!=1 or ps[0]['entry_width']!=3 or ps[0]['capacity']!=64:fails.append('PowerReservation directory schema mismatch')
if fails:
 print('Power management contracts: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Power management contracts: PASS')
print(' - POWER/ENERGY reuse Resource Profile + Endpoint/Reservation/Link contracts')
print(' - source uses Reservation S6 export and sink uses S7 import')
print(' - bounded priority dispatch, transformer overhead, common reservation epoch')
print(' - JobType.POWER uses Gateway lane D and finite policy lifecycle')
