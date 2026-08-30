#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
R=_PROJECT_ROOT;fails=[]

def text(f): return (R/f).read_text()
def need(f,*toks):
 s=text(f)
 for x in toks:
  if x not in s:fails.append(f'{f}: missing {x!r}')
def before(f,a,b):
 s=text(f);ia=s.find(a);ib=s.find(b)
 if ia<0 or ib<0 or ia>=ib:fails.append(f'{f}: expected {a!r} before {b!r}')
def fence(f,token_read,cmp_read,state_read):
 s=text(f);a=s.find(token_read);b=s.find(cmp_read,a+1);c=s.find(state_read,b+1)
 if a<0 or b<0 or c<0 or not (a<b<c):fails.append(f'{f}: expected identity fence before {state_read!r}')

# LIVE_CURRENT producers: request-specific state/error is initialized before CurrentToken.
for f,state,token in [
 ('ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10','poke 6 0','poke 7 r6'),
 ('ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10','poke 6 0','poke 7 r6'),
 ('ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10','poke 22 1','poke 16 r15'),
 ('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','poke 20 2','poke 21 r15'),
 ('ic10/manufacturing/transform_candidate_executor_v2_0.ic10','poke 11 2','poke 10 r15'),
 ('ic10/manufacturing/print_candidate_executor_v2_0.ic10','poke 11 2','poke 10 r15'),
 ('ic10/manufacturing/generic_print_runtime_v2_0.ic10','poke 8 2','poke 15 r15'),
 ('ic10/manufacturing/transform_job_driver_v2_0.ic10','poke 10 2','poke 9 r15'),
 ('ic10/manufacturing/print_job_driver_v2_0.ic10','poke 10 2','poke 9 r15')]:
 need(f,state,token);before(f,state,token)
need('ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10','poke 6 -1','poke 7 r0 # accepted fault publishes current identity LAST')
before('ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10','poke 6 -1','poke 7 r0 # accepted fault publishes current identity LAST')
need('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','poke 21 r15','blez r6 Fault');before('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','poke 21 r15','blez r6 Fault')

# Feeder caller publishes all payload, including emit reset, before RequestToken S18.
need('ic10/material-grid/material_transfer_executor_v1_0.ic10','put d1 16 r4','put d1 17 r2','put d1 19 0','put d1 18 r3 # RequestToken LAST after complete Feeder payload')
before('ic10/material-grid/material_transfer_executor_v1_0.ic10','put d1 19 0','put d1 18 r3 # RequestToken LAST after complete Feeder payload')
# And it never consumes Feeder state until S7 exactly matches the current epoch.
for label in ('WaitReady:','WaitEmit:'):
 s=text('ic10/material-grid/material_transfer_executor_v1_0.ic10');p=s.find(label);q=s.find('j Publish',p)
 block=s[p:q]
 if not all(x in block for x in ('get r1 db 2','get r0 d1 7','bne r0 r1 Publish','get r0 d1 6')):fails.append('ic10/material-grid/material_transfer_executor_v1_0.ic10: '+label+' lacks CurrentToken fence before status')

# Diagnostic request publishers complete payload before request identity/publication.
need('ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10','poke r0 r9\njal BumpController','poke 18 r9\nget r0 db 25\nadd r0 r0 1\npoke 25 r0')
need('ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10','putd controllerSelector 10 r10\nputd controllerSelector 11 r11\nputd controllerSelector 12 r12','putd consoleSelector 12 r10\nputd consoleSelector 13 r12')

# Diagnostic selectors are TERMINAL_RESPONSE producers. Result/status precedes handled token(s).
need('ic10/controller-discovery/controller_selector_v3_0.ic10','poke 8 1','poke 13 r4 # TERMINAL_RESPONSE token LAST');before('ic10/controller-discovery/controller_selector_v3_0.ic10','poke 8 1','poke 13 r4 # TERMINAL_RESPONSE token LAST')
need('ic10/diagnostics/console_selector_v1_1.ic10','poke 17 1','poke 14 r15 # handled desired token after complete result/status','poke 11 r4 # handled advance token after complete result/status')
before('ic10/diagnostics/console_selector_v1_1.ic10','poke 17 1','poke 14 r15 # handled desired token after complete result/status');before('ic10/diagnostics/console_selector_v1_1.ic10','poke 17 1','poke 11 r4 # handled advance token after complete result/status')
# Mapping Editor must prove controller desired, console desired, and console auto-advance requests are settled before status/result reads.
need('ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10','getd r8 input 24','getd r0 controllerSelector 13','getd r8 input 25','getd r0 consoleSelector 14','getd r8 consoleSelector 10','getd r0 consoleSelector 11','getd r0 consoleSelector 17','getd r0 controllerSelector 8')
s=text('ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10')
for a,b in [('getd r0 controllerSelector 13','getd r0 controllerSelector 8'),('getd r0 consoleSelector 14','getd r0 consoleSelector 17'),('getd r0 consoleSelector 11','getd display consoleSelector 16')]:
 if s.find(a)>=s.find(b):fails.append('ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10: stale selector result can be consumed before '+a)

# Existing pressure request/response services are formally TERMINAL_RESPONSE.
pressure=[
 ('ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10','poke 12 r8','poke 9 r14'),
 ('ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10','poke 9 1','poke 10 r14'),
 ('ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10','poke 8 1','poke 9 r14'),
 ('ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10','poke 10 r0','poke 11 r15'),
 ('ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10','poke 9 r0','poke 10 r15'),
 ('ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10','poke 9 1','poke 10 r3'),
 ('ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10','poke 9 1','poke 10 r14')]
for f,result,token in pressure:need(f,result,token);before(f,result,token)
# Pressure callers fence child status/results on exact child response tokens.
for f,toks in {
 'ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10':('get r0 d2 10','bne r0 r15 Loop','get r0 d2 9'),
 'ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10':('get r0 d0 10','bne r0 r10 WaitPath','get r0 d0 9','get r0 d1 9','bne r0 r10 WaitAlloc','get r0 d1 8'),
 'ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10':('get r0 d1 9','bne r0 r13 Loop','get r0 d1 8'),
 'ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10':('get r0 d0 11','bne r0 r13 Loop','get r0 d0 10','get r0 d1 9','bne r0 r13 Loop','get r0 d1 8'),
 'ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10':('get r0 d1 10','bne r0 r6 Loop','get r0 d1 9','get r0 d0 10','bne r0 r5 Loop','get r0 d0 9')}.items(): need(f,*toks)

# Generic Config Committer is the async caller: complete masked candidate before Host request token, then consume only an exact Host response.
need('ic10/controller-config/generic_config_committer_v1_1.ic10','putd host r12 r9','putd host 6 r15 # publish only after complete masked candidate copy','getd r0 host 7','beq r0 r15 Response','getd r0 host 11')
before('ic10/controller-config/generic_config_committer_v1_1.ic10','putd host r12 r9','putd host 6 r15 # publish only after complete masked candidate copy')

# Config Host + family policies already implement terminal response fencing.
need('ic10/controller-config/generic_persistent_config_host_v1_1.ic10','poke 11 5','poke 7 r15','get r0 db 20','bne r0 r15 Loop');before('ic10/controller-config/generic_persistent_config_host_v1_1.ic10','poke 11 5','poke 7 r15')
for f in ('ic10/controller-pi/pi_config_policy_v1_0.ic10','ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10','ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10','ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10','ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10'):
 need(f,'put Host 21 sp','put Host 20 r15');before(f,'put Host 21 sp','put Host 20 r15')

# Other existing terminal-response services.
for f,result,token in [
 ('ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10','poke 8 1','poke 16 r15'),
 ('ic10/generic-jobs/generic_job_store_v1_0.ic10','poke 9 1','poke 8 r15'),
 ('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10','poke 9 1','poke 8 r15'),
 ('ic10/manufacturing/print_material_resolver_v1_0.ic10','poke 12 1','poke 13 r15'),
 ('ic10/printer-directory/printer_capacity_client_v2_0.ic10','poke 7 r0','poke 6 r15'),
 ('ic10/manufacturing/transform_candidate_readiness_v1_0.ic10','poke 9 r0','poke 10 r0')]:
 need(f,result,token);before(f,result,token)
# Multi-material Stager publishes terminal status immediately before each response token.
need('ic10/material-transform/multi_material_reservation_stager_v1_0.ic10','poke 13 1\npoke 14 r15','poke 13 2\npoke 14 r15','poke 13 -1\npoke 14 r15')
# Printer Execution Bank has six independent per-pin terminal streams: status before handled request token.
need('ic10/printer-directory/printer_execution_bank_v2_0.ic10','poke r0 r14\nadd r0 r7 56\npoke r0 r5')

# Generic Snapshot Directory host uses command request S14 / ack S15; mutation/result precedes ack.
need('ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10','get r15 db 14','poke 23 -1','poke 15 r15');before('ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10','poke 23 -1','poke 15 r15')
# Adapter freeze request S11 / ack S12 is the same terminal-ack profile.
for f in ('ic10/controller-discovery/controller_directory_adapter_v4_0.ic10','ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10','ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10'):
 need(f,'get r0 db 16','poke 17 r0')
for f in ('ic10/directory-core/generic_registry_directory_host_v2_0.ic10','ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10'):
 need(f,'put d0 16 r11','get r0 d0 17','bne r0 r11 Freeze')


# Cargo LArRE storage service is TERMINAL_RESPONSE; endpoint client publishes payload before token and fences response.
need('ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','Reply:\npoke 9 r0','poke 14 r15');before('ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','Reply:\npoke 9 r0','poke 14 r15')
need('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','put d0 22 r2','put d0 8 r7','get r0 d0 14','bne r0 r7 WaitScan','bne r0 r7 WaitMove')
before('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','put d0 22 r2','put d0 8 r7')

# Router exposes request-specific state only after selected driver echoes the token.
need('ic10/manufacturing/manufacturing_driver_router_v2_0.ic10','get r0 d0 9','get r0 d1 9','poke 10 r15')
need('ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','get r0 d2 10','get r1 db 27','bne r0 r1 Loop')
# Snapshot identity fencing used by Transform readiness remains separate from async request identity.
need('ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10','poke 68 r10','poke 69 1','poke 71 -2','poke 71 -3')

if fails:
 print('Async request contracts: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Async request contracts: PASS')
print(' - LIVE_CURRENT producers initialize state before current request identity; invalid accepted requests bind identity')
print(' - diagnostic selector and material-feeder consumers reject stale status/results before exact token equality')
print(' - pressure, config, recipe, Job Store, print resolver, printer bank, LArRE storage and directory handshakes are registered TERMINAL_RESPONSE users')
print(' - request payload publication is token-last and transaction/directory/snapshot authorities remain distinct')
