#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import IC10,Device
R=_PROJECT_ROOT
T=(R/'ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10').read_text(); G=(R/'ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10').read_text(); A=(R/'ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10').read_text(); Rank=(R/'ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10').read_text(); LD=(R/'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10').read_text(); fails=[]
for n in ('poke 97 2','bdns d3 SafeOff','bne r0 HASH("PressureTransferGrantGuard.v1") SafeOff','get r15 d3 18','bne r6 r15 SafeOff'):
 if n not in T: fails.append('Transfer missing '+n)
for n in ('get r14 d0 115','bne r0 r14 Loop','bne r4 r10 Consume','get r14 d1 14'):
 if n not in G: fails.append('Guard missing '+n)
if 'get r13 db 16' not in A: fails.append('Allocator lacks quote operation')
if 'getd r13 r11 12' not in Rank: fails.append('Ranker ignores current reservations')
for n in ('getd r15 r1 115','getd r0 r1 115','bne r0 r15 Scan'):
 if n not in LD: fails.append('Link Directory lacks coherent Transfer snapshot')
# The enumerator must preserve the selected ordinal while deriving the active bank base.
source=Device(9201,stack={18:1},props={'ReferenceId':9201})
junction=Device(9202,stack={18:3},props={'ReferenceId':9202})
sink=Device(9203,stack={18:2},props={'ReferenceId':9203})
link_a=Device(9101,stack={100:5,102:77,103:1,109:0},props={'ReferenceId':9101})
link_b=Device(9102,stack={100:6,102:77,103:1,109:0},props={'ReferenceId':9102})
directory=Device(9000,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',9:'HASH:DirectorySchema.PressureGridLink.v1',11:3,12:8,24:1,26:7,28:4,30:0,59:9101,60:9201,61:9202,62:9102,63:9202,64:9203},props={'ReferenceId':9000})
enumerator=IC10((R/'ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10').read_text(),{'d0':directory,'source':source,'junction':junction,'sink':sink,'link_a':link_a,'link_b':link_b})
enumerator.run(1);enumerator.stack.update({32:9201,33:1,34:77,35:1,36:1});enumerator.run(2,max_steps=10000)
if enumerator.stack.get(9)!=1 or enumerator.stack.get(37)!=2 or [enumerator.stack.get(16),enumerator.stack.get(17)]!=[9101,9102]:
 fails.append('Path Enumerator clobbered the selected record ordinal while deriving bank stride')
# Issue #142: the same-key resume (S35 == S11) trusts r4..r8 and sp, so the enumerator may
# take it only on a stack its own image published. A boot onto anything else clears first.
E=(R/'ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10').read_text()
link_c=Device(9103,stack={100:9,102:77,103:1,109:0},props={'ReferenceId':9103})
def grid(direct=False):
 links={56:9101,57:9201,58:9202,59:9102,60:9202,61:9203}
 if direct: links.update({62:9103,63:9201,64:9203})
 directory=Device(9000,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',9:'HASH:DirectorySchema.PressureGridLink.v1',11:3,12:8,24:1,26:7,28:len(links)//3,30:0,**links},props={'ReferenceId':9000})
 return {'d0':directory,'source':source,'junction':junction,'sink':sink,'link_a':link_a,'link_b':link_b,'link_c':link_c}
def ask(vm,key,token):
 vm.stack.update({32:9201,33:1,34:77,35:key,36:token}); vm.run(2,max_steps=10000)
 return [vm.stack.get(k,0) for k in (9,10,37,16,17)]
CANDIDATE=[1,100,2,9101,9102]; EXHAUSTED=[0,101,0,9101,9102]
# A foreign image left S11 equal to the consumer's S35, and its registers are whatever it used.
FOREIGN={0:'HASH:SomeOtherContract.v1',11:1,35:1,36:100,32:9201,33:1,34:77}
STALE={'r4':1.0,'r5':7.0,'r6':2.0,'r7':0.0,'r8':10.0,'sp':3.0}
vm=IC10(E,grid()); vm.stack.update(FOREIGN); vm.reg.update(STALE); vm.run(1)
if [vm.stack.get(k,0) for k in (11,35,36)]!=[0,0,0]:
 fails.append('Path Enumerator kept a foreign image\'s resume key across boot')
vm.run(1,max_steps=10000)
if {k for k,v in vm.stack.items() if v}-{0,1,2}:
 fails.append('Path Enumerator answered or wrote through stale registers on a foreign boot with no request')
if ask(vm,1,100)!=CANDIDATE or vm.stack.get(33)!=1:
 fails.append('Path Enumerator did not take the new-key path after a foreign boot')
# The answered-token echo is read back from S10, so the clear reseeds it with the stack: a foreign
# echo that happens to equal the first token must not make that request look already answered.
vm=IC10(E,grid()); vm.stack.update(FOREIGN|{10:100}); vm.reg.update(STALE); vm.run(1)
if ask(vm,1,100)!=CANDIDATE:
 fails.append('Path Enumerator let a foreign token echo swallow the first request after boot')
# The same image reflashed between requests finds its own S0 and resumes where it stopped.
vm=IC10(E,grid()); vm.run(1)
if ask(vm,1,100)!=CANDIDATE: fails.append('Path Enumerator missed the two-hop candidate')
again=IC10(E,grid()); again.stack=vm.stack; again.reg=dict(vm.reg); again.run(1)
if again.stack.get(11)!=1 or ask(again,1,101)!=EXHAUSTED:
 fails.append('Path Enumerator restarted a same-image search instead of resuming it')
# A direct LOW->HIGH link belongs to the Singlehop Builder and is never a one-hop candidate.
vm=IC10(E,grid(direct=True)); vm.run(1)
if ask(vm,1,100)!=CANDIDATE or ask(vm,1,101)!=EXHAUSTED or vm.stack.get(24)!=3:
 fails.append('Path Enumerator emitted or skipped a one-hop LOW->HIGH link')
# Issue #169: a fault ends the resume key. The directory republishes into its other bank between
# requests, so the cursors index a snapshot that is gone: the same SearchId answers -1 once, and
# the next request under it starts over on the new snapshot instead of faulting forever.
g=grid(); vm=IC10(E,g); vm.run(1)
if ask(vm,1,100)!=CANDIDATE: fails.append('Path Enumerator missed the candidate before the bank switch')
g['d0'].stack.update({24:0,25:8,27:2,29:0,32:9101,33:9201,34:9202,35:9102,36:9202,37:9203})
if ask(vm,1,101)!=[-1,101,0,9101,9102] or vm.stack.get(11)!=0:
 fails.append('Path Enumerator did not fault and drop the resume key when the snapshot changed')
if ask(vm,1,102)!=[1,102,2,9101,9102] or vm.stack.get(11)!=1:
 fails.append('Path Enumerator kept faulting on a SearchId it had already faulted')
if fails:
 print('Pressure-grid hardening model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-grid hardening model: PASS')
print(' - Transfer ABI2 executes only coherent GrantGuard output')
print(' - GrantGuard binds lease to coherent topology and Planner commit')
print(' - Allocator supports quote and topology-bound staging')
print(' - Route Ranker uses remaining reserved capacity')
print(' - Link Directory snapshots Transfer topology coherently')
print(' - Path Enumerator clears a foreign housing before it can resume and resumes only its own image')
print(' - Path Enumerator drops its resume key on a fault so the same SearchId searches the new snapshot')
