#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
R=_PROJECT_ROOT;fails=[]
def text(n):return (R/n).read_text()
def need(t,s,l):
 if s not in t:fails.append(f'{l}: missing {s!r}')
def ordered(t,a,b,l):
 if a not in t or b not in t or t.index(a)>=t.index(b):fails.append(f'{l}: expected {a!r} before {b!r}')
# ITEM endpoint/link primitives.
e=text('ic10/material-grid/material_import_slot_endpoint_v1_0.ic10')
for s in ('poke 0 31415949','poke 2 2','poke 4 2','get r14 d1 29','bne r0 31415963 Bad','get r0 d1 8','bne r0 2 Bad','ls r4 d0 0 Occupied','poke 11 r0'):need(e,s,'material import endpoint')
l=text('ic10/material-grid/material_resource_link_v1_0.ic10')
for s in ('l r3 d0 ReferenceId','l r4 d1 ReferenceId','poke 2 r3','poke 3 r4','poke 6 HASH("MaterialStackerSorter")','poke 19 r10','poke 20 r11','poke 21 r13','poke 22 r8'):need(l,s,'material link')
# Grant Guard is current-allocator-only and binds exact topology/transaction identity.
g=text('ic10/material-grid/material_transfer_grant_guard_v1_0.ic10')
for s in ('poke 0 31415960','bne r0 2 Bad','bne r0 r2 Consume','bne r0 r3 Consume','bne r0 r4 Consume','bne r0 r5 Consume','bne r0 r6 Consume','bne r0 r7 Consume','bne r0 r1 Consume','bne r0 r11 Consume','bne r0 2 ResBad'):need(g,s,'material grant guard')
# Feeder/executor exact-batch safety remains unchanged.
f=text('ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10')
for s in ('beq r0 31415961 Init','s d0 RequestHash r8','s d1 Setting r9','sll r0 r8 8','or r0 r0 1','put d2 0 r0','s d1 On 0','s d2 On 0'):need(f,s,'material feeder')
x=text('ic10/material-grid/material_transfer_executor_v1_0.ic10')
for s in ('ld r3 r2 ImportCount','poke 13 r3','put d1 19 r1','get r0 d1 7','bne r0 r1 Publish','poke 15 r4','poke 16 1'):need(x,s,'material executor')
ordered(x,'poke 13 r3','put d1 19 r1','material executor delivery snapshot')
# One canonical transform transaction path: Admission -> Resolver -> Stager -> Allocator2 -> Runtime.
a=text('ic10/material-transform/material_transform_admission_v1_0.ic10');r=text('ic10/material-transform/material_transform_link_resolver_v1_0.ic10');s=text('ic10/material-transform/multi_material_reservation_stager_v1_0.ic10');m=text('ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10');rt=text('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10')
for tok in ('bgt r4 3 Bad','HASH("StructureArcFurnace")','HASH("StructureFurnace")','HASH("StructureAdvancedFurnace")','poke 8 1'):need(a,tok,'transform admission')
for tok in ('bne r0 31415981 Bad','HASH("DirectorySchema.ResourceLink.v1")','getd r0 r1 22','poke r0 r1'):need(r,tok,'transform link resolver')
for tok in ('putd r2 14 r10','putd r3 15 r10','putd r4 17 r1','poke 13 1'):need(s,tok,'reservation stager')
for tok in ('poke 0 31415954','poke 1 2','poke 14 r1','poke 14 0','put d1 9 2'):need(m,tok,'multi allocator')
ordered(m,'put d1 9 1','poke 14 r1','allocator stages before common epoch')
for tok in ('s d0 Activate 1','sub r0 r0 r1','s d0 Activate 0','put d3 23 r0'):need(rt,tok,'generic runtime')
# Profile/catalog current contract.
tv=text('ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10')
for tok in ('poke 1 4','move r1 8','move r1 32','jal CopyPool'):need(tv,tok,'transform profile view')
tl=text('ic10/transform-catalog/resource_transform_catalog_loader_00_v6_0.ic10')
for tok in ('clr db','poke 0 31415969','poke 1 5','poke 18 1 # immutable candidate publication LAST'):need(tl,tok,'transform catalog loader')
if 'putd ' in tl or 'put d0 ' in tl or 'yield' in tl:fails.append('transform catalog loader must publish only its own one-shot stack')
# Deleted predecessor path must stay deleted.
for stale in ('78_material_reservation_allocator_v1_0.ic10','79_arc_furnace_transform_admission_v1_0.ic10','80_arc_furnace_transform_runtime_v1_0.ic10'):
 if (R/stale).exists():fails.append('obsolete transform path returned: '+stale)
if fails:
 print('MaterialGrid protocol model: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('MaterialGrid protocol model: PASS')
print(' - material endpoint/link/feeder/executor primitives remain exact-batch safe')
print(' - Grant Guard requires Allocator ABI2')
print(' - one canonical 1..3-input transform execution path remains')
print(' - obsolete serialized Allocator/Arc-Furnace compatibility ICs are absent')
