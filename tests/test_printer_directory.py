#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import Device,IC10
R=_PROJECT_ROOT
A=(R/'ic10/printer-directory/printer_directory_adapter_v1_0.ic10').read_text()
B=(R/'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10').read_text()
H=(R/'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10').read_text()
fails=[]

def publish(devices,base=800,rounds=5000):
    hv=IC10(H,self_ref=base);hv.run(2)
    hd=Device(base,hv.stack,{'ReferenceId':base})
    av=IC10(A,{f'p{i}':d for i,d in enumerate(devices)},self_ref=base+1)
    ad=Device(base+1,av.stack,{'ReferenceId':base+1})
    bv=IC10(B,{'d0':ad,'d1':hd},self_ref=base+2)
    for _ in range(rounds):
        av.run(1,max_steps=50000);bv.run(1,max_steps=50000);hv.run(1,max_steps=50000)
        if max(hd.stack.get(3,0),hd.stack.get(4,0))>0:return av,bv,hv,hd
    raise RuntimeError('Printer Directory did not publish')

def recs(h):
    b=int(h.stack.get(2,0));w=int(h.stack.get(11,0));cap=int(h.stack.get(12,0));n=int(h.stack.get(5+b,0));base=32+b*w*cap
    return [[h.stack.get(base+i*w+j,0) for j in range(w)] for i in range(n)]

def printer(ref,prefab,power=1,on=1,active=0,error=0,lock=0):
    return Device(ref,props={'ReferenceId':ref,'PrefabHash':'HASH:'+prefab,'Power':power,'On':on,'Activate':active,'Error':error,'Lock':lock})

# All canonical families plus retained naming aliases; deprecated Fabricator must never appear.
devs=[
 printer(901,'StructureAutolathe'),printer(902,'StructureAutolatheMKII'),
 printer(903,'StructureElectronicsPrinter'),printer(904,'StructureElectronicsPrinterMKII'),
 printer(905,'StructureHydraulicPipeBender'),printer(906,'StructurePipeBender'),printer(907,'StructurePipeBenderMKII'),
 printer(908,'StructureToolManufactory'),printer(909,'StructureToolmaker'),printer(910,'StructureToolmakerMKII'),
 printer(911,'StructureSecurityPrinter'),printer(912,'StructureRocketManufactory'),
 printer(913,'StructureFabricator')]
av,bv,hv,hd=publish(devs)
r=recs(hv)
expected=[
 [901,'HASH:Printer.Autolathe',2305],[902,'HASH:Printer.Autolathe',2306],
 [903,'HASH:Printer.ElectronicsPrinter',2305],[904,'HASH:Printer.ElectronicsPrinter',2306],
 [905,'HASH:Printer.HydraulicPipeBender',2305],[906,'HASH:Printer.HydraulicPipeBender',2305],[907,'HASH:Printer.HydraulicPipeBender',2306],
 [908,'HASH:Printer.ToolManufactory',2305],[909,'HASH:Printer.ToolManufactory',2305],[910,'HASH:Printer.ToolManufactory',2306],
 [911,'HASH:Printer.SecurityPrinter',2305],[912,'HASH:Printer.RocketManufactory',2305]]
if r!=expected:fails.append('family/capability mapping or Fabricator exclusion mismatch')
if hd.stack.get(0)!=31415981 or hd.stack.get(1)!=1 or hd.stack.get(9)!='HASH:DirectorySchema.Printer.v2' or hd.stack.get(11)!=3 or hd.stack.get(12)!=64:
    fails.append('Generic Snapshot Printer schema header mismatch')
if av.stack.get(0)!=31415983 or av.stack.get(1)!=3 or av.stack.get(2)!=17 or av.stack.get(3)!='HASH:DirectorySchema.Printer.v2' or av.stack.get(10)!=3 or av.stack.get(11)!=64:
    fails.append('Printer Adapter ABI3 header mismatch')

# Every packed operational flag and capability survives publication; changed state advances snapshot generation.
target=devs[3]
g0=max(hd.stack.get(3,0),hd.stack.get(4,0))
target.props.update({'Power':1,'On':1,'Activate':1,'Error':1,'Lock':1})
for _ in range(5000):
    av.run(1,max_steps=50000);bv.run(1,max_steps=50000);hv.run(1,max_steps=50000)
    if max(hd.stack.get(3,0),hd.stack.get(4,0))>g0:break
else:fails.append('changed printer status did not advance snapshot generation')
rr={x[0]:x for x in recs(hv)}
# cap2 + Power256 + Busy512 + Error1024 + On2048 + Lock4096 = 7938
if rr.get(904)!=[904,'HASH:Printer.ElectronicsPrinter',7938]:fails.append('PrinterStatusSpec packed bit publication mismatch')

# Exactly 64 complete records are retained and active-bank overflow marks the 65th supported printer.
many=[printer(1000+i,'StructureAutolathe') for i in range(65)]
_,_,oh,od=publish(many,base=850)
ob=int(od.stack.get(2,0));orows=recs(oh)
if len(orows)!=64 or od.stack.get(7+ob,0)!=1:fails.append('65-printer overflow did not publish 64 complete records + overflow')
if any(len(x)!=3 for x in orows):fails.append('overflow split/corrupted a Printer record')

if fails:
    print('Printer Directory validation: FAIL')
    for f in fails:print(' -',f)
    sys.exit(1)
print('Printer Directory validation: PASS')
print(' - six supported printer families map to Recipe Catalog FamilyHash identities')
print(' - Capability and Power/Busy/Error/On/Lock pack into ProcessorSpec')
print(' - Fabricator is excluded and retained prefab aliases remain recognized')
print(' - live state changes publish a new schema-qualified Generic Snapshot generation')
print(' - 65th printer fails closed with overflow while preserving 64 whole records')
