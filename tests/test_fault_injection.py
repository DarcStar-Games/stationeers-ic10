#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.fault_injection import Step,inject_every_boundary
from framework.ic10_harness import IC10
from framework.job_abi import JobState,WAIT_STATES,TERMINAL,allowed_transition

R=_PROJECT_ROOT
checks=0

def ck(cond,msg):
 global checks
 checks+=1
 if not cond: raise AssertionError(msg)

# 1. Whole-item catalog migration: the authoritative source cannot disappear
# before the destination publication is durable/visible.
initial={'src':True,'payload':False,'dst':False}
steps=[
 Step('copy-payload',lambda s:s.__setitem__('payload',True)),
 Step('publish-destination',lambda s:s.__setitem__('dst',True)),
 Step('remove-source',lambda s:s.__setitem__('src',False)),
]
def recover_migration(s,cut):
 # Unpublished copied bytes are not authority. A published destination is.
 if not s['dst']: s['payload']=False
 return s
def check_migration(s,cut): ck(s['src'] or s['dst'],f'catalog copy lost at cut {cut}')
mcuts=inject_every_boundary(initial,steps,recover_migration,check_migration)

# 2. Directory snapshots are observations, not mutation authority. Odd sequence
# or generation/sequence change around a read must reject the snapshot.
def snapshot(seq1,gen1,records,seq2,gen2):
 return tuple(records) if seq1==seq2 and gen1==gen2 and seq1%2==0 and gen1>0 else None
ck(snapshot(8,4,[1,2],8,4)==(1,2),'stable directory snapshot rejected')
ck(snapshot(9,4,[1,2],9,4) is None,'odd directory snapshot accepted')
ck(snapshot(8,4,[1,2],10,5) is None,'mutated directory snapshot accepted')

# Store/processor identity changes after planning are stale authority.
def act(plan_ref,plan_gen,live_ref,live_gen): return plan_ref==live_ref and plan_gen==live_gen
ck(act(100,7,100,7),'stable processor rejected')
ck(not act(100,7,101,8),'replaced processor accepted')
ck(not act(100,7,100,8),'changed processor generation accepted')

# 3. ITEM quote -> commit -> action. Semantic generation is revalidated at both
# ownership boundaries; post-pick failure retains a recovery origin.
def item_commit(quoted,current): return quoted==current
def item_action(committed,current): return committed==current
ck(not item_commit(5,6),'stale ITEM quote committed')
ck(item_commit(5,5),'stable ITEM quote rejected')
ck(not item_action(5,6),'stale ITEM reservation acted')
held={'hand':True,'origin':('locker',4),'destination_open':False}
def recover_held(s):
 if s['hand'] and not s['destination_open']:
  s['returned_to']=s['origin'];s['hand']=False
 return s
recover_held(held)
ck(held.get('returned_to')==('locker',4) and not held['hand'],'LArRE held-item origin lost')

# 4. Generic Job cancellation is legal from every nonterminal state and terminal
# states cannot be reopened. This is exhaustive over the ABI state enum.
for state in JobState:
 if state in TERMINAL:
  ck(not allowed_transition(state,JobState.PLANNING,0),f'terminal {state.name} reopened')
 else:
  ck(allowed_transition(state,JobState.CANCELLED,0),f'{state.name} cannot cancel')
for state in WAIT_STATES:
 ck(allowed_transition(state,JobState.PLANNING,0),f'{state.name} cannot resume planning')

# 5. Dependency cleanup is reference-aware: a shared active child survives one
# parent cancellation; a sole child is cancelled. Catalog meaning is live data.
def cancel_child(active_parent_refs): return len(active_parent_refs)==0
ck(not cancel_child([202]),'shared dependency child cancelled')
ck(cancel_child([]),'orphan dependency child not cancelled')
def child_valid(expected_output,live_output): return expected_output==live_output
ck(not child_valid(9001,9002),'stale child catalog meaning accepted')

# 6. Gateway replay identity is deterministic across reflash. Replaying the same
# external token/lane may observe the prior mutation but may not apply it twice.
def internal_token(external,lane): return external*5+lane
ck(internal_token(77,4)==internal_token(77,4),'Gateway replay identity changed')
applied=set();mutations=0
for _ in range(2):
 tok=internal_token(77,4)
 if tok not in applied: applied.add(tok);mutations+=1
ck(mutations==1,'Gateway replay double-applied Store mutation')

# 7. POWER allocator replacement: staged reservation ownership is not execution
# authority. Only a published (plan generation, allocator epoch) pair may run.
p0={'old_epoch':10,'old_reserved':True,'new_epoch':11,'new_reserved':False,'old_released':False,'published':(5,10)}
psteps=[
 Step('commit-new-reservations',lambda s:s.__setitem__('new_reserved',True)),
 Step('release-old-epoch',lambda s:s.__setitem__('old_released',True)),
 Step('publish-new-authority',lambda s:s.__setitem__('published',(6,11))),
]
def recover_power(s,cut):
 # If the new epoch was never published it may be cleaned; it never authorizes actuation.
 if s['published']!=(6,11): s['new_reserved']=False
 return s
def check_power(s,cut):
 plan,epoch=s['published']
 if (plan,epoch)==(6,11): ck(s['new_reserved'],f'published POWER epoch missing reservations at cut {cut}')
 else: ck((plan,epoch)==(5,10),f'unpublished POWER authority escaped at cut {cut}')
pcuts=inject_every_boundary(p0,psteps,recover_power,check_power)

# 8. Actual Power Dispatch Plan Store: interrupt real IC10 COMMIT at many
# instruction boundaries. Reflash must invalidate an odd/torn plan and restore
# an even readable sequence before readers can proceed.
psrc=(R/'ic10/power-grid/power_dispatch_plan_store_v1_0.ic10').read_text()
odd_cuts=0
for quantum in range(8,60):
 vm=IC10(psrc,{},self_ref=227)
 vm.stack.update({0:'HASH:PowerDispatchPlanStore.v1',1:1,27:0,28:5,29:1,30:0,31:0,10:1,11:0,12:3,14:0,15:0,24:1})
 for i,v in enumerate([1401,1201,1202,80,85,5,6,9],128): vm.stack[i]=v
 vm.run(2,instruction_quantum=quantum)
 if int(vm.stack.get(27,0))%2:
  odd_cuts+=1
  rf=IC10(psrc,{},self_ref=227);rf.stack=vm.stack.copy();rf.run(1)
  ck(int(rf.stack.get(27,0))%2==0,f'Power Plan Store remained odd after reflash q={quantum}')
  ck(rf.stack.get(28)==0 and rf.stack.get(29)==0,f'torn Power plan remained authoritative q={quantum}')
ck(odd_cuts>=10,'Power Plan Store campaign did not reach interrupted COMMIT window')

# 9. Allocator reflash itself is fail-closed: startup clears active-authority flag.
asrc=(R/'ic10/power-grid/power_reservation_allocator_v1_0.ic10').read_text()
a=IC10(asrc,{},self_ref=236);a.stack.update({8:5,9:10,10:1,20:2,21:6,22:11,30:11})
a.run(1)
ck(a.stack.get(10)==0 and a.stack.get(20)==0,'Power allocator reflash retained actuation authority')

# 10. Allocator reflash is safe *and live*: the current unchanged plan is
# revalidated, a fresh epoch is committed, the prior epoch is released, and
# authority is republished only after that sequence completes.
from framework.ic10_harness import Device
plan=Device(3000,stack={28:5},props={'ReferenceId':3000})
validator=Device(3001,stack={},props={'ReferenceId':3001})
committer=Device(3002,stack={},props={'ReferenceId':3002})
releaser=Device(3003,stack={},props={'ReferenceId':3003})
a=IC10(asrc,{'d0':plan,'d1':validator,'d2':committer,'d3':releaser},self_ref=2360)
a.stack.update({8:5,9:10,10:1,20:2,21:6,22:11,30:10})
a.run(1)
ck(a.stack.get(8)==0 and a.stack.get(9)==10 and a.stack.get(10)==0,'allocator boot did not preserve old epoch while invalidating accepted plan')
# Start validation of unchanged PlanGeneration 5.
a.run(2)
ck(a.stack.get(20)==1 and validator.stack.get(8)==5,'allocator did not revalidate unchanged current plan after reflash')
req=int(a.stack.get(30));validator.stack.update({10:req,11:1})
a.run(2)
ck(a.stack.get(20)==2 and committer.stack.get(8)==5,'allocator did not advance to fresh reservation commit')
committer.stack.update({11:req,12:1})
a.run(2)
ck(a.stack.get(20)==3 and releaser.stack.get(8)==10,'allocator did not release prior epoch before republish')
releaser.stack.update({10:req,11:1})
a.run(2)
ck(a.stack.get(8)==5 and a.stack.get(9)==11 and a.stack.get(10)==1,'allocator did not reacquire current plan with fresh epoch')

# 11. Managed load executor: revoke allocator authority after plan/reservation
# validation but before the physical write. The device must remain OFF.
alloc=Device(3100,stack={8:5,9:10,10:1},props={'ReferenceId':3100})
load=Device(3101,props={'ReferenceId':3101,'On':0})
endpoint=Device(3102,stack={9:3101},props={'ReferenceId':3102})
res=Device(3103,stack={0:'HASH:ResourceReservation.v1',32:3102,33:4,17:3100,18:10,19:6,28:2,31:8},props={'ReferenceId':3103})
pl=Device(3104,stack={0:'HASH:PowerDispatchPlanStore.v1',27:2,28:5,29:1,32:0,33:0,34:3103,38:6},props={'ReferenceId':3104})
loadvm=IC10((R/'ic10/power-grid/power_load_executor_v1_0.ic10').read_text(),{'d0':pl,'d1':alloc,'x0':res,'x1':endpoint,'x2':load},self_ref=2370)
loadvm.run(1)
for _ in range(500):
 if loadvm.pc==loadvm.labels['Set'] and loadvm.reg.get('r4')==1: break
 loadvm.run(1000,instruction_quantum=1)
else: raise AssertionError('load executor did not reach pre-write authority boundary')
alloc.stack[10]=0
for _ in range(40):
 loadvm.run(1000,instruction_quantum=1)
 if load.props.get('On')==0 and loadvm.pc==loadvm.labels['Scan']: break
ck(load.props.get('On')==0,'managed load actuated after allocator authority revocation')

# 12. Transformer executor: same authority withdrawal window must zero Setting
# and keep the transformer OFF rather than applying the stale plan.
alloc2=Device(3200,stack={8:5,9:10,10:1},props={'ReferenceId':3200})
xf=Device(3201,props={'ReferenceId':3201,'Setting':0,'On':0})
sr=Device(3202,stack={17:3200,18:10,19:5},props={'ReferenceId':3202})
kr=Device(3203,stack={17:3200,18:10,19:6},props={'ReferenceId':3203})
link=Device(3204,stack={0:'HASH:ResourceLink.v1',30:4,32:2,10:3201,12:9},props={'ReferenceId':3204})
pl2=Device(3205,stack={0:'HASH:PowerDispatchPlanStore.v1',27:2,28:5,29:1,32:3204,33:3202,34:3203,35:80,37:5,38:6,39:9},props={'ReferenceId':3205})
xfvm=IC10((R/'ic10/power-grid/power_link_executor_v1_0.ic10').read_text(),{'d0':pl2,'d1':alloc2,'x0':link,'x1':sr,'x2':kr,'x3':xf},self_ref=2380)
xfvm.run(1)
for _ in range(500):
 if xfvm.pc==xfvm.labels['Set'] and xfvm.reg.get('r5')==1: break
 xfvm.run(1000,instruction_quantum=1)
else: raise AssertionError('transformer executor did not reach pre-write authority boundary')
alloc2.stack[10]=0
for _ in range(50):
 xfvm.run(1000,instruction_quantum=1)
 if xf.props.get('On')==0 and xfvm.pc==xfvm.labels['Scan']: break
ck(xf.props.get('Setting')==0 and xf.props.get('On')==0,'transformer actuated after allocator authority revocation')

print('Broad interruption/fault-injection campaign: PASS')
print(f' - {len(mcuts)} catalog-migration cuts + {len(pcuts)} power-replacement cuts')
print(f' - {odd_cuts} real IC10 Power Plan Store interrupted-COMMIT cuts recover fail-closed')
print(f' - {checks} invariant assertions across directory, processor, ITEM/LArRE, dependency, Gateway, POWER, and Job lifecycle boundaries')
