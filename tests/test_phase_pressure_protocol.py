from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
import json,math,subprocess,hashlib,sys
R=_PROJECT_ROOT
D=json.loads((R/'resource_profiles.json').read_text())
fails=[]
phase=[p for p in D['profiles'] if p['profile_kind']==1]
if len(phase)!=9: fails.append(f'expected 9 phase-medium resource profiles, got {len(phase)}')
# Unified catalog generation must be reproducible.
before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [*R.glob('*_resource_profile_loader_*_v4_0.ic10'),R/'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10',R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10']}
subprocess.run([sys.executable,str(R/'generate_resource_profiles.py')],check=True,cwd=R,stdout=subprocess.DEVNULL)
after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [*R.glob('*_resource_profile_loader_*_v4_0.ic10'),R/'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10',R/'ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10',R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10']}
if before!=after: fails.append('resource profile catalog is not reproducible from resource_profiles.json')
for p in phase:
    q=p['params']; A,B,minP,maxP,minT,maxT,ratio,purity,latent=q
    if p['resource_class']!=1 or p['unit']!=1 or p['profile_schema']!=2: fails.append(p['slug']+': phase type metadata mismatch')
    if not isinstance(ratio,str) or not ratio.startswith('Ratio'): fails.append(p['slug']+': missing gas-ratio LogicType')
    if not (0 <= purity <= 1): fails.append(p['slug']+': purity outside 0..1')
    if latent <= 0: fails.append(p['slug']+': latent heat must be positive')
    T=(minT+maxT)/2; P=A*(T**B)
    if not math.isfinite(P): fails.append(p['slug']+': non-finite in-range phase boundary')
view=(R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10').read_text()
for n in ('poke 0 31415963','get r10 db 2','get r11 db 3','get r12 d0 11','getd r15 r12 7','getd r14 r2 17','getd r1 r2 7','poke 5 0','poke 4 1'):
    if n not in view: fails.append('Resource Profile View missing '+n)
r=(R/'ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10').read_text()
for n in ('poke 97 2','get r9 d1 5','bne r0 31415963 ProfileBad','get r0 d1 11','bne r0 1 ProfileBad','get r10 d1 13','get r15 d1 18','get r0 d1 5','bne r0 r9 Loop','poke 115 0','poke 115 r0'):
    if n not in r: fails.append('PhasePressure runtime missing '+n)
if fails:
 print('Phase-pressure/resource-profile model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Phase-pressure/resource-profile model: PASS')
print(' - 9 phase-medium records share the unified resource profile source/catalog')
print(' - catalog store/loaders reproduce exactly from resource_profiles.json')
print(' - phase records retain thermodynamic, latent-heat, gas-ratio, and purity metadata')
print(' - PhasePressure consumes coherent Resource Profile View generation and publishes telemetry ABI2')
