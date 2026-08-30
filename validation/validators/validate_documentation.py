#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,re,sys
import tools.generate.update_magic_registry as magic_registry
ROOT=_PROJECT_ROOT
mds=[p for p in ROOT.rglob('*.md') if 'validation' not in p.parts and '.claude' not in p.parts]
existing={p.name for p in ROOT.iterdir() if p.is_file()}
fails=[]
GLOB=set('*{}?[]')
def referenced_paths(ref):
    """Yield every concrete repo path inside one backtick span.

    A span may chain programs ('A -> B -> C'), map a pin ('d1 -> A'), or carry a
    prose prefix ('dedicated ic10/...'), so split on the arrow and keep the last
    word of each segment. A wildcard family ('..._loader_*_v4_0.ic10') names a
    set rather than a file and is left unchecked.
    """
    for seg in ref.split('->'):
        seg=seg.strip()
        if not seg: continue
        seg=seg.split()[-1]
        if seg.endswith(('.ic10','.md','.py','.json')) and '/' in seg and not GLOB&set(seg):
            yield seg

for p in mds:
    txt=p.read_text(errors='replace')
    for ref in sorted(set(re.findall(r'`([^`\n]+\.(?:ic10|md|py|json))`',txt))):
        if '/' not in ref:
            if ref not in existing: fails.append(f'{p.name}: missing referenced file {ref}')
            continue
        for seg in referenced_paths(ref):
            if not (ROOT/seg).exists(): fails.append(f'{p.name}: missing referenced file {seg}')
    # A documented command is a promise the operator can paste. Backtick checks
    # above only see a span that *ends* in a path, so `python x.py --resume` and
    # anything inside a fenced block would otherwise never be resolved.
    for cmd in sorted(set(re.findall(r'\bpython3?\s+([\w./-]+\.py)\b',txt))):
        if not (ROOT/cmd).exists(): fails.append(f'{p.name}: documented command names missing script {cmd}')
    # A path *operand* is a promise too. --game-data names an in-tree fixture
    # directory that a later move would silently invalidate, because the check
    # above resolves only the script name. Other operands are placeholders
    # (<tmpdir>) or deliberately out-of-tree (--session ../field_evidence/...),
    # so this stays keyed to the one operand that must resolve in-tree. Pointing
    # --game-data at an installed game ('/opt/Stationeers/...') is that flag's
    # other legitimate use and is not this repository's to resolve: an absolute
    # or escaping path would otherwise pass or fail by which machine ran the
    # check, which is exactly the machine-dependence this file exists to prevent.
    for operand in sorted(set(re.findall(r'--game-data\s+([\w./-]+)',txt))):
        if operand.startswith('/') or '..' in Path(operand).parts: continue
        if not (ROOT/operand).exists(): fails.append(f'{p.name}: documented --game-data path does not exist: {operand}')
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',txt):
        target=target.strip()
        if target.startswith(('http://','https://','mailto:','#')):
            continue
        local=target.split('#',1)[0]
        if local and not (ROOT/local).exists():
            fails.append(f'{p.name}: broken local markdown link {target}')

forbidden={
    'View ABI3':'the Transform Profile View is ABI4 with the S68..S75 resolved-request mailbox',
    'View ABI 3':'the Transform Profile View is ABI4 with the S68..S75 resolved-request mailbox',
    'Pressure Reservation Allocator ABI2':'Allocator is ABI3',
    'Pressure Reservation Allocator ABI 2':'Allocator is ABI3',
    'PressureTransfer v1.3 publishes':'Transfer runtime is v2.0',
    'Transfer telemetry ABI v1':'Transfer telemetry is ABI2',
    'Inventory v1 intentionally':'Inventory is ABI2',
    'phase_media.json':'profile source consolidated',
    'material_resources.json':'profile source consolidated',
    'generate_phase_profiles.py':'generator consolidated',
    'generate_material_profiles.py':'generator consolidated',
    'Resource Profile Catalog Page':'Store model replaced page model',
    'generated Transform Profile':'shared Transform Catalog/View is current',
    'CATALOG_STORE_ABI_V4':'Store ABI5 is current',
    'CATALOG_STORE_ABI_V3':'Store ABI5 is current',
    'CATALOG_STORE_ABI_V2':'Store ABI5 is current',
    'CATALOG_STORE_ABI_V1':'Store ABI5 is current',
    'CATALOG_LOADER_ABI_V3':'Loader ABI5 is current',
    'CATALOG_LOADER_ABI_V2':'Loader ABI5 is current',
    'CATALOG_LOADER_ABI_V1':'Loader ABI5 is current',
    'Coordinator ABI2':'Coordinator ABI3 is current',
    'Store ABI4':'Store ABI5 is current',
    'Loader ABI3':'Loader ABI5 is current',
    'Loader ABI4':'Loader ABI5 is current since the common header migration',
    'Store ABI5':'Store ABI6 is current since the common header migration',
    'Coordinator ABI3':'Coordinator ABI4 is current since the common header migration',
    '167_generic_registry_directory_host_v1_0.ic10':'Registry Host v2 is current',
    '116_recipe_catalog_lookup_v6_0.ic10':'Recipe Lookup v8 is current',
    '116_recipe_catalog_lookup_v7_0.ic10':'Recipe Lookup v8 is current',
    '113_input_profile_view_v4_0.ic10':'Input View v5 is current',
    '112_resource_transform_profile_view_v6_0.ic10':'Transform View v7 is current',
    '149_resource_profile_loader':'Resource loaders are 117..121',
    '150_resource_profile_loader':'Resource loaders are 117..121',
    '95_input_profile_catalog_loader':'Input Profile catalog has three loaders 92..94',
    'ExpectedLoaderMask':'Loader population is open-ended/runtime placed',
    'CompletedLoaderMask':'Loader population is open-ended/runtime placed',
    '117 recipes/store':'Store ABI5 recipe capacity is 80',
    '117 recipes per Store':'Store ABI5 recipe capacity is 80',
    '117 recipes per store':'Store ABI5 recipe capacity is 80',
    '78_material_reservation_allocator_v1_0.ic10':'removed pre-v1 material allocator',
    '79_arc_furnace_transform_admission_v1_0.ic10':'removed Arc-Furnace-only path',
    '80_arc_furnace_transform_runtime_v1_0.ic10':'removed Arc-Furnace-only path',
    'scripts 79/80':'removed Arc-Furnace-only path',
    'scripts 79-80':'removed Arc-Furnace-only path',
    '77/78/81/82':'removed pre-v1 material execution path',
    'Arc Furnace compatibility runtime':'single 161..165 transform path is current',
    'Arc Furnace path remains':'single 161..165 transform path is current',
    'Allocator ABI1 or ABI2':'Material Grant Guard requires ABI2 exactly',
    'Allocator ABI1 and ABI2':'Material Grant Guard requires ABI2 exactly',
    '14142135':'Controller directory uses Generic Snapshot Host',
    '31415939':'Pressure Grid Link directory uses Generic Snapshot Host',
    '14142138':'Resource Endpoint directory uses Generic Snapshot Host',
    '14142139':'Resource Link directory uses Generic Snapshot Host',
    '31415973':'Catalog Store registry uses Generic Registry Host',
    'published_magic':'Directory Adapter no longer carries consumer compatibility headers',
    'published_abi':'Directory Adapter no longer carries consumer compatibility headers',
    'Generic Registry Directory ABI2':'Registry Host ABI3 is current',
    'MaterialGrid retains the serialized ABI1 allocator':'MaterialGrid has one current commit authority: Multi Material Allocator ABI2',
    'serialized exact-quantity ITEM allocator':'MaterialGrid uses Multi Material Allocator ABI2',
    'Exact material link + serialized allocator':'MaterialGrid uses Multi Material Allocator ABI2',
    'from serialized Allocator through Guard':'MaterialGrid uses Multi Material Allocator ABI2',
    '116_recipe_catalog_lookup_v7_0.ic10':'Recipe Lookup v8 is current',
    '6. Manufacturing scheduler — NEXT':'Manufacturing Scheduler is complete',
    'Item 6, Manufacturing scheduler, is the next milestone':'Manufacturing Scheduler is complete',
    'manufacturing scheduler (roadmap item 6);':'Manufacturing Scheduler is complete',
    'Item **8 is next**':'Dependency Planning is complete',
    'Items **1–7 are implemented and validated**':'Items 1–11 are current',
    'Scheduler lifecycle commands use lane A and dependency child create/cancel commands use lane B':'Gateway ABI3 has four independent lanes',
    '199_generic_job_command_gateway_v2_0.ic10':'Gateway ABI3 is current',
    'Job Command Gateway ABI2':'Gateway ABI3 is current',
    '199 Job Command Gateway ABI2':'Gateway ABI3 is current',
    'Items **1–8 are implemented**':'Items 1–11 are current',
    'Item **9 is next**':'Power management is complete',
    'Items **1–9 are implemented and validated**':'Items 1–11 are current',
    'Item **10 is next**':'fault-injection milestone is complete',
    '10. Broad interruption and fault-injection suite — NEXT':'fault-injection milestone is complete',
    '36 Resource Profiles':'39 Resource Profiles are current',
    '32 six-cell parent/child plan records':'Plan Store ABI2 uses eight-cell records',
    '181_manufacturing_job_selector_v2_0.ic10':'Generic Job Selector v3 is current',
    '239_power_job_selector_v1_0.ic10':'POWER reuses Generic Job Selector v3',
    'POWER remains roadmap item 8':'POWER management is complete',
    'POWER remains reserved for roadmap item 8':'POWER management is complete',
    'Simple dependency planner                          NEXT':'dependency planning is complete',
    'sole production Job Store lifecycle writer':'domain lifecycle policy uses Gateway; executor 213 is sole physical writer',
    'sole production Job Store SET_STATE writer':'domain lifecycle policy uses Gateway; executor 213 is sole physical writer',
    'Items **1–10 are implemented and validated**':'Items 1–11 are current',
    '**38 Resource Profiles**':'39 Resource Profiles are current',
    'current 38-profile commissioning estimate':'39 Resource Profiles are current',
    'No numbered roadmap milestone remains active':'Item 12 live commissioning is active',
    'recipe_fixture_data':'Recipe fixture GameData moved to tests/fixtures/recipe_game_data/',
 'S320':'the common header is S0..S4; no fixed window at S320 exists',
 'DIRECTORY_ADAPTER_ABI_V2':'Directory Adapter is ABI3; its payload starts at S8 and records at S18',
 'Directory Adapter ABI2':'Directory Adapter is ABI3 since the common header migration',
 '31416053':'the envelope magic was removed with the S320 window; identity is the service magic at S0',
 'PrimaryPayloadBase':'the payload header is the common header, so there is no separate payload base',
 'publishes TransformType S2':'Material Transform Admission publishes TransformType at S14',
 'S2 is requested batch count, S3 request generation':'Material Transform Runtime receives requests at S8/S16',
 'Runtime S7 = committed material epoch':'Material Transform Runtime mirrors the committed epoch at S22',
}
for p in mds:
    txt=p.read_text(errors='replace')
    for phrase,why in forbidden.items():
        if phrase in txt:fails.append(f'{p.name}: stale phrase {phrase!r} ({why})')

wiring=(ROOT/'data/script_wiring.json').read_text()
for phrase,why in {
    'Runtime S7 = committed material epoch':'Material Transform Runtime mirrors the committed epoch at S22',
}.items():
    if phrase in wiring:fails.append(f'data/script_wiring.json: stale phrase {phrase!r} ({why})')

required={
 'ROADMAP.md':['9. Power-management reuse — COMPLETE','10. Broad interruption and fault-injection suite — COMPLETE','11. Cross-domain process & utility orchestration — COMPLETE','12. Live-game commissioning and evidence closure — ACTIVE','Items **1–11 are implemented and automatically validated**','Item **12 is ACTIVE**','docs/LIVE_COMMISSIONING.md','docs/COMPLETED_MILESTONES.md'],
 'docs/COMPLETED_MILESTONES.md':['1. Runtime Store placement','2. Item-level migration and compaction','3. Generic Directory Adapter ABI','4. Printer Directory — COMPLETE','5. Generic Job ABI — COMPLETE','6. Manufacturing scheduler — COMPLETE','Item 7 — Generic Item Inventory & Storage Discovery — COMPLETE','Item 8 — Simple Dependency Planning — COMPLETE','9. Power-management reuse — COMPLETE','10. Broad interruption and fault-injection suite — COMPLETE','11. Cross-domain process & utility orchestration — COMPLETE'],
 'docs/CATALOG_COORDINATION.md':['Coordinator ABI4','64-node directory','runtime capacity','S27','DRAINING','whole-item','recovery','migration'],
 'docs/CATALOG_STORAGE.md':['Store ABI6','Loader ABI5','item directory','payload heap','runtime Store placement','Whole-item invariant','S27','ItemCellCount + 2'],
 'docs/CATALOG_SCHEMA.md':['CatalogSchemaVersion','CELL_BLOCK_WIDTH = 4','canonical zero padding','Resource Profile schema v2','Input Profile schema v3','Transform schema v4','Recipe schema v3'],
 'docs/DEPENDENCY_PLANNING.md':['199 Job Command Gateway ABI3','ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10','ic10/dependency-planning/dependency_plan_store_v2_0.ic10','QuoteFingerprintA','active','FutureQty','root job -> child -> grandchild','physical reservation authority'],
 'docs/ABI_REFERENCE.md':['Store ABI6','Loader ABI5','Coordinator ABI4','DIRECTORY_ADAPTER_ABI_V3','Generic Snapshot Directory Host','DirectorySchema.Controller','DirectorySchema.ResourceReservation','DirectorySchema.Printer','ProcessorSpec','DirectorySchema.PrinterExecution','Generic Job Store ABI v1','31415984','Transform Profile ABI4','RequiredCapabilityMask','Recipe schema v3','Manufacturing Scheduler','ABI2 exactly','Power Management ABIs — current','DirectorySchema.PowerReservation','S6','S7','ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10'],
 'README.md':['ROADMAP.md','docs/PROCESS_UTILITY_ORCHESTRATION.md','docs/INTERRUPTION_FAULT_INJECTION.md','docs/LIVE_COMMISSIONING.md','complete validator/test inventory defined in `tools/run_validation.py`','docs/DEPENDENCY_PLANNING.md','docs/COMPLETED_MILESTONES.md','docs/CATALOG_COORDINATION.md','docs/CATALOG_STORAGE.md','docs/DIRECTORY_STANDARD.md','docs/PRINTER_DIRECTORY.md','docs/GENERIC_JOB_ABI.md','docs/MANUFACTURING_SCHEDULER.md','docs/ASYNC_REQUEST_STANDARD.md','docs/BANKED_TRANSACTION_STANDARD.md','docs/SCRIPT_INDEX.md','tools/run_validation.py','tools/build_release.py','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ic10/generic-jobs/generic_job_store_v1_0.ic10','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','docs/POWER_MANAGEMENT.md','ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10','ic10/power-jobs/power_job_scheduler_v1_0.ic10'],
 'docs/DIRECTORY_STANDARD.md':['DIRECTORY_ADAPTER_ABI_V3','ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10','ic10/directory-core/generic_registry_directory_host_v2_0.ic10','ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10','ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10','data/directory_schemas.json','DirectorySchema.Controller','DirectorySchema.ResourceReservation','DirectorySchema.Printer','DirectorySchema.TransformLane','DirectorySchema.PrinterExecution','DirectorySchema.CatalogStoreNode','DirectorySchema.PowerReservation','overflow'],
 'docs/PRINTER_DIRECTORY.md':['DirectorySchema.Printer','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ProcessorSpec','Printer.Autolathe','Printer.SecurityPrinter','Printer.RocketManufactory','StructureFabricator','Capacity remains 64','DirectorySchema.PrinterExecution','tests/test_printer_directory.py'],
 'docs/RESOURCE_PROFILES.md':['39 Resource Profiles','ProfileKind=5','Fuel.H2O2','physical width is 16 cells','26','FLUID','ITEM','POWER','ENERGY','ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10','ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10','ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10','Store ABI6'],
 'docs/RECIPE_CATALOG.md':['Recipe schema v3','Lookup ABI3','FamilyHash','PartitionKey','18','ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10','ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10','ManufacturingReagentHash','Store ABI6'],
 'docs/ORE_PROCESSING_TRANSFORMS.md':['## 2. Catalog schema','4-cell-aligned','RequiredCapabilityMask','FURNACE_ALLOY','ADVANCED_ALLOY','Advanced Furnace','complete transform','pressure and temperature bounds','Item 6'],
 'docs/DEPLOYMENT.md':['Catalog control-plane v3 commissioning','ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10','generated FLUID and ITEM Resource Profile loader candidates','runtime','Item Migration Planner','Item Migration Worker','one current material transform transaction path','Allocator ABI2 exactly','Generic Job Store','ic10/generic-jobs/generic_job_store_v1_0.ic10','ExpectedJobGeneration','Manufacturing Scheduler and dependency-planner deployment','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','ic10/printer-directory/printer_execution_bank_v2_0.ic10'],
 'docs/ITEM_STORAGE_SYSTEM.md':['ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10','ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10','ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10','ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10','ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10','proxy slot 255','conservative lower bound'],
 'docs/MATERIAL_GRID_FOUNDATION.md':['unified Resource Profile catalog','ic10/item-storage-vending/material_vending_inventory_v1_0.ic10','ic10/material-grid/material_resource_link_v1_0.ic10','ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10','ic10/material-transform/generic_material_transform_runtime_v2_0.ic10','Manufacturing Scheduler','ManufacturingReagentHash'],
 'docs/RESOURCE_GRID_CORE.md':['Multi Material Allocator ABI2','ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','Admission -> Link Resolver -> Multi Reservation Stager -> Material Allocator ABI2 -> Generic Transform Runtime'],
 'docs/CORRECTNESS_HARDENING.md':['Multi Material Allocator ABI2','one to three typed input Material Links','shared commit epoch','Manufacturing scheduler correctness boundary','selected Printer ReferenceId','pressure/temperature'],
 'docs/PRESSURE_RESERVATION_MODEL.md':['Allocator ABI3','QUOTE','COMMIT','Grant Guard'],
 'docs/ASYNC_REQUEST_STANDARD.md':['ASYNC_REQUEST_V1','RequestToken','CurrentToken','State','Error','current token equals the expected request token'],
 'docs/GENERIC_JOB_ABI.md':['GENERIC_JOB_ABI_V1','ic10/generic-jobs/generic_job_store_v1_0.ic10','JobId','RequiredCapability','WAIT_RESOURCE','WAIT_PROCESSOR','WAIT_CAPACITY','QueueSequence','JobGeneration','PUBLISH_NEW','SET_STATE','REAP','32-slot','Manufacturing Scheduler'],
 'docs/INTERRUPTION_FAULT_INJECTION.md':['inject_every_boundary','Catalog migration','Directory mutation','LArRE','POWER replacement','POWER Executors','Generic Job lifecycle','ic10/power-grid/power_dispatch_plan_store_v1_0.ic10','ic10/power-grid/power_reservation_allocator_v1_0.ic10','load/link executors'],
 'docs/POWER_MANAGEMENT.md':['ResourceClass.POWER','ResourceClass.ENERGY','one-game-tick horizon','ic10/generic-jobs/generic_job_selector_v3_0.ic10','DirectorySchema.PowerReservation','Reservation **S7 ImportCapacity**','Reservation **S6 ExportAvailable**','RespectPhysicalOn','foreign','ic10/power-grid/power_reservation_committer_v1_0.ic10','ic10/power-grid/power_reservation_allocator_v1_0.ic10','ic10/power-grid/power_link_executor_v1_0.ic10','JobType.POWER','Gateway lane D','validation/validators/validate_power_management_contracts.py','tests/test_power_management.py'],
 'docs/PROCESS_UTILITY_ORCHESTRATION.md':['ProcessCondition ABI1','31416048','ic10/process-furnace/furnace_process_condition_request_v1_0.ic10','ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10','ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10','ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10','ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10','ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10','ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10','Fuel.H2O2','PressureGrid','Grant Guard','Electrolyzer'],
 'docs/MANUFACTURING_SCHEDULER.md':['ic10/generic-jobs/generic_job_selector_v3_0.ic10','Job Command Gateway ABI3','ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10','ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10','ic10/manufacturing/manufacturing_driver_router_v2_0.ic10','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','ic10/manufacturing/transform_candidate_readiness_v1_0.ic10','DirectorySchema.TransformLane','DirectorySchema.PrinterExecution','ManufacturingReagentHash','one reusable **dynamic** selector','scheduling cursor','ExpectedPrinterRef','OwnerPrinterRef','sole physical Job Store mailbox writer','WAIT_CAPACITY','pressure','temperature'],
}
for name,needles in required.items():
    p=ROOT/name
    if not p.exists():fails.append(f'missing required doc {name}');continue
    txt=p.read_text()
    for n in needles:
        if n not in txt:fails.append(f'{name}: missing current documentation marker {n!r}')
for name in ('docs/PHASE_PRESSURE_CONTROLLER.md','docs/PRESSURE_DOMAIN_CONTROLLER.md'):
    txt=(ROOT/name).read_text()
    if 'S97  2' not in txt and 'S97    2' not in txt:
        fails.append(f'{name}: telemetry header is not documented as ABI2')



# Line counts have one generated documentation source: docs/SCRIPT_INDEX.md.
line_doc=(ROOT/'docs/LINE_COUNT_OPTIMIZATION.md').read_text()
if 'docs/SCRIPT_INDEX.md' not in line_doc or '117 lines or more' not in line_doc:
    fails.append('docs/LINE_COUNT_OPTIMIZATION.md: generated SCRIPT_INDEX/line-pressure policy is missing')

# Manifest-derived synchronization checks. These guard numeric prose that can drift
# even when filenames/ABI markers remain valid.
profile_manifest=json.loads((ROOT/'data/input_profile_catalog_manifest.json').read_text())
profile_count=profile_manifest['profile_count']
production_controller_profiles=[n for n in profile_manifest['profiles'] if n != 'diagnostic']
controller_family_count=len(production_controller_profiles)
profile_markers={
    'docs/SHARED_INPUT_SYSTEM.md':[f'All {profile_count} production/diagnostic definitions'.replace('6','six') if profile_count==6 else f'All {profile_count} production/diagnostic definitions'],
    'docs/DEPLOYMENT.md':[f'current {profile_count} profiles'.replace('6','six') if profile_count==6 else f'current {profile_count} profiles',f'S9={profile_count}'],
    'docs/COMMISSIONING_QUICKSTART.md':[f'S9={profile_count}'],
    'docs/ABI_REFERENCE.md':[f'{profile_count} self-contained variable-length production/diagnostic profiles'.replace('6','Six') if profile_count==6 else f'{profile_count} self-contained variable-length production/diagnostic profiles'],
    'README.md':[f'{profile_count} self-contained schema-v3 production/diagnostic profiles'.replace('6','six') if profile_count==6 else f'{profile_count} self-contained schema-v3 production/diagnostic profiles'],
}
for name,markers in profile_markers.items():
    txt=(ROOT/name).read_text()
    for marker in markers:
        if marker not in txt:fails.append(f'{name}: profile-count prose is not synchronized to manifest profile_count={profile_count} (missing {marker!r})')

# Reject the known stale count forms explicitly so a later edit cannot reintroduce them.
for p in mds:
    txt=p.read_text(errors='replace')
    for stale in ('All seven definitions','current seven profiles','S9=7','Seven self-contained variable-length profiles','seven self-contained schema-v3 profiles'):
        if stale in txt:fails.append(f'{p.name}: stale Input Profile count phrase {stale!r}; manifest has {profile_count}')

arch=(ROOT/'docs/ARCHITECTURE.md').read_text()
family_names=('ControllerPI','ControllerSequencer','ControllerPhasePressure','ControllerPressureDomain','ControllerPressureTransfer')
if f'contains five controller families' not in arch:
    fails.append(f'docs/ARCHITECTURE.md: production family count is not documented as {controller_family_count}')
for family in family_names:
    cross=arch.split('## Cross-family proof of the abstraction boundary',1)[-1].split('## Transaction hardening layer',1)[0]
    if family not in cross:fails.append(f'docs/ARCHITECTURE.md: cross-family table missing {family}')
if 'All five production controller families' not in arch:
    fails.append('docs/ARCHITECTURE.md: generic-service reuse statement is not synchronized to five production controller families')

# Catch accidental consecutive duplicate deployment bullets.
for p in mds:
    lines=p.read_text(errors='replace').splitlines()
    for i in range(1,len(lines)):
        a,b=lines[i-1].strip(),lines[i].strip()
        if a and a==b and re.match(r'^[-*] `[^`]+`',a):
            fails.append(f'{p.name}:{i+1}: consecutive duplicate artifact bullet {a!r}')

# README invariants are a numbered contract: require a contiguous sequence.
readme=(ROOT/'README.md').read_text()
if '## Important invariants' in readme:
    block=readme.split('## Important invariants',1)[1].split('## Terminology',1)[0]
    nums=[int(n) for n in re.findall(r'(?m)^(\d+)\. \*\*',block)]
    if nums and nums != list(range(1,max(nums)+1)):
        fails.append(f'README.md: invariant numbering is not contiguous: {nums}')

count=len(list((ROOT/'ic10').rglob('*.ic10')))
cat=(ROOT/'docs/SCRIPT_INDEX.md').read_text()
if str(count) not in cat:fails.append(f'docs/SCRIPT_INDEX.md: does not visibly reflect current {count}-script count')
for name in ('ic10/controller-discovery/controller_directory_adapter_v4_0.ic10','ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10','ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10','ic10/printer-directory/printer_directory_adapter_v1_0.ic10','ic10/generic-jobs/generic_job_store_v1_0.ic10','ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10','ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10','ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10','ic10/manufacturing/transform_candidate_executor_v2_0.ic10','ic10/manufacturing/print_candidate_executor_v2_0.ic10','ic10/manufacturing/print_material_resolver_v1_0.ic10','ic10/manufacturing/generic_print_runtime_v2_0.ic10','ic10/manufacturing/transform_job_driver_v2_0.ic10','ic10/manufacturing/print_job_driver_v2_0.ic10','ic10/generic-jobs/generic_job_selector_v3_0.ic10','ic10/manufacturing/manufacturing_driver_router_v2_0.ic10','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','ic10/printer-directory/printer_execution_bank_v2_0.ic10','ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10','ic10/printer-directory/printer_capacity_client_v2_0.ic10'):
    if name not in cat:fails.append(f'docs/SCRIPT_INDEX.md: missing {name}')
# Every magic a program publishes must be registered. The block is generated, so a
# new service cannot reach release with its header undocumented.
reference=(ROOT/'docs'/'ABI_REFERENCE.md').read_text()
block=re.search(re.escape(magic_registry.START)+r'.*?'+re.escape(magic_registry.END),reference,re.S)
if not block:
 fails.append('docs/ABI_REFERENCE.md: generated published-header block is missing')
elif block.group(0)!=magic_registry.render(magic_registry.rows()):
 fails.append('docs/ABI_REFERENCE.md: published-header block is stale; run tools/generate/update_magic_registry.py')
registered=set(re.findall(r'`(\d{8})`',reference))
for source in sorted(ROOT.glob('ic10/*/*.ic10')):
 found=re.search(r'^poke 0 (\d+)$',source.read_text(),re.M)
 if found and found.group(1) not in registered:
  fails.append(f'docs/ABI_REFERENCE.md: {source.relative_to(ROOT).as_posix()} publishes unregistered magic {found.group(1)}')
if fails:
    print('Documentation synchronization validation: FAIL')
    for f in fails:print(' -',f)
    sys.exit(1)
print('Documentation synchronization validation: PASS')
print(' - local artifact/test references and local Markdown links resolve')
print(f' - Input Profile prose matches manifest profile_count={profile_count}; production controller-family proof covers {controller_family_count} families')
print(' - generated script index carries current line counts and README invariants are contiguous')
print(' - Store ABI6 / Loader ABI5 / Coordinator ABI4 and Material Allocator ABI2 are documented consistently')
print(' - runtime placement, item migration, Adapter ABI3 freeze, and Registry ABI3 fencing are documented')
print(f' - script index reflects {count} deployable IC10 programs')
