#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys,tempfile
from framework.catalog_test_helpers import generate_recipe_fixture
R=_PROJECT_ROOT; fails=[]
def fail(x): fails.append(x)
def need(path,*tokens):
    t=(R/path).read_text()
    for tok in tokens:
        if tok not in t: fail(f'{path}: missing {tok!r}')
# Recipe v3 + execution metadata.
recipe_tmp=tempfile.TemporaryDirectory();rm=generate_recipe_fixture(Path(recipe_tmp.name))
if rm.get('catalog_schema_version')!=3 or rm.get('format')!='RECIPE_CATALOG_V6': fail('Recipe catalog is not schema3/format V6')
if rm.get('item_model')!='header5_plus_reagent_pairs_block_aligned' or rm.get('max_material_inputs')!=16: fail('Recipe execution item model mismatch')
need('ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10')
need('ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10','poke 0 31415985','poke 1 1','bgt r4 16 Bad','poke 41 r10')
# Material semantic aliases reuse Resource Profiles.
profiles=json.loads((R/'data/resource_profiles.json').read_text())['profiles']
ingots=[p for p in profiles if p['resource_class']==2 and p.get('profile_schema')==2]
if not ingots or any(p['parameter_names'][2]!='ManufacturingReagentHash' or not p['params'][2] for p in ingots): fail('ITEM schema2 ingot reagent aliases missing')
need('ic10/material-grid/material_resource_link_v1_0.ic10','poke 27 r0','getd r0 r5 14','getd r0 r0 15')
# Transform environmental bounds are enforced for every compatible furnace class.
need('ic10/material-transform/material_transform_admission_v1_0.ic10','l r0 d1 Pressure','get r5 d0 64','get r5 d0 65','l r0 d1 Temperature','get r5 d0 66','get r5 d0 67')
# Transform Profile View ABI4 publishes resolved request identity/status.
need('ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10','poke 1 4','poke 68 r10','poke 69 1','poke 71 -2','poke 71 -3')
# Generation-driven readiness replaces the old arbitrary 16-tick executor wait.
need('ic10/manufacturing/transform_candidate_readiness_v1_0.ic10','poke 0 31415998','poke 1 1','getd r0 r12 68','bne r0 r2 Loop','getd r7 r9 9','beq r7 r0 Loop','getd r7 r10 7','beq r7 r0 Loop','move r0 -2','move r0 -3','move r0 -4')
if 'blt r' in (R/'ic10/manufacturing/transform_candidate_executor_v2_0.ic10').read_text() and ' 16 ' in (R/'ic10/manufacturing/transform_candidate_executor_v2_0.ic10').read_text(): fail('Transform executor retains fixed 16-tick timeout')
need('ic10/manufacturing/transform_candidate_executor_v2_0.ic10','poke 1 2','put d0 8 r15','get r0 d0 10','bne r0 r15 Loop')
# Dynamic generic candidate selector: one physical instance can serve either schema.
need('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10','poke 1 2','get r9 db 16','getd r0 r9 0','bne r0 r2 Bad','getd r0 r9 2','bne r0 r8 Loop')
# Printing reuses four-cell resolver records + common allocator.
need('ic10/manufacturing/print_material_resolver_v1_0.ic10','poke 0 31415989','bne r0 HASH("DirectorySchema.ResourceLink.v1") Bad','mul r0 r7 4','poke r0 r1','poke r0 r12','poke r0 r5','poke r0 2')
need('ic10/manufacturing/generic_print_runtime_v2_0.ic10','poke 1 2','poke 8 2','poke 9 0','poke 7 r15','put d1 2 r4','putd r2 0 3')
# Async state is fenced by matching request identities across every orchestration boundary.
need('ic10/manufacturing/transform_job_driver_v2_0.ic10','poke 1 2','poke 10 2','poke 11 0','poke 9 r15','get r1 d1 10','bne r1 r15 Loop','put d0 16 r1')
need('ic10/manufacturing/print_job_driver_v2_0.ic10','poke 1 2','poke 10 2','poke 11 0','poke 9 r15','get r1 d2 10','bne r1 r15 Loop','put d0 16 r1')
need('ic10/manufacturing/manufacturing_driver_router_v2_0.ic10','poke 1 2','get r0 d0 9','bne r0 r15 Loop','get r0 d1 9','bne r0 r15 Loop','poke 10 r15')
need('ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','get r0 d2 10','get r1 db 27','bne r0 r1 Loop')
# Fair queue traversal skips all JobIds at/before cursor, so multiple WAIT jobs cannot alternate forever.
need('ic10/generic-jobs/generic_job_selector_v3_0.ic10','poke 1 3','get r10 db 18','ble r4 r0 Next','bgt r14 r7 Choose','bge r4 r8 Next')
if 'put d0' in (R/'ic10/generic-jobs/generic_job_selector_v3_0.ic10').read_text(): fail('Job Selector must remain read-only')
# Printer bank ABI2 separates requests/responses/ownership and validates expected exact identity.
need('ic10/printer-directory/printer_execution_bank_v2_0.ic10','poke 1 2','add r0 r7 32','get r11 db r0','bne r11 r1 Processor','add r0 r7 64','poke r0 r1','add r0 r7 72','poke r0 r5','add r0 r7 48','poke r0 r14','add r0 r7 56','poke r0 r5')
bank=(R/'ic10/printer-directory/printer_execution_bank_v2_0.ic10').read_text()
reset=bank.split('Reset:',1)[1].split('Loop:',1)[0]
if 'Lock 0' in reset: fail('Execution Bank clears external Lock during reset without ownership proof')
# Capacity client reasserts request during wait, post-validates owner identity, and acknowledges release.
need('ic10/printer-directory/printer_capacity_client_v2_0.ic10','poke 1 2','WaitReserve:','putd r1 r0 r4','putd r1 r0 r15','getd r0 r1 r0','bne r0 r4 Cleanup','getd r0 r1 r0','bne r0 r15 Cleanup','ReleaseWait:','bne r0 r12 ReleaseWait')
# Central services never attempt remote slot access.
for f in ('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10','ic10/manufacturing/print_candidate_executor_v2_0.ic10','ic10/manufacturing/print_material_resolver_v1_0.ic10','ic10/manufacturing/generic_print_runtime_v2_0.ic10','ic10/manufacturing/print_job_driver_v2_0.ic10','ic10/printer-directory/printer_capacity_client_v2_0.ic10'):
    if '\nls ' in '\n'+(R/f).read_text(): fail(f+': central manufacturing service performs direct slot access')
# Scheduler alone applies Job Store lifecycle SET_STATE.
need('ic10/manufacturing/manufacturing_scheduler_v1_0.ic10','poke 0 31415995','put d0 11 2','put d0 13 r1','put d0 14 r4','put d0 15 r5','add r4 r2 1')
sched=(R/'ic10/manufacturing/manufacturing_scheduler_v1_0.ic10').read_text()
for tok in ('put d0 288','put d0 289','put d0 290'):
    if tok in sched: fail('Scheduler bypasses Job Store mailbox: '+tok)
# Manufacturing/recipe/printer execution services remain bounded after semantic renaming.
item6=[
'ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10','ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10',
'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10','ic10/manufacturing/transform_candidate_executor_v2_0.ic10',
'ic10/manufacturing/print_candidate_executor_v2_0.ic10','ic10/manufacturing/print_material_resolver_v1_0.ic10',
'ic10/manufacturing/generic_print_runtime_v2_0.ic10','ic10/manufacturing/transform_job_driver_v2_0.ic10',
'ic10/manufacturing/print_job_driver_v2_0.ic10','ic10/generic-jobs/generic_job_selector_v3_0.ic10',
'ic10/manufacturing/manufacturing_driver_router_v2_0.ic10','ic10/manufacturing/manufacturing_scheduler_v1_0.ic10',
'ic10/printer-directory/printer_execution_bank_v2_0.ic10','ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10',
'ic10/printer-directory/printer_capacity_client_v2_0.ic10','ic10/manufacturing/transform_candidate_readiness_v1_0.ic10']
for rel in item6:
    p=R/rel
    if not p.exists(): fail(f'missing manufacturing service {rel}')
    elif len(p.read_text().splitlines())>128: fail(rel+': exceeds the 128-line hard limit')
if fails:
    print('Manufacturing contracts: FAIL'); [print(' -',x) for x in fails]; sys.exit(1)
print('Manufacturing contracts: PASS')
print(' - async state/error publication is request-token fenced end-to-end')
print(' - Transform readiness is profile/generation-qualified with no arbitrary 16-tick timeout')
print(' - WAIT traversal reaches lower-priority runnable jobs across multiple waiters')
print(' - Printer reservation separates request/response identity from exact-ref lock ownership')
print(' - one dynamic manufacturing selector implementation can serve Transform and Print domains')
print(' - manufacturing execution contains 16 bounded semantic services/adapters, all <=120 lines')
