#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.catalog_generation import (
 CatalogFamily,CatalogPartition,declared_output_inventory,run_catalog_generation,
)
from framework.catalog_schema import (
 CELL_BLOCK_WIDTH,COORDINATION_PROGRAM_FILES,COORD_TOKEN,GENERIC_STORE_FILE,STORE_ABI,STORE_TOKEN,CatalogItem,align_block,
)
SOURCE_FILE='data/input_profiles.json';MANIFEST_FILE='data/input_profile_catalog_manifest.json';VIEW_FILE='ic10/input-profile-catalog/input_profile_view_v5_0.ic10'
R=_PROJECT_ROOT
SCHEMA='CatalogSchema.InputProfile';SCHEMA_VERSION=3;INSTANCE='Catalog.InputProfiles.Schema3';PROFILE_CONTRACT='InputProfileView';PROFILE_ABI=1;PROFILE_TOKEN='HASH("InputProfileView.v1")'

def build_partitions(D):
 P=D['profiles']
 for p in P:
  if p['field_count']!=len(p['descriptors']):raise SystemExit(p['slug']+': field count mismatch')
 def ev(v):
  if isinstance(v,str) and (v.startswith('Controller') or v=='DiagnosticMapping'):return f'HASH("{v}")'
  return v
 items=[]
 for p in P:
  vals=[ev(p['profile_type']),p['schema'],p['field_count'],len(p['enum_pairs'])]
  for d in p['descriptors']:vals += [ev(x) for x in d]
  for pair in p['enum_pairs']:vals += [ev(x) for x in pair]
  vals += [0]*(align_block(len(vals))-len(vals));items.append(CatalogItem(tuple(vals),p.get('name') or p['profile_type']))
 return (CatalogPartition('0','GENERATED Input Profile loader',tuple(items)),)

def render_outputs(D):
 view=f'''# Input Profile View v5: dynamic Store ABI5 self-contained profile items.
poke 0 {PROFILE_TOKEN}
poke 1 {PROFILE_ABI}
poke 2 0
poke 11 0
Loop:
yield
get r10 db 8
get r11 db 9
bdns d0 Bad
l r2 d0 ReferenceId
get r12 d0 11
blez r12 Bad
getd r0 r12 0
bne r0 {COORD_TOKEN} Bad
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
bne r0 {STORE_TOKEN} Bad
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
Find:
bge r5 r7 StoreDone
mul r8 r5 2
add r8 r8 32
getd r8 r2 r8
getd r0 r2 r8
bne r0 r10 Next
add r9 r8 1
getd r0 r2 r9
bne r0 r11 Next
add r9 r8 2
getd r4 r2 r9
blt r4 1 Bad
bgt r4 32 Bad
add r9 r8 3
getd r6 r2 r9
poke 11 0
move r9 0
Zero:
add r1 r9 32
poke r1 0
add r9 r9 1
blt r9 224 Zero
move r9 0
mul r1 r4 4
add r7 r8 4
CopyDesc:
bge r9 r1 EnumStart
add sp r7 r9
getd ra r2 sp
add sp r9 32
poke sp ra
add r9 r9 1
j CopyDesc
EnumStart:
add r7 r7 r1
move r9 0
Enum:
bge r9 r6 Done
mul sp r9 2
add sp sp r7
getd ra r2 sp
add sp sp 1
getd sp r2 sp
blt ra 128 Bad
bgt ra 255 Bad
poke ra sp
add r9 r9 1
j Enum
Done:
getd r0 r2 17
bne r0 r14 Loop
getd r0 r12 22
bne r0 r15 Loop
poke 10 r4
poke 11 r14
j Loop
Next:
add r5 r5 1
j Find
StoreDone:
getd r1 r2 24
blez r1 Missing
move r2 r1
j Store
Bad:
poke 11 0
j Loop
Missing:
getd r0 r12 22
bne r0 r15 Loop
poke 11 0
j Loop'''
 return {VIEW_FILE:view}

def loader_filename(partition,ordinal):
 return f'ic10/input-profile-catalog/input_profile_catalog_loader_{ordinal:02d}_v4_0.ic10'

def manifest_extensions(D,result):
 partition=result.partitions[0]
 return {'format':'INPUT_PROFILE_CATALOG_V4','catalog_token':result.token,'profile_count':result.total_items,'runtime_store_placement':True,'runtime_min_store_count':result.runtime_min_store_count,'runtime_store_item_counts':list(partition.store_item_counts),'item_cell_lengths':[x.cells for x in result.items],'loader_segment_count':len(result.loaders),'loaders':list(result.loaders),'loader_items':list(partition.loader_items),'profiles':[p['slug'] for p in D['profiles']],'loader_item_atomicity':'profile_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':result.coordination_programs[1],'loader_router_program':result.coordination_programs[2]}

def source_extensions(D,result):
 return {'format':'INPUT_PROFILE_CATALOG_V4','catalog_schema_id':SCHEMA,'catalog_schema_version':SCHEMA_VERSION,'catalog_instance_id':INSTANCE,'cell_block_width':CELL_BLOCK_WIDTH}

FIXED_OUTPUTS=COORDINATION_PROGRAM_FILES+(VIEW_FILE,MANIFEST_FILE,SOURCE_FILE)

def family():
 return CatalogFamily(root=R,source_file=SOURCE_FILE,manifest_file=MANIFEST_FILE,schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,collection_key='profiles',digest_prefix='IP4',cleanup_globs=('ic10/input-profile-catalog/input_profile_catalog_loader_*.ic10','ic10/input-profile-catalog/input_profile_view_v*.ic10'),rendered_output_files=(VIEW_FILE,),build_partitions=build_partitions,loader_filename=loader_filename,render_outputs=render_outputs,manifest_extensions=manifest_extensions,source_extensions=source_extensions,summary_label='Input Profile',summary_item_name='profiles')

def declared_outputs():return declared_output_inventory(family())

def main():run_catalog_generation(family())

if __name__=='__main__':main()
