#!/usr/bin/env python3
from pathlib import Path
import json
from framework.catalog_schema import *
R=Path(__file__).resolve().parent;OUT=R/'ic10'/'input-profile-catalog';OUT.mkdir(parents=True,exist_ok=True);COORD_PROGRAMS=ensure_coordination_programs(R);D=json.loads((R/'input_profiles.json').read_text());P=D['profiles']
SCHEMA='CatalogSchema.InputProfile';SCHEMA_VERSION=3;INSTANCE='Catalog.InputProfiles.Schema3';PROFILE_MAGIC=31415929;PROFILE_ABI=1
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
cat_obj={'schema':SCHEMA,'schema_version':SCHEMA_VERSION,'profiles':P};digest,token=stable_hash_token('IP4',cat_obj)
for pat in ('input_profile_catalog_loader_*.ic10','input_profile_view_v*.ic10'):
 for f in OUT.glob(pat):f.unlink()
parts=split_catalog_items(label='GENERATED Input Profile loader',schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,partition_key_expr='0',items=items)
loaders=[];meta=[]
for i,(subset,text) in enumerate(parts):
 name=f'input_profile_catalog_loader_{i:02d}_v4_0.ic10';(OUT/name).write_text(text);loaders.append(f'ic10/input-profile-catalog/{name}');meta.append({'item_count':len(subset),'line_count':len(text.splitlines())})
view=f'''# Input Profile View v5: dynamic Store ABI5 self-contained profile items.
poke 0 {PROFILE_MAGIC}
poke 1 {PROFILE_ABI}
poke 5 0
Loop:
yield
get r10 db 2
get r11 db 3
bdns d0 Bad
l r2 d0 ReferenceId
get r12 d0 11
blez r12 Bad
getd r0 r12 0
bne r0 {COORD_MAGIC} Bad
getd r15 r12 7
mod r0 r15 2
bnez r0 Bad
get r13 d0 4
First:
getd r1 r2 6
blez r1 Store
move r2 r1
j First
Store:
getd r0 r2 0
bne r0 {STORE_MAGIC} Bad
getd r0 r2 1
bne r0 {STORE_ABI} Bad
getd r0 r2 2
bne r0 HASH("{SCHEMA}") Bad
getd r0 r2 3
bne r0 {SCHEMA_VERSION} Bad
getd r0 r2 4
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
poke 5 0
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
getd r0 r12 7
bne r0 r15 Loop
poke 4 r4
poke 5 r14
j Loop
Next:
add r5 r5 1
j Find
StoreDone:
getd r1 r2 7
blez r1 Missing
move r2 r1
j Store
Bad:
poke 5 0
j Loop
Missing:
getd r0 r12 7
bne r0 r15 Loop
poke 5 0
j Loop
'''
(OUT/'input_profile_view_v5_0.ic10').write_text(view)
counts=pack_store_counts([x.cells for x in items]);manifest=common_manifest(schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,store_count=len(counts),total_items=len(P),catalog_digest=digest)
manifest.update({'format':'INPUT_PROFILE_CATALOG_V4','catalog_token':token,'profile_count':len(P),'runtime_store_placement':True,'runtime_min_store_count':len(counts),'runtime_store_item_counts':counts,'item_cell_lengths':[x.cells for x in items],'loader_segment_count':len(parts),'loaders':loaders,'loader_items':meta,'profiles':[p['slug'] for p in P],'loader_item_atomicity':'profile_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':COORD_PROGRAMS[1],'loader_router_program':COORD_PROGRAMS[2]})
(R/'input_profile_catalog_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');D.update({'format':'INPUT_PROFILE_CATALOG_V4','catalog_schema_id':SCHEMA,'catalog_schema_version':SCHEMA_VERSION,'catalog_instance_id':INSTANCE,'cell_block_width':CELL_BLOCK_WIDTH});(R/'input_profiles.json').write_text(json.dumps(D,indent=2)+'\n')
print(f'Input Profile generation: PASS - {len(P)} profiles / runtime min {len(counts)} stores / {len(parts)} relocatable loaders')
