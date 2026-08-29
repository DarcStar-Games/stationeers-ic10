#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys
R=_PROJECT_ROOT;fails=[]
def need(path,*tokens):
 t=(R/path).read_text()
 for x in tokens:
  if x not in t:fails.append(path+': missing '+repr(x))
# Existing consumer-facing service ABIs.
for f,toks in {
'ic10/diagnostics/console_registry_v1_1.ic10':['poke 1 1'],'ic10/controller-discovery/controller_selector_v3_0.ic10':['poke 1 2','HASH("DirectorySchema.Controller")'],'ic10/controller-config/generic_persistent_config_host_v1_1.ic10':['poke 1 1'],'ic10/shared-input/generic_input_resolver_v1_0.ic10':['poke 1 1'],'ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10':['poke 97 2'],'ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10':['poke 97 2'],
'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10':['poke 0 31415968','poke 1 5','poke 10 32','poke 19 32','poke 20 512'],
'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10':['poke 0 31415970','poke 1 3'],
'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10':['poke 0 31415971','poke 1 3','putd ra 27 r11'],
'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10':['poke 0 31415981','poke 1 1'],
'ic10/directory-core/generic_registry_directory_host_v2_0.ic10':['poke 0 31415982','poke 1 3','poke 23 r10'],
'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10':['bne r0 31415983 Loop','bne r0 3 Loop','put d0 16 r11'],
'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10':['poke 0 31415983','poke 1 3','poke 2 17','poke 10 6','poke 11 64','poke 15 2'],
'ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10':['poke 0 31415975','poke 1 2'],
'ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10':['poke 0 31415976','poke 1 2'],
'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10':['poke 0 31415963','poke 1 1','bne r0 5 Bad'],
'ic10/input-profile-catalog/input_profile_view_v5_0.ic10':['poke 0 31415929','poke 1 1','bne r0 5 Bad'],
'ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10':['poke 0 31415952','poke 1 4','bne r0 5 Bad','poke 68 r10','poke 69 1'],
'ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10':['poke 0 31415967','poke 1 3','bne r0 5 CatalogBad','bne r0 3 CatalogBad'],
'ic10/catalog-control-plane/catalog_inspector_v4_0.ic10':['poke 0 31415972','poke 1 4','bne r0 5 Bad','bne r0 3 Bad'],
'ic10/material-transform/generic_material_transform_runtime_v2_0.ic10':['poke 0 31415980','poke 1 2'],
'ic10/generic-jobs/generic_job_store_v1_0.ic10':['poke 0 31415984','poke 1 1','poke 5 32','poke 23 1','beq r10 3 Reap','beq r6 7 Respond','bgt r6 10 Respond'],
'ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10':['poke 0 31415985','poke 1 1','bne r0 3 Bad','poke 41 r10'],
'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10':['poke 0 31415986','poke 1 2'],
'ic10/manufacturing/transform_candidate_executor_v2_0.ic10':['poke 0 31415987','poke 1 2'],
'ic10/manufacturing/print_candidate_executor_v2_0.ic10':['poke 0 31415988','poke 1 2'],
'ic10/manufacturing/print_material_resolver_v1_0.ic10':['poke 0 31415989','poke 1 1'],
'ic10/manufacturing/generic_print_runtime_v2_0.ic10':['poke 0 31415990','poke 1 2'],
'ic10/manufacturing/transform_job_driver_v2_0.ic10':['poke 0 31415991','poke 1 2'],
'ic10/manufacturing/print_job_driver_v2_0.ic10':['poke 0 31415992','poke 1 2'],
'ic10/generic-jobs/generic_job_selector_v3_0.ic10':['poke 0 31415993','poke 1 3'],
'ic10/manufacturing/manufacturing_driver_router_v2_0.ic10':['poke 0 31415994','poke 1 2'],
'ic10/manufacturing/manufacturing_scheduler_v1_0.ic10':['poke 0 31415995','poke 1 1'],
'ic10/printer-directory/printer_execution_bank_v2_0.ic10':['poke 0 31415996','poke 1 2'],
'ic10/printer-directory/printer_capacity_client_v2_0.ic10':['poke 0 31415997','poke 1 2'],
'ic10/manufacturing/transform_candidate_readiness_v1_0.ic10':['poke 0 31415998','poke 1 1']}.items():need(f,*toks)
# Every current catalog Loader is ABI4, sparse and producer-owned.
loaders=list(R.glob('*_resource_profile_loader_*_v4_0.ic10'))+list(R.glob('*_input_profile_catalog_loader_*_v4_0.ic10'))+list(R.glob('*_resource_transform_catalog_loader_*_v6_0.ic10'))
for p in loaders:
 t=p.read_text()
 for x in ('clr db','poke 0 31415969','poke 1 4','poke 12 1'):
  if x not in t:fails.append(p.name+': missing '+x)
 if 'putd ' in t or 'put d0 ' in t or '\nyield' in t or '\nj ' in t:fails.append(p.name+': Loader ABI4 must be immutable one-shot producer')
for name,count,ver in [('resource_profiles.json',39,2),('input_profiles.json',6,3),('resource_transforms.json',17,4)]:
 d=json.loads((R/'data'/name).read_text());rows=d.get('profiles',d.get('transforms',[]))
 if len(rows)!=count or d.get('catalog_schema_version')!=ver:fails.append(name+': cardinality/schema version mismatch')
if fails:
 print('ABI contract validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('ABI contract validation: PASS')
print(' - Store ABI5 / Loader ABI4 / Coordinator ABI3 separate runtime placement from payload schema versions')
print(' - Directory Adapter ABI2 freezes coherent candidates for Snapshot Host ABI1 or Registry Host ABI3')
print(' - Resource/Input consumer ABIs remain ABI1; Transform/Recipe Lookup remain ABI3; manufacturing services use explicit ABI1/ABI2 contracts; changed async-token semantics are ABI2')
