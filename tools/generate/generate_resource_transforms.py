#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json
from framework.catalog_schema import *
SOURCE_FILE='data/resource_transforms.json';MANIFEST_FILE='data/resource_transform_catalog_manifest.json';VIEW_FILE='ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10';RESOLVER_FILE='ic10/dependency-planning/item_producer_resolver_v1_0.ic10'
FIXED_OUTPUTS=COORDINATION_PROGRAM_FILES+(VIEW_FILE,RESOLVER_FILE,MANIFEST_FILE,SOURCE_FILE)
R=_PROJECT_ROOT;OUT=(R/VIEW_FILE).parent;DEP=(R/RESOLVER_FILE).parent
SCHEMA='CatalogSchema.ResourceTransform';SCHEMA_VERSION=4;INSTANCE='Catalog.ResourceTransforms.Schema4';VIEW_MAGIC=31415952;VIEW_ABI=4

def main():
 OUT.mkdir(parents=True,exist_ok=True);DEP.mkdir(parents=True,exist_ok=True);COORD_PROGRAMS=ensure_coordination_programs(R);D=json.loads((R/SOURCE_FILE).read_text());T=D['transforms']
 seen=set();items=[];input_total=output_total=0
 for t in T:
  if t['name'] in seen:raise SystemExit('duplicate '+t['name'])
  seen.add(t['name']);ni=len(t['inputs']);no=len(t['outputs']);input_total+=ni;output_total+=no
  if not 1<=ni<=6 or not 1<=no<=8:raise SystemExit(t['name']+': descriptor count outside View ABI4')
  c=t['conditions'];flags=4|(1 if c['min_pressure_kpa'] or c['max_pressure_kpa'] else 0)|(2 if c['min_temperature_k'] or c['max_temperature_k'] else 0)
  vals=[f'HASH("{t["name"]}")',t['required_capability_mask'],ni,no,c['min_pressure_kpa'],c['max_pressure_kpa'],c['min_temperature_k'],c['max_temperature_k'],flags,0,0,0]
  for d in t['inputs']:vals += [d['resource_class'],d['resource_type'],d['unit'],d['quantity']]
  for d in t['outputs']:vals += [d['resource_class'],d['resource_type'],d['unit'],d['quantity']]
  vals += [0]*(align_block(len(vals))-len(vals));items.append(CatalogItem(tuple(vals),t.get('display_name',t['name'])))
 cat_obj={'schema':SCHEMA,'schema_version':SCHEMA_VERSION,'transforms':T};digest,token=stable_hash_token('RT5',cat_obj)
 for pat in ('resource_transform_catalog_loader_*.ic10','resource_transform_profile_view_v*.ic10'):
  for f in OUT.glob(pat):f.unlink()
 (R/RESOLVER_FILE).unlink(missing_ok=True)
 parts=split_catalog_items(label='GENERATED Resource Transform loader',schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,partition_key_expr='0',items=items)
 loaders=[];meta=[]
 for i,(subset,text) in enumerate(parts):
  name=f'resource_transform_catalog_loader_{i:02d}_v6_0.ic10';(OUT/name).write_text(text);loaders.append(f'ic10/transform-catalog/{name}');meta.append({'item_count':len(subset),'line_count':len(text.splitlines())})
 view=f'''# Resource Transform View v8: Store ABI5 items; ABI4 resolved-request fencing.
poke 0 {VIEW_MAGIC}
poke 1 {VIEW_ABI}
poke 2 0
poke 68 0
poke 69 0
Loop:
yield
get r10 db 70
bdns d0 Bad
l r2 d0 ReferenceId
get r12 d0 11
blez r12 Bad
getd r0 r12 0
bne r0 {COORD_MAGIC} Bad
getd r15 r12 22
mod r0 r15 2
bnez r0 Bad
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
getd r0 r2 r8
beq r0 r10 Found
add r5 r5 1
j Scan
Found:
get r0 db 68
bne r0 r10 Rewrite
get r0 db 69
bne r0 1 Rewrite
get r0 db 74
beq r0 r14 Loop
Rewrite:
poke 69 0
move r9 8
Clear:
poke r9 0
add r9 r9 1
blt r9 68 Clear
add r0 r8 1
getd r0 r2 r0
poke 71 r0
add r0 r8 2
getd r4 r2 r0
bgt r4 6 Bad
poke 72 r4
add r0 r8 3
getd r5 r2 r0
bgt r5 8 Bad
poke 73 r5
add r0 r8 8
getd r0 r2 r0
poke 75 r0
add r6 r8 4
move r1 64
move r11 1
jal CopyPool
add r6 r8 12
move r1 8
move r11 r4
jal CopyPool
move r1 32
move r11 r5
jal CopyPool
getd r0 r2 17
bne r0 r14 Loop
getd r0 r12 22
bne r0 r15 Loop
poke 69 1
poke 74 r14
poke 68 r10
j Loop
StoreDone:
getd r1 r2 24
blez r1 Missing
move r2 r1
j Store
Bad:
poke 69 0
poke 71 -2
poke 68 r10
j Loop
Missing:
getd r0 r12 22
bne r0 r15 Loop
poke 69 0
poke 71 -3
poke 68 r10
j Loop
CopyPool:
mul r9 r11 4
add r9 r9 r1
CPCell:
bge r1 r9 CPDone
getd r13 r2 r6
poke r1 r13
add r6 r6 1
add r1 r1 1
j CPCell
CPDone:
j ra'''
 (R/VIEW_FILE).write_text(view)
 # Item 8 reverse producer index. Unknown ITEM outputs deliberately fall back to PRINT;
 # known transform outputs must be unique so dependency planning never chooses ambiguously.
 producer=[]; producer_seen={}
 for t in T:
  for o in t['outputs']:
   if o['resource_class'] != 2: continue
   rt=o['resource_type']
   if rt in producer_seen: raise SystemExit(f'duplicate ITEM producer for {rt}: {producer_seen[rt]} and {t["name"]}')
   producer_seen[rt]=t['name']; producer.append((rt,t['name']))
 pl=['# Generated ITEM producer resolver.','Boot:','get r0 db 0','beq r0 31416003 Table','clr db','poke 0 31416003','poke 1 1','Table:','move sp 32']
 for rt,name in producer: pl += [f'push {rt}',f'push HASH("{name}")']
 pl += ['Loop:','yield','get r15 db 3','get r0 db 4','beq r15 r0 Loop','get r2 db 2','beqz r2 Bad','move r6 0','move r7 32','Find:',f'bge r6 {len(producer)} Print','get r0 db r7','beq r0 r2 Found','add r7 r7 2','add r6 r6 1','j Find','Found:','add r7 r7 1','get r0 db r7','poke 6 1','poke 7 r0','j Good','Print:','poke 6 2','poke 7 r2','Good:','poke 5 1','poke 4 r15','j Loop','Bad:','poke 5 -1','poke 6 0','poke 7 0','poke 4 r15','j Loop']
 producer_text='\n'.join(pl)+'\n'
 if len(producer_text.splitlines())>120: raise SystemExit('201 producer resolver exceeds 120-line IC10 ceiling')
 (R/RESOLVER_FILE).write_text(producer_text)
 counts=pack_store_counts([x.cells for x in items]);manifest=common_manifest(schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,store_count=len(counts),total_items=len(T),catalog_digest=digest)
 manifest.update({'format':'RESOURCE_TRANSFORM_CATALOG_V6','catalog_token':token,'transform_count':len(T),'input_descriptor_count':input_total,'output_descriptor_count':output_total,'runtime_store_placement':True,'runtime_min_store_count':len(counts),'runtime_store_item_counts':counts,'item_cell_lengths':[x.cells for x in items],'loader_segment_count':len(parts),'loaders':loaders,'loader_items':meta,'view_magic':VIEW_MAGIC,'view_abi':VIEW_ABI,'processor_capability_model':D.get('processor_capability_model',{}),'loader_item_atomicity':'transform_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':COORD_PROGRAMS[1],'loader_router_program':COORD_PROGRAMS[2]})
 (R/MANIFEST_FILE).write_text(json.dumps(manifest,indent=2)+'\n');D.update({'schema':SCHEMA_VERSION,'catalog_schema_id':SCHEMA,'catalog_schema_version':SCHEMA_VERSION,'catalog_instance_id':INSTANCE,'cell_block_width':CELL_BLOCK_WIDTH});(R/SOURCE_FILE).write_text(json.dumps(D,indent=2)+'\n')
 print(f'Resource Transform generation: PASS - {len(T)} transforms / runtime min {len(counts)} stores / {len(parts)} relocatable loaders')

if __name__=='__main__':main()
