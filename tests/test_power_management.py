#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from framework.ic10_harness import IC10,Device
from framework.job_abi import JobIntent,JobType
import sys
R=_PROJECT_ROOT;fails=[]
def ck(cond,msg):
 if not cond:fails.append(msg)
# Live POWER producer endpoint.
p=Device(1001,props={'ReferenceId':1001,'PowerPotential':500,'On':1,'Error':0})
vm=IC10((R/'ic10/power-grid/power_producer_endpoint_v1_0.ic10').read_text(),{'d0':p},self_ref=221)
vm.stack.update({16:'PowerPotential',17:400,18:10,19:101,20:2});vm.run(2)
ck(vm.stack.get(5)==400 and vm.stack.get(6)==0 and vm.stack.get(35)==1,'producer capacity publication')
# Consumer desired demand survives physical off; SHED zeros demand.
c=Device(1002,props={'ReferenceId':1002,'On':0})
cv=IC10((R/'ic10/power-grid/power_consumer_endpoint_v1_0.ic10').read_text(),{'d0':c},self_ref=222)
cv.stack.update({16:0,17:120,18:10,19:201,20:900,21:10});cv.run(2)
ck(cv.stack.get(6)==120 and cv.stack.get(8)==1,'consumer desired demand erased by physical off')
cv.stack[50]=2;cv.run(1);ck(cv.stack.get(6)==0,'consumer SHED override did not zero import')
# Battery reserve/target math + off suppression.
b=Device(1003,props={'ReferenceId':1003,'On':1,'Error':0,'Charge':600,'Maximum':1000,'PowerPotential':50,'PowerActual':20})
bv=IC10((R/'ic10/power-grid/power_battery_endpoint_v1_0.ic10').read_text(),{'d0':b},self_ref=223)
bv.stack.update({16:200,17:150,18:.2,19:.8,20:10,21:301,22:500,23:1,50:0,51:0});bv.run(2)
ck(bv.stack.get(5)==150 and bv.stack.get(6)==200,'battery reserve/target capacity math')
b.props['On']=0;bv.run(1);ck(bv.stack.get(5)==0 and bv.stack.get(6)==0,'off battery still advertises capacity')
# Generic Reservation offset regression: endpoint export/import land at Reservation S6/S7.
ep=Device(1100,stack={0:31415949,1:1,2:4,3:'HASH:Power.Electrical',4:3,5:321,6:123,7:0,8:1,9:1001,10:0,11:1,12:4,13:3,35:1,38:10,39:101,40:16},props={'ReferenceId':1100})
rrvm=IC10((R/'ic10/resource-grid-core/resource_reservation_v1_0.ic10').read_text(),{'d0':ep},self_ref=1200);rrvm.run(2)
ck(rrvm.stack.get(6)==321 and rrvm.stack.get(7)==123 and rrvm.stack.get(5)==3,'Reservation POWER capacity offsets wrong')
# Source/Sink selectors must read S6/S7, not role/cross-direction cells.
src=Device(1201,stack={0:31415950,1:1,2:1100,3:4,4:'HASH:Power.Electrical',5:1,6:100,7:0,9:1,12:5,17:0,28:1,30:101,31:16},props={'ReferenceId':1201})
sink=Device(1202,stack={0:31415950,1:1,2:1101,3:4,4:'HASH:Power.Electrical',5:2,6:0,7:80,9:1,12:6,17:0,28:2,30:201,31:14410},props={'ReferenceId':1202})
pdir=Device(1300,stack={0:31415981,1:1,2:0,5:2,7:0,9:'HASH:DirectorySchema.PowerReservation.v1',11:3,12:64,32:1000001,33:101,34:1201,35:3000099,36:201,37:1202},props={'ReferenceId':1300})
plan=Device(1301,stack={24:0},props={'ReferenceId':1301})
sv=IC10((R/'ic10/power-grid/power_source_selector_v1_0.ic10').read_text(),{'d0':pdir,'d1':plan,'x0':src,'x1':sink},self_ref=228)
sv.stack.update({2:0,3:1});sv.run(3);ck(sv.stack.get(5)==1 and sv.stack.get(7)==100,'source selector did not use Reservation S6 export')
kv=IC10((R/'ic10/power-grid/power_sink_selector_v1_0.ic10').read_text(),{'d0':pdir,'x0':src,'x1':sink},self_ref=230)
kv.stack.update({2:0,3:1});kv.run(3);ck(kv.stack.get(5)==1 and kv.stack.get(7)==80,'sink selector did not use Reservation S7 import')
# Transformer overhead link selector.
link=Device(1401,stack={0:31415953,1:1,28:1201,29:1202,30:4,31:'HASH:Power.Electrical',32:2,33:100,8:0,9:1,10:1500,11:0,12:9,13:3,14:5},props={'ReferenceId':1401})
ldir=Device(1400,stack={0:31415981,1:1,2:0,5:1,7:0,9:'HASH:DirectorySchema.ResourceLink.v1',11:1,12:64,32:1401},props={'ReferenceId':1400})
lv=IC10((R/'ic10/power-grid/power_link_selector_v1_0.ic10').read_text(),{'d0':ldir,'x0':link},self_ref=229)
lv.stack.update({2:1201,3:1202,4:80,5:1});lv.run(3);ck(lv.stack.get(7)==1 and lv.stack.get(9)==85,'transformer overhead not charged source-side')
# Live coherent PlanStore BEGIN/ADD/COMMIT.
ps=IC10((R/'ic10/power-grid/power_dispatch_plan_store_v1_0.ic10').read_text(),{},self_ref=227);ps.run(1)
ps.stack.update({12:1,10:1});ps.run(2)
for i,v in enumerate([1401,1201,1202,80,85,5,6,9],16):ps.stack[i]=v
ps.stack.update({12:2,10:2});ps.run(2);ps.stack.update({14:20,15:0,12:3,10:3});ps.run(2)
ck(ps.stack.get(2)%2==0 and ps.stack.get(3)==1 and ps.stack.get(4)==1 and ps.stack.get(32)==1401,'PlanStore coherent transaction')
# Reference dispatch model: critical first, sheddable whole-load, battery charge partial.
def dispatch(gen,batt,critical,shed,charge):
 flows=[]; battery_dir=0; remaining_gen=gen
 # critical then shed; a load can use one source only.
 for name,demand in [('critical',critical),('shed',shed)]:
  if remaining_gen>=demand: flows.append((name,'gen',demand));remaining_gen-=demand;continue
  if batt>=demand: flows.append((name,'battery',demand));batt-=demand;battery_dir=1;continue
 # battery charge only if battery was not discharged.
 charged=0
 if battery_dir==0 and charge>0 and remaining_gen>0:
  charged=min(charge,remaining_gen);flows.append(('charge','gen',charged))
 return flows,charged
f,ch=dispatch(500,200,250,180,100)
ck(('critical','gen',250) in f and ('shed','gen',180) in f and ch==70,'priority/surplus charging model')
f,ch=dispatch(300,200,250,180,100)
ck(('critical','gen',250) in f and ('shed','battery',180) in f and ch==0,'battery discharge/shedding order model')

# Generic Job Selector exact-type mode replaces the duplicate POWER selector and
# preserves cursor fairness across POWER jobs while ignoring other domains.
def boot_job_store():
 vm=IC10((R/'ic10/generic-jobs/generic_job_store_v1_0.ic10').read_text());vm.run(1);return vm
def publish_job(vm,token,slot,intent):
 base=32+8*slot
 for n,v in enumerate([intent.job_type,intent.required_capability,intent.identity,intent.input_count,intent.output_count,intent.requested_quantity,intent.priority],1): vm.stack[base+n]=v
 vm.stack.update({11:1,12:slot,7:token});vm.run(1)
 return int(vm.stack.get(10,0))
js=boot_job_store()
print_id=publish_job(js,1,0,JobIntent(JobType.PRINT,1,7001,1,1,1,999))
power_a=publish_job(js,2,1,JobIntent(JobType.POWER,2,8001,0,0,40,100))
power_b=publish_job(js,3,2,JobIntent(JobType.POWER,3,8002,0,0,50,90))
jsdev=Device(1700,js.stack,{'ReferenceId':1700})
gsel=IC10((R/'ic10/generic-jobs/generic_job_selector_v3_0.ic10').read_text(),{'d0':jsdev},self_ref=1701);gsel.run(1)
gsel.stack.update({2:0,3:1,18:4});gsel.run(1)
ck(gsel.stack.get(7)==power_a and gsel.stack.get(8)==4,'generic selector exact POWER mode selected wrong domain/job')
gsel.stack.update({2:power_a,3:2,18:4});gsel.run(1)
ck(gsel.stack.get(7)==power_b,'generic selector POWER cursor did not advance')
ck(gsel.stack.get(7)!=print_id,'generic selector exact POWER mode leaked PRINT job')

# Missing READY target is retryable WAIT_RESOURCE, while ambiguous/invalid target
# faults the job instead of leaving a high-priority READY job to spin forever.
def prep_transition(resolver_status):
 life=Device(1710,stack={},props={'ReferenceId':1710});resolver=Device(1711,stack={},props={'ReferenceId':1711});apply=Device(1712,stack={},props={'ReferenceId':1712})
 vm=IC10((R/'ic10/power-jobs/power_job_prepare_v1_0.ic10').read_text(),{'d0':life,'d1':resolver,'d2':apply},self_ref=2440);vm.run(1)
 vm.stack.update({14:0,15:77,16:4,17:3,18:100,19:1,8:900,9:11});vm.run(1)
 resolver.stack.update({12:11,13:resolver_status});vm.run(1)
 return vm,life
pv,pl=prep_transition(-2)
ck(pl.stack.get(12)==8 and pl.stack.get(13)==1,'missing POWER target did not request WAIT_RESOURCE')
pv,pl=prep_transition(-3)
ck(pl.stack.get(12)==11 and pl.stack.get(13)==-1,'ambiguous POWER target did not request FAULT')

# Verification wait returns control to scheduler instead of monopolizing one
# worker indefinitely; cursor fairness can then service another POWER job.
life=Device(1720,stack={},props={'ReferenceId':1720});resolver=Device(1721,stack={},props={'ReferenceId':1721});verify=Device(1722,stack={},props={'ReferenceId':1722})
fv=IC10((R/'ic10/power-jobs/power_job_finalize_v1_0.ic10').read_text(),{'d0':life,'d1':resolver,'d2':verify},self_ref=2450);fv.run(1)
fv.stack.update({14:1,15:88,16:5,17:4,18:100,19:1,8:901,9:12});fv.run(1)
resolver.stack.update({12:12,13:1,14:999});fv.run(1)
verify.stack.update({13:12,8:0});fv.run(1)
ck(fv.stack.get(10)==12 and fv.stack.get(11)==0,'POWER finalize wait did not yield pending result to scheduler')

# Lane-D lifecycle client contract with fake successful Gateway response.
gw=Device(1600,stack={65:0,66:0},props={'ReferenceId':1600})
lc=IC10((R/'ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10').read_text(),{'d0':gw},self_ref=243)
lc.stack.update({10:3,11:7,12:5,13:0,14:11});lc.run(2)
# emulate Gateway completion after request publication
ck(gw.stack.get(64)==11 and gw.stack.get(68)==2 and gw.stack.get(70)==7,'lane D request framing')
gw.stack[65]=11;gw.stack[66]=1;lc.run(3)
ck(lc.stack.get(8)==1 and lc.stack.get(9)==8,'lifecycle client did not return expected generation + 1')

# PolicyId resolution scans the POWER Reservation directory snapshot and binds
# exactly one live Reservation through the relocated request/reply cells S8..S15.
res_a=Device(2500,stack={0:31415950,1:1,2:2600,3:4,12:9,17:0,28:2,30:501,31:0},props={'ReferenceId':2500})
res_b=Device(2501,stack={0:31415950,1:1,2:2601,3:4,12:4,17:0,28:3,30:502,31:0},props={'ReferenceId':2501})
pdir2=Device(2400,stack={0:31415981,2:0,5:2,7:0,9:'HASH:DirectorySchema.PowerReservation.v1',32:1000001,33:501,34:2500,35:2000002,36:502,37:2501},props={'ReferenceId':2400})
tr=IC10((R/'ic10/power-jobs/power_policy_target_resolver_v1_0.ic10').read_text(),{'d0':pdir2,'x0':res_a,'x1':res_b},self_ref=2410)
tr.stack.update({10:501,11:1});tr.run(2)
ck(tr.stack.get(13)==1 and tr.stack.get(14)==2500 and tr.stack.get(15)==2600 and tr.stack.get(8)==2 and tr.stack.get(9)==9 and tr.stack.get(12)==1,'policy target resolver did not bind the unique POWER reservation')
pdir2.stack.update({5:3,38:3000003,39:501,40:2501});tr.stack[11]=2;tr.run(1)
ck(tr.stack.get(13)==-3 and tr.stack.get(12)==2,'policy target resolver accepted an ambiguous PolicyId')
pdir2.stack[5]=2;tr.stack.update({10:999,11:3});tr.run(1)
ck(tr.stack.get(13)==-2 and tr.stack.get(12)==3,'policy target resolver resolved an absent PolicyId')

# Policy verification settles or waits on the bound Reservation/Endpoint pair.
vres=Device(2510,stack={0:31415950,1:1,2:2610,3:4,6:0,7:0,12:5,28:2},props={'ReferenceId':2510})
vep=Device(2610,stack={50:2,51:3},props={'ReferenceId':2610})
pvv=IC10((R/'ic10/power-jobs/power_job_policy_verify_v1_0.ic10').read_text(),{'x0':vres,'x1':vep},self_ref=2420)
pvv.stack.update({9:2510,10:2,11:3,12:1});pvv.run(2)
ck(pvv.stack.get(8)==1 and pvv.stack.get(13)==1,'policy verify rejected a settled consumer policy')
bres=Device(2511,stack={0:31415950,1:1,2:2611,3:4,6:4,7:0,12:6,28:3},props={'ReferenceId':2511})
bep=Device(2611,stack={50:5,51:3},props={'ReferenceId':2611})
pvv2=IC10((R/'ic10/power-jobs/power_job_policy_verify_v1_0.ic10').read_text(),{'x0':bres,'x1':bep},self_ref=2421)
pvv2.stack.update({9:2511,10:5,11:3,12:1});pvv2.run(2)
ck(pvv2.stack.get(8)==0 and pvv2.stack.get(13)==1,'policy verify settled a battery with outstanding export')
vres.stack[0]=1;pvv.stack[12]=2;pvv.run(1)
ck(pvv.stack.get(8)==-1 and pvv.stack.get(13)==2,'policy verify accepted a non-Reservation target')
if fails:
 print('Power management protocol: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Power management protocol: PASS')
print(' - live producer/consumer/battery endpoints and Reservation mirror')
print(' - live source/sink/link selectors use correct generic offsets')
print(' - live PlanStore coherent transaction and transformer overhead')
print(' - priority/load-shed/battery-charge reference model')
print(' - POWER Job Gateway lane-D generation contract')
print(' - live policy target resolver binds unique Reservations and rejects ambiguity')
print(' - live policy verify settles consumer/battery modes through the bound pair')
