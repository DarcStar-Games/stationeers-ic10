#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.ic10_source import game_hash
from pathlib import Path
import json,sys
from framework.ic10_harness import Device,IC10,run_round_robin,without_lines
R=_PROJECT_ROOT;fails=[]
H=(R/'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10').read_text();B=(R/'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10').read_text()
S=json.loads((R/'data/directory_schemas.json').read_text())
if S.get('format')!='GENERIC_DIRECTORY_SCHEMAS_V10' or S.get('adapter_abi',{}).get('magic')!=game_hash('DirectoryAdapter.v3') or S['adapter_abi'].get('abi')!=2:fails.append('Directory Adapter ABI registry metadata mismatch')

def host(ref):
 vm=IC10(H,self_ref=ref);vm.run(2);d=Device(ref,vm.stack,{'ReferenceId':ref});return vm,d

def snapshot(adapter_src,screws,ref,rounds=3000):
 hv,hd=host(ref);av=IC10(adapter_src,screws,self_ref=ref+1);ad=Device(ref+1,av.stack,{'ReferenceId':ref+1});bv=IC10(B,{'d0':ad,'d1':hd},self_ref=ref+2)
 for _ in range(rounds):
  av.run(1,max_steps=50000);bv.run(1,max_steps=50000);hv.run(1,max_steps=50000)
  if max(hd.stack.get(25,0),hd.stack.get(26,0))>0:return av,bv,hv,hd
 raise RuntimeError('adapter/bridge/host did not publish')

def records(h):
 b=int(h.stack.get(24,0));w=int(h.stack.get(11,0));cap=int(h.stack.get(12,0));c=int(h.stack.get(27+b,0));base=32+b*w*cap
 return [[h.stack.get(base+i*w+j,0) for j in range(w)] for i in range(c)]

def adapter_ok(a,mode=1):return a.stack.get(0)=='HASH:DirectoryAdapter.v3' and a.stack.get(1)==3 and a.stack.get(15)==mode and int(a.stack.get(13,0))%2==0
# Controller snapshot.
cs=[]
for ref,typ in ((201,'HASH:Z'),(202,'HASH:A'),(203,'HASH:A')):cs.append(Device(ref,stack={96:27182818,97:2,99:typ},props={'ReferenceId':ref,'PrefabHash':-128473777}))
a,b,h,hd=snapshot((R/'ic10/controller-discovery/controller_directory_adapter_v4_0.ic10').read_text(),{f'c{i}':d for i,d in enumerate(cs)},100)
if not adapter_ok(a) or hd.stack.get(0)!='HASH:GenericSnapshotDirectoryHost.v1' or hd.stack.get(1)!=1 or hd.stack.get(9)!='HASH:DirectorySchema.Controller.v1' or records(h)!=[['HASH:A',202],['HASH:A',203],['HASH:Z',201]]:fails.append('Controller Adapter ABI/snapshot mismatch')
# Once initialized, the Bridge must reject live geometry changes instead of combining
# a new capacity with records and an active-bank selector from the old layout.
controller_records=records(h);controller_generation=max(hd.stack.get(25,0),hd.stack.get(26,0))
a.stack[11]=32
for _ in range(300):a.run(1,max_steps=50000);b.run(1,max_steps=50000);h.run(1,max_steps=50000)
if hd.stack.get(12)!=64 or records(h)!=controller_records or max(hd.stack.get(25,0),hd.stack.get(26,0))!=controller_generation:fails.append('Snapshot Bridge accepted a live capacity change without Host reinitialization')
# Endpoint snapshot.
eps=[Device(301,stack={0:'HASH:ResourceEndpoint.v1',1:1,52:2,53:9,11:1},props={'ReferenceId':301,'PrefabHash':2037291645}),Device(302,stack={0:'HASH:ResourceEndpoint.v1',1:1,52:1,53:7,11:1},props={'ReferenceId':302,'PrefabHash':-128473777})]
a,b,h,hd=snapshot((R/'ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10').read_text(),{'e0':eps[0],'e1':eps[1]},110)
if not adapter_ok(a) or records(h)!=[[1,7,302],[2,9,301]]:fails.append('Resource Endpoint Adapter ABI/snapshot mismatch')
# Resource Link snapshot.
links=[Device(402,stack={0:'HASH:ResourceLink.v1',1:1,12:1},props={'ReferenceId':402,'PrefabHash':2037291645}),Device(401,stack={0:'HASH:ResourceLink.v1',1:1,12:1},props={'ReferenceId':401,'PrefabHash':-128473777})]
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
cd=Device(131,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,24:0,25:1,27:2,9:'HASH:DirectorySchema.Controller.v1',11:2,12:64,32:'HASH:ControllerPressureTransfer',33:501,34:'HASH:ControllerPressureTransfer',35:502},props={'ReferenceId':131})
a,b,h,hd=snapshot((R/'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10').read_text(),{'d1':cd,'p1':p1,'p2':p2},130)
if records(h)!=[[501,601,602],[502,603,604]]:fails.append('Pressure Link Adapter ABI/snapshot mismatch')
g0=max(hd.stack.get(3,0),hd.stack.get(4,0))
for _ in range(80):a.run(1);b.run(1,max_steps=50000);h.run(1,max_steps=50000)
g1=max(hd.stack.get(3,0),hd.stack.get(4,0))
if g1!=g0:fails.append('generic Adapter Bridge advanced generation for unchanged snapshot')
# Power Reservation snapshot: dispatch keys, class filtering, and the S8 allocator owner binding.
pres=[
 Device(901,stack={0:'HASH:ResourceReservation.v1',1:1,33:4,35:100,12:1,17:0,28:1,30:601,31:32},props={'ReferenceId':901}),
 Device(902,stack={0:'HASH:ResourceReservation.v1',1:1,33:4,12:1,17:0,28:2,30:602,31:25},props={'ReferenceId':902}),
 Device(903,stack={0:'HASH:ResourceReservation.v1',1:1,33:4,12:1,17:0,28:3,30:603,31:48},props={'ReferenceId':903}),
 Device(904,stack={0:'HASH:ResourceReservation.v1',1:1,33:4,12:1,17:0,28:2,30:604,31:42},props={'ReferenceId':904}),
 Device(905,stack={0:'HASH:ResourceReservation.v1',1:1,33:9,35:50,12:1,17:0,28:1,30:699,31:16},props={'ReferenceId':905}),
 Device(906,stack={0:'HASH:ResourceReservation.v1',1:1,33:4,35:80,12:1,17:4242,28:1,30:605,31:16},props={'ReferenceId':906}),
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
bank=int(hd.stack.get(24,0))
if hd.stack.get(29+bank,0)!=1:fails.append('Snapshot Host failed to publish overflow')
# Registry mode consumes the same Adapter ABI directly and indexes by NodeId.
store1=Device(701,stack={0:'HASH:GenericCatalogStore.v6',1:6,16:2,18:7,22:100,26:3,13:'HASH:CatA'},props={'ReferenceId':701,'PrefabHash':2037291645})
store2=Device(702,stack={0:'HASH:GenericCatalogStore.v6',1:6,16:1,18:9,22:32,26:0,13:0},props={'ReferenceId':702,'PrefabHash':2037291645})
av=IC10((R/'ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10').read_text(),{'s1':store1,'s2':store2},self_ref=710);ad=Device(710,av.stack,{'ReferenceId':710});rv=IC10((R/'ic10/directory-core/generic_registry_directory_host_v2_0.ic10').read_text(),{'d0':ad},self_ref=711)
for _ in range(40):av.run(1,max_steps=50000);rv.run(1,max_steps=50000)
if not adapter_ok(av,2) or rv.stack.get(0)!='HASH:GenericRegistryDirectoryHost.v3' or rv.stack.get(1)!=3 or rv.stack.get(3)!='HASH:DirectorySchema.CatalogStoreNode.v1':fails.append('Registry Adapter ABI/header mismatch')
base7=64+(7-1)*6;base9=64+(9-1)*6
if rv.stack.get(base7)!=701 or rv.stack.get(base7+1)!=2 or rv.stack.get(base9)!=702:fails.append('Registry Host NodeId indexing mismatch')
# The Catalog Inspector's registry diagnostics S35..S38 read only cells the Registry Host publishes: S16 status,
# S23 publication sequence, S24 freeze-token counter, S25 accepted candidate generation (issue #194).
core=Device(712,stack={0:'HASH:CatalogCoordinatorCore.v4',1:4,22:4,23:711},props={'ReferenceId':712})
iv=IC10((R/'ic10/catalog-control-plane/catalog_inspector_v4_0.ic10').read_text(),{'d0':Device(701,{**store1.stack,11:712},{'ReferenceId':701}),'core':core,'host':Device(711,rv.stack,{'ReferenceId':711})},self_ref=713)
for _ in range(4):iv.run(1,max_steps=50000)
if iv.stack.get(41)!=1:fails.append('Inspector did not publish a coherent registry snapshot: S41=%r'%iv.stack.get(41))
if rv.stack.get(24,0)<1 or rv.stack.get(25,0)<1:fails.append('Registry Host published no freeze token or accepted generation to inspect')
if [iv.stack.get(c) for c in (35,36,37,38)]!=[rv.stack.get(16),rv.stack.get(23),rv.stack.get(24),rv.stack.get(25)]:fails.append('Inspector S35..S38 are not the Host S16, S23, S24, S25: %r'%[iv.stack.get(c) for c in (35,36,37,38)])
if (iv.stack.get(30),iv.stack.get(31),iv.stack.get(32))!=(rv.stack.get(base7+1),rv.stack.get(base7+5),rv.stack.get(26)):fails.append('Inspector node state, LastSeenEpoch, or registry generation mismatch: %r'%[iv.stack.get(c) for c in (30,31,32)])
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
bank=int(hd2.stack.get(24,0))
if hd2.stack.get(29+bank,0)!=0 or records(hv2)!=[[x] for x in range(1,65)]:fails.append('Snapshot Host falsely overflowed on exact duplicate at capacity')
# Registry Host must reject wrong schema even when geometry/mode are otherwise valid.
wrong='''# synthetic wrong registry schema Adapter ABI2
Boot:
clr db
poke 0 HASH("DirectoryAdapter.v3")
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
if wr.stack.get(16)!=-4 or wr.stack.get(3,0)!=0:fails.append('Registry Host accepted wrong schema/version')
# A count above the capacity is a malformed source (issue #151). The Adapter header says 64 six-cell
# records at S18..S401; a count of 65 walks the unguarded Host into S402, past the table, where it finds
# a record naming node 7 again and overwrites node 7's ReferenceId with it. The guarded Host rejects the
# count before it reads a record. Each witness runs the production program beside the same program with
# its guard lines removed, so the guard is shown to be what stops the walk.
def acking_adapter(mode,schema):
 return f"""Boot:
poke 0 HASH("DirectoryAdapter.v3")
poke 1 3
poke 2 17
poke 3 HASH("{schema}")
poke 15 {mode}
Loop:
yield
get r0 db 16
poke 17 r0
j Loop"""
registry_src=(R/'ic10/directory-core/generic_registry_directory_host_v2_0.ic10').read_text()
overfull={7:1,10:6,11:64,12:65,13:2,14:0}
for n in range(64):overfull.update({18+6*n:n+1,19+6*n:1000+n,20+6*n:2})
overfull.update({402:7,403:9999,404:2})
def registry_after(source):
 av=IC10(acking_adapter(2,'DirectorySchema.CatalogStoreNode.v1'),self_ref=740);av.stack.update(overfull);ad=Device(740,av.stack,{'ReferenceId':740})
 rv=IC10(source,{'d0':ad},self_ref=741)
 for _ in range(40):av.run(1,max_steps=50000);rv.run(1,max_steps=50000)
 return rv.stack.get(16),rv.stack.get(100)
if registry_after(registry_src)!=(-4,None):fails.append('Registry Host accepted a candidate count above its 64-node capacity: %r'%(registry_after(registry_src),))
if registry_after(without_lines(registry_src,'bgt r13 64 SourceBad'))!=(0,9999):fails.append('witness: the unguarded Registry Host did not read the 65th record past the candidate table: %r'%(registry_after(without_lines(registry_src,'bgt r13 64 SourceBad')),))
# The Bridge trusts the same header for the Snapshot Host it feeds. Its candidate copy lands at Host
# S17 + cell, so a width above three writes over the Host's rebuild state at S20/S21; a capacity above 64
# is configured into the Host, which then errors every command; and a count above the capacity walks the
# copy past the Adapter's table, here into a 65th record the Adapter never counted, which the unguarded
# Bridge publishes as an overflow the Adapter never reported.
bridge_guards=('bgt r2 3 Release','bgt r3 64 Release','bgt r13 r3 Release')
def bridged(source,cells):
 hv,hd=host(750);av=IC10(acking_adapter(1,'DirectorySchema.Test.v1'),self_ref=751);av.stack.update(cells);ad=Device(751,av.stack,{'ReferenceId':751});bv=IC10(source,{'d0':ad,'d1':hd},self_ref=752)
 for _ in range(400):av.run(1,max_steps=50000);bv.run(1,max_steps=50000);hv.run(1,max_steps=50000)
 return hd.stack.get(11,0),hd.stack.get(12,0),hd.stack.get(21,0),max(hd.stack.get(25,0),hd.stack.get(26,0)),hd.stack.get(29,0)+hd.stack.get(30,0)
wide={7:1,10:5,11:64,12:1,13:2,14:0,18:1,19:2,20:3,21:4,22:5}
deep={7:1,10:3,11:100,12:1,13:2,14:0,18:1,19:2,20:3}
many={7:1,10:3,11:64,12:65,13:2,14:0}
for n in range(65):many.update({18+3*n:n+1,19+3*n:n+1,20+3*n:n+1})
if bridged(B,wide)!=(0,0,0,0,0) or bridged(B,deep)!=(0,0,0,0,0) or bridged(B,many)!=(3,64,0,0,0):
 fails.append('Bridge published from an Adapter header its Host cannot hold: %r'%([bridged(B,c) for c in (wide,deep,many)],))
unguarded_bridge=without_lines(B,*bridge_guards)
w=bridged(unguarded_bridge,wide);d=bridged(unguarded_bridge,deep);m=bridged(unguarded_bridge,many)
if (w[0],w[2])!=(5,5):fails.append('witness: the unguarded Bridge did not write a five-cell candidate over the Host rebuild state: %r'%(w,))
if d[1]!=100:fails.append('witness: the unguarded Bridge did not configure a capacity of 100 into the Host: %r'%(d,))
if not (m[3]>0 and m[4]==1):fails.append('witness: the unguarded Bridge did not publish a 65th candidate as an overflow the Adapter never reported: %r'%(m,))
# Harness models the automatic execution quantum even without explicit yield.
q=IC10('Loop:\nadd r0 r0 1\nj Loop\n')
if q.run_tick(128)!='quantum' or q.reg.get('r0',0)<=0:fails.append('IC10 harness does not preempt a no-yield loop at the instruction quantum')
# Adversarial interleaving: alternating Adapter generations may never be mixed by Bridge publication.
toggle='''Boot:
clr db
poke 0 HASH("DirectoryAdapter.v3")
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
 if max(int(hd3.stack.get(25,0)),int(hd3.stack.get(26,0)))>0:break
if max(int(hd3.stack.get(25,0)),int(hd3.stack.get(26,0)))==0:fails.append('Bridge did not recover freeze handshake after Adapter reboot')
seen_gen=0
for _ in range(1200):
 run_round_robin([tv,bb,hv3],rounds=1,max_instructions=8)
 g=max(int(hd3.stack.get(25,0)),int(hd3.stack.get(26,0)))
 if g!=seen_gen and g>0:
  seen_gen=g; rr=records(hv3)
  if rr not in ([[10],[20]],[[11],[21]]):fails.append('Bridge published torn mixed Adapter generation under interleaving: '+repr(rr));break
if seen_gen==0:fails.append('adversarial interleaving test never published a snapshot')
if fails:
 print('Generic Directory infrastructure: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generic Directory infrastructure: PASS')
print(' - DIRECTORY_ADAPTER_ABI_V2 freezes coherent candidate generations across multi-tick consumers')
print(' - Snapshot Bridge/Host publishes one generic ABI with schema-qualified stable generations')
print(' - Snapshot Bridge rejects live schema-geometry changes until Host reinitialization')
print(' - Registry Host ABI3 consumes the same Adapter ABI with S23 transactional publication fencing')
print(' - Catalog Inspector registry diagnostics read only cells the Registry Host publishes')
print(' - 65th snapshot candidate sets overflow without splitting/corrupting a record')
print(' - exact duplicate at full capacity does not falsely overflow')
print(' - 128-instruction/8-instruction adversarial scheduler never publishes a torn Adapter generation')
print(' - freeze request is reasserted and recovers after Adapter reboot')
print(' - Registry Host rejects wrong schema/version before mutation')
print(' - Registry Host and Adapter Bridge hold the Adapter count, width, and capacity to the table they walk')
print(' - Power Reservation Adapter keys producer/consumer/battery dispatch and honors the S8 owner binding')
