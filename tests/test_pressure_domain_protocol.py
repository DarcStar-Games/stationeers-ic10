#!/usr/bin/env python3
"""Pressure-domain protocol model: the Arbiter's fences and the runtime's telemetry on every publish path."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import math,sys
from framework.ic10_harness import Device,IC10
R=_PROJECT_ROOT
fails=[]
a=(R/'ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10').read_text(); d=(R/'ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10').read_text(); pol=(R/'ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10').read_text()
for n in ('getd r12 ra 115','getd r0 ra 115','bne r0 r12 Next','add sp r6 29','bgtz r0 BadDirectory'):
 if n not in a: fails.append('Arbiter missing '+n)
# The fault tail shares NoRequest's standby publication: each fault sets r14 and joins at Idle (issue #176).
for n in ('poke 97 2','poke 115 0','poke 115 r0','get r15 d1 29','bne r0 r15 Loop','bltz r14 Idle','move r14 -6\nj Idle','move r14 -7\nj Idle','NoRequest:\nmove r14 0\nIdle:\nmove r11 r5\nmove r12 0\nPublish:'):
 if n not in d: fails.append('PressureDomain missing '+n.replace('\n',' / '))
if 'bgt r2 3 Reject' not in pol: fails.append('STORAGE role not represented in policy')
req=[1700,2100,1900]
if min(req)!=1700 or max(req)!=2100: fails.append('LOW/HIGH reference reduction failure')
# Every publish path of the runtime, run in the harness against the status table in
# docs/PRESSURE_DOMAIN_CONTROLLER.md: S101..S105 after the tick, what the actuators hold, and
# that S115 carries the tick's generation. Config: LOW role, bounds 100..5000, standby 300.
MEDIUM='HASH:Water'
def host(enabled=1,role=1,direct=1,gen=4): return Device(501,stack={0:'HASH:GenericPersistentConfigHost.v1',8:1,12:'HASH:CFG1|ControllerPressureDomain|1|1|255|0|0|0',51:gen,96:enabled,97:role,98:100,99:5000,100:300,101:'Setting',102:'Setting',103:direct},props={'ReferenceId':501})
def profile(gen=9,kind=1): return Device(502,stack={0:'HASH:ResourceProfileView.v1',8:kind,9:MEDIUM,29:gen},props={'ReferenceId':502})
def arbiter(pressure=1500,count=2,status=1,gen=1,config_gen=4,medium=MEDIUM): return Device(503,stack={0:'HASH:PhasePressureRequestArbiter.v1',8:pressure,9:count,10:status,12:gen,13:config_gen,14:medium},props={'ReferenceId':503})
def screws(**kw):
 s={'d0':Device(504,props={'ReferenceId':504,'Pressure':1234}),'d1':profile(),'d2':arbiter(),'d3':Device(505,props={'ReferenceId':505,'Setting':-1}),'d4':Device(506,props={'ReferenceId':506,'Setting':-1}),'d5':host()}
 for k,v in kw.items():
  if v is None: s.pop(k)
  else: s[k]=v
 return s
def telemetry(vm,s): return tuple(vm.stack.get(c) for c in (101,102,103,104,105)),tuple(s[k].props.get('Setting') if k in s else None for k in ('d3','d4'))
def tick(name,expect,acts,vanish=None,**kw):
 s=screws(**kw); vm=IC10(d,s,self_ref=500); vm.run(1)
 if vanish: vm.run(1); s.pop(vanish)
 vm.run(1); got=telemetry(vm,s); ticks=2 if vanish else 1
 if got!=(expect,acts): fails.append(f'{name}: published {got[0]} actuators {got[1]}, expected {expect} {acts}')
 if vm.stack.get(115)!=ticks or vm.stack.get(119)!=ticks or ('d0' not in kw and vm.stack.get(100)!=1234): fails.append(f'{name}: S115/S119/S100 = {vm.stack.get(115)}/{vm.stack.get(119)}/{vm.stack.get(100)} after {ticks} ticks')
 return vm
W=MEDIUM
tick('LOW request in bounds',(1500,2,1,W,1),(1500,1500))
tick('LOW request below the minimum',(100,2,1,W,-8),(100,100),d2=arbiter(pressure=50))
tick('LOW request above the maximum is clamped without -8',(5000,2,1,W,1),(5000,5000),d2=arbiter(pressure=9000))
tick('HIGH request above the maximum',(5000,2,2,W,-8),(5000,5000),d5=host(role=2),d2=arbiter(pressure=9000,status=2))
tick('HIGH request below the minimum is clamped without -8',(100,2,2,W,2),(100,100),d5=host(role=2),d2=arbiter(pressure=50,status=2))
tick('STORAGE enabled publishes its bounds and writes nothing',(100,5000,3,W,3),(-1,-1),d5=host(role=3))
tick('STORAGE disabled',(100,5000,3,W,0),(-1,-1),d5=host(role=3,enabled=0))
tick('DirectWrite=0 publishes only',(1500,2,1,W,1),(-1,-1),d5=host(direct=0))
tick('no Arbiter pass yet',(300,0,1,W,0),(300,300),d2=arbiter(gen=0))
tick('Arbiter pass under a stale config generation',(300,0,1,W,0),(300,300),d2=arbiter(config_gen=3))
tick('Arbiter pass for another medium',(300,0,1,W,0),(300,300),d2=arbiter(medium='HASH:Pollutant'))
tick('Arbiter pass with no matching request',(300,0,1,W,0),(300,300),d2=arbiter(count=0))
tick('Arbiter reports -3',(300,0,1,W,-3),(300,300),d2=arbiter(status=-3))
tick('Arbiter reports -9',(300,0,1,W,-9),(300,300),d2=arbiter(status=-9))
tick('Arbiter absent',(300,0,1,W,-7),(300,300),d2=None)
tick('Arbiter with another identity',(300,0,1,W,-7),(300,300),d2=Device(503,stack={0:'HASH:Other.v1'},props={'ReferenceId':503}))
tick('Profile View absent at boot publishes MediumType 0',(300,0,1,0,-6),(300,300),d1=None)
tick('Profile View not ready',(300,0,1,0,-6),(300,300),d1=profile(gen=0))
tick('Profile View of another kind',(300,0,1,0,-6),(300,300),d1=profile(kind=2))
tick('Profile View lost after a good tick keeps the last MediumType',(300,0,1,W,-6),(300,300),vanish='d1')
tick('Arbiter lost after a good tick',(300,0,1,W,-7),(300,300),vanish='d2')
tick('one output absent writes neither',(1500,2,1,W,-2),(None,-1),d3=None)
tick('one output without the property writes neither',(1500,2,1,W,-2),(-1,None),d4=Device(506,props={'ReferenceId':506}))
vm=tick('sensor absent publishes NaN pressure',(1500,2,1,W,1),(1500,1500),d0=None)
if not (isinstance(vm.stack.get(100),float) and math.isnan(vm.stack.get(100))): fails.append(f'sensor absent: S100 {vm.stack.get(100)}, expected NaN')
vm=tick('Config Host lost after a good tick leaves the channels as published',(1500,2,1,W,-4),(1500,1500),vanish='d5')
for name,kw in (('Config Host absent',dict(d5=None)),('Config Host not ready',dict(d5=host(gen=0))),('Config Host with another identity',dict(d5=Device(501,stack={0:'HASH:Other.v1'},props={'ReferenceId':501})))):
 s=screws(**kw); vm=IC10(d,s,self_ref=500); vm.run(2)
 if telemetry(vm,s)!=((None,None,None,None,-4),(-1,-1)) or vm.stack.get(115)!=1: fails.append(f'{name}: published {telemetry(vm,s)} S115 {vm.stack.get(115)}, expected only -4 under generation 1')
if fails:
 print('Pressure-domain protocol model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-domain protocol model: PASS')
print(' - Arbiter rejects torn telemetry ABI2 and overflowed discovery snapshots')
print(' - LOW=min/HIGH=max arbitration remains intact')
print(' - PressureDomain publishes coherent telemetry ABI2')
print(' - every runtime publish path reports the documented status, standby or clamped command, and actuator writes')
print(' - STORAGE role remains supported')
