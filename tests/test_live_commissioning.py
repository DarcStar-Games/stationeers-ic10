#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from tempfile import TemporaryDirectory
from framework.ic10_harness import IC10,Device
import tools.live_commission as lc
import sys
R=_PROJECT_ROOT
fails=[]
# Session lifecycle and required-suite closure.
s=lc.new_session(label='test')
if not lc.session_fresh(s): fails.append('new session not fresh')
for c in lc.load_catalog()['cases']:
    if c.get('required',True):
        s.setdefault('results',{})[c['id']]={'runs':[{'status':'PASS','recorded_at':'x','precondition':'p','action':'a','observed':'o','reference_ids':[],'notes':''}]}
v=lc.verify_session(s)
if v['required_pass']!=v['required_total'] or v['failed'] or v['blocked'] or v['unrun']: fails.append('required-suite PASS closure mismatch')
stale=dict(s);stale['framework_fingerprint']='stale'
if lc.verify_session(stale)['fresh']: fails.append('stale framework fingerprint accepted')
# CLI evidence writes atomically and preserves prior runs.
with TemporaryDirectory() as td:
    p=Path(td)/'s.json';lc.write_session(p,lc.new_session())
    rc=lc.main(['record','--session',str(p),'--case','LG-SEQUENCER','--status','FAIL','--precondition','p','--action','a','--observed','bad'])
    rc|=lc.main(['record','--session',str(p),'--case','LG-SEQUENCER','--status','PASS','--precondition','p2','--action','a2','--observed','good'])
    ss=lc.read_session(p);runs=ss['results']['LG-SEQUENCER']['runs']
    if rc or len(runs)!=2 or runs[-1]['status']!='PASS': fails.append('append-only live result history mismatch')
# Execute the actual read-only IC10 probe: one dynamic LogicType and one generation-fenced stack value.
logic=Device(101,props={'ReferenceId':101,42:12.5})
stack=Device(102,stack={10:7,20:99},props={'ReferenceId':102})
vm=IC10((R/'ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10').read_text(),{'d0':logic,'d1':stack},self_ref=2540)
vm.run(1)
vm.stack.update({6:1,32:1,33:42,34:-1,35:2,36:20,37:10,2:1})
vm.run(2)
if vm.stack.get(3)!=1 or vm.stack.get(4)!=1 or vm.stack.get(5)!=2: fails.append(f'probe response header mismatch: {vm.stack.get(3)}, {vm.stack.get(4)}, {vm.stack.get(5)}')
if vm.stack.get(64)!=101 or vm.stack.get(66)!=1 or vm.stack.get(67)!=12.5: fails.append('probe dynamic LogicType capture mismatch')
if vm.stack.get(69)!=102 or vm.stack.get(71)!=1 or vm.stack.get(72)!=99 or vm.stack.get(73)!=7: fails.append('probe fenced stack capture mismatch')
# A nonpositive stack fence fails closed, without preventing a response token.
stack.stack[10]=0;vm.stack[2]=2;vm.run(2)
if vm.stack.get(3)!=2 or vm.stack.get(4)!=-2 or vm.stack.get(71)!=-3: fails.append('probe torn/nonpositive generation did not fail closed')
if fails:
    print('Live commissioning tests: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Live commissioning tests: PASS')
print(' - release-bound session freshness and append-only rerun history')
print(' - all required suites can close only through explicit PASS observations')
print(' - real IC10 probe captures dynamic LogicType + generation-fenced stack values')
print(' - nonpositive/torn stack generation fails closed')
