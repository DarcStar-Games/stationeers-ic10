#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from dataclasses import dataclass
import sys
from framework.async_request import posting_token
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
re=IC10(src('ic10/dependency-planning/dependency_plan_store_v2_0.ic10'));re.stack.update({0:'HASH:DependencyPlanStore.v2',1:2,40:5,128:0,129:999});re.run(1)
ck(int(re.stack.get(40,0))%2==0 and re.stack.get(128)==0,'Plan Store reflash did not normalize interrupted odd sequence')

# Live Job Store + sole executor + Gateway child creation.
def boot_store():
 v=IC10(src('ic10/generic-jobs/generic_job_store_v1_0.ic10'));v.run(1);return v
def store_req(v,t,cmd,slot,gen=0,state=0,err=0):
 v.stack.update({11:cmd,12:slot,13:gen,14:state,15:err,19:t});v.run(1);return int(v.stack.get(9,0)),int(v.stack.get(10,0))
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
gw=IC10(src('ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10'),{'d0':edev},self_ref=102);gw.run(1)
# Lane C may create children only; a negative ParentJobId cannot acquire root authority.
before=int(store.stack.get(23,0))
gw.stack.update({53:-1,54:0,55:0,56:1,57:1,58:599,59:1,60:1,61:1,62:21,63:-1,48:9})
run_round_robin([gw,exe,store],30)
ck(gw.stack.get(49)==9 and gw.stack.get(50)!=1 and int(store.stack.get(23,0))==before,
   'Gateway lane C accepted a root create sentinel')
# Child intent; executor chooses free slot atomically.
gw.stack.update({53:parent,54:pgen,55:0,56:1,57:1,58:600,59:1,60:1,61:2,62:21,63:-1,48:10})
run_round_robin([gw,exe,store],40)
ck(gw.stack.get(49)==10 and gw.stack.get(50)==1,'Gateway/Executor child creation did not acknowledge')
child=int(gw.stack.get(51,0));slot=int(gw.stack.get(52,-1));ck(child>parent and slot==1,'atomic child allocation returned wrong JobId/slot')
# Same token after Gateway same-stack reflash must not allocate another child.
before=int(store.stack.get(23,0));gw2=IC10(src('ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10'),{'d0':edev},self_ref=102);gw2.stack.update(gw.stack);gw2.run(1);run_round_robin([gw2,exe,store],10)
ck(int(store.stack.get(23,0))==before,'same-stack Gateway replay duplicated committed child')
# Parent-generation guard: stale creator request fails before publication.
gw2.stack.update({53:parent,54:pgen-1,55:0,56:1,57:1,58:601,59:1,60:1,61:1,62:21,63:-1,48:11})
run_round_robin([gw2,exe,store],30)
ck(gw2.stack.get(49)==11 and gw2.stack.get(50)!=1,'stale parent generation created a child')
# The Gateway is the sole mutation path, so it must name its Executor rather than
# post commands to whatever occupies d0.
before=int(store.stack.get(23,0))
stranger=Device(103,{0:'HASH:GenericJobStore.v1'},{'ReferenceId':103})
gw3=IC10(src('ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10'),{'d0':stranger},self_ref=104);gw3.run(1)
gw3.stack.update({53:parent,54:pgen,55:0,56:1,57:1,58:602,59:1,60:1,61:2,62:21,63:-1,48:12})
run_round_robin([gw3,exe,store],20)
ck(sorted(stranger.stack)==[0] and int(store.stack.get(23,0))==before,'Gateway posted a command to a device that is not its Executor')
# Lane A is the Scheduler's: request payload S11..S15 with the nonce at S19, and the
# reply lands where the Scheduler waits for it -- acknowledgement S8, status S9,
# second word S10 -- leaving the payload it just copied untouched. ABI5 briefly put
# the lane one cell high, which acknowledged into S9 and overwrote S11.
pst,pgen=state(store,0);ck(pst==2,'parent left PLANNING before the lane A edge')
gw.stack.update({11:2,12:0,13:pgen,14:3,15:0,19:13})
run_round_robin([gw,exe,store],40)
ck(gw.stack.get(8)==13 and gw.stack.get(9)==1,'Gateway lane A did not acknowledge on S8 with status on S9')
ck(gw.stack.get(11)==2 and gw.stack.get(24)==0,'Gateway lane A reply overwrote the request payload or left the lane busy')
ck(state(store,0)[0]==3,'lane A lifecycle edge did not reach the Store')
# Reflashing with a command in flight must not settle it against whatever d0 now is:
# the stranger's S8 is allowed to collide with the pending sequence.
other=Device(105,{0:'HASH:GenericSnapshotDirectoryHost.v1',8:7,9:1,10:55},{'ReferenceId':105})
resume=IC10(src('ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10'),{'d0':other},self_ref=106)
resume.stack.update({0:'HASH:GenericJobStoreCommandExecutor.v1',1:1,2:0,31:7,32:99,34:3,23:99,24:0})
resume.run(4)
ck(resume.stack.get(31)==7 and resume.stack.get(24)==0,'reflashed Executor settled a pending command against a stranger')
# The Planner reaches its Existing controller from the plan path and the cleanup path;
# a cleanup request must not post into a d1 that is not that controller.
notctl=Device(107,{0:'HASH:DependencyPlanStore.v2'},{'ReferenceId':107})
planner=IC10(src('ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10'),
 {'d0':Device(108,{},{'ReferenceId':108}),'d1':notctl,'d2':Device(109,{},{'ReferenceId':109})},self_ref=110)
planner.stack.update({25:5,26:0,24:7});planner.run(4)
ck(sorted(notctl.stack)==[0],'Planner cleanup posted to a d1 that is not its Existing controller')

# The Selector publishes at most six legs, and Preflight bounds the count it
# publishes before folding legs into its fingerprints: a count of seven would
# read S50 and S52, past the quote table the Selector's contract declares, and
# fingerprint whatever sat there as a seventh leg.
def without_guard(path,*lines):
 text=src(path)
 for line in lines:
  ck(line+'\n' in text,f'{path} lost its count guard `{line}`');text=text.replace(line+'\n','')
 return text
def preflight_status(source):
 requirement=IC10("Loop:\nyield\nget r15 db 19\nget r0 db 20\nbeq r15 r0 Loop\npoke 21 1\npoke 23 1\npoke 26 777\npoke 27 5\npoke 20 r15\nj Loop\n");requirement.run(1)
 selector=IC10('poke 0 HASH("ItemResourceReservationSelector.v1")\nLoop:\nyield\nget r15 db 15\nget r0 db 16\nbeq r15 r0 Loop\npoke 8 -2\npoke 9 3\npoke 10 7\npoke 16 r15\nj Loop\n');selector.run(1)
 for leg in range(7):selector.stack[32+3*leg]=601+leg;selector.stack[34+3*leg]=1
 legs={f'x{leg}':Device(601+leg,stack={11:0},props={'ReferenceId':601+leg}) for leg in range(7)}
 vm=IC10(source,{'d0':Device(600,requirement.stack),'d1':Device(599,selector.stack),**legs},self_ref=598)
 vm.run(1);vm.stack.update({15:41,16:1,17:1,18:9});run_round_robin([vm,requirement,selector],40)
 return vm.stack.get(20)
preflight='ic10/dependency-planning/job_inventory_preflight_v1_0.ic10'
ck(preflight_status(without_guard(preflight,'blt r12 0 Bad','bgt r12 6 Bad'))==3,
   'witness: the unguarded Preflight did not fingerprint a seventh leg as a deficit quote')
ck(preflight_status(src(preflight))==-1,'Preflight folded a leg past the six-leg quote table into its fingerprints')

# A Plan Store change after the Monitor has answered restarts the Ancestry Guard's scan,
# and the restart posts the same parent again. Each posting under one request carries a
# counter, so the Monitor latches the repost instead of leaving the Guard to consume the
# earlier reply; the 512th posting under one request fails the request instead (#148).
# Reflashed after the Monitor's reply, the Guard continues its count from S18 (#182).
def guard_restarts(restarts,reflash=False):
 plan=Device(700,{0:'HASH:DependencyPlanStore.v2',40:0,128:9,129:5,130:101,131:4,132:0,133:6})
 monitor=IC10('poke 0 HASH("GenericJobMonitor.v1")\nLoop:\nyield\nget r15 db 14\nget r0 db 15\nbeq r15 r0 Loop\nget r0 db 30\nadd r0 r0 1\npoke 30 r0\npoke 16 1\npoke 18 0\npoke 19 0\npoke 15 r15\nj Loop\n',self_ref=701);monitor.run(1)
 guard=IC10(src(GUARD),{'d0':plan,'d1':Device(701,monitor.stack)},self_ref=702)
 guard.run(1);guard.stack.update({10:5,11:1,12:100,13:2,14:200,15:9})
 for posted in range(1,restarts+1):
  for _ in range(60):
   run_round_robin([guard,monitor],1)
   if monitor.stack.get(30)==posted:break
  else:ck(False,f'the Ancestry Guard never reached posting {posted}')
  plan.stack[40]+=2
 if reflash:
  for _ in range(60):
   run_round_robin([guard,monitor],1)
   if monitor.stack.get(30)==restarts+1:break
  fresh=IC10(src(GUARD),guard.screws,self_ref=702);fresh.stack=guard.stack;fresh.run(1);guard=fresh
 run_round_robin([guard,monitor],80)
 return guard.stack.get(17),guard.stack.get(16),int(monitor.stack.get(30,0)),monitor.stack.get(14),guard.stack.get(18)
GUARD='ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10'
ck(guard_restarts(0)==(1,9,1,posting_token(9,1),0),'an unrestarted Ancestry Guard scan did not post its first token and answer Good')
ck(guard_restarts(1)==(1,9,2,posting_token(9,2),0),"the Monitor did not latch the Ancestry Guard's posting after the restart")
ck(guard_restarts(511)==(-1,9,511,posting_token(9,511),0),'the 512th posting under one Ancestry Guard request did not fail the request')
ck(guard_restarts(0,reflash=True)==(1,9,2,posting_token(9,2),0),"the Monitor did not latch the posting of an Ancestry Guard reflashed mid-request")
ck(guard_restarts(1,reflash=True)==(1,9,3,posting_token(9,3),0),'an Ancestry Guard reflashed after a restart did not continue its count from S18')

# The Monitor answers Priority, State, JobGeneration at S21..S23, where the New controller,
# Child Validity, and the Cancellation Guard read them. It used to publish State, Generation,
# ErrorStatus there, so a PLANNING parent was planned only when its Generation happened to be
# 2, and the Builder was handed the parent's State as its Priority and its ErrorStatus as the
# generation the Gateway checks (#193). The parent here has waited once, so its Generation is
# 4 and nothing lines up by accident.
def plan_new(parent_edges):
 st=boot_store()
 for i,v in enumerate([1,1,500,1,1,1,20],1):st.stack[32+i]=v
 _,parent=store_req(st,1,1,0)
 for t,new in enumerate(parent_edges,2):
  _,g=state(st,0);store_req(st,t,2,0,g,new)
 monitor=IC10(src('ic10/dependency-planning/generic_job_monitor_v1_0.ic10'),{'d0':Device(800,st.stack)},self_ref=801);monitor.run(1)
 preflight=IC10('poke 0 HASH("JobInventoryPreflight.v1")\nLoop:\nyield\nget r15 db 18\nget r0 db 19\nbeq r15 r0 Loop\npoke 20 3\npoke 22 101\npoke 23 6\npoke 24 2\npoke 25 1\npoke 26 11\npoke 27 12\npoke 19 r15\nj Loop\n',self_ref=802);preflight.run(1)
 builder=IC10('poke 0 HASH("DependencyPlanBuilder.v2")\nLoop:\nyield\nget r15 db 30\nget r0 db 31\nbeq r15 r0 Loop\npoke 32 1\npoke 33 55\npoke 34 8\npoke 31 r15\nj Loop\n',self_ref=803);builder.run(1)
 ctl=IC10(src('ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10'),
  {'d0':Device(802,preflight.stack),'d1':Device(803,builder.stack),'d2':Device(801,monitor.stack)},self_ref=804)
 ctl.run(1);ctl.stack.update({20:parent,21:3})
 run_round_robin([ctl,monitor,preflight,builder],40)
 return ctl,builder,monitor,parent,state(st,0)
ctl,builder,monitor,parent,(pst,pgen)=plan_new([2,8,2])
ck((pst,pgen)==(2,4),'the parent did not return to PLANNING at Generation 4')
ck((monitor.stack.get(16),monitor.stack.get(21),monitor.stack.get(22),monitor.stack.get(23))==(1,20,2,4),
   'the Monitor did not publish Priority, State, JobGeneration at S21..S23')
ck(ctl.stack.get(22)==3 and ctl.stack.get(23)==6 and ctl.stack.get(31)==55 and ctl.stack.get(32)==101,
   'the New controller did not plan a PLANNING parent over the real Monitor')
ck(tuple(builder.stack.get(c) for c in range(19,25))==(parent,0,4,1,500,20),
   "the Builder was not handed the parent's JobId, slot, JobGeneration, JobType, Identity, and Priority")
ctl,builder,monitor,parent,(pst,pgen)=plan_new([2,3])
ck(pst==3 and ctl.stack.get(22)==3 and ctl.stack.get(23)==-1 and 30 not in builder.stack,
   'a RESERVING parent was planned over the real Monitor')
if fails:
 print('Dependency planning: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Dependency planning: PASS')
print(' - future-output sharing accounts for aggregate claims and never reuses completed children')
print(' - bounded depth/cycle and completed-child inventory liveness semantics are covered')
print(' - Plan Store 8-cell commit marker survives interrupted odd-sequence recovery')
print(' - six-lane Gateway + sole Store executor atomically guards parent generation and allocates child slots')
print(' - the Gateway writes nothing at all to a d0 that is not its Store Command Executor')
print(' - Gateway lane A acknowledges on S8 and replies on S9..S10 without touching the request payload')
print(' - a reflashed Executor re-checks the Store identity before resuming a pending command')
print(' - the Planner names its Existing controller on the cleanup path as well as the plan path')
print(' - Preflight bounds the Selector leg count at six before walking the quote table')
print(' - a restarted Ancestry Guard scan posts again under a new token the Monitor latches; the 512th posting fails the request')
print(' - an Ancestry Guard reflashed mid-request continues its posting count from S18 and the Monitor latches the next posting')
print(' - the real Monitor hands the New controller a PLANNING parent with its Priority and JobGeneration where the controller reads them')
