#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys
from framework.ic10_harness import Device,IC10,run_round_robin
R=_PROJECT_ROOT;fails=[]
H=(R/'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10').read_text();B=(R/'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10').read_text()
S=json.loads((R/'data/directory_schemas.json').read_text())
if S.get('format')!='GENERIC_DIRECTORY_SCHEMAS_V10' or S.get('adapter_abi',{}).get('magic')!=31415983 or S['adapter_abi'].get('abi')!=2:fails.append('Directory Adapter ABI registry metadata mismatch')

def host(ref):
 vm=IC10(H,self_ref=ref);vm.run(2);d=Device(ref,vm.stack,{'ReferenceId':ref});return vm,d

def snapshot(adapter_src,screws,ref,rounds=3000):
 hv,hd=host(ref);av=IC10(adapter_src,screws,self_ref=ref+1);ad=Device(ref+1,av.stack,{'ReferenceId':ref+1});bv=IC10(B,{'d0':ad,'d1':hd},self_ref=ref+2)
 for _ in range(rounds):
  av.run(1,max_steps=50000);bv.run(1,max_steps=50000);hv.run(1,max_steps=50000)
  if max(hd.stack.get(3,0),hd.stack.get(4,0))>0:return av,bv,hv,hd
 raise RuntimeError('adapter/bridge/host did not publish')

def records(h):
 b=int(h.stack.get(2,0));w=int(h.stack.get(11,0));cap=int(h.stack.get(12,0));c=int(h.stack.get(5+b,0));base=32+b*w*cap
 return [[h.stack.get(base+i*w+j,0) for j in range(w)] for i in range(c)]

def adapter_ok(a,mode=1):return a.stack.get(0)==31415983 and a.stack.get(1)==3 and a.stack.get(15)==mode and int(a.stack.get(13,0))%2==0
# Controller snapshot.
cs=[]
for ref,typ in ((201,'HASH:Z'),(202,'HASH:A'),(203,'HASH:A')):cs.append(Device(ref,stack={96:27182818,97:2,99:typ},props={'ReferenceId':ref,'PrefabHash':-128473777}))
a,b,h,hd=snapshot((R/'ic10/controller-discovery/controller_directory_adapter_v4_0.ic10').read_text(),{f'c{i}':d for i,d in enumerate(cs)},100)
if not adapter_ok(a) or hd.stack.get(0)!=31415981 or hd.stack.get(1)!=1 or hd.stack.get(9)!='HASH:DirectorySchema.Controller.v1' or records(h)!=[['HASH:A',202],['HASH:A',203],['HASH:Z',201]]:fails.append('Controller Adapter ABI/snapshot mismatch')
# Endpoint snapshot.
eps=[Device(301,stack={0:31415949,1:1,52:2,53:9,11:1},props={'ReferenceId':301,'PrefabHash':2037291645}),Device(302,stack={0:31415949,1:1,52:1,53:7,11:1},props={'ReferenceId':302,'PrefabHash':-128473777})]
a,b,h,hd=snapshot((R/'ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10').read_text(),{'e0':eps[0],'e1':eps[1]},110)
if not adapter_ok(a) or records(h)!=[[1,7,302],[2,9,301]]:fails.append('Resource Endpoint Adapter ABI/snapshot mismatch')
# Resource Link snapshot.
links=[Device(402,stack={0:31415953,1:1,12:1},props={'ReferenceId':402,'PrefabHash':2037291645}),Device(401,stack={0:31415953,1:1,12:1},props={'ReferenceId':401,'PrefabHash':-128473777})]
a,b,h,hd=snapshot((R/'ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10').read_text(),{'l0':links[0],'l1':links[1]},120)
if not adapter_ok(a) or records(h)!=[[401],[402]]:fails.append('Resource Link Adapter ABI/snapshot mismatch')
# Printer snapshot: six supported families, tier/capability packing, live operational flags, no Fabricator.
printers=[
 Device(451,props={'ReferenceId':451,'PrefabHash':'HASH:StructureAutolathe','Power':1,'On':1,'Activate':0,'Error':0,'Lock':0}),
 Device(452,props={'ReferenceId':452,'PrefabHash':'HASH:StructureElectronicsPrinterMKII','Power':1,'On':1,'Activate':1,'Error':0,'Lock':1}),
 Device(453,props={'ReferenceId':453,'PrefabHash':'HASH:StructurePipeBenderMKII','Power':1,'On':0,'Activate':0,'Error':0,'Lock':0}),
 Device(454,props={'ReferenceId':454,'PrefabHash':'HASH:StructureToolManufactory','Power':0,'On':1,'Activate':0,'Error':0,'Lock':0}),
 Device(455,props={'ReferenceId':455,'PrefabHash':'HASH:StructureSecurityPrinter','Power':1,'On':1,'Activate':0,'Error':1,'Lock':0}),
 Device(456,props={'ReferenceId':456,'PrefabHash':'HASH:StructureRocketManufactory','Power':1,'On':1,'Activate':0,'Error':0,'Lock':0}),
 Device(457,props={'ReferenceId':457,'PrefabHash':'HASH:StructureFabricator','Power':1,'On':1,'Activate':0,'Error':0,'Lock':0}),
]
a,b,h,hd=snapshot((R/'ic10/printer-directory/printer_directory_adapter_v1_0.ic10').read_text(),{f'p{i}':d for i,d in enumerate(printers)},125)
pr=records(h)
expected_pr=[
 [451,'HASH:Printer.Autolathe',2305],
 [452,'HASH:Printer.ElectronicsPrinter',6914],
 [453,'HASH:Printer.HydraulicPipeBender',258],
 [454,'HASH:Printer.ToolManufactory',2049],
 [455,'HASH:Printer.SecurityPrinter',3329],
 [456,'HASH:Printer.RocketManufactory',2305],
]
if not adapter_ok(a) or hd.stack.get(9)!='HASH:DirectorySchema.Printer.v2' or pr!=expected_pr:fails.append('Printer Adapter ABI/status snapshot mismatch')

# Pressure adapter consumes Controller Directory but publishes generic candidates; generic Bridge suppresses unchanged commits.
p1=Device(501,stack={97:2,106:601,107:602,115:4},props={'ReferenceId':501});p2=Device(502,stack={97:2,106:603,107:604,115:5},props={'ReferenceId':502})
cd=Device(131,stack={0:31415981,1:1,2:0,3:1,5:2,9:'HASH:DirectorySchema.Controller.v1',11:2,12:64,32:'HASH:ControllerPressureTransfer',33:501,34:'HASH:ControllerPressureTransfer',35:502},props={'ReferenceId':131})
a,b,h,hd=snapshot((R/'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10').read_text(),{'d1':cd,'p1':p1,'p2':p2},130)
if records(h)!=[[501,601,602],[502,603,604]]:fails.append('Pressure Link Adapter ABI/snapshot mismatch')
g0=max(hd.stack.get(3,0),hd.stack.get(4,0))
for _ in range(80):a.run(1);b.run(1,max_steps=50000);h.run(1,max_steps=50000)
g1=max(hd.stack.get(3,0),hd.stack.get(4,0))
if g1!=g0:fails.append('generic Adapter Bridge advanced generation for unchanged snapshot')
# Power Reservation snapshot: dispatch keys, class filtering, and the S8 allocator owner binding.
pres=[
 Device(901,stack={0:31415950,1:1,33:4,35:100,12:1,17:0,28:1,30:601,31:32},props={'ReferenceId':901}),
 Device(902,stack={0:31415950,1:1,33:4,12:1,17:0,28:2,30:602,31:25},props={'ReferenceId':902}),
 Device(903,stack={0:31415950,1:1,33:4,12:1,17:0,28:3,30:603,31:48},props={'ReferenceId':903}),
 Device(904,stack={0:31415950,1:1,33:4,12:1,17:0,28:2,30:604,31:42},props={'ReferenceId':904}),
 Device(905,stack={0:31415950,1:1,33:9,35:50,12:1,17:0,28:1,30:699,31:16},props={'ReferenceId':905}),
 Device(906,stack={0:31415950,1:1,33:4,35:80,12:1,17:4242,28:1,30:605,31:16},props={'ReferenceId':906}),
]
a,b,h,hd=snapshot((R/'ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10').read_text(),{f'q{i}':d for i,d in enumerate(pres)},150)
expected_power=[[1000002,601,901],[2000996,603,903],[3000998,602,902],[4000997,604,904],[5000996,603,903]]
if not adapter_ok(a) or hd.stack.get(9)!='HASH:DirectorySchema.PowerReservation.v1' or records(h)!=expected_power:fails.append('Power Reservation Adapter dispatch-key snapshot mismatch: '+repr(records(h)))
a.stack[8]=4242
owned_power=[[1000001,605,906]]+expected_power
for _ in range(3000):
 a.run(1,max_steps=50000);b.run(1,max_steps=50000);h.run(1,max_steps=50000)
 if records(h)==owned_power:break
if records(h)!=owned_power:fails.append('Power Reservation Adapter did not admit the allocator-owned reservation after S8 binding: '+repr(records(h)))
# Direct Host overflow keeps whole records.
hv,hd=host(140);hd.stack.update({9:'HASH:DirectorySchema.Test.v1',11:1,12:64});req=0
def hcmd(command,candidate=None):
 global req;req+=1
 if candidate is not None:hd.stack[17]=candidate
 hd.stack[16]=command;hd.stack[14]=req
 for _ in range(60):
  hv.run(1,max_steps=50000)
  if hd.stack.get(15,0)==req:return
 raise RuntimeError('host command not acknowledged')
hcmd(1)
for x in range(65,0,-1):hcmd(2,x)
hcmd(3)
if records(hv)!=[[x] for x in range(2,66)]:fails.append('Snapshot Host overflow corrupted whole records')
bank=int(hd.stack.get(2,0))
if hd.stack.get(7+bank,0)!=1:fails.append('Snapshot Host failed to publish overflow')
# Registry mode consumes the same Adapter ABI directly and indexes by NodeId.
store1=Device(701,stack={0:31415968,1:6,16:2,18:7,22:100,26:3,13:'HASH:CatA'},props={'ReferenceId':701,'PrefabHash':2037291645})
store2=Device(702,stack={0:31415968,1:6,16:1,18:9,22:32,26:0,13:0},props={'ReferenceId':702,'PrefabHash':2037291645})
av=IC10((R/'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10').read_text(),{'s1':store1,'s2':store2},self_ref=710);ad=Device(710,av.stack,{'ReferenceId':710});rv=IC10((R/'ic10/directory-core/generic_registry_directory_host_v2_0.ic10').read_text(),{'d0':ad},self_ref=711)
for _ in range(40):av.run(1,max_steps=50000);rv.run(1,max_steps=50000)
if not adapter_ok(av,2) or rv.stack.get(0)!=31415982 or rv.stack.get(1)!=3 or rv.stack.get(2)!='HASH:DirectorySchema.CatalogStoreNode.v1':fails.append('Registry Adapter ABI/header mismatch')
base7=64+(7-1)*6;base9=64+(9-1)*6
if rv.stack.get(base7)!=701 or rv.stack.get(base7+1)!=2 or rv.stack.get(base9)!=702:fails.append('Registry Host NodeId indexing mismatch')
# Removing Node9 from adapter discovery marks its persistent record MISSING on a later adapter generation.
del av.screws['s2']
for _ in range(20):av.run(1,max_steps=50000);rv.run(1,max_steps=50000)
if rv.stack.get(base9+1)!=7:fails.append('Registry Host did not mark missing node')
# Full-capacity exact duplicate must not create a false overflow.
hv2,hd2=host(141);hd2.stack.update({9:'HASH:DirectorySchema.Test.v1',11:1,12:64});req2=0
def hcmd2(command,candidate=None):
 global req2;req2+=1
 if candidate is not None:hd2.stack[17]=candidate
 hd2.stack[16]=command;hd2.stack[14]=req2
 for _ in range(60):
  hv2.run(1,max_steps=50000)
  if hd2.stack.get(15,0)==req2:return
 raise RuntimeError('host duplicate command not acknowledged')
hcmd2(1)
for x in range(1,65):hcmd2(2,x)
hcmd2(2,64);hcmd2(3)
bank=int(hd2.stack.get(2,0))
if hd2.stack.get(7+bank,0)!=0 or records(hv2)!=[[x] for x in range(1,65)]:fails.append('Snapshot Host falsely overflowed on exact duplicate at capacity')
# Registry Host must reject wrong schema even when geometry/mode are otherwise valid.
wrong='''# synthetic wrong registry schema Adapter ABI2
Boot:
clr db
poke 0 31415983
poke 1 3
poke 2 17
poke 8 HASH(\"DirectorySchema.Wrong\")
poke 9 9
poke 10 6
poke 11 64
poke 12 0
poke 7 1
poke 13 2
poke 15 2
Loop:
yield
get r0 db 16
beqz r0 Loop
poke 17 r0
j Loop'''
wv=IC10(wrong,self_ref=720);wd=Device(720,wv.stack,{'ReferenceId':720});wr=IC10((R/'ic10/directory-core/generic_registry_directory_host_v2_0.ic10').read_text(),{'d0':wd},self_ref=721)
for _ in range(20):wv.run(1,max_steps=50000);wr.run(1,max_steps=50000)
if wr.stack.get(16)!=-4 or wr.stack.get(2,0)!=0:fails.append('Registry Host accepted wrong schema/version')
# Harness models the automatic execution quantum even without explicit yield.
q=IC10('Loop:\nadd r0 r0 1\nj Loop\n')
if q.run_tick(128)!='quantum' or q.reg.get('r0',0)<=0:fails.append('IC10 harness does not preempt a no-yield loop at the instruction quantum')
# Adversarial interleaving: alternating Adapter generations may never be mixed by Bridge publication.
toggle='''Boot:
clr db
poke 0 31415983
poke 1 3
poke 2 17
poke 3 HASH(\"DirectorySchema.Test.v1\")
poke 8 HASH(\"DirectorySchema.Test\")
poke 9 1
poke 10 1
poke 11 2
poke 15 1
Loop:
yield
get r0 db 16
beqz r0 Scan
poke 17 r0
j Loop
Scan:
poke 17 0
get r0 db 13
add r0 r0 1
poke 13 r0
get r13 db 20
bnez r13 B
poke 18 10
poke 19 20
j Finish
B:
poke 18 11
poke 19 21
Finish:
poke 12 2
get r0 db 13
add r0 r0 1
poke 13 r0
seq r13 r13 0
poke 20 r13
get r0 db 7
add r0 r0 1
poke 7 r0
j Loop'''
hv3,hd3=host(730);tv=IC10(toggle,self_ref=731);td=Device(731,tv.stack,{'ReferenceId':731});bb=IC10(B,{'d0':td,'d1':hd3},self_ref=732)
# Reboot the Adapter while a freeze is outstanding; Bridge must reassert the token and recover.
rebooted=False
for _ in range(100):
 run_round_robin([tv,bb,hv3],rounds=1,max_instructions=8)
 if td.stack.get(16,0) and td.stack.get(17,0)!=td.stack.get(16,0):
  tv.pc=0; rebooted=True; break
if not rebooted:fails.append('could not stage Adapter reboot during freeze')
for _ in range(300):
 run_round_robin([tv,bb,hv3],rounds=1,max_instructions=8)
 if max(int(hd3.stack.get(3,0)),int(hd3.stack.get(4,0)))>0:break
if max(int(hd3.stack.get(3,0)),int(hd3.stack.get(4,0)))==0:fails.append('Bridge did not recover freeze handshake after Adapter reboot')
seen_gen=0
for _ in range(1200):
 run_round_robin([tv,bb,hv3],rounds=1,max_instructions=8)
 g=max(int(hd3.stack.get(3,0)),int(hd3.stack.get(4,0)))
 if g!=seen_gen and g>0:
  seen_gen=g; rr=records(hv3)
  if rr not in ([[10],[20]],[[11],[21]]):fails.append('Bridge published torn mixed Adapter generation under interleaving: '+repr(rr));break
if seen_gen==0:fails.append('adversarial interleaving test never published a snapshot')
if fails:
 print('Generic Directory infrastructure: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generic Directory infrastructure: PASS')
print(' - DIRECTORY_ADAPTER_ABI_V2 freezes coherent candidate generations across multi-tick consumers')
print(' - Snapshot Bridge/Host publishes one generic ABI with schema-qualified stable generations')
print(' - Registry Host ABI3 consumes the same Adapter ABI with S23 transactional publication fencing')
print(' - 65th snapshot candidate sets overflow without splitting/corrupting a record')
print(' - exact duplicate at full capacity does not falsely overflow')
print(' - 128-instruction/8-instruction adversarial scheduler never publishes a torn Adapter generation')
print(' - freeze request is reasserted and recovers after Adapter reboot')
print(' - Registry Host rejects wrong schema/version before mutation')
print(' - Power Reservation Adapter keys producer/consumer/battery dispatch and honors the S8 owner binding')
