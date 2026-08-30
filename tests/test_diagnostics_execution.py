#!/usr/bin/env python3
"""Drive one request through each diagnostics program that relocated payload cells.

Static token assertions cannot see a consumer stranded on a peer's pre-migration
cell layout (issue #43); each scenario here executes the real program against
peers modeled on the cells the current sources publish and asserts the published
response.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import math,sys
from framework.ic10_harness import IC10,Device
R=_PROJECT_ROOT;fails=[]
def ck(cond,msg):
 if not cond:fails.append(msg)
def src(p):return (R/p).read_text()

# Diagnostic Input Bridge: one resolved control edit lands in UI state with status 1.
# The Profile generation lives at Profile S11; a Profile that publishes none is invalid
# (the #41 defect read a vacated cell and rejected every request).
profile=Device(800,stack={0:'HASH:InputProfileView.v1',1:1,8:'HASH:DiagnosticMapping',9:1,10:7,11:5},props={'ReferenceId':800})
resolver=Device(801,stack={0:'HASH:GenericInputResolver.v1',1:1,13:3,14:9,11:1,12:2},props={'ReferenceId':801})
ib=IC10(src('ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10'),{'p':profile,'r':resolver},self_ref=810)
ib.stack.update({8:801,9:800});ib.run(2)
ck(ib.stack.get(10)==1 and ib.stack.get(18)==9 and ib.stack.get(25)==2,'input bridge SetConsole request rejected or misplaced')
ck(resolver.stack.get(9)==7 and resolver.stack.get(10)==800,'input bridge did not frame the Resolver request')
ib.run(1)
ck(ib.stack.get(25)==2,'input bridge re-bumped console generation for an unchanged value')
resolver.stack.update({13:1,14:4});ib.run(1)
ck(ib.stack.get(16)==4 and ib.stack.get(24)==2,'input bridge SetController did not republish the pair generation')
resolver.stack.update({13:7,14:1});ib.run(1)
ck(ib.stack.get(22)==1 and ib.stack.get(23)==1 and ib.stack.get(10)==1,'input bridge commit rising edge did not fire')
ib.run(1)
ck(ib.stack.get(23)==1,'input bridge held commit switch fired twice')
profile.stack[11]=0;ib.run(1)
ck(ib.stack.get(10)==-1,'input bridge accepted a Profile with no published generation')
profile.stack[11]=5;ib.run(1)
ck(ib.stack.get(10)==1,'input bridge did not recover once the Profile generation returned')

# Console Registry: enrollment sorts [PrefabHash,ReferenceId] pairs into the inactive
# bank and publishes count/generation (S12/13, S10/11) before flipping S8.
led_a=Device(501,props={'ReferenceId':501,'NameHash':'HASH:DiagAuto','PrefabHash':200,'Setting':0,'Mode':0,'Color':0,'On':1})
led_b=Device(502,props={'ReferenceId':502,'NameHash':'HASH:DiagAuto','PrefabHash':100,'Setting':0,'Mode':0,'Color':0,'On':1})
mirror=Device(503,props={'ReferenceId':503,'NameHash':'HASH:DiagAuto','PrefabHash':100,'Setting':0})
other=Device(504,props={'ReferenceId':504,'NameHash':'HASH:Other','PrefabHash':50,'Setting':0,'Mode':0,'Color':0,'On':1})
no_on=Device(505,props={'ReferenceId':505,'NameHash':'HASH:DiagAuto','PrefabHash':60,'Setting':0,'Mode':0,'Color':0})
reg=IC10(src('ic10/diagnostics/console_registry_v1_1.ic10'),{'c0':led_a,'c1':led_b,'c2':mirror,'c3':other,'c4':no_on},self_ref=500)
reg.run(7)
ck(reg.stack.get(8)==1 and reg.stack.get(13)==3 and reg.stack.get(11)==1,'registry first commit bank/count/generation')
ck([reg.stack.get(160+i) for i in range(6)]==[100,502,100,503,200,501],'registry bank B pairs unsorted or misfiltered')
reg.run(6)
ck(reg.stack.get(8)==0 and reg.stack.get(12)==3 and reg.stack.get(10)==2,'registry second commit did not alternate banks monotonically')
ck([reg.stack.get(32+i) for i in range(6)]==[100,502,100,503,200,501],'registry bank A pairs diverged from bank B')

# Console Selector: resolve a desired ordinal against the Registry's current
# publication cells (bank S8, generation S10/11, count S12/13) and blink it.
regdev=Device(520,stack={0:'HASH:ConsoleRegistry.v1',1:1,8:0,10:3,12:2,32:100,33:601,34:200,35:602},props={'ReferenceId':520})
led1=Device(601,props={'ReferenceId':601,'On':1})
led2=Device(602,props={'ReferenceId':602,'On':1})
sel=IC10(src('ic10/diagnostics/console_selector_v1_1.ic10'),{'led1':led1,'led2':led2,'reg':regdev},self_ref=530)
sel.stack.update({9:520,12:2,13:1});sel.run(2)
ck(sel.stack.get(17)==1,'console selector rejected a live Registry publication')
ck(sel.stack.get(15)==2 and sel.stack.get(16)==602 and sel.stack.get(19)==3 and sel.stack.get(14)==1,'console selector desired-ordinal resolution')
sel.stack[10]=1;sel.run(1)
ck(sel.stack.get(15)==1 and sel.stack.get(16)==601 and sel.stack.get(11)==1,'console selector advance did not wrap to the next console')
ck(led2.props.get('On')==1 and led1.props.get('On')==0,'console selector did not restore the previous display before blinking')
regdev.stack[12]=0;sel.run(1)
ck(sel.stack.get(17)==-2 and led1.props.get('On')==1,'console selector fault did not report NoConsole and re-enable the display')
regdev.stack[12]=2

# Diagnostic Selector Bridge: copies the Input Bridge UI state into both selector
# request windows only while the Input Bridge reports a valid status.
inputd=Device(540,stack={0:'HASH:DiagnosticInputBridge.v1',1:1,10:1,16:2,17:3,24:4,18:5,25:6},props={'ReferenceId':540})
ctrlsel=Device(541,stack={0:'HASH:ControllerSelector.v2',1:2},props={'ReferenceId':541})
conssel=Device(542,stack={0:'HASH:ConsoleSelector.v1',1:1},props={'ReferenceId':542})
sb=IC10(src('ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10'),{'a':inputd,'b':ctrlsel,'c':conssel},self_ref=550)
sb.stack.update({8:540,9:541,10:542});sb.run(2)
ck(ctrlsel.stack.get(10)==2 and ctrlsel.stack.get(11)==3 and ctrlsel.stack.get(12)==4,'selector bridge controller pair propagation')
ck(conssel.stack.get(12)==5 and conssel.stack.get(13)==6 and sb.stack.get(11)==6,'selector bridge console request propagation')
inputd.stack.update({10:-1,18:9,25:7});sb.run(1)
ck(conssel.stack.get(13)==6 and ctrlsel.stack.get(12)==4,'selector bridge propagated requests from an invalid Input Bridge')

# Hash Console Mode: apply desired circuitboard Modes from own-stack records,
# counting writes and skipping boards whose Mode slot is unreadable.
board=Device(560,props={'ReferenceId':560},slots={2:{'Mode':0}})
dead=Device(561,props={'ReferenceId':561},slots={0:{'Mode':math.nan}})
hm=IC10(src('ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10'),{'b0':board,'b1':dead},self_ref=570)
hm.stack.update({8:2,16:560,17:2,18:1,19:561,20:0,21:1});hm.run(2)
ck(board.slots[2].get('Mode')==1,'hash console mode did not write the desired Mode')
ck(hm.stack.get(9)==1 and hm.stack.get(10)==1,'hash console mode write/skip counters')
hm.run(1)
ck(hm.stack.get(9)==0 and hm.stack.get(10)==1,'hash console mode rewrote an already-correct Mode')

if fails:
 print('Diagnostics execution: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Diagnostics execution: PASS')
print(' - real Input Bridge resolves console/controller/commit edits and fails closed without a Profile generation')
print(' - real Console Registry double-buffers sorted console pairs with monotonic generations')
print(' - real Console Selector resolves ordinals against current Registry cells, advances, and restores displays')
print(' - real Selector Bridge propagates UI state only from a valid Input Bridge')
print(' - real Hash Console Mode writes desired Modes once and skips unreadable slots')
