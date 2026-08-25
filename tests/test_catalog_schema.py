#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from framework.ic10_harness import IC10,Device
import json,sys
import framework.catalog_schema as C
R=_PROJECT_ROOT;fails=[]
# Common ABI/runtime-placement contract.
if (C.STORE_MAGIC,C.STORE_ABI,C.LOADER_MAGIC,C.LOADER_ABI,C.COORD_MAGIC,C.COORD_ABI)!=(31415968,5,31415969,4,31415970,3):fails.append('Catalog common ABI constants mismatch')
if (C.STORE_HEADER_CELLS,C.STORE_DIR_WIDTH,C.STORE_TOTAL_CELLS)!=(32,2,512):fails.append('Store ABI5 item-directory geometry mismatch')
for f in ('resource_profile_catalog_manifest.json','input_profile_catalog_manifest.json','resource_transform_catalog_manifest.json'):
 m=json.loads((R/'data'/f).read_text())
 if not m.get('runtime_store_placement') or m.get('store_model')!='generic_dynamic_item_heap' or m.get('catalog_store_abi')!=5 or m.get('catalog_loader_abi')!=4:fails.append(f+': not on runtime-placement ABI')
# A Loader item is relocatable: producer leaves runtime assignment fields zero.
for p in list(R.glob('*_loader_*_v4_0.ic10'))+list(R.glob('*_loader_*_v6_0.ic10')):
 txt=p.read_text()
 if '31415969' not in txt: continue
 if 'poke 13 0' in txt or 'poke 14 0' in txt: pass
 # More importantly no producer writes a positive physical target into S13/S14.
 for line in txt.splitlines():
  code=line.split('#',1)[0].strip().split()
  if len(code)>=3 and code[0]=='poke' and code[1] in ('13','14'):
   try:
    if float(code[2])>0:fails.append(p.name+': loader preassigns physical Store')
   except ValueError:pass
# Item-level compaction test: two compatible Stores, source DRAINING with two items, destination ACTIVE with one.
SCHEMA='HASH:CatalogSchema.Test';INSTANCE='HASH:Catalog.Test';PART='HASH:Partition.Test';core_ref=500;src_ref=501;dst_ref=502;dir_ref=503
core=Device(core_ref,stack={0:C.COORD_MAGIC,1:C.COORD_ABI,6:0,7:2,25:0,40:0,41:0,42:0},props={'ReferenceId':core_ref})
def mkstore(ref,node,state,items):
 st={0:C.STORE_MAGIC,1:C.STORE_ABI,2:SCHEMA,3:1,4:INSTANCE,5:1,6:0,7:0,8:node-1,9:len(items),10:32,11:core_ref,12:1,15:1,16:state,17:2,18:node,19:32+2*len(items),20:512-4*len(items),22:32+6*len(items),23:PART,26:1,27:0,29:(512-4*len(items))-(32+2*len(items)),31:1}
 for i,item in enumerate(items):
  base=508-i*4;st[32+i*2]=base;st[33+i*2]=4
  for j,v in enumerate(item):st[base+j]=v
 return Device(ref,stack=st,props={'ReferenceId':ref})
src=mkstore(src_ref,1,3,[(101,1,0,0),(202,2,0,0)]);dst=mkstore(dst_ref,2,2,[(303,3,0,0)])
src.stack[7]=dst_ref;dst.stack[6]=src_ref
# Registry records only need RefIds for planner traversal.
dir_stack={0:31415982,1:3,2:'HASH:DirectorySchema.CatalogStoreNode',19:1,20:6,21:64,23:0,64:src_ref,65:3,66:src.stack[22],70:dst_ref,71:2,72:dst.stack[22]};directory=Device(dir_ref,dir_stack,{'ReferenceId':dir_ref})
planner=IC10((R/'ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10').read_text(),{'d0':core,'d1':directory,'src':src,'dst':dst},self_ref=504)
worker=IC10((R/'ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10').read_text(),{'d0':core,'src':src,'dst':dst},self_ref=505)
def move_one():
 for _ in range(6):
  planner.run(1,max_steps=50000)
  if core.stack.get(40,0):break
 if core.stack.get(40)!=src_ref or core.stack.get(41)!=dst_ref:return False
 if dst.stack.get(27,0)!=6:return False
 before_src=int(src.stack.get(9,0));before_dst=int(dst.stack.get(9,0))
 for _ in range(4):
  worker.run(1,max_steps=50000)
  if not core.stack.get(40,0):break
 return int(src.stack.get(9,0))==before_src-1 and int(dst.stack.get(9,0))==before_dst+1 and dst.stack.get(27,0)==0
if not move_one() or dst.stack.get(504)!=202:fails.append('first whole-item migration/commit failed')
if not move_one() or int(src.stack.get(9,0))!=0 or int(dst.stack.get(9,0))!=3:fails.append('second migration did not compact source to empty')
# Source removal is now safe; retirement unlinks only the empty DRAINING Store.
ret=IC10((R/'ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10').read_text(),{'d0':core,'d1':directory,'src':src,'dst':dst},self_ref=506)
for _ in range(3):ret.run(1,max_steps=50000)
if src.stack.get(16)!=5 or dst.stack.get(6,0)!=0:fails.append('empty compacted Store retirement/unlink failed')
# Destination contains all three complete 4-cell items and source did not leave live payload ownership.
keys=[]
for i in range(int(dst.stack.get(9,0))):keys.append(dst.stack.get(int(dst.stack.get(32+i*2))))
if sorted(keys)!=[101,202,303]:fails.append('compaction lost/duplicated an item')
if core.stack.get(7,0)%2:fails.append('catalog topology seqlock left odd after migration')
if fails:
 print('Catalog runtime placement / item migration: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Catalog runtime placement / item migration: PASS')
print(' - Store ABI5 uses a runtime item directory + downward payload heap; Loader ABI4 carries relocatable whole items')
print(' - migration reserves destination capacity, publishes whole items, pops source heap safely, then permits empty Store retirement')
print(' - compaction test moves two complete items from a DRAINING Store into compatible free capacity without data loss')
