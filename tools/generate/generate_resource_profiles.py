#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from collections import defaultdict
from framework.catalog_generation import (
 CatalogFamily,CatalogPartition,declared_output_inventory,run_catalog_generation,
)
from framework.catalog_schema import (
 CELL_BLOCK_WIDTH,COORDINATION_PROGRAM_FILES,COORD_MAGIC,GENERIC_STORE_FILE,STORE_ABI,STORE_MAGIC,CatalogItem,
)
SOURCE_FILE='data/resource_profiles.json';MANIFEST_FILE='data/resource_profile_catalog_manifest.json';VIEW_FILE='ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10';RESOLVER_FILE='ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10'
R=_PROJECT_ROOT
SCHEMA='CatalogSchema.ResourceProfile';SCHEMA_VERSION=2;INSTANCE='Catalog.ResourceProfiles.Schema2'
VIEW_MAGIC=31415963;VIEW_ABI=1;SEMANTIC_WIDTH=14;ITEM_CELLS=16
CLASS_NAMES={1:'fluid',2:'item',4:'power',5:'energy'}

def build_partitions(D):
 P=D['profiles']
 seen=set()
 for p in P:
  k=(p['resource_class'],str(p['resource_type_kind']),str(p['resource_type']))
  if k in seen:raise SystemExit(f'duplicate resource profile identity: {k}')
  seen.add(k)
  if len(p['params'])!=9:raise SystemExit(p['slug']+': expected 9 params')
 groups=defaultdict(list)
 for p in P:groups[p['resource_class']].append(p)
 partitions=[]
 for cls in sorted(groups):
  items=[]
  for p in groups[cls]:
   typ=f'HASH("{p["resource_type"]}")' if p['resource_type_kind']=='hash_name' else p['resource_type']
   vals=[typ,p['resource_class'],p['unit'],p['profile_kind'],p['profile_schema'],*p['params'],0,0]
   vals=vals[:ITEM_CELLS]+[0]*max(0,ITEM_CELLS-len(vals))
   human=p.get('description') or p.get('resource_type_name') or p['slug'];items.append(CatalogItem(tuple(vals),human))
  cname=CLASS_NAMES[cls]
  partitions.append(CatalogPartition(str(cls),f'GENERATED Resource Profile {cname.upper()} loader',tuple(items),{'partition_key':cls,'partition':'ResourceClass.'+cname.upper(),'cname':cname}))
 return tuple(partitions)

def render_outputs(D):
 P=D['profiles']
 view=f'''# Resource Profile View v4: dynamic Store ABI5 item directory; d0=any Store.
poke 0 {VIEW_MAGIC}
poke 1 {VIEW_ABI}
poke 2 0
poke 28 0
poke 29 0
Loop:
yield
get r10 db 26
get r11 db 27
bdns d0 Bad
l r2 d0 ReferenceId
get r12 d0 11
blez r12 Bad
getd r0 r12 0
bne r0 {COORD_MAGIC} Bad
getd r15 r12 22
mod r0 r15 2
bnez r0 Bad
get r13 d0 13
First:
getd r1 r2 21
blez r1 Store
move r2 r1
j First
Store:
getd r0 r2 0
bne r0 {STORE_MAGIC} Bad
getd r0 r2 1
bne r0 {STORE_ABI} Bad
getd r0 r2 3
bne r0 HASH("{SCHEMA}.v{SCHEMA_VERSION}") Bad
getd r0 r2 13
bne r0 r13 Bad
getd r14 r2 17
mod r0 r14 2
bnez r0 Loop
getd r7 r2 9
move r5 0
Scan:
bge r5 r7 StoreDone
mul r8 r5 2
add r8 r8 32
getd r8 r2 r8
add r0 r8 1
getd r0 r2 r0
bne r0 r10 Next
getd r0 r2 r8
bne r0 r11 Next
poke 29 0
add r0 r8 1
getd r0 r2 r0
poke 8 r0
getd r0 r2 r8
poke 9 r0
move r9 2
Copy:
bge r9 14 Done
add r1 r8 r9
getd r0 r2 r1
add r1 r9 8
poke r1 r0
add r9 r9 1
j Copy
Done:
getd r0 r2 17
bne r0 r14 Loop
getd r0 r12 22
bne r0 r15 Loop
poke 22 r13
getd r0 r12 21
poke 23 r0
poke 28 1
poke 29 r14
j Loop
Next:
add r5 r5 1
j Scan
StoreDone:
getd r1 r2 24
blez r1 Missing
move r2 r1
j Store
Bad:
poke 29 0
poke 28 -2
j Loop
Missing:
getd r0 r12 22
bne r0 r15 Loop
poke 29 0
poke 28 -3
j Loop'''
 # Item 8 manufacturing reagent aliases are derived from ITEM Resource Profiles.
 reagents=[]; reagent_seen={}
 for p in P:
  if p['resource_class'] != 2: continue
  names=p.get('parameter_names',[])
  if 'ManufacturingReagentHash' not in names: continue
  idx=names.index('ManufacturingReagentHash'); alias=p['params'][idx]
  if not alias: continue
  rt=p['resource_type']
  if p['resource_type_kind'] != 'literal_hash': raise SystemExit(p['slug']+': dependency reagent resolver requires literal ITEM ResourceType')
  if alias in reagent_seen and reagent_seen[alias] != rt: raise SystemExit(f'duplicate ManufacturingReagentHash {alias}')
  reagent_seen[alias]=rt; reagents.append((alias,rt))
 rl=['# Generated manufacturing reagent alias -> concrete ITEM ResourceType.','poke 0 31416017','poke 1 1','Loop:','yield','get r15 db 3','get r0 db 4','beq r15 r0 Loop','get r2 db 2']
 for i,(alias,_) in enumerate(reagents): rl.append(f'beq r2 {alias} R{i}')
 rl += ['poke 5 -2','poke 6 0','poke 4 r15','j Loop']
 for i,(_,rt) in enumerate(reagents): rl += [f'R{i}:',f'poke 6 {rt}','poke 5 1','poke 4 r15','j Loop']
 reagent_text='\n'.join(rl)+'\n'
 if len(reagent_text.splitlines())>120: raise SystemExit('215 reagent resolver exceeds 120-line IC10 ceiling')
 return {VIEW_FILE:view,RESOLVER_FILE:reagent_text}

def loader_filename(partition,ordinal):
 cname=partition.metadata['cname']
 return f'ic10/resource-profile-catalog/resource_profile_loader_{cname}_{ordinal:02d}_v4_0.ic10'

def manifest_extensions(D,result):
 partitions=[]
 for generated in result.partitions:
  metadata=generated.definition.metadata
  partitions.append({'partition_key':metadata['partition_key'],'partition':metadata['partition'],'item_count':generated.item_count,'item_cells':ITEM_CELLS,'runtime_min_store_count':generated.runtime_min_store_count,'loader_count':len(generated.loaders),'loaders':list(generated.loaders)})
 return {'format':'RESOURCE_PROFILE_CATALOG_V6','catalog_token':result.token,'profile_count':result.total_items,'semantic_record_width':SEMANTIC_WIDTH,'physical_item_width':ITEM_CELLS,'storage_partition':'resource_class','runtime_store_placement':True,'runtime_min_store_count':result.runtime_min_store_count,'loader_segment_count':len(result.loaders),'loaders':list(result.loaders),'partitions':partitions,'loader_item_atomicity':'logical_item_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':result.coordination_programs[1],'loader_router_program':result.coordination_programs[2]}

def source_extensions(D,result):
 return {'format':'RESOURCE_PROFILE_CATALOG_V6','catalog_schema_id':SCHEMA,'catalog_schema_version':SCHEMA_VERSION,'catalog_instance_id':INSTANCE,'cell_block_width':CELL_BLOCK_WIDTH,'semantic_record_width':SEMANTIC_WIDTH,'physical_item_width':ITEM_CELLS,'storage_partition':'resource_class'}

FIXED_OUTPUTS=COORDINATION_PROGRAM_FILES+(VIEW_FILE,RESOLVER_FILE,MANIFEST_FILE,SOURCE_FILE)

def family():
 return CatalogFamily(root=R,source_file=SOURCE_FILE,manifest_file=MANIFEST_FILE,schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,collection_key='profiles',digest_prefix='RP6',cleanup_globs=('ic10/resource-profile-catalog/resource_profile_loader_*_v*.ic10','ic10/resource-profile-catalog/resource_profile_view_v*.ic10',RESOLVER_FILE),rendered_output_files=(VIEW_FILE,RESOLVER_FILE),build_partitions=build_partitions,loader_filename=loader_filename,render_outputs=render_outputs,manifest_extensions=manifest_extensions,source_extensions=source_extensions,summary_label='Resource Profile',summary_item_name='profiles')

def declared_outputs():return declared_output_inventory(family())

def main():run_catalog_generation(family())

if __name__=='__main__':main()
