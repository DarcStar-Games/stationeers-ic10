#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from pathlib import Path
import json,sys
R=_PROJECT_ROOT;result=Validation(R)
need=result.contains
# Existing consumer-facing service ABIs.
for f,toks in {
'ic10/diagnostics/console_registry_v1_1.ic10':['poke 1 1'],'ic10/controller-discovery/controller_selector_v3_0.ic10':['poke 1 2','HASH("DirectorySchema.Controller.v1")'],'ic10/controller-config/generic_persistent_config_host_v1_1.ic10':['poke 1 1'],'ic10/shared-input/generic_input_resolver_v1_0.ic10':['poke 1 1'],'ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10':['poke 97 2'],'ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10':['poke 97 2'],
'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10':['poke 0 HASH("GenericCatalogStore.v6")','poke 1 6','poke 10 32','poke 19 32','poke 20 512'],
'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10':['poke 0 HASH("CatalogCoordinatorCore.v4")','poke 1 4'],
'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10':['poke 0 HASH("CatalogLoaderRouter.v3")','poke 1 3','putd ra 27 r11'],
'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10':['poke 0 HASH("GenericSnapshotDirectoryHost.v1")','poke 1 1'],
'ic10/directory-core/generic_registry_directory_host_v2_0.ic10':['poke 0 HASH("GenericRegistryDirectoryHost.v3")','poke 1 3','poke 23 r10'],
'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10':['bne r0 HASH("DirectoryAdapter.v3") Loop','put d0 16 r11'],
'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10':['poke 0 HASH("DirectoryAdapter.v3")','poke 1 3','poke 2 17','poke 10 6','poke 11 64','poke 15 2'],
'ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10':['poke 0 HASH("CatalogCoordinatorDirectoryView.v2")','poke 1 2'],
'ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10':['poke 0 HASH("CatalogCoordinatorRecovery.v2")','poke 1 2'],
'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10':['poke 0 HASH("ResourceProfileView.v1")','poke 1 1','bne r0 HASH("GenericCatalogStore.v6") Bad'],
'ic10/input-profile-catalog/input_profile_view_v5_0.ic10':['poke 0 HASH("InputProfileView.v1")','poke 1 1','bne r0 HASH("GenericCatalogStore.v6") Bad'],
'ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10':['poke 0 HASH("ResourceTransformProfileView.v4")','poke 1 4','bne r0 HASH("GenericCatalogStore.v6") Bad','poke 68 r10','poke 69 1'],
'ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10':['poke 0 HASH("RecipeCatalogLookup.v3")','poke 1 3','bne r0 HASH("GenericCatalogStore.v6") CatalogBad',],
'ic10/catalog-control-plane/catalog_inspector_v4_0.ic10':['poke 0 HASH("CatalogInspector.v4")','poke 1 4','bne r0 HASH("GenericCatalogStore.v6") Bad',],
'ic10/material-transform/generic_material_transform_runtime_v2_0.ic10':['poke 0 HASH("GenericMaterialTransformRuntime.v2")','poke 1 2'],
'ic10/generic-jobs/generic_job_store_v1_0.ic10':['poke 0 HASH("GenericJobStore.v1")','poke 1 1','poke 18 32','poke 23 1','beq r10 3 Reap','beq r6 7 Respond','bgt r6 10 Respond'],
'ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10':['poke 0 HASH("RecipeExecutionProfileView.v1")','poke 1 1','poke 49 r10'],
'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10':['poke 0 HASH("ManufacturingCandidateSelector.v2")','poke 1 2'],
'ic10/manufacturing/transform_candidate_executor_v2_0.ic10':['poke 0 HASH("TransformCandidateExecutor.v2")','poke 1 2'],
'ic10/manufacturing/print_candidate_executor_v2_0.ic10':['poke 0 HASH("PrintCandidateExecutor.v2")','poke 1 2'],
'ic10/manufacturing/print_material_resolver_v1_0.ic10':['poke 0 HASH("PrintMaterialResolver.v1")','poke 1 1'],
'ic10/manufacturing/generic_print_runtime_v2_0.ic10':['poke 0 HASH("GenericPrintRuntime.v2")','poke 1 2'],
'ic10/manufacturing/transform_job_driver_v2_0.ic10':['poke 0 HASH("TransformJobDriver.v2")','poke 1 2'],
'ic10/manufacturing/print_job_driver_v2_0.ic10':['poke 0 HASH("PrintJobDriver.v2")','poke 1 2'],
'ic10/generic-jobs/generic_job_selector_v3_0.ic10':['poke 0 HASH("GenericJobSelector.v3")','poke 1 3'],
'ic10/manufacturing/manufacturing_driver_router_v2_0.ic10':['poke 0 HASH("ManufacturingDriverRouter.v2")','poke 1 2'],
'ic10/manufacturing/manufacturing_scheduler_v1_0.ic10':['poke 0 HASH("ManufacturingScheduler.v1")','poke 1 1'],
'ic10/printer-directory/printer_execution_bank_v2_0.ic10':['poke 0 HASH("PrinterExecutionBank.v2")','poke 1 2'],
'ic10/printer-directory/printer_capacity_client_v2_0.ic10':['poke 0 HASH("PrinterCapacityClient.v2")','poke 1 2'],
'ic10/manufacturing/transform_candidate_readiness_v1_0.ic10':['poke 0 HASH("TransformCandidateReadiness.v1")','poke 1 1']}.items():need(f,*toks)
# Every current catalog Loader is ABI5: a sparse, relocatable, immutable one-shot
# candidate image. Glob under ic10/, where the programs actually live -- anchored
# at the repository root these patterns matched nothing and asserted nothing.
loaders=sorted(R.glob('ic10/*/resource_profile_loader_*_v4_0.ic10'))+sorted(R.glob('ic10/*/input_profile_catalog_loader_*_v4_0.ic10'))+sorted(R.glob('ic10/*/resource_transform_catalog_loader_*_v6_0.ic10'))
if not loaders:result.fail('no catalog Loader programs found; the Loader contract is unchecked')
for p in loaders:
 t=p.read_text()
 for x in ('clr db','poke 0 HASH("CatalogLoader.v5")','poke 1 5','poke 18 1'):
  if x not in t:result.fail(p.name+': missing '+x)
 if 'putd ' in t or 'put d0 ' in t or '\nyield' in t or '\nj ' in t:result.fail(p.name+': Loader ABI5 must be immutable one-shot producer')
 # Relocatable: the producer never names a physical Store. S19 TargetStoreRef and
 # S20 assignment epoch stay zero until the Router places the image at runtime.
 for cell in ('poke 19 ','poke 20 '):
  if cell in t:result.fail(p.name+': producer writes runtime placement cell '+cell.strip())
 # Ready at S18 is the publication marker, so it must be the final write.
 pokes=[ln.split('#')[0].strip() for ln in t.splitlines() if ln.startswith('poke ')]
 if pokes and pokes[-1]!='poke 18 1':result.fail(p.name+': S18 Ready is not the last write, so a partial image can be read as complete')
# One ServiceMagic naming one contract is no longer a rule this file can check:
# S0 is HASH("<Contract>.v<ABI>"), so the identity *is* the contract and the ABI
# together, and validate_service_identity.py proves both that every identity is
# derived that way and that no two contracts collide under CRC32.
for name,count,ver in [('resource_profiles.json',39,2),('input_profiles.json',6,3),('resource_transforms.json',17,4)]:
 d=json.loads((R/'data'/name).read_text());rows=d.get('profiles',d.get('transforms',[]))
 if len(rows)!=count or d.get('catalog_schema_version')!=ver:result.fail(name+': cardinality/schema version mismatch')
raise SystemExit(result.finish('ABI contract validation',[
 'Store ABI6 / Loader ABI5 / Coordinator ABI4 separate runtime placement from payload schema versions',
 'Directory Adapter ABI3 freezes coherent candidates for Snapshot Host ABI1 or Registry Host ABI3',
 'S0 identities are derived and unique (validate_service_identity.py); a shared identity is one generic contract with many instances',
 'Resource/Input consumer ABIs remain ABI1; Transform View is ABI4 and Recipe Lookup ABI3; manufacturing services use explicit ABI1/ABI2 contracts; changed async-token semantics are ABI2']))
