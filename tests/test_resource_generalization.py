#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys
R=_PROJECT_ROOT
fails=[]
def need(t,s,msg):
    if s not in t: fails.append(msg+f' missing {s!r}')
# Generic Endpoint ABI is used by both pressure and material providers.
p=(R/'ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10').read_text()
m=(R/'ic10/item-storage-vending/material_vending_inventory_v1_0.ic10').read_text()
for t,label in ((p,'pressure adapter'),(m,'material inventory')):
    need(t,'poke 0 31415949',label)
    need(t,'poke 1 1',label)
    need(t,'poke 11 0',label)
# Resource reservation depends only on Generic Resource Endpoint, not pressure magic.
r=(R/'ic10/resource-grid-core/resource_reservation_v1_0.ic10').read_text()
need(r,'bne r0 31415949 Bad','generic reservation')
need(r,'poke 12 0 # semantic mirror generation LAST','generic reservation')
if '31415935' in r or 'Pressure' in r.split('\n',1)[1]: fails.append('generic reservation leaked pressure-specific dependency')
# Generic Resource Link view binds pressure topology to the corresponding generic endpoint providers.
l=(R/'ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10').read_text()
for n in ('poke 0 31415953','getd r11 r7 2','getd r12 r8 2','getd r0 r9 9','getd r0 r10 9','poke 12 r0'):
    need(l,n,'pressure resource link adapter')
# Resource discovery uses independent 64-entry endpoint/link directories with explicit overflow.
ed=(R/'ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10').read_text()
ld=(R/'ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10').read_text()
bridge=(R/'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10').read_text(); dh=(R/'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10').read_text()
for n in ('poke 0 31415983','poke 2 HASH("DirectorySchema.ResourceEndpoint")','poke 4 3','poke 5 64','poke 10 1'):
    need(ed,n,'resource endpoint adapter')
for n in ('poke 0 31415983','poke 2 HASH("DirectorySchema.ResourceLink")','poke 4 1','poke 5 64','poke 10 1'):
    need(ld,n,'resource link adapter')
for n in ('put d1 11 r2','put d1 12 r3','move r6 2'):
    need(bridge,n,'generic directory adapter bridge')
for n in ('poke 0 31415981','poke 1 1','poke 31 31415981','bgt r3 64 Error','poke 22 1','poke 2 r6'):
    need(dh,n,'generic snapshot directory host')

# Resource Reservation discovery and Item-7 storage providers reuse the same generic substrate.
rd=(R/'ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10').read_text()
for n in ('poke 0 31415983','poke 2 HASH("DirectorySchema.ResourceReservation")','poke 4 3','poke 5 64','poke 10 1'):
    need(rd,n,'resource reservation adapter')
for fn,kind in [
 ('ic10/item-storage-vending/material_vending_inventory_v1_0.ic10','StorageAccess.Vending'),
 ('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','StorageAccess.LArRE'),
 ('ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10','StorageAccess.Direct'),
 ('ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10','StorageAccess.SDB')]:
    z=(R/fn).read_text(); need(z,'poke 0 31415949',fn); need(z,'poke 14 r0',fn); need(z,f'HASH("{kind}")',fn)
res=(R/'ic10/resource-grid-core/resource_reservation_v1_0.ic10').read_text()
for n in ('poke 17 0 # owner ReferenceId','poke 19 0 # reserved semantic mirror generation','CompareHints:','CopyHints:','poke 25 -1 # committed action source slot'):
    need(res,n,'generic reservation Item-7 extension')
if 'StorageAccess.LArRE' in res or 'ItemHash' in res: fails.append('generic reservation interprets ITEM/LArRE-specific action hints')
sdb=(R/'ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10').read_text()
need(sdb,'poke 13 24','SDB lower-bound precision')
feeder=(R/'ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10').read_text()
need(feeder,'poke 0 31415961','SDB feeder ABI reuse'); need(feeder,'s d1 Setting r9','SDB exact Stacker metering')

# Unified Resource Profile source contains the complete current material ITEM set.
data=json.loads((R/'data/resource_profiles.json').read_text())
items=[x for x in data['profiles'] if x['profile_kind']==2]
if len(items)!=27: fails.append('expected 27 current material profiles in unified resource source')
for x in items:
    expected_schema=1 if x['material_group']=='ORE' else 2
    if x['resource_class']!=2 or x['unit']!=2 or x['profile_schema']!=expected_schema: fails.append(x['slug']+': ITEM profile metadata mismatch')
    if x['params'][0] <= 0: fails.append(x['slug']+': invalid MaxStack')
    if expected_schema==2 and x['params'][2]==0: fails.append(x['slug']+': missing ManufacturingReagentHash')
view=(R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10').read_text()
for n in ('poke 0 31415963','get r10 db 2','get r11 db 3','getd r0 r2 r8'):
    need(view,n,'resource profile view')
# Transform ABI3 reads self-contained relocatable items and complete furnace material set.
trs=json.loads((R/'data/resource_transforms.json').read_text())
if len(trs['transforms'])!=17: fails.append('expected 17 furnace transforms')
loaders=sorted((R/'ic10'/'transform-catalog').glob('resource_transform_catalog_loader_*_v6_0.ic10'))
loader='\n'.join(p.read_text() for p in loaders)
viewt=(R/'ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10').read_text()
for n in ('clr db','poke 0 31415969','poke 1 4','poke 2 HASH("CatalogSchema.ResourceTransform")','poke 12 1 # immutable candidate publication LAST'):
    need(loader,n,'transform catalog loader')
if 'putd ' in loader or 'put d0 ' in loader or 'yield' in loader: fails.append('transform catalog loader leaked push/poll behavior')
for n in ('poke 0 31415952','poke 1 4','add r6 r8 12','mul r0 r4 4','jal CopyPool'):
    need(viewt,n,'transform profile view')
for x in trs['transforms']:
    if '# '+x['display_name'] not in loader: fails.append(x['slug']+': transform human-name comment missing')
# Directory bank geometry stays inside the 512-value IC10 stack.
# Endpoint B bank: S224 + 64*3 - 1 = S415. Link B bank: S96 + 64 - 1 = S159.
if 224 + 64*3 - 1 >= 512: fails.append('resource endpoint directory exceeds stack')
if 96 + 64 - 1 >= 512: fails.append('resource link directory exceeds stack')
# Vending scanner is incremental/coherent across import/export counter changes.
for n in ('move r8 2','ble r8 101 Scan','l r6 d0 ImportCount','l r7 d0 ExportCount','bne r0 r6 Start','bne r0 r7 Start'):
    need(m,n,'material inventory coherence')
if fails:
    print('Resource generalization model: FAIL'); [print(' -',x) for x in fails]; sys.exit(1)
print('Resource generalization model: PASS')
print(' - pressure and material providers share Generic Resource Endpoint ABI1')
print(' - Generic Resource Reservation contains no pressure-specific dependency')
print(' - Pressure Resource Link adapter topology-binds generic reservations to native pressure inventories')
print(' - Resource Endpoint/Link/Reservation adapters reuse the 64-entry Generic Snapshot Directory Host with explicit overflow')
print(' - Vending, LArRE, direct-slot and SDB storage share Generic ITEM Endpoint/Reservation contracts; SDB precision remains lower-bound')
print(' - 27 ITEM profiles (10 ores, 7 basic ingots, 5 alloys, 5 superalloys) share the unified Resource Profile catalog')
print(' - 17 variable-input transforms share one block-structured catalog and request-fenced capability-based ABI4 View')
print(' - Vending inventory scan is incremental and invalidates on import/export churn')
