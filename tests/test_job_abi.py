from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
import json, math, sys
from ic10_harness import IC10
from job_abi import JobIntent,JobState,JobType,allowed_transition,can_reap,validate_intent
R=_PROJECT_ROOT
SRC=(R/'ic10/generic-jobs/generic_job_store_v1_0.ic10').read_text()
SCHEMA=json.loads((R/'generic_job_schema.json').read_text())
fails=[]
def ck(cond,msg):
    if not cond:fails.append(msg)

def boot(stack=None):
    vm=IC10(SRC)
    if stack is not None: vm.stack=dict(stack)
    vm.run(1)
    return vm

def state(vm,slot):
    m=288+7*slot;a=int(vm.stack.get(m,0));b=m+1+3*a
    return int(vm.stack.get(b,0)),int(vm.stack.get(b+1,0)),int(vm.stack.get(b+2,0)),a

def intent(vm,slot):
    b=32+8*slot
    return [vm.stack.get(b+i,0) for i in range(8)]

def request(vm,gen,cmd,slot,expected=0,newstate=0,status=0):
    vm.stack.update({11:cmd,12:slot,13:expected,14:newstate,15:status,7:gen})
    vm.run(1)
    return int(vm.stack.get(9,0)),int(vm.stack.get(10,0))

def stage(vm,slot,i):
    b=32+8*slot
    vals=[i.job_type,i.required_capability,i.identity,i.input_count,i.output_count,i.requested_quantity,i.priority]
    for n,v in enumerate(vals,1):vm.stack[b+n]=v

# Canonical schema/model.
ck(SCHEMA['magic']==31415984 and SCHEMA['abi']==1,'schema magic/ABI mismatch')
ck(SCHEMA['capacity']==32 and SCHEMA['logical_record_width']==11,'schema geometry mismatch')
ck(SCHEMA['fields']==['JobId','JobType','RequiredCapability','Identity','InputCount','OutputCount','RequestedQuantity','Priority','State','Generation','ErrorStatus'],'logical fields mismatch')
for jt in JobType:ck(SCHEMA['job_types'][jt.name]==jt.value,f'job type {jt.name} mismatch')
for st in JobState:ck(SCHEMA['states'][st.name]==st.value,f'job state {st.name} mismatch')

valid=JobIntent(JobType.TRANSFORM,7,12345,3,1,2,50)
ck(validate_intent(valid),'valid intent rejected')
for bad in [
    JobIntent(0,0,1,1,1,1,0),JobIntent(1,-1,1,1,1,1,0),JobIntent(1,0,0,1,1,1,0),
    JobIntent(1,0,1,33,1,1,0),JobIntent(1,0,1,1,33,1,0),JobIntent(1,0,1,1,1,0,0),
    JobIntent(1,0,1,1,1,math.nan,0),JobIntent(1,0,1,1,1,1,0.5)]:
    ck(not validate_intent(bad),f'invalid intent accepted: {bad}')

chain=[JobState.QUEUED,JobState.PLANNING,JobState.RESERVING,JobState.READY,JobState.RUNNING,JobState.VERIFYING,JobState.COMPLETE]
for a,b in zip(chain,chain[1:]):ck(allowed_transition(a,b,0),f'normal transition {a}->{b} rejected')
for old in (JobState.PLANNING,JobState.RESERVING,JobState.READY):
    for wait in (JobState.WAIT_RESOURCE,JobState.WAIT_PROCESSOR,JobState.WAIT_CAPACITY):
        ck(allowed_transition(old,wait,1),f'wait transition {old}->{wait} rejected')
for wait in (JobState.WAIT_RESOURCE,JobState.WAIT_PROCESSOR,JobState.WAIT_CAPACITY):
    ck(allowed_transition(wait,JobState.PLANNING,0),f'wait resume {wait}->PLANNING rejected')
for old in (1,2,3,4,5,6,8,9,10):
    ck(allowed_transition(old,JobState.CANCELLED,0),f'cancel from {old} rejected')
    ck(allowed_transition(old,JobState.FAULT,-99),f'fault from {old} rejected')
ck(not allowed_transition(JobState.RUNNING,JobState.COMPLETE,0),'RUNNING skipped VERIFYING')
ck(not allowed_transition(JobState.COMPLETE,JobState.PLANNING,0),'terminal COMPLETE reopened')
ck(not allowed_transition(JobState.FAULT,JobState.PLANNING,0),'terminal FAULT reopened')
ck(not allowed_transition(JobState.PLANNING,JobState.FAULT,0),'FAULT accepted without negative error')
for st in JobState:ck(can_reap(st)==(st in {JobState.COMPLETE,JobState.FAULT,JobState.CANCELLED}),f'reap classification wrong for {st}')

# Store publish/update/reap and optimistic generation.
vm=boot();ck(vm.stack.get(0)==31415984 and vm.stack.get(1)==1,'store header missing')
ck(vm.stack.get(5)==32 and vm.stack.get(23)==1,'store capacity/next id mismatch')
# Same magic with a different Store ABI is incompatible storage geometry and must reset.
rv=boot({0:31415984,1:99,2:7,23:88,288:1,289:12,290:9,291:-1})
ck(rv.stack.get(1)==1 and rv.stack.get(23)==1 and rv.stack.get(288,0)==0,'incompatible Store ABI was interpreted instead of reset')
stage(vm,0,valid)
status,jid=request(vm,1,1,0)
ck(status==1 and jid==1,'new job publication failed')
ck(intent(vm,0)==[1,1,7,12345,3,1,2,50],'published intent mismatch')
ck(state(vm,0)[:3]==(JobState.QUEUED,1,0),'new job state/generation/status mismatch')
ck(int(vm.stack.get(2,1))%2==0 and vm.stack.get(3)==1,'queue publication tokens incorrect')

# Legal lifecycle writes are mechanically generation-checked by Store.
gen=2
for target in chain[1:]:
    old=state(vm,0)[1]
    ck(allowed_transition(state(vm,0)[0],target,0),f'model rejected planned transition to {target}')
    status,_=request(vm,gen,2,0,old,int(target),0);gen+=1
    ck(status==1 and state(vm,0)[:3]==(int(target),old+1,0),f'store failed transition to {target}')
# stale generation cannot mutate.
status,_=request(vm,gen,2,0,1,int(JobState.PLANNING),0);gen+=1
ck(status<0 and state(vm,0)[0]==JobState.COMPLETE,'stale state mutation was accepted')
# COMPLETE cannot be reopened even with current generation.
curgen=state(vm,0)[1]
status,_=request(vm,gen,2,0,curgen,int(JobState.PLANNING),0);gen+=1
ck(status<0 and state(vm,0)[0]==JobState.COMPLETE,'terminal COMPLETE reopened')
# Terminal reap succeeds and slot becomes reusable.
status,_=request(vm,gen,3,0,curgen);gen+=1
ck(status==1 and state(vm,0)[0]==0,'terminal reap failed')
stage(vm,0,JobIntent(JobType.PRINT,2,-123,0,1,4,10))
status,jid2=request(vm,gen,1,0);gen+=1
ck(status==1 and jid2==2 and state(vm,0)[:2]==(JobState.QUEUED,1),'reused slot did not get fresh JobId/generation')

# REAP rejects nonterminal jobs; slot ordinal 32 rejects capacity overflow.
curgen=state(vm,0)[1]
status,_=request(vm,gen,3,0,curgen);gen+=1
ck(status<0 and state(vm,0)[0]==JobState.QUEUED,'nonterminal job was reaped')
status,_=request(vm,gen,1,32);gen+=1
ck(status<0,'slot ordinal 32 accepted beyond 32-slot capacity')

# Fill all 32 slots through the same Store publication path.
vm=boot();g=1
for slot in range(32):
    stage(vm,slot,JobIntent(JobType.TRANSFER,0,1000+slot,1,1,slot+1,0))
    s,j=request(vm,g,1,slot);g+=1
    ck(s==1 and j==slot+1,f'failed to publish slot {slot}')
ck(all(state(vm,s)[0]==JobState.QUEUED for s in range(32)),'not all 32 slots published')
ck(int(vm.stack.get(23,0))==33,'NextJobId did not advance across 32 jobs')

# Crash recovery before active-bank flip: rollback/retry marker, old state remains authoritative.
vm=boot();stage(vm,0,valid);request(vm,1,1,0)
m=288;old_active=state(vm,0)[3];old_state=state(vm,0)[:3]
cr=dict(vm.stack);cr[7]=2;cr[11]=2;cr[12]=0;cr[13]=1;cr[14]=JobState.PLANNING;cr[15]=0
cr[25]=m;cr[26]=old_active;cr[24]=2;cr[2]=int(cr.get(2,0))+1
rv=boot(cr)
ck(int(rv.stack.get(2,1))%2==0 and rv.stack.get(24)==0,'pre-flip crash did not roll request back')
ck(state(rv,0)[:3]==old_state,'pre-flip crash changed authoritative job state')
rv.run(1)
ck(rv.stack.get(8)==2 and state(rv,0)[0]==JobState.PLANNING,'rolled-back request did not retry successfully')

# Crash recovery after active-bank flip: committed state is retained and request is only acked.
vm=boot();stage(vm,0,valid);request(vm,1,1,0)
m=288;old_active=state(vm,0)[3];new_active=1-old_active;nb=m+1+3*new_active
cr=dict(vm.stack);cr.update({7:2,11:2,12:0,13:1,14:JobState.PLANNING,15:0,25:m,26:old_active,24:2})
cr[2]=int(cr.get(2,0))+1;cr[nb]=JobState.PLANNING;cr[nb+1]=2;cr[nb+2]=0;cr[m]=new_active
old_qgen=int(cr.get(3,0));rv=boot(cr)
ck(state(rv,0)[:3]==(JobState.PLANNING,2,0),'post-flip crash lost committed state')
ck(int(rv.stack.get(2,1))%2==0 and int(rv.stack.get(3,0))>old_qgen,'post-flip recovery did not republish queue generation')
rv.run(1)
ck(rv.stack.get(8)==2 and state(rv,0)[1]==2,'post-flip recovery replayed an already committed mutation')

if fails:
    print('Generic Job ABI validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generic Job ABI validation: PASS')
print(' - 11-field logical record, four job types and 12-state lifecycle match GENERIC_JOB_ABI_V1')
print(' - 32 crash-safe slots publish through per-slot A/B state banks and queue seqlock/generation')
print(' - optimistic JobGeneration rejects stale updates; terminal jobs are immutable and reap-only')
print(' - pre-flip reflash retries; post-flip reflash retains and acknowledges the committed mutation')
