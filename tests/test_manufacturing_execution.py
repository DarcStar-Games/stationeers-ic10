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

# Generic candidate selection is schema-qualified and works for both processor families.
printer_dir=Device(100,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,24:1,26:5,28:2,30:0,9:'HASH:DirectorySchema.Printer.v2',11:3,12:8,
 56:501,57:'HASH:Printer.Autolathe',58:257,59:502,60:'HASH:Printer.Autolathe',61:258},props={'ReferenceId':100})
sel=IC10(src('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10'),{'d0':printer_dir});sel.run(1)
sel.stack.update({17:'HASH:DirectorySchema.Printer.v2',18:'HASH:Printer.Autolathe',19:2,20:2,21:0,22:1,15:2,16:100});sel.run(1)
ck(sel.stack.get(9)==1 and sel.stack.get(10)==502 and sel.stack.get(13)==2,'printer tier candidate selection mismatch')
sel.stack.update({22:2,17:'HASH:DirectorySchema.Printer.v1',16:100});sel.run(1);ck(sel.stack.get(9)==-1,'candidate selector accepted a schema identity at the wrong version')
transform_dir=Device(101,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,24:0,25:7,27:1,29:0,9:'HASH:DirectorySchema.TransformLane.v1',11:3,12:64,
 32:601,33:701,34:263},props={'ReferenceId':101})
ts=IC10(src('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10'),{'d0':transform_dir});ts.run(1)
ts.stack.update({17:'HASH:DirectorySchema.TransformLane.v1',18:0,19:4,20:1,21:0,22:1,15:1,16:101});ts.run(1)
ck(ts.stack.get(9)==1 and ts.stack.get(10)==601 and ts.stack.get(11)==701,'transform capability candidate selection mismatch')

# Print material resolver maps semantic recipe reagents to concrete MaterialGrid links/resources.
recipe=Device(200,stack={13:2,14:9,15:1,16:'HASH:Iron',17:30,18:'HASH:Copper',19:10},props={'ReferenceId':200})
# source/sink reservations advertise sufficient exact ITEM capacity.
sr1=Device(211,stack={36:100},props={'ReferenceId':211});dr1=Device(212,stack={37:100},props={'ReferenceId':212})
sr2=Device(221,stack={36:100},props={'ReferenceId':221});dr2=Device(222,stack={37:100},props={'ReferenceId':222})
l1=Device(213,stack={28:211,29:212,31:-1301215609,9:1,22:900,27:'HASH:Iron'},props={'ReferenceId':213})
l2=Device(223,stack={28:221,29:222,31:-404336834,9:1,22:900,27:'HASH:Copper'},props={'ReferenceId':223})
ld=Device(230,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,24:1,26:4,28:2,30:0,9:'HASH:DirectorySchema.ResourceLink.v1',11:1,12:8,13:0,40:213,41:223},props={'ReferenceId':230})
rv=IC10(src('ic10/manufacturing/print_material_resolver_v1_0.ic10'),{'d0':recipe,'d1':ld,'l1':l1,'l2':l2,'sr1':sr1,'dr1':dr1,'sr2':sr2,'dr2':dr2});rv.run(1)
rv.stack.update({16:900,17:2,18:1});rv.run(1)
ck(rv.stack.get(12)==1 and rv.stack.get(9)==2 and rv.stack.get(8)==900,'print material resolver rejected reachable reagents')
ck([rv.stack.get(20+i) for i in range(8)]==[213,30,-1301215609,2,223,10,-404336834,2],'print resolver did not publish transform-compatible four-cell link records')
# Insufficient source resource is classified WAIT_RESOURCE; sink loss is WAIT_CAPACITY.
sr1.stack[36]=1;rv.stack[18]=2;rv.run(1);ck(rv.stack.get(12)==-3,'insufficient reagent was not classified resource wait')
sr1.stack[36]=100;dr1.stack[37]=1;rv.stack[18]=3;rv.run(1);ck(rv.stack.get(12)==-4,'insufficient sink capacity was not classified capacity wait')
dr1.stack[37]=100
# ResourceLink records are one cell, so the Snapshot Host writes bank 1 at
# 32 + 1*64. The active bank alternates on every commit and only bank 0 was ever
# exercised here; reading a 192-cell stride finds cleared cells and then faults
# on a zero ReferenceId.
ld.stack.update({24:1,26:5,28:2,30:0,96:213,97:223});rv.stack[18]=4;rv.run(1)
ck(rv.stack.get(12)==1 and rv.stack.get(9)==2,'print resolver missed the second directory bank at its published stride')

# Generic print runtime consumes the same allocator completion contract and native printer instruction stack.
resolver=Device(300,stack={8:910,9:2,11:1,12:1},props={'ReferenceId':300})
allocator=Device(301,stack={22:0,16:0},props={'ReferenceId':301})
printer=Device(910,stack={},props={'ReferenceId':910,'ExportCount':5,'Error':0,'On':0})
pr=IC10(src('ic10/manufacturing/generic_print_runtime_v2_0.ic10'),{'d0':resolver,'d1':allocator,'p':printer});pr.run(1)
pr.stack.update({10:910,11:123456,12:2,13:77,14:1});pr.run(1)
ck(pr.stack.get(8)==3 and allocator.stack.get(8)==2,'print runtime did not request material allocation')
# allocator completion for request token 1
allocator.stack.update({16:1,22:2});pr.run(1);pr.run(1)
ck(pr.stack.get(8)==5 and printer.stack.get(0)==3 and printer.props.get('On')==1,'print runtime did not launch printer instruction')
# two requested outputs complete one chunk and verify.
printer.props['ExportCount']=7
for _ in range(5):pr.run(1)
ck(pr.stack.get(8)==7 and pr.stack.get(15)==1,'print runtime did not reach COMPLETE after output confirmation')

# Transform lane adapter exposes runtime+processor under common ProcessorSpec.
proc=Device(401,props={'ReferenceId':401,'PrefabHash':'HASH:StructureAdvancedFurnace','Power':1,'Error':0,'Activate':0})
runtime=Device(402,stack={0:'HASH:GenericMaterialTransformRuntime.v2',1:2,3:0,6:0,14:401},props={'ReferenceId':402,'PrefabHash':123})
la=IC10(src('ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10'),{'r':runtime,'p':proc});la.run(2)
ck(la.stack.get(3)=='HASH:DirectorySchema.TransformLane.v1' and la.stack.get(12)==1,'transform lane adapter header/count mismatch')
ck([la.stack.get(18+i) for i in range(3)]==[402,401,263],'transform lane ProcessorSpec mismatch')

if fails:
 print('Manufacturing execution substrate: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Manufacturing execution substrate: PASS')
print(' - candidate selection is schema/version-qualified for Printer v2 and TransformLane v1')
print(' - print reagents resolve through MaterialGrid links into existing four-cell allocator records')
print(' - resource vs capacity shortages remain distinct scheduler wait reasons')
print(' - Generic Print Runtime reuses Multi Material Allocator completion and confirms exported output')
print(' - Transform Lane Directory publishes the common ProcessorSpec used by generic selection')
