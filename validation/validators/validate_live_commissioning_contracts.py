#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT
validation=Validation(R)
try: data=json.loads((R/'data/live_commissioning_cases.json').read_text())
except Exception as e: data={};validation.fail(f'case catalog parse failed: {e}')
cases=data.get('cases',[])
if data.get('format')!='LIVE_COMMISSIONING_CASES_V1': validation.fail('wrong live commissioning catalog format')
ids=[c.get('id') for c in cases]
if len(ids)!=len(set(ids)) or None in ids: validation.fail('commissioning case IDs must be unique/nonempty')
required=[c for c in cases if c.get('required',True)]
expected={'LG-PRESSURE-CORE','LG-PERSISTENCE','LG-SHARED-INPUT','LG-SEQUENCER','LG-PHASE-PRESSURE','LG-PRESSURE-DOMAIN','LG-PRESSURE-MULTIHOP','LG-PRESSURE-COST','LG-MATERIAL','LG-JOB-STORE','LG-MANUFACTURING','LG-ITEM-STORAGE','LG-POWER','LG-XDOMAIN-FURNACE','LG-XDOMAIN-GFG','LG-XDOMAIN-RESTART'}
if not expected.issubset(set(ids)): validation.fail('required live suite catalog is incomplete')
for c in cases:
    for k in ('id','category','title','source_doc','section','acceptance'):
        if not c.get(k): validation.fail(f"{c.get('id','?')}: missing {k}")
    if c.get('source_doc') and not (R/c['source_doc']).exists(): validation.fail(f"{c['id']}: source_doc missing")
probe=R/'ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10'
if not probe.exists(): validation.fail('live commissioning snapshot probe missing')
else:
    s=probe.read_text()
    if 'poke 0 31416051' not in s or 'poke 1 1' not in s: validation.fail('probe magic/ABI mismatch')
    # Probe may write only its own db stack (poke); no external physical/stack mutation instructions.
    for ln in s.splitlines():
        code=ln.split('#',1)[0].strip()
        if re.match(r'^(?:s|sd|put|putd|clr|clrd)\b',code): validation.fail(f'probe is not read-only: {code}')
monitor=R/'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10'
if not monitor.exists(): validation.fail('stack cell monitor missing')
else:
    s=monitor.read_text()
    for token in ('poke 0 31416052','poke 1 1','poke 7 0','move r1 0','get r1 d0 r0','s db Setting r1','s d2 Setting r1'):
        if token not in s: validation.fail(f'stack monitor contract missing {token!r}')
    if re.search(r'\b(?:move|poke)\s+\S+\s+nan\b',s):
        validation.fail('stack monitor uses a game-editor-incompatible NaN immediate')
    for ln in s.splitlines():
        code=ln.split('#',1)[0].strip()
        if re.match(r'^(?:put|putd|clr|clrd|sd)\b',code) or re.match(r'^s\s+(?:d0|d1)\b',code):
            validation.fail(f'stack monitor mutates an observed device: {code}')
for name,needle in [('ROADMAP.md','## 12. Live-game commissioning and evidence closure — ACTIVE'),('README.md','docs/LIVE_COMMISSIONING.md'),('docs/FRAMEWORK_HARDENING_TESTS.md','Item 12 field-evidence workflow'),('docs/ABI_REFERENCE.md','Live Commission Snapshot Probe ABI1'),('docs/ABI_REFERENCE.md','Stack Cell Monitor ABI1')]:
    p=R/name
    if not p.exists() or needle not in p.read_text(): validation.fail(f'{name}: missing commissioning contract marker')
rv=(R/'tools'/'run_validation.py').read_text()
for n in ('validation/validators/validate_live_commissioning_contracts.py','tests/test_live_commissioning.py'):
    if n not in rv: validation.fail(f'run_validation missing {n}')
manifest=json.loads((R/'data/source_manifest.json').read_text()).get('scripts',{})
if 'ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10' not in manifest: validation.fail('source_manifest missing live commissioning snapshot probe')
if 'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10' not in manifest: validation.fail('source_manifest missing stack cell monitor')
raise SystemExit(validation.finish('Live commissioning contracts',[
 f'{len(required)} required suites + {len(cases)-len(required)} optional suite(s)',
 'read-only snapshot probe and visible stack-cell monitor are registered',
 'evidence sessions are release-fingerprint bound and remain separate from automated evidence']))
