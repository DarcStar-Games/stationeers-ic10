#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import Device, IC10
R=_PROJECT_ROOT
fails=[]
def src(n): return (R/n).read_text()
def need(t,s,l):
    if s not in t: fails.append(f'{l}: missing {s!r}')
# Static protocol invariants.
a=src('ic10/material-transform/material_transform_admission_v1_0.ic10')
r=src('ic10/material-transform/material_transform_link_resolver_v1_0.ic10')
s=src('ic10/material-transform/multi_material_reservation_stager_v1_0.ic10')
m=src('ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10')
x=src('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10')
g=src('ic10/material-grid/material_transfer_grant_guard_v1_0.ic10')
for tok in ('bgt r4 3 Bad','and r0 r6 r3','HASH("StructureAdvancedFurnace")','l r0 d1 Pressure','l r0 d1 Temperature','poke 8 1'):
    need(a,tok,'generic admission')
for tok in ('get r10 d2 r0','getd r0 r1 22','getd r0 r15 36','poke r0 r1'):
    need(r,tok,'link resolver')
for tok in ('putd r2 14 r10','putd r3 15 r10','putd r4 17 r1','poke 13 1'):
    need(s,tok,'reservation stager')
for tok in ('poke 14 r1','poke 14 0','getd r0 r9 23','put d1 9 2'):
    need(m,tok,'multi allocator')
if s.index('putd r4 17 r1') >= m.index('poke 14 r1'):
    pass # separate programs: semantic ordering checked dynamically below
need(g,'bne r0 HASH("MultiMaterialReservationAllocator.v2") Bad','grant guard ABI2-only contract')
for tok in ('put d3 21 r15','s d0 Activate 1','sub r0 r0 r1','put d3 23 r0'):
    need(x,tok,'generic runtime')


# Capability matrix: basic smelts run on all furnace classes; 2-input alloys on Furnace/Advanced; superalloys on Advanced only.
def cap_admit(prefab,required,input_count=2,pressure=2000,temperature=1500):
    pp=Device(970,props={'ReferenceId':970,'PrefabHash':'HASH:'+prefab,'Power':1,'Error':0,'Pressure':pressure,'Temperature':temperature})
    vv=Device(971,stack={0:'HASH:ResourceTransformProfileView.v4',1:4,70:321,71:required,72:input_count,73:1,74:7,8:2,9:101,10:2,11:1,12:2,13:102,14:2,15:1,16:2,17:103,18:2,19:1,32:2,33:444,34:2,35:1,64:100,65:100000,66:300,67:100000,68:321,69:1})
    oo=Device(972,stack={0:'HASH:ResourceReservation.v1',1:1,33:2,34:444,36:0,37:100,9:1,10:2,12:1})
    vm=IC10(a,{'d0':vv,'d1':pp,'d2':oo},self_ref=973);vm.run(2);return vm.stack.get(8)
for prefab in ('StructureArcFurnace','StructureFurnace','StructureAdvancedFurnace'):
    if cap_admit(prefab,1,1)!=1:fails.append('basic-smelt capability rejected '+prefab)
if cap_admit('StructureArcFurnace',2)!=-1 or cap_admit('StructureFurnace',2)!=1 or cap_admit('StructureAdvancedFurnace',2)!=1:
    fails.append('2-input Furnace/Advanced capability matrix mismatch')
if cap_admit('StructureFurnace',4,3)!=-1 or cap_admit('StructureAdvancedFurnace',4,3)!=1:
    fails.append('advanced-alloy capability matrix mismatch')
# Environmental bounds are transform requirements, not Furnace-class behavior.
for prefab in ('StructureArcFurnace','StructureFurnace','StructureAdvancedFurnace'):
    if cap_admit(prefab,1,1,pressure=99)!=-1:fails.append('minimum pressure not enforced on '+prefab)
    if cap_admit(prefab,1,1,pressure=100001)!=-1:fails.append('maximum pressure not enforced on '+prefab)
    if cap_admit(prefab,1,1,temperature=299)!=-1:fails.append('minimum temperature not enforced on '+prefab)
    if cap_admit(prefab,1,1,temperature=100001)!=-1:fails.append('maximum temperature not enforced on '+prefab)

# Synthetic 3-input transform path.
proc=Device(900,props={'ReferenceId':900,'PrefabHash':'HASH:StructureAdvancedFurnace','Power':1,'Error':0,'Pressure':2000,'Temperature':1500,'Activate':0})
out=Device(901,stack={0:'HASH:ResourceReservation.v1',1:1,33:2,34:444,36:0,37:100,9:1,10:2,12:1},props={'ReferenceId':901})
view=Device(902,stack={0:'HASH:ResourceTransformProfileView.v4',1:4,70:123,71:4,72:3,73:1,74:5,75:0,
    8:2,9:101,10:2,11:1,12:2,13:102,14:2,15:1,16:2,17:103,18:2,19:2,
    32:2,33:444,34:2,35:1,64:1000,65:3000,66:1200,67:1800,68:123,69:1},props={'ReferenceId':902})
adm_vm=IC10(a,{'d0':view,'d1':proc,'d2':out},self_ref=903); adm_dev=Device(903,adm_vm.stack,{'ReferenceId':903})
adm_vm.run(2)
if adm_vm.stack.get(8)!=1 or adm_vm.stack.get(16)!=3: fails.append('generic admission rejected valid 3-input transform')

links=[]; dyn={}
for i,(typ,qty) in enumerate(((101,1),(102,1),(103,2))):
    sr=Device(910+i*10,stack={0:'HASH:ResourceReservation.v1',1:1,33:2,34:typ,36:20,37:0,9:1,10:2,12:1},props={'ReferenceId':910+i*10})
    dr=Device(911+i*10,stack={0:'HASH:ResourceReservation.v1',1:1,33:2,34:typ,36:0,37:20,9:1,10:2,12:1},props={'ReferenceId':911+i*10})
    guard=Device(912+i*10,stack={0:'HASH:MaterialTransferGrantGuard.v1',1:1,13:1},props={'ReferenceId':912+i*10})
    exe=Device(913+i*10,stack={0:'HASH:MaterialTransferExecutor.v1',1:1,2:0,7:1},props={'ReferenceId':913+i*10})
    feed=Device(914+i*10,stack={0:'HASH:StackerFeeder.v1',1:1},props={'ReferenceId':914+i*10})
    link=Device(915+i*10,stack={0:'HASH:ResourceLink.v1',1:1,28:sr.ref,29:dr.ref,30:2,31:typ,9:1,12:1,14:guard.ref,15:exe.ref,16:feed.ref,21:700+i,22:proc.ref,23:0},props={'ReferenceId':915+i*10})
    links.append((link,sr,dr,guard,exe,feed,qty))
    for d in (link,sr,dr,guard,exe,feed): dyn[f'x{d.ref}']=d
ld=Device(950,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,24:0,25:1,27:3,9:'HASH:DirectorySchema.ResourceLink.v1',11:1,12:64,32:links[0][0].ref,33:links[1][0].ref,34:links[2][0].ref},props={'ReferenceId':950})
res_vm=IC10(r,{'d0':adm_dev,'d1':view,'d2':ld,**dyn},self_ref=951); res_dev=Device(951,res_vm.stack,{'ReferenceId':951})
res_vm.run(2)
if res_vm.stack.get(12)!=1 or [res_vm.stack.get(20+i*4) for i in range(3)] != [z[0].ref for z in links]:
    fails.append('link resolver failed to publish all three input routes')

# The admitted input count is a peer's number, and the record window each
# consumer sizes from it is its own stack. A fourth input that resolves as
# cleanly as the first three would be written past the three records either
# program owns, so both hold the count to what the Admission accepts.
over_view=Device(959,dict(view.stack)|{20:2,21:101,22:2,23:1},{'ReferenceId':959})
over_adm=Device(954,dict(adm_vm.stack)|{16:4},{'ReferenceId':954})
over_res_vm=IC10(r,{'d0':over_adm,'d1':over_view,'d2':ld,**dyn},self_ref=955)
over_res_vm.run(2)
if over_res_vm.stack.get(12)!=-1 or [c for c in over_res_vm.stack if c>31]:
    fails.append('link resolver accepted an input count above the admitted three')

over_links=Device(956,dict(res_vm.stack)|{9:4,32:res_vm.stack.get(20),33:res_vm.stack.get(21),
    34:res_vm.stack.get(22),35:res_vm.stack.get(23)},{'ReferenceId':956})
over_stager_vm=IC10(s,{'d0':over_links,'d1':Device(957,{},{'ReferenceId':957}),**dyn},self_ref=958)
over_stager_vm.run(1)
over_stager_vm.stack.update({9:1,10:1,11:1,12:1,14:0})
over_stager_vm.run(1)
if over_stager_vm.stack.get(13)!=-1 or [c for c in over_stager_vm.stack if c>14]:
    fails.append('reservation stager accepted a resolved count above the admitted three')

# A reflash preserves the whole stack, so a housing that last ran something else hands
# the stager both a staged count at S8 and an unread request at S9..S12/S14. Only its own
# S0 makes any of that its own, so boot disowns every other stack rather than acting on it.
# The count first: a clean walks S8 records over its own window, releasing reservations a
# previous occupant staged. Zeroing S8 unconditionally would close that by destroying the
# crash recovery the incremental `poke 8 r12` exists for, so both directions are pinned.
def reflash_clean(boot):
    a=Device(801,{13:77,14:250,16:1},{'ReferenceId':801})
    b=Device(802,{13:77,15:250,16:2},{'ReferenceId':802})
    vm=IC10(s,{'x801':a,'x802':b},self_ref=805)
    vm.stack.update({8:1,9:2,12:7,14:0,32:700,33:801,34:802}|boot)
    vm.run(2)
    return a.stack.get(14),b.stack.get(15),vm.stack.get(8,0),vm.stack.get(13,0)
if reflash_clean({})!=(250,250,0,0):
    fails.append('reflashed stager released reservations a previous occupant of the housing staged')
if reflash_clean({0:'HASH:MultiMaterialReservationStager.v1'})!=(0,0,0,2):
    fails.append('reflashed stager lost the records it staged itself before the reflash')

# Then the request. An inherited S12 != S14 with an inherited S9 == 1 dispatches against
# whatever the live Resolver currently publishes -- reserving material on both sides and
# arming a Grant Guard with an inherited job id, which is what lets material move. The
# same stack under this program's own S0 is its own unfinished request and must still run.
def reflash_stage(boot):
    ghosts={k:Device(d.ref,dict(d.stack),dict(d.props)) for k,d in dyn.items()}
    vm=IC10(s,{'d0':res_dev,'d1':Device(957,{},{'ReferenceId':957}),**ghosts},self_ref=958)
    vm.stack.update({9:1,10:77,11:3,12:7,14:0}|boot)
    vm.run(2)
    return ([k for k,d in ghosts.items() if d.stack!=dyn[k].stack],
            vm.stack.get(13,0),vm.stack.get(14,0))
if reflash_stage({})!=([],0,0):
    fails.append('reflashed stager staged a request the previous occupant of the housing left behind')
if reflash_stage({0:'HASH:MultiMaterialReservationStager.v1'})==([],0,0):
    fails.append('stager ignored an unfinished request on the stack it published itself')

stager_dev=Device(952,{}, {'ReferenceId':952})
alloc_dev=Device(953,{}, {'ReferenceId':953})
stager_vm=IC10(s,{'d0':res_dev,'d1':alloc_dev,**dyn},self_ref=952); stager_dev.stack=stager_vm.stack
alloc_vm=IC10(m,{'d0':res_dev,'d1':stager_dev,**dyn},self_ref=953); alloc_dev.stack=alloc_vm.stack
stager_vm.run(1); alloc_vm.run(1)
alloc_vm.stack[8]=2; alloc_vm.stack[20]=999; alloc_vm.stack[21]=1
for _ in range(8):
    alloc_vm.run(1); stager_vm.run(1)
    if alloc_vm.stack.get(22)==1: break
epoch=alloc_vm.stack.get(14,0)
if epoch<=0 or alloc_vm.stack.get(22)!=1: fails.append('multi allocator failed atomic common-epoch commit')
for link,sr,dr,guard,exe,feed,qty in links:
    if sr.stack.get(14)!=qty*2 or dr.stack.get(15)!=qty*2 or guard.stack.get(17)!=epoch or guard.stack.get(18)!=alloc_dev.ref:
        fails.append(f'multi allocator staged incorrect reservation/grant for type {link.stack[31]}')
# Every Guard should activate only after the common allocator epoch is visible.
for i,(link,sr,dr,guard,exe,feed,qty) in enumerate(links):
    gv=IC10(g,{'d0':link,'d1':alloc_dev,'d2':exe,'xsrc':sr,'xsink':dr},self_ref=guard.ref); gv.stack=guard.stack; gv.run(2)
    if gv.stack.get(11)!=1 or gv.stack.get(10)!=epoch: fails.append(f'guard {i} did not activate common epoch')
# Simulate all three transfer executors completing the common epoch.
for link,*_ in links: link.stack[23]=epoch
for _ in range(8):
    alloc_vm.run(1); stager_vm.run(1)
    if alloc_vm.stack.get(22)==2: break
if alloc_vm.stack.get(22)!=2: fails.append('multi allocator did not publish completion after all links completed')
for link,sr,dr,*_ in links:
    if sr.stack.get(14)!=0 or sr.stack.get(16)!=0 or dr.stack.get(15)!=0 or dr.stack.get(16)!=0:
        fails.append('multi allocator did not clear completed reservations')
# Rejection on the third input must roll back earlier staging without publishing S14.
links[2][1].stack[36]=1
alloc_vm.stack[8]=2; alloc_vm.stack[20]=999; alloc_vm.stack[21]=2
for _ in range(12):
    alloc_vm.run(1); stager_vm.run(1)
    if alloc_vm.stack.get(16)==2 and alloc_vm.stack.get(22)<0: break
if alloc_vm.stack.get(14)!=0 or alloc_vm.stack.get(22)>=0: fails.append('failed multi-input request published a commit epoch')
for link,sr,dr,*_ in links:
    if sr.stack.get(14)!=0 or dr.stack.get(15)!=0: fails.append('failed multi-input request leaked partial reservation')
links[2][1].stack[36]=20

# Runtime hand-off: use a fresh request and simulate committed input/output completion.
rt_vm=IC10(x,{'d0':proc,'d1':adm_dev,'d2':res_dev,'d3':alloc_dev,'d4':out},self_ref=960)
rt_vm.run(1); rt_vm.stack[8]=2; rt_vm.stack[16]=3
output_done=False
for _ in range(40):
    adm_vm.run(1); res_vm.run(1); rt_vm.run(1); alloc_vm.run(1); stager_vm.run(1)
    ep=alloc_vm.stack.get(14,0)
    if ep>0:
        for link,*_ in links: link.stack[23]=ep
    if proc.props.get('Activate')==1 and not output_done:
        out.stack[36]+=2; out.stack[12]+=1; output_done=True
    if rt_vm.stack.get(21)==3 and rt_vm.stack.get(20)==1: break
if rt_vm.stack.get(21)!=3 or rt_vm.stack.get(20)!=1 or proc.props.get('Activate')!=0:
    fails.append('generic transform runtime failed 3-input transaction/output confirmation')

if fails:
    print('Generic Material Transform protocol: FAIL')
    for f in fails: print(' -',f)
    sys.exit(1)
print('Generic Material Transform protocol: PASS')
print(' - admission validates 1..3 inputs, hierarchical processor capabilities, universal transform conditions, and output capacity')
print(' - resolver selects complete typed Material Links terminating at the exact processor')
print(' - stager prepares every reservation/Guard before allocator publishes one common epoch')
print(' - any failed input rolls back partial reservations without publishing a commit epoch')
print(' - Grant Guard accepts only the current Allocator ABI2 contract')
print(' - generic runtime completes a simulated 3-input transform and confirms output growth')
