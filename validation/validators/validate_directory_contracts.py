#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from framework.scan_coverage import require_nonempty,require_nonempty_glob
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT;result=Validation(R)
fail=result.fail
need=result.contains
D=json.loads((R/'data/directory_schemas.json').read_text())
if D.get('format')!='GENERIC_DIRECTORY_SCHEMAS_V10': fail('schema registry format mismatch')
a=D.get('adapter_abi',{})
for k,v in {'magic':583163590,'abi':2,'candidate_base':16,'entry_width_slot':4,'capacity_slot':5,'candidate_count_slot':6,'candidate_generation_slot':7,'sequence_slot':8,'overflow_slot':9,'mode_slot':10,'freeze_request_slot':11,'freeze_ack_slot':12}.items():
    if a.get(k)!=v: fail(f'adapter ABI {k} mismatch')
for k in ('published_magic_slot','published_abi_slot'):
    if k in a: fail('legacy adapter field remains: '+k)
sh=D.get('snapshot_host',{}); rh=D.get('registry_host',{})
if sh.get('boot_marker_slot')!=31 or 'generic_magic_slot' in sh: fail('snapshot boot marker metadata mismatch')
if rh.get('publication_sequence_slot')!=23 or 'generic_magic_slot' in rh: fail('registry publication metadata mismatch')
need('ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10','poke 0 HASH("GenericSnapshotDirectoryHost.v1")','poke 1 1','bgt r2 3 Error','bgt r3 64 Error','poke 22 1','poke 24 r6','poke 15 r15','Shift:\nbge r6 r3 Full','Insert:\nbge r6 r3 Full')
need('ic10/directory-core/generic_registry_directory_host_v2_0.ic10','poke 0 HASH("GenericRegistryDirectoryHost.v3")','poke 1 3','put d0 16 r11','get r0 d0 17','bne r0 HASH("DirectorySchema.CatalogStoreNode.v1") SourceBad','bne r0 6 SourceBad','get r10 db 23','poke 23 r10','put d0 16 0')
need('ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10','bne r0 HASH("DirectoryAdapter.v3") Loop','put d0 16 r11','get r0 d0 17','get r15 d0 13','get r10 d0 7','bne r0 r15 Release','bne r0 r10 Release','get r1 d1 9\nbeqz r1 Configure\nbne r1 r0 Release','get r1 d1 11\nbeqz r1 Configure\nbne r1 r2 Release','get r1 d1 12\nbeqz r1 Configure\nbne r1 r3 Release','Configure:\nput d1 9 r0\nput d1 11 r2\nput d1 12 r3\nBegin:','put d0 16 0')
expected={
 'DirectorySchema.Controller':('ic10/controller-discovery/controller_directory_adapter_v4_0.ic10',1,2),
 'DirectorySchema.PressureGridLink':('ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10',1,3),
 'DirectorySchema.ResourceEndpoint':('ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10',1,3),
 'DirectorySchema.ResourceReservation':('ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10',1,3),
 'DirectorySchema.PowerReservation':('ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10',1,3),
 'DirectorySchema.ResourceLink':('ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10',1,1),
 'DirectorySchema.Printer':('ic10/printer-directory/printer_directory_adapter_v1_0.ic10',2,3),
 'DirectorySchema.TransformLane':('ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10',1,3),
 'DirectorySchema.PrinterExecution':('ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10',1,3),
}
seen=set()
for x in D.get('schemas',[]):
    sid=x['schema_id']; seen.add(sid)
    if x.get('capacity')!=64: fail(sid+': capacity != 64')
    if 'published_magic' in x or 'published_abi' in x: fail(sid+': legacy consumer header remains')
    if x['mode']=='snapshot':
        if sid not in expected:
            fail('unexpected snapshot schema '+sid); continue
        f,ver,width=expected[sid]
        need(f,'poke 0 HASH("DirectoryAdapter.v3")','poke 1 3','poke 2 17',f'poke 3 HASH("{sid}.v{ver}")',f'poke 10 {width}','poke 11 64','poke 15 1','get r0 db 16','poke 17 r0')
        if width*x['capacity']>192: fail(sid+': A/B bank stride exceeds generic Host geometry')
        if x.get('schema_version')!=ver or x.get('entry_width')!=width: fail(sid+': registry geometry/version mismatch')
    elif sid=='DirectorySchema.CatalogStoreNode':
        if x.get('entry_width')!=6 or x.get('adapter_entry_width')!=6: fail('Catalog Store registry geometry mismatch')
        need('ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10','poke 0 HASH("DirectoryAdapter.v3")','poke 1 3','poke 2 17','poke 3 HASH("DirectorySchema.CatalogStoreNode.v1")','poke 10 6','poke 11 64','poke 15 2','get r0 db 16','poke 17 r0')
    else: fail('unexpected registry schema '+sid)
if seen!=set(expected)|{'DirectorySchema.CatalogStoreNode'}: fail('directory schema set mismatch: '+repr(seen))

# Snapshot records begin at S32 plus active-bank * (published width * capacity).
# Consumers must derive that stride from the Host instead of baking in today's schemas.
snapshot_stride_consumers={
 'ic10/controller-discovery/controller_selector_v3_0.ic10':'get r0 directory 11\nbne r0 2 NoDirectory\nget r8 directory 12\nmul r8 r0 r8\nmul r8 r10 r8\nadd r8 r8 32',
 'ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad\nget r9 d0 12\nmul r9 r0 r9\nmul r9 r12 r9\nadd r9 r9 32',
 'ic10/material-transform/material_transform_link_resolver_v1_0.ic10':'get r0 d2 11\nbne r0 1 Bad\nget r9 d2 12\nmul r9 r0 r9\nmul r9 r12 r9\nadd r9 r9 32',
 'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10':'getd r0 r9 11\nbne r0 3 Bad\ngetd r13 r9 12\nmul r13 r0 r13\nmul r13 r8 r13\nadd r13 r13 32',
 'ic10/manufacturing/print_material_resolver_v1_0.ic10':'get r13 d1 11\nbne r13 1 Bad\nget r1 d1 12\nmul r13 r13 r1\nmul r13 r13 r0\nadd r13 r13 32',
 'ic10/power-grid/power_link_selector_v1_0.ic10':'get r0 d0 11\nbne r0 1 Bad\nget r10 d0 12\nmul r10 r0 r10\nmul r10 r8 r10\nadd r10 r10 32',
 'ic10/power-grid/power_sink_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad\nget r8 d0 12\nmul r8 r0 r8\nmul r8 r5 r8\nadd r8 r8 32',
 'ic10/power-grid/power_source_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad\nget r8 d0 12\nmul r8 r0 r8\nmul r8 r5 r8\nadd r8 r8 32',
 'ic10/power-jobs/power_policy_target_resolver_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad\nget r10 d0 12\nmul r10 r0 r10\nmul r10 r8 r10\nadd r10 r10 32',
 'ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10':'get r0 d0 11\nbne r0 2 BadDirectory\nget sp d0 12\nmul sp r0 sp\nmul sp r6 sp\nadd sp sp 32',
 'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10':'get r0 d1 11\nbne r0 2 Publish\nget sp d1 12\nmul sp r0 sp\nmul sp r6 sp\nadd sp sp 32',
 'ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10':'get sp d0 11\nbne sp 3 Bad\nget r10 d0 12\nmul sp sp r10\nmul sp r4 sp\nadd sp sp 32',
 'ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10':'get r0 d0 11\nbne r0 3 Fail\nget sp d0 12\nmul sp r0 sp\nmul sp r5 sp\nadd sp sp 32',
 'ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10':'get r0 d0 11\nbne r0 3 Loop\nget r13 d0 12\nmul r13 r0 r13\nmul r13 r11 r13\nadd r13 r13 32',
}
snapshot_width_checks={
 'ic10/controller-discovery/controller_selector_v3_0.ic10':'get r0 directory 11\nbne r0 2 NoDirectory',
 'ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad',
 'ic10/material-transform/material_transform_link_resolver_v1_0.ic10':'get r0 d2 11\nbne r0 1 Bad',
 'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10':'getd r0 r9 11\nbne r0 3 Bad',
 'ic10/manufacturing/print_material_resolver_v1_0.ic10':'get r13 d1 11\nbne r13 1 Bad',
 'ic10/power-grid/power_link_selector_v1_0.ic10':'get r0 d0 11\nbne r0 1 Bad',
 'ic10/power-grid/power_sink_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad',
 'ic10/power-grid/power_source_selector_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad',
 'ic10/power-jobs/power_policy_target_resolver_v1_0.ic10':'get r0 d0 11\nbne r0 3 Bad',
 'ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10':'get r0 d0 11\nbne r0 2 BadDirectory',
 'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10':'get r0 d1 11\nbne r0 2 Publish',
 'ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10':'get sp d0 11\nbne sp 3 Bad',
 'ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10':'get r0 d0 11\nbne r0 3 Fail',
 'ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10':'get r0 d0 11\nbne r0 3 Loop',
}
snapshot_host='ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10'
wiring=json.loads((R/'data/script_wiring.json').read_text())['ports']
wired={f for f,ports in wiring.items() for port in ports.values()
       if snapshot_host in port.get('providers',[])}
production_sources=require_nonempty_glob(R,'ic10/*/*.ic10')
identified=set(require_nonempty(
 (p.relative_to(R).as_posix() for p in production_sources
  if 'HASH("GenericSnapshotDirectoryHost.v1")' in p.read_text()),
 'Snapshot Directory identity consumers'))
metadata_only={snapshot_host,'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10',
               'ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10'}
discovered=(wired|identified)-metadata_only
if discovered!=set(snapshot_stride_consumers):
    fail('Snapshot Directory record-consumer inventory mismatch: '+repr(sorted(discovered^set(snapshot_stride_consumers))))
for f,derivation in snapshot_stride_consumers.items():
    need(f,derivation,snapshot_width_checks[f])
    source=(R/f).read_text()
    if re.search(r'(?m)^mul\s+\S+\s+\S+\s+(?:64|128|192)(?:\s|$)',source):
        fail(f+': hard-coded Snapshot Directory bank stride remains')
    if re.search(r'(?m)^move\s+\S+\s+(?:96|160|224)(?:\s|$)',source):
        fail(f+': hard-coded Snapshot Directory bank base remains')

# Printer v2 exposes one common ProcessorSpec shared with TransformLane selection.
ps=next((x for x in D['schemas'] if x['schema_id']=='DirectorySchema.Printer'),None)
if not ps or ps.get('fields')!=['ReferenceId','FamilyHash','ProcessorSpec']: fail('Printer v2 record geometry mismatch')
else:
    spec=ps.get('processor_spec',{})
    for k,v in {'bits_0_7':'capability tier','bit_8':'Power','bit_9':'Busy/Active','bit_10':'Error','bit_11':'On','bit_12':'Lock'}.items():
        if spec.get(k)!=v: fail('Printer ProcessorSpec '+k+' mismatch')
    fams={x.get('family_hash') for x in ps.get('families',[])}
    recipe_src=(R/'tools'/'generate'/'generate_recipe_catalog.py').read_text()
    recipe_fams=set(re.findall(r"\('(?:[^']+)'\s*,\s*'([^']+)'\s*,",recipe_src.split('TIER_WORDS',1)[0]))
    if fams!=recipe_fams: fail('Printer FamilyHash set differs from Recipe Catalog FAMILIES')
need('ic10/printer-directory/printer_directory_adapter_v1_0.ic10','poke 3 HASH("DirectorySchema.Printer.v2")','HASH("Printer.Autolathe")','HASH("Printer.SecurityPrinter")','HASH("Printer.RocketManufactory")','ld r4 r1 Power','ld r6 r1 Activate','ld r9 r1 Error')

# Transform lanes and printer-execution overlay are native generic-directory schemas.
tl=next((x for x in D['schemas'] if x['schema_id']=='DirectorySchema.TransformLane'),None)
if not tl or tl.get('fields')!=['RuntimeReferenceId','ProcessorReferenceId','ProcessorSpec']: fail('TransformLane record mismatch')
need('ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10','getd r0 r1 0','bne r0 HASH("GenericMaterialTransformRuntime.v2") Scan','poke r4 r1','poke r4 r2')
pe=next((x for x in D['schemas'] if x['schema_id']=='DirectorySchema.PrinterExecution'),None)
if not pe or pe.get('fields')!=['PrinterReferenceId','FamilyHash','ProcessorSpec']: fail('PrinterExecution record mismatch')
need('ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10','bne r0 HASH("DirectorySchema.Printer.v2") Loop','poke r0 r2','sll r0 r6 16')

# Incomplete snapshots are unusable on transaction-critical paths.
for f,toks in {
 'ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10':['get r0 d0 2','add sp r0 29','bgtz r1 LinkBad'],
 'ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10':['add sp r4 29','bgtz r0 Bad','get r0 d0 2','bne r0 r4 Bad'],
 'ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10':['add sp r5 29','bgtz r0 Reject'],
 'ic10/material-transform/material_transform_link_resolver_v1_0.ic10':['add r0 r12 29','bgtz r0 Bad','get r0 d2 2','bne r0 r12 Loop'],
 'ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10':['get r9 db 16','add r0 r8 25','getd r12 r9 r0','bnez r12 Bad','getd r0 r9 24','bne r0 r8 Loop'],
 'ic10/manufacturing/print_material_resolver_v1_0.ic10':['add r1 r0 25','get r12 d1 r1','bnez r12 Bad'],
}.items(): need(f,*toks)
# Registry readers that can expose state or trigger side effects fence S23 and require the
# Registry Host identity, which carries ABI3 in its hashed name.
for f,toks in {
 'ic10/catalog-control-plane/catalog_inspector_v4_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Bad','getd r10 r14 23'],
 'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Loop','getd r15 r12 23'],
 'ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Loop','get r14 d0 23'],
 'ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Bad','get r15 d0 23'],
 'ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Loop','get r11 d1 23','bne r0 r11 Loop'],
 'ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Loop','get r12 d1 23','bne r0 r12 Loop'],
 'ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10':['bne r0 HASH("GenericRegistryDirectoryHost.v3") Loop','get r11 d1 23','bne r0 r11 Loop'],
}.items(): need(f,*toks)
# Domain directory magic numbers must not survive in current IC10 code. Glob under
# ic10/, where the programs live -- anchored at the root this matched nothing.
sources={p:p.read_text() for p in production_sources}
if not sources: fail('no production IC10 sources found; the legacy-magic sweep is unchecked')
for legacy in ('14142135','31415939','14142138','14142139','31415973'):
    for p,text in sources.items():
        if legacy in text: fail(f'legacy directory magic {legacy} remains in {p.relative_to(R).as_posix()}')
raise SystemExit(result.finish('Generic Directory contracts',[
 'Adapter ABI3 feeds Controller/Pressure/Resource/Reservation/Printer/TransformLane/PrinterExecution snapshots',
 'Snapshot Directory consumers derive each bank stride from the Host width and capacity',
 'Snapshot Bridge treats nonzero Host schema geometry as immutable until reinitialization',
 'Printer v2 and TransformLane v1 share ProcessorSpec capability/power/busy/error semantics',
 'PrinterExecution v1 preserves exact PrinterRef and overlays locally verified output capacity',
 'transaction-critical snapshot consumers fail closed on overflow and revalidate active bank/generation']))
