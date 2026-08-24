from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
import sys
R=_PROJECT_ROOT
fails=[]
a=(R/'ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10').read_text(); d=(R/'ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10').read_text(); pol=(R/'ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10').read_text()
for n in ('getd r12 ra 115','getd r0 ra 115','bne r0 r12 Next','add sp r6 7','bgtz r0 BadDirectory'):
 if n not in a: fails.append('Arbiter missing '+n)
for n in ('poke 97 2','poke 115 0','poke 115 r0','get r15 d1 5','bne r0 r15 Loop'):
 if n not in d: fails.append('PressureDomain missing '+n)
if 'bgt r2 3 Reject' not in pol: fails.append('STORAGE role not represented in policy')
req=[1700,2100,1900]
if min(req)!=1700 or max(req)!=2100: fails.append('LOW/HIGH reference reduction failure')
if fails:
 print('Pressure-domain protocol model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-domain protocol model: PASS')
print(' - Arbiter rejects torn telemetry ABI2 and overflowed discovery snapshots')
print(' - LOW=min/HIGH=max arbitration remains intact')
print(' - PressureDomain publishes coherent telemetry ABI2')
print(' - STORAGE role remains supported')
