#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import IC10,Device
R=_PROJECT_ROOT;fails=[]
def ck(x,m):
 if not x:fails.append(m)
def src(n):return (R/n).read_text()

# Transform readiness must ignore an old profile/admission/resolver publication indefinitely.
profile=Device(501,stack={2:111,3:2,4:2,5:1,6:5,33:9001,35:2,68:111,69:1},props={'ReferenceId':501})
adm=Device(502,stack={13:501,9:7,8:1,2:111},props={'ReferenceId':502})
res=Device(503,stack={7:9,6:1,2:111},props={'ReferenceId':503})
rpv=Device(506,stack={},props={'ReferenceId':506});ep=Device(505,stack={14:506},props={'ReferenceId':505})
out=Device(504,stack={2:505,7:100},props={'ReferenceId':504})
runtime=Device(500,stack={17:502,18:503,15:504},props={'ReferenceId':500})
ready=IC10(src('ic10/manufacturing/transform_candidate_readiness_v1_0.ic10'),{'p':profile,'a':adm,'r':res,'o':out,'e':ep,'rp':rpv},self_ref=507)
ready.stack.update({2:500,3:222,4:2,5:2,6:1,7:1,8:44})
# expose all refs for getd through screws
ready.screws.update({'rt':runtime,'profile':profile,'adm':adm,'res':res,'out':out,'ep':ep,'rpv':rpv})
ready.run(30)
ck(ready.stack.get(10)!=44,'stale transform profile completed a new readiness request')
profile.stack.update({2:222,3:2,4:2,5:1,6:6,33:9001,35:2,68:222,69:1})
ready.run(2);adm.stack.update({9:8,8:1,2:222});ready.run(2)
# Delay resolver beyond the old 16-tick timeout; request must remain pending, not fail.
ready.run(24);ck(ready.stack.get(10)!=44,'transform readiness retained a fixed timeout')
res.stack.update({7:10,6:1,2:222});ready.run(2)
ck(ready.stack.get(10)==44 and ready.stack.get(9)==1,'generation-qualified transform readiness did not complete')

# Admission and resolver failures map to processor/resource rather than timing out ambiguously.
ready.stack.update({3:333,8:45});profile.stack.update({2:333,6:7,68:333,69:1});ready.run(2);adm.stack.update({9:9,8:-1,2:333});ready.run(2)
ck(ready.stack.get(10)==45 and ready.stack.get(9)==-2,'Admission rejection was not classified WAIT_PROCESSOR')

# LIVE_CURRENT invalid requests must still publish their accepted identity, or callers hang forever.
proc=Device(601,props={'ReferenceId':601,'Activate':0})
adm2=Device(602,props={'ReferenceId':602});res2=Device(603,props={'ReferenceId':603})
alloc=Device(604,stack={},props={'ReferenceId':604});out2=Device(605,props={'ReferenceId':605})
tr=IC10(src('ic10/material-transform/generic_material_transform_runtime_v2_0.ic10'),{'d0':proc,'d1':adm2,'d2':res2,'d3':alloc,'d4':out2},self_ref=606)
tr.run(1);tr.stack.update({8:0,16:71});tr.run(1)
ck(tr.stack.get(21)==71 and tr.stack.get(20)==-1,'invalid Transform Runtime request did not publish matching current token + fault')


# Diagnostic Mapping Editor must not commit an old selector result after a newer UI request.
import re
def no_alias(source,replacements):
    source='\n'.join(x for x in source.splitlines() if not x.lstrip().startswith('alias '))
    for a,b in replacements.items(): source=re.sub(r'\b'+re.escape(a)+r'\b',b,source)
    return source
map_src=no_alias(src('ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10'),{
 'consoleSelector':'r1','controllerSelector':'r2','renderer':'r3','input':'r4','display':'r5','controller':'r6'})
map_src=re.sub(r'move r10 17320509\nmove r11 17320508\nmove r12 16180339\nmove r7 1\nValidateService:\nblez rr7 NoService\ngetd r0 rr7 0\nadd r8 r7 9\nbne r0 rr8 NoService\ngetd r0 rr7 1\nseq r8 r7 2\nselect r8 r8 2 1\nbne r0 r8 NoService\nadd r7 r7 1\nble r7 3 ValidateService\n','',map_src)
old_controller=Device(706,props={'ReferenceId':706});new_controller=Device(707,props={'ReferenceId':707})
display=Device(705,props={'ReferenceId':705,'On':1})
cs=Device(701,stack={0:17320508,1:2,5:706,8:1,13:1},props={'ReferenceId':701})
cons=Device(702,stack={0:17320509,1:1,16:705,17:1,10:0,11:0,14:1},props={'ReferenceId':702})
renderer=Device(703,stack={0:16180339,1:1,8:0},props={'ReferenceId':703})
inp=Device(704,stack={0:17320511,1:1,10:1,19:1,20:0,21:6,23:1,24:2,25:1},props={'ReferenceId':704})
me=IC10(map_src,{'cs':cs,'cons':cons,'renderer':renderer,'input':inp,'display':display,'old':old_controller,'new':new_controller},self_ref=708)
me.stack.update({8:702,9:701,10:703,13:704})
me.run(2)
ck(renderer.stack.get(8,0)==0 and me.stack.get(12)==-2,'Mapping Editor consumed stale Controller Selector success')
cs.stack.update({5:707,13:2,8:1});me.run(1)
ck(renderer.stack.get(8)==1 and renderer.stack.get(65)==707,'Mapping Editor did not commit after Controller Selector token caught up')

# A pending console auto-advance is also part of selector identity and must fence the next commit.
display2=Device(715,props={'ReferenceId':715,'On':1});controller2=Device(716,props={'ReferenceId':716})
cs2=Device(711,stack={0:17320508,1:2,5:716,8:1,13:3},props={'ReferenceId':711})
cons2=Device(712,stack={0:17320509,1:1,16:705,17:1,10:4,11:3,14:2},props={'ReferenceId':712})
renderer2=Device(713,stack={0:16180339,1:1,8:0},props={'ReferenceId':713})
inp2=Device(714,stack={0:17320511,1:1,10:1,19:2,20:0,21:6,23:1,24:3,25:2},props={'ReferenceId':714})
me2=IC10(map_src,{'cs':cs2,'cons':cons2,'renderer':renderer2,'input':inp2,'display1':display,'display2':display2,'controller':controller2},self_ref=718)
me2.stack.update({8:712,9:711,10:713,13:714});me2.run(2)
ck(renderer2.stack.get(8,0)==0,'Mapping Editor consumed console result while auto-advance response was stale')
cons2.stack.update({16:715,11:4,17:1});me2.run(1)
ck(renderer2.stack.get(8)==1 and renderer2.stack.get(64)==715,'Mapping Editor did not resume after console advance token caught up')

# Material Transfer Executor must ignore an old Feeder failure until CurrentToken matches this grant epoch.
feeder=Device(801,stack={6:-1,7:40,8:40,9:40},props={'ReferenceId':801})
mx=IC10(src('ic10/material-grid/material_transfer_executor_v1_0.ic10'),{'d1':feeder},self_ref=802)
mx.stack.update({2:41,4:0,9:1,10:0,12:900,31:31415958})
mx.run(2)
ck(mx.stack.get(9)==1 and mx.stack.get(4)==0,'stale Feeder failure terminated a newer transfer request')
feeder.stack.update({6:1,7:41,8:41});sink=Device(900,props={'ImportCount':7,'ReferenceId':900});mx.screws['sink']=sink
mx.run(1)
ck(mx.stack.get(9)==2 and feeder.stack.get(19)==41,'Executor did not advance after Feeder CurrentToken matched')

# Generic TERMINAL_RESPONSE semantics reject request N while N+1 is expected.
from framework.async_request import terminal,consume_terminal
ck(consume_terminal(102,terminal(101,1)) is None,'stale TERMINAL_RESPONSE result was accepted for a newer request')

if fails:
 print('Async request execution: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Async request execution: PASS')
print(' - stale Transform profile/admission/resolver publications cannot satisfy a new request')
print(' - diagnostic selector results and console auto-advance are fenced by exact response identity')
print(' - stale Feeder failure cannot terminate a newer transfer request')
print(' - invalid LIVE_CURRENT requests publish identity; stale TERMINAL_RESPONSE results are ignored')
