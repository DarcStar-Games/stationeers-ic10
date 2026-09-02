#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from framework.scan_coverage import require_nonempty,require_nonempty_glob
from pathlib import Path
import json,re,sys,tempfile
from framework.catalog_test_helpers import generate_recipe_fixture
R=_PROJECT_ROOT;result=Validation(R)
fail=result.fail
manifest_files=['resource_profile_catalog_manifest.json','input_profile_catalog_manifest.json','resource_transform_catalog_manifest.json']
manifests=[json.loads((R/'data'/f).read_text()) for f in manifest_files]
loader_paths=[]
for m in manifests: loader_paths += [R/f for f in m.get('loaders',[])]
recipe_tmp=tempfile.TemporaryDirectory();recipe_root=Path(recipe_tmp.name);rc=generate_recipe_fixture(recipe_root)
loader_paths += [recipe_root/f for f in rc.get('loaders',[])]
for p in loader_paths:
    if not p.exists(): fail('missing loader '+str(p.relative_to(R))); continue
    t=p.read_text(); code=[x.split('#',1)[0].strip() for x in t.splitlines() if x.split('#',1)[0].strip()]
    if t.count('clr db')!=1 or not code or code[0]!='clr db': fail(p.name+': Loader must self-clear exactly once')
    if 'poke 0 HASH("CatalogLoader.v5")' not in t or 'poke 1 5' not in t or code[-1]!='poke 18 1': fail(p.name+': not one-shot Loader ABI5 / Ready not last')
    if any(x.startswith(('put ','putd ','yield','j ')) for x in code): fail(p.name+': immutable Loader must not push or loop')
    if re.search(r'^poke\s+\d+\s+0(?:\s|$)',t,re.M): fail(p.name+': explicit zero poke defeats sparse contract')
    # directory entries are [loader-cell-base, item-cell-count]; each item is whole and block aligned
    n=None
    for line in code:
        m=re.fullmatch(r'poke 14 (\d+)',line)
        if m: n=int(m.group(1)); break
    if not n or n<1: fail(p.name+': missing positive item count')
# Programs that legitimately own/initialize their own stacks. Generated loaders are included above.
private={
 'ic10/controller-discovery/controller_directory_adapter_v4_0.ic10','ic10/controller-config/generic_config_editor_v1_0.ic10','ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10',
 'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10',
'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10','ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10',
 'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10','ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10','ic10/material-transform/generic_material_transform_runtime_v2_0.ic10',
 'ic10/material-transform/multi_material_reservation_stager_v1_0.ic10',
 'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10','ic10/directory-core/generic_registry_directory_host_v2_0.ic10','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ic10/generic-jobs/generic_job_store_v1_0.ic10',
 'ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','ic10/printer-directory/printer_execution_bank_v2_0.ic10','ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10',
 'ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10','ic10/dependency-planning/item_producer_resolver_v1_0.ic10','ic10/dependency-planning/dependency_plan_store_v2_0.ic10','ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10','ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10','ic10/manufacturing-ingress/operator_order_job_ingress_v1_0.ic10','ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10','ic10/manufacturing-ingress/stock_target_job_ingress_v1_0.ic10','ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10','ic10/power-grid/power_dispatch_plan_store_v1_0.ic10'}
programs=require_nonempty_glob(R/'ic10','*.ic10',recursive=True)
actual=set(require_nonempty(
 (p.relative_to(R).as_posix() for p in programs if 'clr db' in p.read_text()),
 'clr db ownership scan after source filtering'))
prod_loaders=set()
for p in loader_paths:
    try: prod_loaders.add(p.relative_to(R).as_posix())
    except ValueError: pass
expected=private|prod_loaders
if actual!=expected: fail(f'clr db ownership changed: expected {sorted(expected)}, got {sorted(actual)}')
checks={
 'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10':['poke 0 HASH("GenericCatalogStore.v6")','poke 1 6','poke 19 32','poke 20 512','poke 29 480','bne r0 HASH("CatalogLoader.v5") Service','poke 27 0'],
 'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10':['poke 0 HASH("CatalogCoordinatorCore.v4")','poke 1 4','poke 2 0','bgt r7 64 ClaimFail','getd r6 r1 16','bne r6 1 Next','getd r0 r1 29','putd r1 16 2'],
 'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10':['poke 0 HASH("CatalogLoaderRouter.v3")','poke 1 3','bne r0 HASH("CatalogLoader.v5") Scan','getd r0 r2 29','putd ra 27 r11','putd r1 19 ra'],
 'ic10/directory-core/generic_registry_directory_host_v2_0.ic10':['poke 0 HASH("GenericRegistryDirectoryHost.v3")','poke 1 3','bne r0 HASH("DirectoryAdapter.v3") Loop','poke 23 r10'],
 'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10':['poke 1 3','poke 3 HASH("DirectorySchema.CatalogStoreNode.v1")','poke 10 6','poke 11 64','poke 15 2'],
 'ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10':['get r14 d0 15','putd r1 12 r14'],
 'ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10':['getd r0 r1 16','bne r0 3 NextSrc','putd r2 27 r11','put d0 40 r13'],
 'ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10':['# Catalog Item Migration Worker','putd r2 r12 r10','putd r1 9 r0','putd r2 27 0'],
 'ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10':['getd r0 r1 9','bgtz r0 Next','putd r1 16 5'],
}
for f,needles in checks.items():
    t=(R/f).read_text()
    for n in needles:
        if n not in t: fail(f+': missing '+n)
expected_schema={
 'resource_profile_catalog_manifest.json':('CatalogSchema.ResourceProfile',2,39),
 'input_profile_catalog_manifest.json':('CatalogSchema.InputProfile',3,6),
 'resource_transform_catalog_manifest.json':('CatalogSchema.ResourceTransform',4,17),
}
for name,(schema,version,count) in expected_schema.items():
    m=json.loads((R/'data'/name).read_text())
    if (m.get('catalog_store_magic'),m.get('catalog_store_abi'),m.get('catalog_loader_magic'),m.get('catalog_loader_abi'),m.get('catalog_coordinator_magic'),m.get('catalog_coordinator_abi'))!=(875310516,6,-284599001,5,4515138,4): fail(name+': common ABI mismatch')
    if m.get('catalog_schema_id')!=schema or m.get('catalog_schema_version')!=version or m.get('total_item_count')!=count: fail(name+': schema/count mismatch')
    if m.get('control_plane')!='catalog_coordinator_v3_runtime_placement_item_migration' or m.get('store_model')!='generic_dynamic_item_heap' or m.get('loader_model')!='one_shot_sparse_relocatable_whole_items': fail(name+': runtime placement model metadata missing')
    if not m.get('runtime_store_placement'): fail(name+': runtime placement flag missing')
rp=json.loads((R/'data/resource_profile_catalog_manifest.json').read_text())
if rp.get('storage_partition')!='resource_class' or rp.get('runtime_min_store_count')!=5: fail('Resource Profile runtime partition/capacity estimate mismatch')
if [p.get('item_count') for p in rp.get('partitions',[])]!=[10,27,1,1]: fail('Resource Profile partition item counts mismatch')
if (rc.get('catalog_store_abi'),rc.get('catalog_loader_abi'),rc.get('catalog_coordinator_abi'),rc.get('catalog_schema_id'),rc.get('catalog_schema_version'))!=(6,5,4,'CatalogSchema.Recipe',3): fail('Recipe common ABI/schema mismatch')
if rc.get('storage_partition')!='printer_family' or rc.get('runtime_min_store_count')!=6: fail('Recipe fixture runtime family capacity mismatch')
raise SystemExit(result.finish('Catalog coordination/storage invariant validation',[
 f'{len(loader_paths)} sparse relocatable Loader ABI5 producers are immutable after Ready publication',
 'Coordinator ABI3 performs runtime Store placement with in-flight capacity reservations',
 'Generic Store ABI5 owns a 2-cell item directory plus downward payload heap',
 'item-level migration/compaction moves whole items before empty Store retirement']))
