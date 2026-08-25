from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from dataclasses import dataclass
import sys
from framework.ic10_harness import IC10,Device,run_round_robin
R=_PROJECT_ROOT; fails=[]
def ck(v,m):
 if not v:fails.append(m)
def src(n):return (R/n).read_text()

# Pure bounded-planning model checks.
@dataclass
class Plan:
 parent:int; child:int; resource:int; required:float; baseline:float; future:float; fp1:int=0; fp2:int=0

def shareable(plans,resource,deficit,active):
 by={}
 for p in plans:
  if p.resource!=resource or p.child not in active:continue
  d=by.setdefault(p.child,[p.future,0]); d[1]+=max(0,p.required-p.baseline)
 for child,(future,claimed) in by.items():
  if future-claimed>=deficit:return child
 return None
p1=Plan(1,50,101,8,0,10)
ck(shareable([p1],101,2,{50})==50,'unclaimed future surplus was not reusable')
ck(shareable([p1],101,3,{50}) is None,'future output was overbooked across parents')
p2=Plan(2,50,101,2,0,10)
ck(shareable([p1,p2],101,1,{50}) is None,'aggregate shared claims can exceed child future output')
ck(shareable([p1],101,1,set()) is None,'COMPLETE/non-active child was reused as future work')

def depth_ok(edges,current,producer_job,job_identity):
 parents=[p for p,c in edges if c==current]
 if job_identity.get(current)==producer_job:return False,'cycle'
 for p in parents:
  if job_identity.get(p)==producer_job:return False,'cycle'
  if any(c==p for _,c in edges):return False,'depth'
 return True,'ok'
ids={1:(1,100),2:(1,200),3:(1,300),4:(1,400)}
ck(depth_ok([(1,2)],2,ids[3],ids)==(True,'ok'),'depth-2 edge was rejected')
ck(depth_ok([(1,2),(2,3)],3,ids[4],ids)==(False,'depth'),'third dependency edge was accepted')
ck(depth_ok([(1,2)],2,ids[1],ids)==(False,'cycle'),'A->B->A cycle was accepted')

def completed_decision(oldfp,newfp,ready,ambiguous=False):
 if ready:return 'ready'
 if ambiguous:return 'probe'
 return 'wait_publish' if oldfp==newfp else 'replan'
ck(completed_decision((7,9),(7,9),False)=='wait_publish','unchanged completion publication did not wait')
ck(completed_decision((7,9),(8,10),False)=='replan','changed short inventory did not replan')
ck(completed_decision((7,9),(8,10),True)=='ready','visible child output did not release parent')

# Live Plan Store: upsert, lookup, clear, and interrupted odd-sequence recovery.
ps=IC10(src('ic10/dependency-planning/dependency_plan_store_v2_0.ic10'));ps.run(1)
ps.stack.update({12:2,13:77,14:88,15:101,16:12,17:4,18:10,19:111,20:222,9:1});ps.run(1)
ck(ps.stack.get(10)==1 and ps.stack.get(11)==1,'Plan Store upsert failed')
ck(ps.stack.get(128)==77 and ps.stack.get(129)==88 and ps.stack.get(135)==222,'Plan Store committed record geometry wrong')
ck(int(ps.stack.get(40,0))%2==0,'Plan Store mutation left odd sequence')
ps.stack.update({12:1,13:77,9:2});ps.run(1)
ck(ps.stack.get(10)==2 and ps.stack.get(32)==77 and ps.stack.get(39)==222,'Plan Store lookup did not return 8-cell record')
ps.stack.update({12:3,13:77,9:3});ps.run(1);ck(ps.stack.get(128)==0,'Plan Store clear did not invalidate ParentJobId commit marker')
re=IC10(src('ic10/dependency-planning/dependency_plan_store_v2_0.ic10'));re.stack.update({0:31416007,1:2,40:5,128:0,129:999});re.run(1)
ck(int(re.stack.get(40,0))%2==0 and re.stack.get(128)==0,'Plan Store reflash did not normalize interrupted odd sequence')

# Live Job Store + sole executor + 3-lane Gateway child creation.
def boot_store():
 v=IC10(src('ic10/generic-jobs/generic_job_store_v1_0.ic10'));v.run(1);return v
def store_req(v,t,cmd,slot,gen=0,state=0,err=0):
 v.stack.update({11:cmd,12:slot,13:gen,14:state,15:err,7:t});v.run(1);return int(v.stack.get(9,0)),int(v.stack.get(10,0))
def state(v,slot):
 m=288+7*slot;a=int(v.stack.get(m,0));b=m+1+3*a
 return int(v.stack.get(b,0)),int(v.stack.get(b+1,0))
store=boot_store()
# Parent intent then publish + PLANNING.
for i,v in enumerate([1,1,500,1,1,1,20],1):store.stack[32+i]=v
st,parent=store_req(store,1,1,0);ck(st==1,'parent publish failed')
st0,g0=state(store,0);store_req(store,2,2,0,g0,2);pst,pgen=state(store,0);ck(pst==2,'parent did not enter PLANNING')
sdev=Device(100,store.stack,{'ReferenceId':100})
exe=IC10(src('ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10'),{'d0':sdev},self_ref=101);exe.run(1)
edev=Device(101,exe.stack,{'ReferenceId':101})
gw=IC10(src('ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10'),{'d0':edev},self_ref=102);gw.run(1)
# Child intent; executor chooses free slot atomically.
gw.stack.update({53:parent,54:pgen,55:0,56:1,57:1,58:600,59:1,60:1,61:2,62:21,63:-1,48:10})
run_round_robin([gw,exe,store],40)
ck(gw.stack.get(49)==10 and gw.stack.get(50)==1,'Gateway/Executor child creation did not acknowledge')
child=int(gw.stack.get(51,0));slot=int(gw.stack.get(52,-1));ck(child>parent and slot==1,'atomic child allocation returned wrong JobId/slot')
# Same token after Gateway same-stack reflash must not allocate another child.
before=int(store.stack.get(23,0));gw2=IC10(src('ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10'),{'d0':edev},self_ref=102);gw2.stack.update(gw.stack);gw2.run(1);run_round_robin([gw2,exe,store],10)
ck(int(store.stack.get(23,0))==before,'same-stack Gateway replay duplicated committed child')
# Parent-generation guard: stale creator request fails before publication.
gw2.stack.update({53:parent,54:pgen-1,55:0,56:1,57:1,58:601,59:1,60:1,61:1,62:21,63:-1,48:11})
run_round_robin([gw2,exe,store],30)
ck(gw2.stack.get(49)==11 and gw2.stack.get(50)!=1,'stale parent generation created a child')

if fails:
 print('Dependency planning: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Dependency planning: PASS')
print(' - future-output sharing accounts for aggregate claims and never reuses completed children')
print(' - bounded depth/cycle and completed-child inventory liveness semantics are covered')
print(' - Plan Store 8-cell commit marker survives interrupted odd-sequence recovery')
print(' - four-lane Gateway + sole Store executor atomically guards parent generation and allocates child slots')
