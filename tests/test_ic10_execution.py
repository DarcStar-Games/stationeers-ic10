from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from ic10_harness import IC10, Device
from catalog_test_helpers import load_catalog_store,load_catalog_chain
import sys,json
R=_PROJECT_ROOT
fails=[]
# Populate the linked ResourceClass-partitioned Resource Profile catalog, then resolve through the real View.
rpm=json.loads((R/'resource_profile_catalog_manifest.json').read_text())
generic=(R/rpm['generic_store_program']).read_text()
resource_loader_groups=[[(R/f).read_text() for f in part['loaders']] for part in rpm['partitions']]
resource_stores,resource_vms,_=load_catalog_chain([generic]*rpm['runtime_min_store_count'], resource_loader_groups, store_ref_base=180,loader_ref_base=1180)
resource_store=resource_stores[0]
resource_coord=resource_vms[0].screws['coord']
def make_view(resource_class,resource_type,ref):
    screws={'d0':resource_store,'coord':resource_coord}|{f'x{i}':d for i,d in enumerate(resource_stores[1:])}
    vm=IC10((R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10').read_text(),screws,self_ref=ref)
    vm.stack[2]=resource_class; vm.stack[3]=resource_type; vm.run(2)
    return Device(ref,stack=dict(vm.stack),props={'ReferenceId':ref})
profile=make_view(1,'HASH:Pollutant',200)
if profile.stack.get(0)!=31415963 or profile.stack.get(4)!=1 or profile.stack.get(5,0)<=0 or profile.stack.get(8)!=1 or profile.stack.get(9)!='HASH:Pollutant' or profile.stack.get(11)!=1 or profile.stack.get(12)!=2 or profile.stack.get(19)!='RatioPollutant' or profile.stack.get(20)!=.995:
    fails.append('Pollutant Resource Profile View publication mismatch')
# Purity Guard good and contaminated cases.
for ratio,expect in [(.999,1),(.90,-4)]:
    analyzer=Device(201,props={'ReferenceId':201,'TotalMoles':100,'RatioPollutant':ratio})
    g=IC10((R/'ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10').read_text(),{'d0':analyzer,'d1':profile})
    g.run(2)
    if g.stack.get(5)!=expect: fails.append(f'Purity Guard ratio {ratio} produced {g.stack.get(5)}, expected {expect}')
# Grant Guard: coherent current topology must equal staged topology and committed planner epoch.
transfer=Device(300,stack={96:27182818,97:2,99:'HASH:ControllerPressureTransfer',101:1,102:'HASH:Pollutant',106:401,107:402,108:5,109:7,110:500,111:4,115:10,117:401,118:402,119:'HASH:Pollutant',120:1},props={'ReferenceId':300})
planner=Device(500,stack={0:31415937,1:2,14:7},props={'ReferenceId':500})
g=IC10((R/'ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10').read_text(),{'d0':transfer,'d1':planner},self_ref=590); g.run(2)
if g.stack.get(4)!=1 or g.stack.get(2)!=5: fails.append('Grant Guard did not activate matching committed lease')
# A next plan may be staged while the current lease is active; it must not cancel the current lease.
transfer.stack.update({108:7,109:8,110:500,111:4,117:401,118:402,119:'HASH:Pollutant',120:1,115:11})
g.run(1)
if g.stack.get(4)!=1 or g.stack.get(5)!=7: fails.append('Staging next epoch disturbed current committed lease')
# Commit the staged epoch and verify it becomes the new lease.
planner.stack[14]=8
g.run(1)
if g.stack.get(4)!=1 or g.stack.get(2)!=7 or g.stack.get(5)!=8: fails.append('Grant Guard failed to switch atomically to newly committed epoch')
# Exhaust the short lease and prove the same committed epoch cannot reactivate itself.
g.run(4)
if g.stack.get(4)!=0 or g.stack.get(3)!=0: fails.append('Grant Guard did not expire bounded lease')
g.run(2)
if g.stack.get(4)!=0 or g.stack.get(3)!=0 or g.stack.get(5)!=8: fails.append('Expired committed epoch reactivated without a new commit')
# A topology mismatch consumes the current epoch; restoring topology cannot restart that same lease.
transfer.stack.update({108:6,109:9,111:4,117:401,118:402,119:'HASH:Pollutant',120:1,115:12})
planner.stack[14]=9
g.run(1)
if g.stack.get(4)!=1: fails.append('Grant Guard failed to activate epoch used for topology test')
transfer.stack[106]=999; transfer.stack[115]=13
g.run(1)
if g.stack.get(4)!=0 or g.stack.get(2)!=0: fails.append('Grant Guard failed to shut off topology-mismatched lease')
transfer.stack[106]=401; transfer.stack[115]=14
g.run(2)
if g.stack.get(4)!=0 or g.stack.get(5)!=9: fails.append('Topology-consumed epoch reactivated after topology restoration')

# Generic resource contracts: execute real pressure adapter and material vending inventory.
inv=Device(610,stack={0:31415935,1:2,3:3,4:'HASH:Pollutant',5:120,6:80,11:1,12:4},props={'ReferenceId':610})
ep=IC10((R/'ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10').read_text(),{'d0':inv},self_ref=600); ep.run(2)
if ep.stack.get(0)!=31415949 or ep.stack.get(2)!=1 or ep.stack.get(4)!=7 or ep.stack.get(5)!=120 or ep.stack.get(6)!=80: fails.append('Pressure Resource Endpoint adapter publication mismatch')
profile_item=make_view(2,1758427767,620)
if profile_item.stack.get(4)!=1 or profile_item.stack.get(8)!=2 or profile_item.stack.get(9)!=1758427767 or profile_item.stack.get(10)!=2 or profile_item.stack.get(11)!=2 or profile_item.stack.get(13)!=50 or profile_item.stack.get(14)!=10:
    fails.append('Iron Ore Resource Profile View publication mismatch')
slots={2:{'Occupied':1,'OccupantHash':1758427767,'Quantity':20,'MaxQuantity':50},3:{'Occupied':1,'OccupantHash':-707307845,'Quantity':10,'MaxQuantity':50},4:{'Occupied':1,'OccupantHash':1758427767,'Quantity':50,'MaxQuantity':50}}
vending=Device(621,props={'ReferenceId':621,'Error':0,'Power':1,'ImportCount':7,'ExportCount':3},slots=slots)
mi=IC10((R/'ic10/item-storage-vending/material_vending_inventory_v1_0.ic10').read_text(),{'d0':vending,'d1':profile_item},self_ref=680); mi.run(103)
if mi.stack.get(0)!=31415949 or mi.stack.get(3)!=1758427767 or mi.stack.get(5)!=70 or mi.stack.get(6)!=4880 or mi.stack.get(8)!=1: fails.append(f'Material Vending Inventory execution mismatch: avail={mi.stack.get(5)} cap={mi.stack.get(6)} status={mi.stack.get(8)}')
endpoint=Device(630,stack=dict(mi.stack),props={'ReferenceId':630})
rr=IC10((R/'ic10/resource-grid-core/resource_reservation_v1_0.ic10').read_text(),{'d0':endpoint},self_ref=611); rr.run(2)
if rr.stack.get(3)!=2 or rr.stack.get(4)!=1758427767 or rr.stack.get(6)!=70 or rr.stack.get(7)!=4880: fails.append('Generic Resource Reservation did not mirror material endpoint')
# Execute Generic Resource Link adapter against topology-consistent pressure/generic reservations.
src_inv=Device(701,stack={0:31415935,1:2},props={'ReferenceId':701})
sink_inv=Device(702,stack={0:31415935,1:2},props={'ReferenceId':702})
src_pres=Device(711,stack={0:31415936,1:1,2:701},props={'ReferenceId':711})
sink_pres=Device(712,stack={0:31415936,1:1,2:702},props={'ReferenceId':712})
src_ep=Device(721,stack={0:31415949,1:1,2:1,3:'HASH:Pollutant',4:1,5:20,6:0,7:0,8:1,9:701,10:1,11:3,12:1,13:3},props={'ReferenceId':721})
sink_ep=Device(722,stack={0:31415949,1:1,2:1,3:'HASH:Pollutant',4:2,5:0,6:20,7:0,8:1,9:702,10:1,11:4,12:1,13:3},props={'ReferenceId':722})
src_gr=Device(731,stack={0:31415950,1:1,2:721,3:1,4:'HASH:Pollutant',5:1,6:20,7:0,8:0,9:1,10:1,11:3,12:2},props={'ReferenceId':731})
sink_gr=Device(732,stack={0:31415950,1:1,2:722,3:1,4:'HASH:Pollutant',5:2,6:0,7:20,8:0,9:1,10:1,11:3,12:2},props={'ReferenceId':732})
pt=Device(740,stack={96:27182818,97:2,99:'HASH:ControllerPressureTransfer',100:4.5,101:1,102:'HASH:Pollutant',103:1,106:711,107:712,115:9},props={'ReferenceId':740})
rl=IC10((R/'ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10').read_text(),{'d0':pt,'d1':src_gr,'d2':sink_gr,'x1':src_pres,'x2':sink_pres,'x3':src_ep,'x4':sink_ep,'x5':src_inv,'x6':sink_inv},self_ref=720); rl.run(2)
if rl.stack.get(0)!=31415953 or rl.stack.get(2)!=731 or rl.stack.get(3)!=732 or rl.stack.get(5)!='HASH:Pollutant' or rl.stack.get(7)!=4.5 or rl.stack.get(9)!=1: fails.append('Generic Resource Link adapter execution mismatch')

# Harness device-validity branches follow IC10 semantics: bdnvs branches only when a LogicType is not writable.
wdev=Device(801,props={'ReferenceId':801,'On':1})
wv=IC10('bdnvs d0 On Missing\ns d0 On 0\nyield\nMissing:\nyield',{'d0':wdev},self_ref=802);wv.run(1)
if wdev.props.get('On')!=0: fails.append('IC10 harness bdnvs incorrectly branched on a writable property')
wv2=IC10('bdnvs d0 Setting Missing\ns d0 Setting 5\nyield\nMissing:\nyield',{'d0':wdev},self_ref=803);wv2.run(1)
if 'Setting' in wdev.props: fails.append('IC10 harness bdnvs failed to branch on a non-writable/missing property')

# Material transform execution is covered exhaustively by tests/test_material_transform_protocol.py.

if fails:
 print('IC10 execution harness: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('IC10 execution harness: PASS')
print(' - linked FLUID/ITEM Resource Profile stores + real View resolve Pollutant and Iron Ore')
print(' - real Purity Guard accepts sufficiently pure nonempty gas')
print(' - real Purity Guard rejects contaminated gas')
print(' - real Grant Guard keeps the current lease active while the next epoch is only staged')
print(' - real Grant Guard switches only after Planner commit')
print(' - real Grant Guard expires each committed lease exactly once')
print(' - real Grant Guard consumes a topology-mismatched epoch without later reactivation')
print(' - real Pressure Resource Endpoint adapter normalizes molar capacity')
print(' - real Material Vending Inventory scans 100 slots coherently and publishes exact item capacity')
print(' - real Generic Resource Reservation mirrors a material endpoint without pressure coupling')
print(' - real Generic Resource Link adapter preserves pressure topology identity in generalized form')
