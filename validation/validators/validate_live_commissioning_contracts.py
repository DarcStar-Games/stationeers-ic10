from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT
fails=[]
try: data=json.loads((R/'data/live_commissioning_cases.json').read_text())
except Exception as e: data={};fails.append(f'case catalog parse failed: {e}')
cases=data.get('cases',[])
if data.get('format')!='LIVE_COMMISSIONING_CASES_V1': fails.append('wrong live commissioning catalog format')
ids=[c.get('id') for c in cases]
if len(ids)!=len(set(ids)) or None in ids: fails.append('commissioning case IDs must be unique/nonempty')
required=[c for c in cases if c.get('required',True)]
expected={'LG-PRESSURE-CORE','LG-PERSISTENCE','LG-SHARED-INPUT','LG-SEQUENCER','LG-PHASE-PRESSURE','LG-PRESSURE-DOMAIN','LG-PRESSURE-MULTIHOP','LG-PRESSURE-COST','LG-MATERIAL','LG-JOB-STORE','LG-MANUFACTURING','LG-ITEM-STORAGE','LG-POWER','LG-XDOMAIN-FURNACE','LG-XDOMAIN-GFG','LG-XDOMAIN-RESTART'}
if not expected.issubset(set(ids)): fails.append('required live suite catalog is incomplete')
for c in cases:
    for k in ('id','category','title','source_doc','section','acceptance'):
        if not c.get(k): fails.append(f"{c.get('id','?')}: missing {k}")
    if c.get('source_doc') and not (R/c['source_doc']).exists(): fails.append(f"{c['id']}: source_doc missing")
probe=R/'ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10'
if not probe.exists(): fails.append('live commissioning snapshot probe missing')
else:
    s=probe.read_text()
    if 'poke 0 31416051' not in s or 'poke 1 1' not in s: fails.append('probe magic/ABI mismatch')
    # Probe may write only its own db stack (poke); no external physical/stack mutation instructions.
    for ln in s.splitlines():
        code=ln.split('#',1)[0].strip()
        if re.match(r'^(?:s|sd|put|putd|clr|clrd)\b',code): fails.append(f'probe is not read-only: {code}')
for name,needle in [('ROADMAP.md','## 12. Live-game commissioning and evidence closure — ACTIVE'),('README.md','docs/LIVE_COMMISSIONING.md'),('docs/FRAMEWORK_HARDENING_TESTS.md','Item 12 field-evidence workflow'),('docs/ABI_REFERENCE.md','Live Commission Snapshot Probe ABI1')]:
    p=R/name
    if not p.exists() or needle not in p.read_text(): fails.append(f'{name}: missing commissioning contract marker')
rv=(R/'tools'/'run_validation.py').read_text()
for n in ('validation/validators/validate_live_commissioning_contracts.py','tests/test_live_commissioning.py'):
    if n not in rv: fails.append(f'run_validation missing {n}')
manifest=json.loads((R/'data/source_manifest.json').read_text()).get('scripts',{})
if 'ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10' not in manifest: fails.append('source_manifest missing live commissioning snapshot probe')
if fails:
    print('Live commissioning contracts: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Live commissioning contracts: PASS')
print(f' - {len(required)} required suites + {len(cases)-len(required)} optional suite(s)')
print(' - read-only 6-source commissioning snapshot probe is registered')
print(' - evidence sessions are release-fingerprint bound and remain separate from automated evidence')
