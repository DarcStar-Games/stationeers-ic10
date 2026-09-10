#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,math,subprocess,hashlib,sys
from framework.ic10_harness import Device,IC10
R=_PROJECT_ROOT
D=json.loads((R/'data/resource_profiles.json').read_text())
fails=[]
phase=[p for p in D['profiles'] if p['profile_kind']==1]
if len(phase)!=9: fails.append(f'expected 9 phase-medium resource profiles, got {len(phase)}')
# Unified catalog generation must be reproducible. Glob under ic10/, where the
# loaders live: anchored at the repository root this matched none of them, so
# every generated loader sat outside the byte-stability check.
generated=[*sorted(R.glob('ic10/*/resource_profile_loader_*_v4_0.ic10')),R/'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10',R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10']
if len(generated)<5: fails.append('resource profile loaders are missing from the reproducibility check')
def digests(): return {q.name:hashlib.sha256(q.read_bytes()).hexdigest() for q in generated}
before=digests()
subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_resource_profiles.py')],check=True,cwd=R,stdout=subprocess.DEVNULL)
if before!=digests(): fails.append('resource profile catalog is not reproducible from resource_profiles.json')
for p in phase:
    q=p['params']; A,B,minP,maxP,minT,maxT,ratio,purity,latent=q
    if p['resource_class']!=1 or p['unit']!=1 or p['profile_schema']!=2: fails.append(p['slug']+': phase type metadata mismatch')
    if not isinstance(ratio,str) or not ratio.startswith('Ratio'): fails.append(p['slug']+': missing gas-ratio LogicType')
    if not (0 <= purity <= 1): fails.append(p['slug']+': purity outside 0..1')
    if latent <= 0: fails.append(p['slug']+': latent heat must be positive')
    T=(minT+maxT)/2; P=A*(T**B)
    if not math.isfinite(P): fails.append(p['slug']+': non-finite in-range phase boundary')
view=(R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10').read_text()
for n in ('poke 0 HASH("ResourceProfileView.v1")','get r10 db 26','get r11 db 27','get r12 d0 11','getd r15 r12 22','getd r14 r2 17','getd r1 r2 24','poke 29 0','poke 28 1'):
    if n not in view: fails.append('Resource Profile View missing '+n)
RT=(R/'ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10').read_text()
# The nine config fields load into r1..r9, so r9 is DirectWrite; the Profile View's S29 snapshot
# lives in ra, which is free between the Load loop and the Temperature read, and both write gates
# test r9 (issue #184).
for n in ('poke 97 2','move r0 1\nmove ra 96\nLoad:\nget rr0 d2 ra','ble r0 9 Load','get ra d1 29\nblez ra ProfileBad','bne r0 HASH("ResourceProfileView.v1") ProfileBad','get r0 d1 11','bne r0 1 ProfileBad','get r10 d1 13','get r15 d1 18','get r0 d1 29\nbne r0 ra Loop','beqz r1 Commit\nbeqz r9 Commit\nbdnvs d0 r8 OutputBad\ns d0 r8 r0','poke 105 ra\nbeqz r9 Commit\nbdnvs d0 r8 Commit\ns d0 r8 r0','poke 115 0','poke 115 r0'):
    if n not in RT: fails.append('PhasePressure runtime missing '+n.replace('\n',' / '))
# Runtime publish and fault paths in the harness. Host: Enabled, Mode, factors 0.9/2.0, bounds
# 50..5000, standby 300, output Setting, DirectWrite. Profile View: unit curve (A=B=1), pressure
# window 10..4000, liquid window 200..500 K. Chamber at 100 kPa and 300 K, so the boundary is
# 300 kPa: EVAPORATE requests 270, CONDENSE 600, HOLD and every operational fault the standby 300.
MEDIUM='HASH:Water'
def host(enabled=1,mode=1,direct=1,gen=4): return Device(601,stack={0:'HASH:GenericPersistentConfigHost.v1',8:1,51:gen,12:'HASH:CFG1|ControllerPhasePressure|1|2|255|1|0|0',96:enabled,97:mode,98:0.9,99:2.0,100:50,101:5000,102:300,103:'Setting',104:direct},props={'ReferenceId':601})
def profile(gen=9): return Device(602,stack={0:'HASH:ResourceProfileView.v1',9:MEDIUM,11:1,13:1.0,14:1.0,15:10,16:4000,17:200,18:500,29:gen},props={'ReferenceId':602})
def chamber(): return Device(603,props={'ReferenceId':603,'Pressure':100.0,'Temperature':300.0,'Setting':-1.0})
class Torn(dict):
    """A stack whose S29 moves on every read, so the recheck never matches the snapshot."""
    def get(self,k,default=None):
        v=dict.get(self,k,default)
        if k==29: dict.__setitem__(self,29,v+1)
        return v
def tick(name,expect,written,act=lambda s:None,good=False,**kw):
    """Boot; optionally one good tick with the chamber's Setting reset after it; apply act to the
    screws; run one tick. Checks (S103,S105), whether d0.Setting was written and with what, the
    tick counters, and on a valid request the boundary, mode, medium, and that r9 holds the flag."""
    s={'d0':chamber(),'d1':profile(),'d2':host(**kw)}; d=s['d0']; vm=IC10(RT,s,self_ref=600); vm.run(1)
    if good: vm.run(1); d.props['Setting']=-1.0
    act(s); vm.run(1); ticks=2 if good else 1; direct=s['d2'].stack[104] if 'd2' in s else kw.get('direct',1)
    got=(vm.stack.get(103),vm.stack.get(105)); wrote=d.props.get('Setting',-1.0)
    if got!=expect: fails.append(f'{name}: published (S103,S105) {got}, expected {expect}')
    if written and wrote!=expect[0]: fails.append(f'{name}: d0.Setting {wrote}, expected {expect[0]}')
    if not written and wrote!=-1.0: fails.append(f'{name}: d0.Setting written {wrote}, expected untouched')
    if (vm.stack.get(119),vm.stack.get(115))!=(ticks,ticks): fails.append(f'{name}: (S119,S115) {(vm.stack.get(119),vm.stack.get(115))}, expected {(ticks,ticks)}')
    if expect[1]!=-4 and vm.reg['r9']!=direct: fails.append(f'{name}: r9 {vm.reg["r9"]}, expected DirectWrite {direct}')
    if expect[1] in (1,2) and (vm.stack.get(102),vm.stack.get(104),vm.stack.get(106))!=(300.0,expect[1],MEDIUM): fails.append(f'{name}: (S102,S104,S106) {(vm.stack.get(102),vm.stack.get(104),vm.stack.get(106))}')
    return vm
def lose(port): return lambda s:s.pop(port)
def cell(port,k,v):
    def act(s): s[port].stack[k]=v
    return act
def prop(k,v=None):
    def act(s):
        if v is None: s['d0'].props.pop(k)
        else: s['d0'].props[k]=v
    return act
def reload(cells):
    def act(s): s['d2'].stack.update(cells); s['d2'].stack[51]=5
    return act
for dw in (1,0):
    w=bool(dw); t=f' DirectWrite={dw}'
    def T(name,expect,written,act=lambda s:None,good=False,**kw): return tick(name+t,expect,written,act,good,direct=dw,**kw)
    T('EVAPORATE',(270.0,1),w)
    T('CONDENSE',(600.0,2),w,mode=2)
    T('HOLD',(300,0),w,mode=0)
    T('disabled',(300,0),False,enabled=0)
    T('temperature above the liquid window',(300,-7),w,prop('Temperature',600.0))
    T('NaN pressure',(300,-5),w,prop('Pressure',math.nan))
    T('chamber without Pressure',(300,-1),w,prop('Pressure'))
    T('chamber absent',(300,-1),False,lose('d0'))
    T('output property missing',(270.0,-2 if dw else 1),False,prop('Setting'))
    T('Profile View absent at boot',(300,-6),w,lose('d1'))
    T('Profile View not ready at boot',(300,-6),w,cell('d1',29,0))
    T('Profile View wrong identity',(300,-6),w,cell('d1',0,'HASH:other'))
    T('Profile View not a phase medium',(300,-6),w,cell('d1',11,2))
    T('Profile View lost after a good tick',(300,-6),w,lose('d1'),good=True)
    T('Profile View not ready after a good tick',(300,-6),w,cell('d1',29,0),good=True)
    T('Config Host absent',(None,-4),False,lose('d2'))
    T('Config Host not ready',(None,-4),False,cell('d2',8,0))
    T('Config Host wrong signature',(None,-4),False,cell('d2',12,'HASH:other'))
    T('Config Host lost after a good tick',(270.0,-4),False,lose('d2'),good=True)
    T('second good tick',(270.0,1),w,good=True)
    T('reload to CONDENSE',(600.0,2),w,reload({97:2}),good=True)
tick('reload flips DirectWrite off',(270.0,1),False,reload({104:0}),good=True)
tick('reload flips DirectWrite on',(270.0,1),True,reload({104:1}),good=True,direct=0)
# A torn Profile View publishes nothing: the recheck returns to Loop before any telemetry or write.
s={'d0':chamber(),'d1':profile(),'d2':host()}; s['d1'].stack=Torn(s['d1'].stack); vm=IC10(RT,s,self_ref=600); vm.run(2)
if (vm.stack.get(103),vm.stack.get(105),vm.stack.get(119),vm.stack.get(115),s['d0'].props['Setting'])!=(None,None,0,0,-1.0): fails.append(f'torn Profile View: published {(vm.stack.get(103),vm.stack.get(105),vm.stack.get(119),vm.stack.get(115),s["d0"].props["Setting"])}, expected nothing')
if fails:
 print('Phase-pressure/resource-profile model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Phase-pressure/resource-profile model: PASS')
print(' - 9 phase-medium records share the unified resource profile source/catalog')
print(' - catalog store/loaders reproduce exactly from resource_profiles.json')
print(' - phase records retain thermodynamic, latent-heat, gas-ratio, and purity metadata')
print(' - PhasePressure consumes coherent Resource Profile View generation and publishes telemetry ABI2')
print(' - every runtime publish and fault path reports the documented status and writes d0 only under DirectWrite=1')
