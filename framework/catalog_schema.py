"""Shared dynamic catalog storage/control-plane helpers.

Architecture v5:
- Loader ABI4 producers are one-shot, self-clearing, sparse, relocatable whole-item sources.
- Generic Store ABI5 owns a 2-cell item directory growing upward from S32 and a
  block-aligned payload heap growing downward from S511.
- Loader source layout is independent of Store layout. Router assigns each next whole item
  to any compatible Store with sufficient capacity; no generator-defined Store ordinal exists.
- Coordinator ABI3 owns membership/topology claims. Migration moves whole items, newest first,
  so draining reclaims Store capacity without holes and can retire/compact Stores safely.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json
from pathlib import Path

CELL_BLOCK_WIDTH=4
STORE_MAGIC=31415968; STORE_ABI=5
LOADER_MAGIC=31415969; LOADER_ABI=4
COORD_MAGIC=31415970; COORD_ABI=3
STORE_HEADER_CELLS=32; STORE_DIR_WIDTH=2; STORE_TOTAL_CELLS=512
LOADER_HEADER_CELLS=16; LOADER_DIR_WIDTH=2
COORDINATION_PROGRAM_FILES=('ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10','ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10','ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10','ic10/directory-core/generic_registry_directory_host_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10','ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10','ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10','ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10')
GENERIC_STORE_FILE=COORDINATION_PROGRAM_FILES[0]
MAX_LOGICAL_STORES=64
STORE_UNCLAIMED=1;STORE_ACTIVE=2;STORE_DRAINING=3;STORE_FAULT=4;STORE_RETIRED=5;STORE_MIGRATING=6;STORE_MISSING=7;STORE_DUPLICATE=8

@dataclass(frozen=True)
class CatalogItem:
    payload: tuple
    human_name: str=''
    @property
    def cells(self): return len(self.payload)

def align_block(cell):return ((cell+CELL_BLOCK_WIDTH-1)//CELL_BLOCK_WIDTH)*CELL_BLOCK_WIDTH
def mask(valid_cells):
    if valid_cells<0 or valid_cells>32:raise ValueError('mask word supports 0..32 cells')
    return (1<<valid_cells)-1 if valid_cells else 0
def masks(valid_cells):
    if valid_cells<0 or valid_cells>MAX_MASK_BITS:raise ValueError('region unit too wide')
    return mask(min(valid_cells,32)),mask(max(0,valid_cells-32))
def stable_hash_token(prefix,obj):
    raw=json.dumps(obj,sort_keys=True,separators=(',',':'));d=hashlib.sha256(raw.encode()).hexdigest();return d,f'{prefix}:{d[:16]}'
def emit(v):return v if isinstance(v,str) else repr(v)
def is_zero(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and v==0

def common_manifest(*,schema_name,schema_version,instance_name,regions=(),store_count=0,total_items,catalog_digest,**extra):
    out={'catalog_store_abi':STORE_ABI,'catalog_store_magic':STORE_MAGIC,'catalog_loader_abi':LOADER_ABI,'catalog_loader_magic':LOADER_MAGIC,
      'catalog_coordinator_abi':COORD_ABI,'catalog_coordinator_magic':COORD_MAGIC,'store_model':'generic_dynamic_item_heap',
      'loader_model':'one_shot_sparse_relocatable_whole_items','control_plane':'catalog_coordinator_v3_runtime_placement_item_migration',
      'cell_block_width':CELL_BLOCK_WIDTH,'store_header_cells':STORE_HEADER_CELLS,'store_item_directory_width':STORE_DIR_WIDTH,
      'catalog_schema_id':schema_name,'catalog_schema_version':schema_version,'catalog_instance_id':instance_name,
      'store_count':store_count,'total_item_count':total_items,'catalog_sha256':catalog_digest,'regions':[]}
    out.update(extra);return out

def item_store_capacity(item_cells):
    """Maximum equal-size items in an empty Store, including 2-cell directory entries."""
    return (STORE_TOTAL_CELLS-STORE_HEADER_CELLS)//(align_block(item_cells)+STORE_DIR_WIDTH)

def pack_store_counts(item_lengths):
    """Deterministic append-to-tail capacity planning used only for commissioning estimates/tests."""
    stores=[];free=STORE_TOTAL_CELLS-STORE_HEADER_CELLS;count=0
    for n in item_lengths:
        n=align_block(n);need=n+STORE_DIR_WIDTH
        if need>STORE_TOTAL_CELLS-STORE_HEADER_CELLS:raise ValueError(f'item {n} cannot fit one Store')
        if need>free:
            stores.append(count);free=STORE_TOTAL_CELLS-STORE_HEADER_CELLS;count=0
        free-=need;count+=1
    if count or not stores:stores.append(count)
    return stores

def make_item_loader(*,label,schema_name,schema_version,instance_name,partition_key_expr,loader_id_expr,items):
    """Loader ABI4. Items are stored independently in the loader heap; zeros are implicit after clr db."""
    if not items:raise ValueError('empty loader')
    for x in items:
        if x.cells<=0 or x.cells%CELL_BLOCK_WIDTH:raise ValueError('loader item must be non-empty and block aligned')
    n=len(items);dir_end=LOADER_HEADER_CELLS+n*LOADER_DIR_WIDTH;floor=STORE_TOTAL_CELLS
    placements=[]
    for x in items:
        floor-=x.cells
        if floor<dir_end:raise ValueError('loader stack geometry overflow')
        placements.append((floor,x))
    total=sum(x.cells for x in items)
    sig_obj={'schema':schema_name,'version':schema_version,'instance':instance_name,'partition':str(partition_key_expr),'items':[[str(v) for v in x.payload] for x in items]}
    _,tok=stable_hash_token('LD4',sig_obj)
    L=[f'# {label}; relocatable sparse Loader ABI4; whole items.','clr db',f'poke 0 {LOADER_MAGIC}',f'poke 1 {LOADER_ABI}',
       f'poke 2 HASH("{schema_name}")',f'poke 3 {schema_version}',f'poke 4 HASH("{instance_name}")']
    if str(partition_key_expr)!='0':L.append(f'poke 5 {partition_key_expr}')
    L += [f'poke 6 {loader_id_expr}','poke 7 1',f'poke 8 {n}',f'poke 9 {LOADER_HEADER_CELLS}',f'poke 10 {total}',f'poke 11 HASH("{tok}")']
    for i,(start,x) in enumerate(placements):
        L += [f'poke {LOADER_HEADER_CELLS+i*2} {start}',f'poke {LOADER_HEADER_CELLS+i*2+1} {x.cells}']
        for j,v in enumerate(x.payload):
            if is_zero(v):continue
            line=f'poke {start+j} {emit(v)}'
            if j==0 and x.human_name:line+=f' # {x.human_name}'
            L.append(line)
    L.append('poke 12 1 # immutable candidate publication LAST')
    return '\n'.join(L)+'\n'

def split_catalog_items(*,label,schema_name,schema_version,instance_name,partition_key_expr,items,max_lines=120):
    """Split source only between complete logical items. Loader ordinals are not Store ordinals."""
    out=[];pos=0;li=0
    while pos<len(items):
        best=None
        for end in range(pos+1,len(items)+1):
            subset=items[pos:end]
            _,tok=stable_hash_token('LoaderId',{'schema':schema_name,'partition':str(partition_key_expr),'ordinal':li,'items':[[str(v) for v in x.payload] for x in subset]})
            text=make_item_loader(label=label,schema_name=schema_name,schema_version=schema_version,instance_name=instance_name,
                partition_key_expr=partition_key_expr,loader_id_expr=f'HASH("{tok}")',items=subset)
            if len(text.splitlines())<=max_lines:best=(end,subset,text)
            else:break
        if best is None:raise ValueError(f'loader {li} cannot fit one whole item')
        end,subset,text=best;out.append((subset,text));pos=end;li+=1
    return out

# ---------- Generic Store + Coordinator services ----------
def make_generic_store_program():
    L=[
'# Generic Catalog Store v3.0: Store ABI5 dynamic item heap; set S18 NodeId 1..64.','Boot:','yield','get r13 db 18','blez r13 NeedId','bgt r13 64 NeedId','get r0 db 0',f'beq r0 {STORE_MAGIC} Existing','clr db',f'poke 0 {STORE_MAGIC}',f'poke 1 {STORE_ABI}','poke 10 32','poke 16 1','poke 18 r13','poke 19 32','poke 20 512','poke 22 32','poke 29 480','j Service','Existing:','get r0 db 1',f'bne r0 {STORE_ABI} Fault',
'Service:','yield','get r0 db 16','bne r0 2 Idle','l r12 db ReferenceId','get r1 db:0 r7','blt r1 0 Reset','add r7 r7 1','getd r0 r1 0',f'bne r0 {LOADER_MAGIC} Service','getd r0 r1 1',f'bne r0 {LOADER_ABI} Service','getd r0 r1 12','bne r0 1 Service','getd r0 r1 13','bne r0 r12 Service','getd r0 r1 2','get r6 db 2','bne r0 r6 Service','getd r0 r1 3','get r6 db 3','bne r0 r6 Service','getd r0 r1 4','get r6 db 4','bne r0 r6 Service','getd r0 r1 5','get r6 db 23','bne r0 r6 Service','getd r3 r1 15','getd r4 r1 8','bge r3 r4 Service','mul r5 r3 2','add r5 r5 16','getd r8 r1 r5','add r5 r5 1','getd r9 r1 r5','get r0 db 29','add r6 r9 2','bgt r6 r0 Bad','get r0 db 17','add r0 r0 1','poke 17 r0','get r10 db 20','sub r10 r10 r9','get r11 db 19','move r5 0',
'Copy:','bge r5 r9 Commit','add r6 r8 r5','getd r6 r1 r6','add r0 r10 r5','poke r0 r6','add r5 r5 1','j Copy','Commit:','poke r11 r10','add r11 r11 1','poke r11 r9','add r11 r11 1','poke 19 r11','poke 20 r10','get r0 db 9','add r0 r0 1','poke 9 r0','get r6 db 22','add r6 r6 r9','add r6 r6 2','poke 22 r6','sub r6 r10 r11','poke 29 r6','get r0 db 15','add r0 r0 1','poke 15 r0','get r0 db 17','add r0 r0 1','poke 17 r0','add r3 r3 1','putd r1 15 r3','poke 27 0','putd r1 13 0','j Service','Bad:','poke 16 4','poke 28 -2','j Idle','Reset:','move r7 0','j Service','NeedId:','s db Setting -1','j Boot','Fault:','poke 16 4','Idle:','yield','get r0 db 16','beq r0 2 Service','j Idle']
    return '\n'.join(L)+'\n' 

def make_coordinator_directory_host_program():
    return '''Boot: # Generic Registry Directory Host ABI3: CatalogStoreNode persistent registry.
yield
get r0 db 0
bne r0 31415982 Init
get r0 db 1
beq r0 3 Loop
Init:
clr db
poke 0 31415982
poke 1 3
Loop:
yield
bdns d0 Loop
get r0 d0 0
bne r0 31415983 Loop
get r0 d0 1
bne r0 3 Loop
get r0 d0 15
bne r0 2 Loop
get r11 db 24
add r11 r11 1
poke 24 r11
Freeze:
put d0 16 r11
yield
get r0 d0 17
bne r0 r11 Freeze
get r0 d0 8
bne r0 HASH("DirectorySchema.CatalogStoreNode") SourceBad
get r0 d0 9
bne r0 1 SourceBad
get r0 d0 10
bne r0 6 SourceBad
get r0 d0 11
bne r0 64 SourceBad
get r0 d0 14
bgtz r0 Overflow
get r15 d0 13
mod r0 r15 2
bnez r0 SourceBad
get r14 d0 7
get r0 db 3
beq r14 r0 Release
get r13 d0 12
get r10 db 23
mod r0 r10 2
bnez r0 Mutating
add r10 r10 1
poke 23 r10
Mutating:
poke 16 0
move r7 0
Candidates:
bge r7 r13 Sweep
mul r3 r7 6
add r3 r3 18
get r2 d0 r3
blt r2 1 Bad
bgt r2 64 Bad
mul r4 r2 6
add r4 r4 58
add r3 r3 1
move r6 0
Copy:
bge r6 5 Seen
add r0 r3 r6
get r0 d0 r0
add r1 r4 r6
poke r1 r0
add r6 r6 1
j Copy
Seen:
add r5 r4 5
poke r5 r14
add r7 r7 1
j Candidates
Sweep:
move r7 1
SweepNode:
bgt r7 64 Publish
mul r4 r7 6
add r4 r4 58
get r1 db r4
blez r1 SweepNext
add r5 r4 5
get r0 db r5
beq r0 r14 SweepNext
add r5 r4 1
get r0 db r5
beq r0 5 SweepNext
poke r5 7
SweepNext:
add r7 r7 1
j SweepNode
Overflow:
poke 16 -3
j Release
SourceBad:
poke 16 -4
j Release
Bad:
poke 16 -1
j Close
Publish:
get r0 d0 8
poke 2 r0
poke 3 r14
get r0 db 4
add r0 r0 1
poke 4 r0
get r0 d0 9
poke 19 r0
poke 20 6
poke 21 64
Close:
add r10 r10 1
poke 23 r10
Release:
put d0 16 0
j Loop
'''
def make_coordinator_core_program():
    return '''# Catalog Coordinator Core v3.0: runtime Store claim/topology authority; d0 Directory.
Boot:
yield
get r13 db 2
get r14 db 3
get r0 db 0
beq r0 31415970 Loop
clr db
max r13 r13 1
max r14 r14 1
poke 0 31415970
poke 1 3
poke 2 r13
poke 3 r14
poke 5 1
poke 25 0
Loop:
yield
bdns d0 Loop
get r0 d0 0
bne r0 31415982 Loop
get r0 d0 1
bne r0 3 Loop
get r0 d0 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Loop
get r0 d0 19
bne r0 1 Loop
l r12 d0 ReferenceId
poke 23 r12
get r0 d0 6
poke 8 r0
get r0 d0 14
poke 9 r0
get r0 d0 11
poke 10 r0
get r0 d0 9
poke 11 r0
get r0 d0 7
poke 12 r0
get r0 d0 8
poke 13 r0
get r0 db 25
blez r0 Publish
jal Claim
Publish:
get r0 db 4
add r0 r0 1
poke 4 r0
j Loop
Claim:
getd r15 r12 23
mod r0 r15 2
bnez r0 ra
move r7 1
Find:
bgt r7 64 ClaimFail
mul r0 r7 6
add r0 r0 58
add r2 r0 1
getd r6 r12 r2
bne r6 1 Next
getd r1 r12 r0
blez r1 Next
getd r6 r1 16
bne r6 1 Next
getd r0 r1 29
get r2 db 32
blt r0 r2 Next
j Do
Next:
add r7 r7 1
j Find
Do:
getd r0 r12 23
bne r0 r15 ra
get r0 db 7
add r0 r0 1
poke 7 r0
get r2 db 27
putd r1 2 r2
get r2 db 28
putd r1 3 r2
get r2 db 29
putd r1 4 r2
get r2 db 2
putd r1 5 r2
get r2 db 30
putd r1 6 r2
blez r2 LinkDone
putd r2 7 r1
LinkDone:
get r2 db 31
putd r1 8 r2
l r2 db ReferenceId
putd r1 11 r2
get r2 db 3
putd r1 12 r2
get r2 db 26
putd r1 23 r2
get r2 db 20
add r2 r2 1
poke 20 r2
putd r1 26 r2
putd r1 31 r2
putd r1 16 2
get r0 db 6
add r0 r0 1
poke 6 r0
get r0 db 7
add r0 r0 1
poke 7 r0
poke 17 r7
poke 25 0
j ra
ClaimFail:
poke 19 -1
j ra
'''
def make_loader_router_program():
    L=[
'# Catalog Loader Router v3.0: per-item runtime capacity placement; d0 Coordinator ABI3.','Loop:','yield','bdns d0 Loop','l r15 d0 ReferenceId','getd r0 r15 0',f'bne r0 {COORD_MAGIC} Loop','getd r0 r15 1',f'bne r0 {COORD_ABI} Loop','poke 0 31415971','poke 1 3','poke 2 0','poke 3 0','poke 4 0','move r7 0','Scan:','get r1 db:0 r7','blt r1 0 Reset','add r7 r7 1','getd r0 r1 0',f'bne r0 {LOADER_MAGIC} Scan','getd r0 r1 1',f'bne r0 {LOADER_ABI} Scan','getd r0 r1 12','bne r0 1 Scan','getd r3 r1 15','getd r4 r1 8','bge r3 r4 Scan','getd r0 r1 13','bgtz r0 Scan','mul r0 r3 2','add r0 r0 17','getd r11 r1 r0','add r11 r11 2','get r0 db 2','add r0 r0 1','poke 2 r0','get r6 db 3','add r6 r6 1','poke 3 r6','get r6 db 4','add r6 r6 r11','poke 4 r6','getd r12 r1 5','getd r13 r1 4','getd r14 r1 2','getd sp r1 3','move r8 0','move r9 0','move r10 -1','move r6 0','move ra 0',
'Find:','get r2 db:0 r8','blt r2 0 FindDone','add r8 r8 1','getd r0 r2 0',f'bne r0 {STORE_MAGIC} Find','getd r0 r2 1',f'bne r0 {STORE_ABI} Find','getd r0 r2 16','bne r0 2 Find','getd r0 r2 11','bne r0 r15 Find','getd r0 r2 4','bne r0 r13 Find','getd r0 r2 8','ble r0 r10 Match','move r10 r0','move r9 r2','Match:','getd r0 r2 2','bne r0 r14 Find','getd r0 r2 3','bne r0 sp Find','getd r0 r2 23','bne r0 r12 Find','getd r0 r2 29','blt r0 r11 Find','getd r0 r2 27','blez r0 Free','move r6 1','j Find','Free:','move ra r2','j Find',
'FindDone:','bgtz ra Assign','bgtz r6 Scan','getd r0 r15 25','bgtz r0 Scan','putd r15 25 1','putd r15 26 r12','putd r15 27 r14','putd r15 28 sp','putd r15 29 r13','putd r15 30 r9','add r0 r10 1','putd r15 31 r0','putd r15 32 r11','j Scan','Assign:','get r0 d0 6','add r0 r0 1','put d0 6 r0','putd ra 27 r11','putd r1 13 ra','putd r1 14 r0','j Scan','Reset:','move r7 0','j Loop']
    return '\n'.join(L)+'\n'

def make_recovery_manager_program():
    return '''# Catalog Coordinator Recovery v2.0: d0 Core,d1 Registry ABI3; epoch takeover.
Loop:
yield
bdns d0 Loop
bdns d1 Loop
get r0 d0 0
bne r0 31415970 Loop
get r0 d1 0
bne r0 31415982 Loop
get r0 d1 1
bne r0 3 Loop
get r0 d1 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Loop
get r0 d1 19
bne r0 1 Loop
get r11 d1 23
mod r0 r11 2
bnez r0 Loop
l r12 d1 ReferenceId
l r15 d0 ReferenceId
get r13 d0 2
get r14 d0 3
move r7 1
Scan:
bgt r7 64 Done
mul r0 r7 6
add r0 r0 58
getd r1 r12 r0
blez r1 Next
add r0 r0 1
getd r6 r12 r0
beq r6 1 Next
beq r6 5 Next
getd r0 r1 5
bne r0 r13 Next
getd r0 r1 12
bge r0 r14 Next
get r0 d1 23
bne r0 r11 Loop
putd r1 11 r15
putd r1 12 r14
get r0 d0 22
add r0 r0 1
put d0 22 r0
Next:
add r7 r7 1
j Scan
Done:
get r0 d1 23
bne r0 r11 Loop
poke 0 31415976
poke 1 2
get r0 db 2
add r0 r0 1
poke 2 r0
j Loop
'''
def make_migration_manager_program():
    return '''# Catalog Item Migration Planner v2.0: d0 Core,d1 Directory.
Boot:
poke 0 31416069
poke 1 1
poke 2 0
Loop:
yield
bdns d0 Loop
bdns d1 Loop
get r0 d0 0
bne r0 31415970 Loop
get r0 d0 40
bgtz r0 Loop
get r0 d1 0
bne r0 31415982 Loop
get r0 d1 1
bne r0 3 Loop
get r0 d1 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Loop
get r0 d1 19
bne r0 1 Loop
get r12 d1 23
mod r0 r12 2
bnez r0 Loop
move r7 1
FindSrc:
bgt r7 64 Loop
jal DirRef
blez r1 NextSrc
getd r0 r1 16
bne r0 3 NextSrc
getd r3 r1 9
blez r3 NextSrc
sub r3 r3 1
mul r4 r3 2
add r4 r4 32
add r4 r4 1
getd r9 r1 r4
add r11 r9 2
move r13 r1
move r15 0
move r6 1
FindDst:
bgt r6 64 NeedStore
move r14 r7
move r7 r6
jal DirRef
move r7 r14
blez r2 DNext
beq r2 r13 DNext
getd r0 r2 16
bne r0 2 DNext
getd r0 r2 2
getd r5 r13 2
bne r0 r5 DNext
getd r0 r2 3
getd r5 r13 3
bne r0 r5 DNext
getd r0 r2 4
getd r5 r13 4
bne r0 r5 DNext
getd r0 r2 23
getd r5 r13 23
bne r0 r5 DNext
getd r0 r2 29
blt r0 r11 DNext
getd r0 r2 27
blez r0 DFree
move r15 1
j DNext
DFree:
get r0 d1 23
bne r0 r12 Loop
putd r2 27 r11
put d0 40 r13
put d0 41 r2
get r0 d0 42
add r0 r0 1
put d0 42 r0
j Loop
DNext:
add r6 r6 1
j FindDst
NeedStore:
get r0 d1 23
bne r0 r12 Loop
bgtz r15 Loop
get r0 d0 25
bgtz r0 Loop
getd r0 r13 23
put d0 26 r0
getd r0 r13 2
put d0 27 r0
getd r0 r13 3
put d0 28 r0
getd r0 r13 4
put d0 29 r0
getd r0 r13 7
put d0 30 r0
getd r0 r13 8
add r0 r0 1
put d0 31 r0
put d0 32 r11
put d0 25 1
j Loop
DirRef:
sub r0 r7 1
mul r0 r0 6
add r0 r0 64
get r1 d1 r0
move r2 r1
j ra
NextSrc:
add r7 r7 1
j FindSrc
'''
def make_migration_worker_program():
    L=['# Catalog Item Migration Worker v1.0: d0 Core; copies newest whole item then pops source.','Boot:','poke 0 31416071','poke 1 1','poke 2 0','Loop:','yield','bdns d0 Loop','get r0 d0 0',f'bne r0 {COORD_MAGIC} Loop','get r1 d0 40','blez r1 Loop','get r2 d0 41','blez r2 Loop','getd r3 r1 9','blez r3 Clear','sub r3 r3 1','mul r4 r3 2','add r4 r4 32','getd r8 r1 r4','add r4 r4 1','getd r9 r1 r4','add r11 r9 2','getd r0 r2 29','blt r0 r11 Clear','get r0 d0 7','add r0 r0 1','put d0 7 r0','getd r10 r2 20','sub r10 r10 r9','getd r12 r2 19','move r5 0','Copy:','bge r5 r9 Publish','add r0 r8 r5','getd r0 r1 r0','add r4 r10 r5','putd r2 r4 r0','add r5 r5 1','j Copy','Publish:','putd r2 r12 r10','add r12 r12 1','putd r2 r12 r9','add r12 r12 1','putd r2 19 r12','putd r2 20 r10','getd r0 r2 9','add r0 r0 1','putd r2 9 r0','getd r0 r2 22','add r0 r0 r11','putd r2 22 r0','sub r0 r10 r12','putd r2 29 r0','getd r0 r2 15','add r0 r0 1','putd r2 15 r0','getd r0 r1 9','sub r0 r0 1','putd r1 9 r0','getd r0 r1 19','sub r0 r0 2','putd r1 19 r0','add r0 r8 r9','putd r1 20 r0','getd r0 r1 22','sub r0 r0 r11','putd r1 22 r0','getd r4 r1 19','getd r5 r1 20','sub r0 r5 r4','putd r1 29 r0','getd r0 r1 15','add r0 r0 1','putd r1 15 r0','get r0 d0 6','add r0 r0 1','put d0 6 r0','get r0 d0 7','add r0 r0 1','put d0 7 r0','Clear:','blez r2 NoReserve','putd r2 27 0','NoReserve:','put d0 40 0','put d0 41 0','j Loop']
    return '\n'.join(L)+'\n' 

def make_retirement_manager_program():
    return '''# Catalog Store Retirement Manager v2.0: d0 Core,d1 Registry ABI3.
Boot:
poke 0 31416070
poke 1 1
poke 2 0
Loop:
yield
bdns d0 Loop
bdns d1 Loop
get r0 d0 0
bne r0 31415970 Loop
get r0 d1 0
bne r0 31415982 Loop
get r0 d1 1
bne r0 3 Loop
get r0 d1 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Loop
get r0 d1 19
bne r0 1 Loop
get r11 d1 23
mod r0 r11 2
bnez r0 Loop
move r7 1
Scan:
bgt r7 64 Loop
mul r0 r7 6
add r0 r0 58
get r1 d1 r0
blez r1 Next
getd r0 r1 16
bne r0 3 Next
getd r0 r1 9
bgtz r0 Next
get r0 d1 23
bne r0 r11 Loop
get r0 d0 7
add r0 r0 1
put d0 7 r0
getd r2 r1 6
getd r3 r1 7
blez r2 NoPrev
putd r2 7 r3
NoPrev:
blez r3 NoNext
putd r3 6 r2
NoNext:
putd r1 16 5
get r0 d0 6
add r0 r0 1
put d0 6 r0
get r0 d0 7
add r0 r0 1
put d0 7 r0
j Loop
Next:
add r7 r7 1
j Scan
'''
def make_coordinator_directory_scanner_program():
    return '''# Catalog Store Directory Adapter v3.0: Adapter ABI3; unique NodeId candidates.
Boot:
clr db
poke 0 31415983
poke 1 3
poke 2 17
poke 3 HASH("DirectorySchema.CatalogStoreNode.v1")
poke 8 HASH("DirectorySchema.CatalogStoreNode")
poke 9 1
poke 10 6
poke 11 64
poke 15 2
Loop:
yield
get r0 db 16
beqz r0 ScanStart
poke 17 r0
j Loop
ScanStart:
poke 17 0
get r15 db 13
add r15 r15 1
poke 13 r15
poke 14 0
move r6 448
Clear:
poke r6 0
add r6 r6 1
ble r6 511 Clear
move r7 0
move r8 0
Scan:
get r1 db:0 r7
blt r1 0 Publish
add r7 r7 1
getd r0 r1 0
bne r0 31415968 Scan
getd r0 r1 1
bne r0 5 Scan
getd r2 r1 18
blez r2 Scan
bgt r2 64 Scan
add r5 r2 447
get r6 db r5
bgtz r6 Duplicate
bge r8 64 Overflow
mul r3 r8 6
add r3 r3 18
poke r3 r2
add r3 r3 1
ld r0 r1 ReferenceId
poke r3 r0
add r3 r3 1
getd r0 r1 16
poke r3 r0
add r3 r3 1
getd r0 r1 22
poke r3 r0
add r3 r3 1
getd r0 r1 26
poke r3 r0
add r3 r3 1
getd r0 r1 4
poke r3 r0
add r6 r8 1
poke r5 r6
add r8 r8 1
j Scan
Duplicate:
sub r6 r6 1
mul r6 r6 6
add r6 r6 18
add r3 r6 1
get r0 db r3
putd r0 16 4
putd r1 16 4
add r3 r6 2
poke r3 8
j Scan
Overflow:
poke 14 1
j Scan
Publish:
poke 12 r8
get r0 db 13
add r0 r0 1
poke 13 r0
get r0 db 7
add r0 r0 1
poke 7 r0
j Loop
'''
def make_coordinator_directory_telemetry_program():
    return '''# Catalog Directory Telemetry v2.0: d0 Generic Registry Host ABI3.
Boot:
poke 0 31416068
poke 1 1
poke 2 0
Loop:
yield
bdns d0 Loop
get r0 d0 0
bne r0 31415982 Loop
get r0 d0 1
bne r0 3 Loop
get r0 d0 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Loop
get r0 d0 19
bne r0 1 Loop
get r14 d0 23
mod r0 r14 2
bnez r0 Loop
get r15 d0 18
mod r0 r15 2
bnez r0 Open
add r15 r15 1
put d0 18 r15
Open:
move r0 5
Zero:
put d0 r0 0
add r0 r0 1
ble r0 15 Zero
move r7 1
Sweep:
bgt r7 64 Publish
mul r3 r7 6
add r3 r3 58
get r1 d0 r3
blez r1 Next
get r0 d0 5
add r0 r0 1
put d0 5 r0
add r4 r3 1
get r6 d0 r4
beq r6 1 Unclaimed
beq r6 2 Active
beq r6 3 Draining
beq r6 4 Faulted
beq r6 5 Retired
beq r6 6 Active
beq r6 7 Missing
beq r6 8 Duplicate
j Next
Unclaimed:
move r2 7
j Count
Active:
move r2 6
j CountCap
Draining:
move r2 8
j CountCap
Faulted:
move r2 9
j Count
Retired:
move r2 10
j Count
Missing:
move r2 11
j Count
Duplicate:
move r2 12
Count:
get r0 d0 r2
add r0 r0 1
put d0 r2 r0
j Next
CountCap:
get r0 d0 r2
add r0 r0 1
put d0 r2 r0
add r4 r3 2
get r5 d0 r4
get r0 d0 13
add r0 r0 r5
put d0 13 r0
sub r5 512 r5
get r0 d0 14
add r0 r0 r5
put d0 14 r0
get r0 d0 15
add r0 r0 512
put d0 15 r0
Next:
add r7 r7 1
j Sweep
Publish:
get r0 d0 23
bne r0 r14 Loop
add r15 r15 1
put d0 18 r15
j Loop
'''
def make_coordinator_directory_view_program():
    return '''# Catalog Coordinator Directory View ABI2: d0 Registry ABI3,d1 Core; S2 NodeId.
poke 0 31415975
poke 1 2
Loop:
yield
bdns d0 Bad
bdns d1 Bad
get r0 d0 0
bne r0 31415982 Bad
get r0 d0 1
bne r0 3 Bad
get r0 d0 2
bne r0 HASH("DirectorySchema.CatalogStoreNode") Bad
get r0 d0 19
bne r0 1 Bad
get r15 d0 23
mod r0 r15 2
bnez r0 Bad
get r0 d1 0
bne r0 31415970 Bad
get r2 db 2
blt r2 1 Bad
bgt r2 64 Bad
mul r3 r2 6
add r3 r3 58
move r4 3
Copy:
get r0 d0 r3
poke r4 r0
add r3 r3 1
add r4 r4 1
blt r4 9 Copy
get r0 d0 18
poke 11 r0
get r0 d1 6
poke 25 r0
get r0 d1 7
poke 26 r0
get r0 d1 3
poke 27 r0
get r0 d0 23
bne r0 r15 Bad
poke 28 1
j Loop
Bad:
poke 28 -1
j Loop
'''
def ensure_coordination_programs(root:Path):
    names=COORDINATION_PROGRAM_FILES
    texts=(make_generic_store_program(),make_coordinator_core_program(),make_loader_router_program(),make_coordinator_directory_host_program(),make_coordinator_directory_scanner_program(),make_coordinator_directory_telemetry_program(),make_coordinator_directory_view_program(),make_recovery_manager_program(),make_migration_manager_program(),make_migration_worker_program(),make_retirement_manager_program())
    for n,t in zip(names,texts):
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(t)
    return names
