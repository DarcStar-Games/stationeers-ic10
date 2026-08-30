#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from pathlib import Path
import sys
R=_PROJECT_ROOT;result=Validation(R)
txt=result.source
need=result.contains
before=result.ordered
# Cargo LArRE is sole native owner: scan, exact pre-pick quantity, whole-stack move, held-item recovery, token-last reply.
need('ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','poke 0 31415986','beq r2 1 Scan','beq r2 2 Move','beq r2 3 Recover',
 'ls r0 d0 255 OccupantHash','ls r13 d0 255 Quantity','get r0 db 15','bne r13 r0 Fault','s d0 Activate 1',
 'ls r1 d0 0 Occupied','select r0 r1 -6 -1','Reply:\npoke 9 r0','poke 14 r15')
before('ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','get r0 db 15','s d0 Activate 1')
before('ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10','Reply:\npoke 9 r0','poke 14 r15')
# Storage extension is high-cell and must preserve material S14 ResourceProfileRef.
for f,kind in [('ic10/item-storage-vending/material_vending_inventory_v1_0.ic10','StorageAccess.Vending'),('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','StorageAccess.LArRE'),('ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10','StorageAccess.Direct'),('ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10','StorageAccess.SDB')]:
 need(f,'poke 14 r0',f'poke 35 HASH("{kind}")','get r0 db 36','db 37','poke 38','poke 39','poke 40')
# LArRE endpoint serializes scan and raw move through one service and publishes response last.
need('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','put d0 17 1','put d0 8 r7','bne r0 r7 WaitScan','put d0 17 r13','put d0 15 r0','put d0 8 r7','bne r0 r7 WaitMove','poke 32 r0','poke 33 r1','poke 34 r15')
before('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','put d0 22 r2','put d0 8 r7')
before('ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10','poke 33 r1','poke 34 r15')
# Generic reservation owns a semantic mirror generation and coherently mirrors opaque storage action hints.
need('ic10/resource-grid-core/resource_reservation_v1_0.ic10','poke 17 0','poke 18 0','poke 19 0','poke 20 r14','poke 21 0','poke 22 -1','poke 23 0','poke 24 -1','CompareHints:','Changed:','CopyHints:','poke 12 r0')
before('ic10/resource-grid-core/resource_reservation_v1_0.ic10','poke 20 r14','poke 12 r0')
# Reservation directory + bounded read-only selector.
need('ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10','HASH("DirectorySchema.ResourceReservation.v1")','poke 10 3','poke 11 64')
need('ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10','HASH("DirectorySchema.ResourceReservation.v1")','bge r8 6 Overflow','and r1 r1 9','and r1 r1 18','HASH("StorageAccess.LArRE")','getd sp ra 23','getd r0 ra 12','bne r0 r13 Find','poke 8 r0','poke 16 r15')
if 'putd ' in txt('ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10'): result.fail('191 selector mutates reservations; quote must be read-only')
# Allocator revalidates semantic mirror generation, commits owner+epoch+action hints, and releaser is exact-owner/epoch only.
need('ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10','getd r0 r1 12','bne r0 ra Bad','get r0 d0 16','bne r0 r14 Bad','putd r1 17 r12','putd r1 18 r13','putd r1 19 ra','putd r1 25 r0','putd r1 26 r0','putd r1 27 r0','poke 13 r15')
need('ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10','getd r0 r1 17','bne r0 r12 Scan','getd r0 r1 18','bne r0 r13 Scan','putd r1 19 0','putd r1 25 -1','putd r1 26 0','putd r1 27 -1','poke 10 r15')
# Reserved movement requires same allocator owner, both plan epochs, current semantic reservation generations, committed action hints, and paired capacity.
need('ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10','blez r0 Stale','bne r0 r1 Stale','get r0 d1 18','bne r0 r10 Stale','get r0 d2 18','bne r0 r11 Stale',
 'get r0 d1 12','get r1 d1 19','bne r0 r1 Stale','get r0 d2 12','get r1 d2 19','bne r0 r1 Stale','get r6 d1 26','get r4 d1 25','get r5 d1 27',
 'get r0 d2 15','blt r0 r6 Capacity','get r0 d1 15','blt r0 r6 Capacity','poke 11 r3','poke 12 r4','poke 13 r6','put d0 31 r9','bne r0 r9 Wait')
before('ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10','poke 13 r6','put d0 31 r9')
# Chute/export source, direct storage, and SDB providers are generic Endpoint ABI1 variants.
need('ic10/material-grid/material_export_slot_endpoint_v1_0.ic10','poke 0 31415949','poke 13 1','HASH("ItemAccess.ExportSlot")','ls r5 d0 0 Quantity')
need('ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10','bgt r5 16 Bad','Scan:','ls r0 d0 r4 Occupied','ls r1 d0 r4 MaxQuantity')
# no yield in direct bounded scan body
body=txt('ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10').split('Scan:',1)[1].split('Bad:',1)[0]
if 'yield' in body: result.fail('196 direct storage scan yields inside bounded snapshot')
# SDB is explicitly lower-bound, dedicated, locked, and never pretends stack count is exact quantity.
need('ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10','poke 13 24','bne r0 1 Bad','get r7 db 21','l r4 d0 Quantity','mul r8 r4 r7','sub r9 600 r4','s d0 Lock 1')
# SDB feeder reuses Material Feeder ABI and exact Stacker metering after FIFO stack export.
need('ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10','poke 0 31415961','s d0 Lock 1','l r0 d0 Quantity','s d0 Open 1','l r0 d1 ImportCount','s d1 Setting r9','s d1 Output 0','poke 25 r6')
before('ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10','poke 24 0','poke 25 r6')
raise SystemExit(result.finish('Item storage contracts',[
 'ITEM storage uses one Generic Endpoint/Reservation model across Vending, LArRE, direct slots, chute export and SDB',
 'split reservation quotes are read-only; commits bind allocator identity/epoch, semantic mirror generation, and exact physical action hints',
 'physical LArRE movement requires current source and destination reservations before pickup and supports held-item recovery',
 'SDB inventory is conservative lower-bound while Stacker-backed dispense meters exact requested quantities']))
