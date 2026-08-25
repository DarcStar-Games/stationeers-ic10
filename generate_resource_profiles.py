#!/usr/bin/env python3
from pathlib import Path
from collections import defaultdict
import json
from framework.catalog_schema import *
R=Path(__file__).resolve().parent;OUT=R/'ic10'/'resource-profile-catalog';DEP=R/'ic10'/'dependency-planning';OUT.mkdir(parents=True,exist_ok=True);DEP.mkdir(parents=True,exist_ok=True);COORD_PROGRAMS=ensure_coordination_programs(R)
D=json.loads((R/'data/resource_profiles.json').read_text());P=D['profiles']
SCHEMA='CatalogSchema.ResourceProfile';SCHEMA_VERSION=2;INSTANCE='Catalog.ResourceProfiles.Schema2'
VIEW_MAGIC=31415963;VIEW_ABI=1;SEMANTIC_WIDTH=14;ITEM_CELLS=16
CLASS_NAMES={1:'fluid',2:'item',4:'power',5:'energy'}
seen=set()
for p in P:
 k=(p['resource_class'],str(p['resource_type_kind']),str(p['resource_type']))
 if k in seen:raise SystemExit(f'duplicate resource profile identity: {k}')
 seen.add(k)
 if len(p['params'])!=9:raise SystemExit(p['slug']+': expected 9 params')
cat_obj={'schema':SCHEMA,'schema_version':SCHEMA_VERSION,'profiles':P};digest,token=stable_hash_token('RP6',cat_obj)
for pat in ('resource_profile_loader_*_v*.ic10','resource_profile_view_v*.ic10'):
 for f in OUT.glob(pat):f.unlink()
(DEP/'manufacturing_reagent_resolver_v1_0.ic10').unlink(missing_ok=True)
groups=defaultdict(list)
for p in P:groups[p['resource_class']].append(p)
all_loaders=[];parts_meta=[]
for cls in sorted(groups):
 items=[]
 for p in groups[cls]:
  typ=f'HASH("{p["resource_type"]}")' if p['resource_type_kind']=='hash_name' else p['resource_type']
  vals=[typ,p['resource_class'],p['unit'],p['profile_kind'],p['profile_schema'],*p['params'],0,0]
  vals=vals[:ITEM_CELLS]+[0]*max(0,ITEM_CELLS-len(vals))
  human=p.get('description') or p.get('resource_type_name') or p['slug'];items.append(CatalogItem(tuple(vals),human))
 cname=CLASS_NAMES[cls]
 parts=split_catalog_items(label=f'GENERATED Resource Profile {cname.upper()} loader',schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,partition_key_expr=str(cls),items=items)
 lfiles=[]
 for li,(subset,text) in enumerate(parts):
  name=f'resource_profile_loader_{cname}_{li:02d}_v4_0.ic10';(OUT/name).write_text(text);rel=f'ic10/resource-profile-catalog/{name}';lfiles.append(rel);all_loaders.append(rel)
 parts_meta.append({'partition_key':cls,'partition':'ResourceClass.'+cname.upper(),'item_count':len(items),'item_cells':ITEM_CELLS,'runtime_min_store_count':len(pack_store_counts([ITEM_CELLS]*len(items))),'loader_count':len(parts),'loaders':lfiles})
view=f'''# Resource Profile View v4: dynamic Store ABI5 item directory; d0=any Store.
poke 0 {VIEW_MAGIC}
poke 1 {VIEW_ABI}
poke 4 0
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
poke 5 0
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
getd r0 r12 7
bne r0 r15 Loop
poke 22 r13
getd r0 r12 6
poke 23 r0
poke 4 1
poke 5 r14
j Loop
Next:
add r5 r5 1
j Scan
StoreDone:
getd r1 r2 7
blez r1 Missing
move r2 r1
j Store
Bad:
poke 5 0
poke 4 -2
j Loop
Missing:
getd r0 r12 7
bne r0 r15 Loop
poke 5 0
poke 4 -3
j Loop
'''
(OUT/'resource_profile_view_v4_0.ic10').write_text(view)
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
(DEP/'manufacturing_reagent_resolver_v1_0.ic10').write_text(reagent_text)
minstores=sum(x['runtime_min_store_count'] for x in parts_meta)
manifest=common_manifest(schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,store_count=minstores,total_items=len(P),catalog_digest=digest)
manifest.update({'format':'RESOURCE_PROFILE_CATALOG_V6','catalog_token':token,'profile_count':len(P),'semantic_record_width':SEMANTIC_WIDTH,'physical_item_width':ITEM_CELLS,'storage_partition':'resource_class','runtime_store_placement':True,'runtime_min_store_count':minstores,'loader_segment_count':len(all_loaders),'loaders':all_loaders,'partitions':parts_meta,'loader_item_atomicity':'logical_item_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':COORD_PROGRAMS[1],'loader_router_program':COORD_PROGRAMS[2]})
(R/'data/resource_profile_catalog_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
D.update({'format':'RESOURCE_PROFILE_CATALOG_V6','catalog_schema_id':SCHEMA,'catalog_schema_version':SCHEMA_VERSION,'catalog_instance_id':INSTANCE,'cell_block_width':CELL_BLOCK_WIDTH,'semantic_record_width':SEMANTIC_WIDTH,'physical_item_width':ITEM_CELLS,'storage_partition':'resource_class'})
(R/'data/resource_profiles.json').write_text(json.dumps(D,indent=2)+'\n')
print(f'Resource Profile generation: PASS - {len(P)} profiles / runtime min {minstores} stores / {len(all_loaders)} relocatable loaders')
