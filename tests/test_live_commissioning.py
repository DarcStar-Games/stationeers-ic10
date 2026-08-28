#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from tempfile import TemporaryDirectory
from framework.ic10_harness import IC10,Device
import tools.live_commission as lc
import math,sys
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
# Execute the actual stack monitor against an IC housing and optional output Memory.
target=Device(201,stack={6:1,8:4,9:0},props={
    'ReferenceId':201,'PrefabHash':'HASH:StructureCircuitHousing'})
selector=Device(202,props={'ReferenceId':202,'Setting':6})
output=Device(203,props={'ReferenceId':203,'Setting':0})
monitor=IC10((R/'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10').read_text(),
             {'d0':target,'d1':selector,'d2':output},self_ref=2541)
monitor.stack[9]=math.nan
monitor.run(2)
if monitor.stack.get(5)!=1 or monitor.stack.get(6)!=6 or monitor.stack.get(7)!=1:
    fails.append('stack monitor finite capture mismatch')
if monitor.stack.get(8)!=201 or output.props.get('Setting')!=1:
    fails.append('stack monitor target identity/output mirror mismatch')
if monitor.stack.get(9)!=1:
    fails.append('stack monitor did not initialize generation on a reused housing')
target.stack[9]=math.nan;selector.props['Setting']=9;monitor.run(1)
if monitor.stack.get(5)!=2 or not math.isnan(output.props.get('Setting')):
    fails.append('stack monitor did not distinguish captured NaN')
selector.props['Setting']=512;monitor.run(1)
if monitor.stack.get(5)!=-4 or monitor.stack.get(6)!=512:
    fails.append('stack monitor accepted an out-of-range address')
selector.props['Setting']=6.25;monitor.run(1)
if monitor.stack.get(5)!=-4:
    fails.append('stack monitor accepted a fractional address')
target.props['PrefabHash']='HASH:StructureLogicMemory';selector.props['Setting']=6;monitor.run(1)
if monitor.stack.get(5)!=-2:
    fails.append('stack monitor accepted a non-IC target')
# Compact IC housings work without the optional d2 output.
compact=Device(204,stack={17:42},props={
    'ReferenceId':204,'PrefabHash':'HASH:StructureCircuitHousingCompact'})
compact_selector=Device(205,props={'ReferenceId':205,'Setting':17})
compact_monitor=IC10((R/'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10').read_text(),
                     {'d0':compact,'d1':compact_selector},self_ref=2542)
compact_monitor.run(2)
if compact_monitor.stack.get(5)!=1 or compact_monitor.stack.get(7)!=42:
    fails.append('stack monitor failed compact housing capture without optional output')
# Missing required inputs publish their distinct status instead of faulting.
no_target=IC10((R/'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10').read_text(),
               {'d1':compact_selector},self_ref=2543)
no_target.run(2)
if no_target.stack.get(5)!=-1 or no_target.stack.get(7)!=0:
    fails.append('stack monitor did not report a missing target with a neutral value')
no_selector=IC10((R/'ic10/live-commissioning/stack_cell_monitor_v1_0.ic10').read_text(),
                 {'d0':compact},self_ref=2544)
no_selector.run(2)
if no_selector.stack.get(5)!=-3:
    fails.append('stack monitor did not report a missing selector')
if fails:
    print('Live commissioning tests: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Live commissioning tests: PASS')
print(' - release-bound session freshness and append-only rerun history')
print(' - all required suites can close only through explicit PASS observations')
print(' - real IC10 probe captures dynamic LogicType + generation-fenced stack values')
print(' - nonpositive/torn stack generation fails closed')
print(' - real stack monitor covers reused state, both housing types, optional output, and invalid inputs')
