#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT;fails=[]
families={
 'ControllerPI':('ic10/controller-pi/pi_config_policy_v1_0.ic10','ic10/controller-pi/controller_pi_runtime_v1_1.ic10',2,[255,63,0,0],14),
 'ControllerSequencer':('ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10','ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10',2,[255,1,0,0],9),
 'ControllerPhasePressure':('ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10','ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10',2,[255,1,0,0],9),
 'ControllerPressureDomain':('ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10','ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10',1,[255,0,0,0],8),
 'ControllerPressureTransfer':('ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10','ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10',1,[15,0,0,0],4)}
profiles={p['profile_type']:p for p in json.loads((R/'data/input_profiles.json').read_text())['profiles']}
def num(t,p):
 m=re.search(p,t,re.M);return int(m.group(1)) if m else None
def hashtype(t):
 m=re.search(r'HASH\("(Controller[^"|]+)',t);return m.group(1) if m else None
host=(R/'ic10/controller-config/generic_persistent_config_host_v1_1.ic10').read_text()
for typ in families:
 if typ in host:fails.append('Generic Host special-cases '+typ)
for pat,label in [(r'add sp sp 226','destination-footer invalidation'),(r'push r13','footer schema'),(r'push r15','footer config revision'),(r'push r11','bank revision LAST')]:
 if not re.search(pat,host,re.M):fails.append('Generic Host missing '+label)
for pat,label in [(r'get r15 db 52','replay request generation'),(r'get r0 db 9','recovered config revision'),(r'bne r15 r0 NoReplay','post-commit replay comparison'),(r'poke 53 r15','post-commit replay acknowledgement')]:
 if not re.search(pat,host,re.M):fails.append('Generic Host missing '+label)
for typ,(pn,rn,blocks,masks,fields) in families.items():
 pol=(R/pn).read_text();run=(R/rn).read_text();prof=profiles.get(typ)
 if hashtype(pol)!=typ or hashtype(run)!=typ:fails.append(typ+': Policy/Runtime type mismatch')
 if not prof or prof['schema']!=1 or prof['field_count']!=fields:fails.append(typ+': Input Profile catalog geometry mismatch')
 if num(pol,r'put Host 10 (\d+)')!=blocks:fails.append(pn+': blockCount mismatch')
 active=0
 for i,mask in enumerate(masks):
  if num(pol,rf'put Host {16+i} (\d+)')!=mask:fails.append(f'{pn}: mask{i} mismatch')
  active+=mask.bit_count()
 if active!=fields:fails.append(typ+': mask field count mismatch')
 sig=re.search(r'put Host 12 HASH\("([^"]+)"\)',pol);expected='CFG1|'+typ+'|1|'+str(blocks)+'|'+'|'.join(map(str,masks))
 if not sig or sig.group(1)!=expected:fails.append(pn+': persistence signature mismatch')
# ControllerTest remains available only as a test fixture, outside production catalogs.
test_runtime=R/'tests/ic10/framework_test_controller_v1_0.ic10'
test_policy=R/'tests/ic10/framework_test_config_policy_v1_0.ic10'
test_profile=R/'tests/ic10/framework_test_input_profile_fixture_v1_0.ic10'
for q in (test_runtime,test_policy,test_profile):
 if not q.exists():fails.append('missing test-only ControllerTest fixture: '+str(q.relative_to(R)))
for q in (test_runtime,test_policy):
 if q.exists() and 'HASH("ControllerTest")' not in q.read_text():fails.append(q.name+': ControllerTest identity missing')

# Input metadata is centralized: production must not reintroduce standalone per-family Input Profile programs.
for q in R.glob('*.ic10'):
 text=q.read_text()
 if 'poke 0 31415929' in text and q.name!='ic10/input-profile-catalog/input_profile_view_v5_0.ic10':
  fails.append('standalone production Input Profile program exists: '+q.name)
if fails:
 print('Config contract validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Config contract validation: PASS')
print(' - Generic Persistent Config Host remains family-neutral')
print(' - controller masks/signatures agree with centralized Input Profile metadata')
print(' - no standalone per-family Input Profile ICs remain')
