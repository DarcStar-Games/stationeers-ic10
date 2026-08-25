#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import IC10,Device
from framework.job_abi import JobIntent,JobType,JobState
R=_PROJECT_ROOT;fails=[]
def ck(x,m):
 if not x:fails.append(m)
def src(n):return (R/n).read_text()
def boot_store():
 vm=IC10(src('ic10/generic-jobs/generic_job_store_v1_0.ic10'));vm.run(1);return vm
def state(vm,slot):
 m=288+7*slot;a=int(vm.stack.get(m,0));b=m+1+3*a
 return int(vm.stack.get(b,0)),int(vm.stack.get(b+1,0)),int(vm.stack.get(b+2,0))
def stage(vm,slot,i):
 b=32+8*slot
 vals=[i.job_type,i.required_capability,i.identity,i.input_count,i.output_count,i.requested_quantity,i.priority]
 for n,v in enumerate(vals,1):vm.stack[b+n]=v
def req(vm,g,cmd,slot,expected=0,newstate=0,err=0):
 vm.stack.update({11:cmd,12:slot,13:expected,14:newstate,15:err,7:g});vm.run(1)
 return int(vm.stack.get(9,0)),int(vm.stack.get(10,0))
def publish(vm,g,slot,i):
 stage(vm,slot,i);s,j=req(vm,g,1,slot);ck(s==1,f'publish slot {slot} failed');return g+1,j

def transition(vm,g,slot,newstate,err=0):
 st,gen,_=state(vm,slot);s,_=req(vm,g,2,slot,gen,newstate,err);ck(s==1,f'transition {st}->{newstate} failed');return g+1

# Selector priority/tie-break and cursor fairness across multiple waiters.
store=boot_store();g=1
g,a=publish(store,g,0,JobIntent(JobType.PRINT,1,101,1,1,1,100))
g,b=publish(store,g,1,JobIntent(JobType.TRANSFORM,1,102,1,1,1,90))
g,c=publish(store,g,2,JobIntent(JobType.TRANSFORM,1,103,1,1,1,10))
for slot in (0,1):
 g=transition(store,g,slot,JobState.PLANNING);g=transition(store,g,slot,JobState.WAIT_PROCESSOR,0)
sdev=Device(100,store.stack,{'ReferenceId':100});sel=IC10(src('ic10/generic-jobs/generic_job_selector_v3_0.ic10'),{'d0':sdev},self_ref=101);sel.run(1)
sel.stack.update({2:0,3:1});sel.run(1);ck(sel.stack.get(7)==a,'selector did not choose highest-priority waiter')
sel.stack.update({2:a,3:2});sel.run(1);ck(sel.stack.get(7)==b,'cursor did not advance past first waiter')
sel.stack.update({2:b,3:3});sel.run(1);ck(sel.stack.get(7)==c,'two waiters can still starve a runnable lower-priority job')

# Router must not mirror stale state until selected driver publishes current request identity.
tdrv=Device(201,{9:99,10:7,11:0},{'ReferenceId':201});pdrv=Device(202,{}, {'ReferenceId':202})
ss=Device(203,{7:77,8:1,9:7,10:1111,11:3,12:1,13:2},{'ReferenceId':203})
router=IC10(src('ic10/manufacturing/manufacturing_driver_router_v2_0.ic10'),{'d0':tdrv,'d1':pdrv,'d2':ss},self_ref=204);router.run(1)
router.stack[9]=3;router.run(2)
ck(router.stack.get(10)!=3,'router acknowledged stale previous-driver state as current')
tdrv.stack.update({9:3,10:5,11:0});router.run(1)
ck(router.stack.get(10)==3 and router.stack.get(11)==5,'router did not publish current driver state after token match')

# Scheduler + actual Store/Selector: stale COMPLETE with no router acknowledgement cannot advance a new job.
store=boot_store();g=1;g,jid=publish(store,g,0,JobIntent(JobType.TRANSFORM,1,4242,1,1,1,20))
sdev=Device(300,store.stack,{'ReferenceId':300});sel=IC10(src('ic10/generic-jobs/generic_job_selector_v3_0.ic10'),{'d0':sdev},self_ref=301);sel.run(1);seldev=Device(301,sel.stack,{'ReferenceId':301})
route=Device(302,{10:99,11:7,12:0},{'ReferenceId':302});sched=IC10(src('ic10/manufacturing/manufacturing_scheduler_v1_0.ic10'),{'d0':sdev,'d1':seldev,'d2':route},self_ref=303);sched.run(1)
def rounds(n=1,accept=False,target=2):
 for _ in range(n):
  sched.run(1)
  if accept and route.stack.get(9): route.stack.update({10:route.stack[9],11:target,12:0})
  sel.run(1);store.run(1)
rounds(20,False)
ck(state(store,0)[0]==JobState.PLANNING,'stale COMPLETE advanced a job whose driver never accepted the request')

# Once the router acknowledges the current request, scheduler still advances exactly one legal edge per commit.
seen=[state(store,0)[0]]
for _ in range(30):
 rounds(1,True,JobState.RUNNING);st=state(store,0)[0]
 if seen[-1]!=st:seen.append(st)
 if st==JobState.RUNNING:break
ck(seen[-3:]==[JobState.RESERVING,JobState.READY,JobState.RUNNING],f'scheduler skipped lifecycle edge(s): {seen}')
for _ in range(30):
 rounds(1,True,JobState.COMPLETE);st=state(store,0)[0]
 if seen[-1]!=st:seen.append(st)
 if st==JobState.COMPLETE:break
ck(seen[-3:]==[JobState.RUNNING,JobState.VERIFYING,JobState.COMPLETE],f'scheduler skipped verification edge: {seen}')

if fails:
 print('Manufacturing Scheduler: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Manufacturing Scheduler: PASS')
print(' - JobId cursor guarantees progress across multiple high-priority WAIT jobs')
print(' - Router publishes state only after selected driver current-token match')
print(' - stale prior COMPLETE cannot advance a new job without driver acceptance')
print(' - scheduler still commits exactly one legal Job ABI edge at a time')
