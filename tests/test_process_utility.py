#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from framework.ic10_harness import IC10,Device
import math,sys
R=_PROJECT_ROOT;fails=[]
def ck(c,m):
 if not c:fails.append(m)
def close(a,b,t=1e-5):return abs(a-b)<=t
H=lambda s:'HASH:'+s
# Furnace transform conditions become a coherent cross-domain utility request.
view=Device(100,stack={0:31415952,1:4,74:7,64:23500,65:24000,66:600,67:100000,68:H('AlloyInconel'),69:1},props={'ReferenceId':100})
furnace=Device(101,props={'ReferenceId':101,'PrefabHash':H('StructureAdvancedFurnace'),'Pressure':20000,'Temperature':500,'Power':1,'Error':0,'Maximum':100,'SettingInput':0,'SettingOutput':0})
freq=IC10((R/'ic10/process-furnace/furnace_process_condition_request_v1_0.ic10').read_text(),{'d0':view,'d1':furnace},self_ref=247)
freq.stack.update({16:H('Fuel.H2O2'),17:1,18:1});freq.run(2)
ck(freq.stack.get(10)==1 and freq.stack.get(12)==1,'furnace condition request not active/coherent')
ck(freq.stack.get(8)==3,'furnace P/T deficit mask must report pressure+temperature')
ck([freq.stack.get(i) for i in range(24,28)]==[23500,24000,600,100000],'furnace condition bounds not copied from Transform Profile')
ck(freq.stack.get(23)==H('Fuel.H2O2') and freq.stack.get(9)==H('AlloyInconel'),'furnace utility identity mismatch')
furnace.props.update({'Pressure':23750,'Temperature':700});freq.run(1);ck(freq.stack.get(8)==0,'ready furnace still reports unmet utility condition')
# Process target is projected into the existing PressureDomain ABI rather than a parallel pressure model.
cond=Device(102,stack=freq.stack,props={'ReferenceId':102})
pdom=IC10((R/'ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10').read_text(),{'d0':cond,'d1':furnace},self_ref=248);pdom.run(2)
ck(pdom.stack.get(96)==27182818 and pdom.stack.get(97)==2 and pdom.stack.get(99)==H('ControllerPressureDomain'),'process pressure projection does not reuse PressureDomain ABI2')
ck(pdom.stack.get(101)==23500 and pdom.stack.get(102)==24000 and pdom.stack.get(103)==3 and pdom.stack.get(104)==H('Fuel.H2O2') and pdom.stack.get(105)==3,'process PressureDomain bounds/medium/status mismatch')
# Embedded Advanced Furnace pump acts as an ordinary PressureTransfer under GrantGuard authority.
src=Device(201,stack={0:31415936,1:1,4:1,5:H('Fuel.H2O2'),6:100,7:0,8:.1,9:1,11:1},props={'ReferenceId':201})
sink=Device(202,stack={0:31415936,1:1,4:3,5:H('Fuel.H2O2'),6:0,7:100,8:.1,9:1,11:1},props={'ReferenceId':202})
guard=Device(203,stack={0:31415948,1:1,2:100,4:1,6:249,7:1},props={'ReferenceId':203})
tr=IC10((R/'ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10').read_text(),{'d0':src,'d1':sink,'d2':furnace,'d3':guard},self_ref=249)
tr.stack.update({16:1,17:1,18:0,19:.1,20:100});tr.run(2)
ck(tr.stack.get(99)==H('ControllerPressureTransfer') and tr.stack.get(103)==1,'embedded furnace pump not exposed as active PressureTransfer')
ck(furnace.props.get('SettingInput',0)>0,'Grant-authorized furnace inlet pump did not actuate')
guard.stack[4]=0;tr.run(1);ck(furnace.props.get('SettingInput')==0,'withdrawn PressureGrid grant did not safe-off embedded furnace pump')
# Mixture profile purity checks two components under the existing PurityGuard ABI.
prof=Device(301,stack={0:31415963,1:1,28:1,29:3,8:1,9:H('Fuel.H2O2'),10:1,11:5,12:1,13:'RatioVolatiles',14:2/3,15:'RatioOxygen',16:1/3,17:.005,18:1,19:5000,20:12805,21:1},props={'ReferenceId':301})
mix=Device(302,props={'ReferenceId':302,'TotalMoles':10,'Temperature':300,'RatioVolatiles':2/3,'RatioOxygen':1/3})
pg=IC10((R/'ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10').read_text(),{'d0':mix,'d1':prof},self_ref=250);pg.run(2)
ck(pg.stack.get(0)==31415947 and pg.stack.get(5)==1 and pg.stack.get(2)==H('Fuel.H2O2'),'two-component mixture did not reuse PurityGuard ABI1')
mix.props['RatioVolatiles']=.60;mix.props['RatioOxygen']=.40;pg.run(1);ck(pg.stack.get(5)==-4,'off-ratio fuel mix not rejected')
# Composition mixer compensates for unequal source temperatures.
in1=Device(311,props={'ReferenceId':311,'Temperature':400,'RatioVolatiles':1.0})
in2=Device(312,props={'ReferenceId':312,'Temperature':300,'RatioOxygen':1.0})
out=Device(313,props={'ReferenceId':313,'TotalMoles':0,'Pressure':0,'RatioVolatiles':0,'RatioOxygen':0})
mixd=Device(315,stack={0:31416048,1:1,23:H('Fuel.H2O2'),24:100,10:1,11:1,12:1},props={'ReferenceId':315})
mixer=Device(314,props={'ReferenceId':314,'Setting':0,'On':0})
mc=IC10((R/'ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10').read_text(),{'d0':in1,'d1':in2,'d2':out,'d3':mixer,'d4':prof,'d5':mixd},self_ref=251);mc.run(2)
expected=((2/3)*400)/(((1/3)*300)+((2/3)*400))*100
ck(close(mixer.props.get('Setting'),expected,1e-4) and mixer.props.get('On')==1,'temperature-corrected fuel mixer setting wrong')
out.props.update({'TotalMoles':5,'Pressure':50,'RatioVolatiles':2/3,'RatioOxygen':1/3});mc.run(1);ck(mixer.props.get('On')==1 and mc.stack.get(8)==2,'fuel mixer stopped before demanded mixture pressure was available')
out.props['Pressure']=120;mc.run(1);ck(mixer.props.get('On')==0 and mc.stack.get(8)==1,'fuel mixer did not stop after target composition+pressure became visible')
# Thermal mixer uses the process temperature window while preserving pressure routing as a separate authority.
hot=Device(321,props={'ReferenceId':321,'Temperature':1000});cold=Device(322,props={'ReferenceId':322,'Temperature':300});tout=Device(323,props={'ReferenceId':323,'Temperature':500,'Pressure':100});tmix=Device(324,props={'ReferenceId':324,'Setting':0,'On':0})
treq=Device(325,stack={0:31416048,1:1,24:500,26:600,27:700,10:1,11:2,12:1},props={'ReferenceId':325})
tm=IC10((R/'ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10').read_text(),{'d0':hot,'d1':cold,'d2':tout,'d3':tmix,'d4':treq},self_ref=252);tm.run(2)
ck(tmix.props.get('On')==1 and 0<=tmix.props.get('Setting',-1)<=100 and close(tm.stack.get(10),650),'thermal mixer did not target midpoint of bounded process window')
tout.props['Temperature']=650;tm.run(1);ck(tmix.props.get('On')==1 and tm.stack.get(8)==2,'thermal mixer stopped before demanded conditioned-gas pressure')
tout.props['Pressure']=600;tm.run(1);ck(tmix.props.get('On')==0 and tm.stack.get(8)==1,'thermal mixer did not stop at process temperature+pressure window')
# POWER shortage -> fuel-pressure request -> GFG start; shortage removal shuts it down.
gfg=Device(401,props={'ReferenceId':401,'PrefabHash':H('StructureGasGenerator'),'Pressure':.05,'Temperature':300,'Error':0,'On':0})
plan=Device(402,stack={0:31416028,1:1,2:2,5:5000,6:0},props={'ReferenceId':402})
ambient=Device(403,props={'ReferenceId':403,'Pressure':100,'Temperature':300})
guard2=Device(404,stack={5:1,7:2},props={'ReferenceId':404})
gc=IC10((R/'ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10').read_text(),{'d0':gfg,'d1':plan,'d2':ambient,'d3':guard2},self_ref=253)
gc.stack.update({16:H('Fuel.H2O2'),17:.1,18:1,19:1000,20:1});gc.run(2)
ck(gc.stack.get(10)==1 and gc.stack.get(21)==2 and gfg.props.get('On')==0,'GFG shortage did not request fuel while remaining safely off')
ck(gc.stack.get(23)==H('Fuel.H2O2') and gc.stack.get(24)==.1 and gc.stack.get(25)==1,'GFG fuel PressureDomain request wrong')
# The GFG ProcessCondition can directly drive prepared-fuel generation; mixing continues until its demanded pressure is available.
gd=Device(405,stack=gc.stack,props={'ReferenceId':405});fuelout=Device(406,props={'ReferenceId':406,'TotalMoles':1,'Pressure':0,'RatioVolatiles':2/3,'RatioOxygen':1/3});gmix=Device(407,props={'ReferenceId':407,'Setting':0,'On':0})
gmc=IC10((R/'ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10').read_text(),{'d0':in1,'d1':in2,'d2':fuelout,'d3':gmix,'d4':prof,'d5':gd},self_ref=2511);gmc.run(2);ck(gmix.props.get('On')==1,'GFG fuel demand did not activate prepared-mixture generation')
fuelout.props['Pressure']=.2;gmc.run(1);ck(gmix.props.get('On')==0 and gmc.stack.get(8)==1,'prepared-mixture generator did not satisfy GFG pressure demand')
gfg.props['Pressure']=.5;gc.run(1);ck(gfg.props.get('On')==1 and gc.stack.get(21)==1,'GFG did not start after fuel+ambient readiness')
plan.stack.update({2:4,5:0,6:0});gc.run(1);ck(gfg.props.get('On')==0 and gc.stack.get(10)==0,'GFG did not stop when POWER shortage cleared')
# Adversarial stale-authority cuts: mutate authority after initial observation but before final physical write.
def to_pc(vm,target,limit=400):
 for _ in range(limit):
  if vm.pc==target:return True
  vm.run(1,instruction_quantum=1)
 return vm.pc==target
# Embedded pump: withdraw GrantGuard immediately before the final guard re-fence.
af=Device(501,props={'ReferenceId':501,'PrefabHash':H('StructureAdvancedFurnace'),'Power':1,'Error':0,'Maximum':100,'SettingInput':0,'SettingOutput':0})
asrc=Device(502,stack=dict(src.stack),props={'ReferenceId':502}); asrc.stack[4]=1;asrc.stack[5]=H('Fuel.H2O2');asrc.stack[6]=100;asrc.stack[8]=.1;asrc.stack[9]=1;asrc.stack[11]=1
asink=Device(503,stack=dict(sink.stack),props={'ReferenceId':503}); asink.stack[4]=3;asink.stack[5]=H('Fuel.H2O2');asink.stack[7]=100;asink.stack[8]=.1;asink.stack[9]=1;asink.stack[11]=1
ag=Device(504,stack={0:31415948,1:1,2:100,4:1,6:549,7:1},props={'ReferenceId':504})
at=IC10((R/'ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10').read_text(),{'d0':asrc,'d1':asink,'d2':af,'d3':ag},self_ref=549);at.stack.update({16:1,17:1,18:0,19:.1,20:100});at.run(1)
ck(to_pc(at,87),'could not reach embedded-pump final authority cut');ag.stack[4]=0;at.run(1)
ck(af.props.get('SettingInput')==0,'embedded furnace pump actuated after final-cut GrantGuard withdrawal')
# Composition mixer: change ProcessCondition generation just before its final demand fence.
miout=Device(511,props={'ReferenceId':511,'TotalMoles':0,'Pressure':0,'RatioVolatiles':0,'RatioOxygen':0});mid=Device(512,stack={0:31416048,1:1,23:H('Fuel.H2O2'),24:100,10:1,11:1,12:1},props={'ReferenceId':512});midev=Device(513,props={'ReferenceId':513,'Setting':0,'On':0})
mi=IC10((R/'ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10').read_text(),{'d0':in1,'d1':in2,'d2':miout,'d3':midev,'d4':prof,'d5':mid},self_ref=551);mi.run(1)
ck(to_pc(mi,88),'could not reach composition-mixer final demand cut');mid.stack[11]=2;mi.run(1)
ck(midev.props.get('On')==0,'composition mixer actuated on stale ProcessCondition generation')
# Thermal mixer: same stale ProcessCondition cut.
thout=Device(521,props={'ReferenceId':521,'Temperature':400,'Pressure':0});thdev=Device(522,props={'ReferenceId':522,'Setting':0,'On':0});threq=Device(523,stack={0:31416048,1:1,24:500,26:600,27:700,10:1,11:1,12:1},props={'ReferenceId':523})
th=IC10((R/'ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10').read_text(),{'d0':hot,'d1':cold,'d2':thout,'d3':thdev,'d4':threq},self_ref=552);th.run(1)
ck(to_pc(th,54),'could not reach thermal-mixer final demand cut');threq.stack[11]=2;th.run(1)
ck(thdev.props.get('On')==0,'thermal mixer actuated on stale ProcessCondition generation')
# GFG: replace PowerPlan sequence immediately before final plan/mixture re-fence.
gf=Device(531,props={'ReferenceId':531,'PrefabHash':H('StructureGasGenerator'),'Pressure':.5,'Temperature':300,'Error':0,'On':0});pl=Device(532,stack={0:31416028,1:1,2:2,5:5000,6:0},props={'ReferenceId':532});amb=Device(533,props={'ReferenceId':533,'Pressure':100,'Temperature':300});mg=Device(534,stack={5:1,7:2},props={'ReferenceId':534})
gv=IC10((R/'ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10').read_text(),{'d0':gf,'d1':pl,'d2':amb,'d3':mg},self_ref=553);gv.stack.update({16:H('Fuel.H2O2'),17:.1,18:1,19:1000,20:1});gv.run(1)
ck(to_pc(gv,57),'could not reach GFG final PowerPlan cut');pl.stack.update({2:4,5:0,6:0});gv.run(1)
ck(gf.props.get('On')==0,'GFG started from stale/replaced PowerPlan shortage')
if fails:
 print('Cross-domain process utility protocol: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Cross-domain process utility protocol: PASS')
print(' - transform P/T bounds become coherent ProcessCondition requests')
print(' - furnace chambers/pumps reuse PressureDomain, PressureTransfer and GrantGuard authorities')
print(' - H2/O2 mixture generation is temperature-corrected and purity-gated through Resource Profiles')
print(' - hot/cold gas blending targets furnace temperature windows without bypassing PressureGrid')
print(' - POWER shortage drives fuel pressure demand and GFG startup, then shuts down when shortage clears')
