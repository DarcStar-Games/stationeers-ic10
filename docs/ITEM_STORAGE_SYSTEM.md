# Generic Item Inventory & Storage Discovery

Item Storage is the physical-inventory layer used before manufacturing dependency planning. It answers four different questions without creating a warehouse-specific resource ABI:

1. **What ITEM resource is physically available, and where?**
2. **How much of it may a planner reserve without double-spending another job's stock?**
3. **Where is there reserved destination capacity?**
4. **Which specialized actuator can safely move the reserved material?**

The subsystem reuses Generic Resource Endpoint ABI1, Generic Resource Reservation ABI1, Generic Snapshot Directory, and `ASYNC_REQUEST_V1`. Vending, directly readable storage, Cargo-LArRE-accessible lockers, chute export slots, and dedicated SDB Silos therefore meet at one planning boundary while retaining different physical execution mechanisms.

## 1. Layering

```text
physical storage / chute source
       |
       +-- Vending ----------------------> 68 Endpoint
       +-- direct readable slots --------> 196 Endpoint
       +-- locker/passive slots -> LArRE -> 188 -> 189 Endpoint
       +-- Chute Export Bin slot --------> 195 Endpoint
       +-- dedicated SDB Silo -----------> 197 lower-bound Endpoint
                                             |
                                             v
                                  61 Generic Reservation
                                             |
                            190 Reservation Directory
                                             |
                    191 read-only split quote selector
                                             |
                    192 owner/epoch commit allocator
                              |              |
                       source reserve   destination reserve
                              |              |
                              +-------> 194 reserved LArRE move
                                             |
                         189 -> 188 -> physical Cargo LArRE

Dedicated SDB exact processor delivery:
197 lower-bound inventory -> reservation/planning
198 SDB+Stacker Feeder -> exact quantity -> existing Material Link/Executor
```

A planner never treats inventory discovery as physical authority. A physical move requires current reservations and a current Endpoint publication generation.

## 2. Common ITEM storage extension

Material ITEM Endpoints preserve the established material extension:

```text
S14  Resource Profile View ReferenceId
```

Storage-specific metadata uses high cells so it does not collide with that contract:

```text
S35  AccessKind
S36  PolicyFlags
S37  ReserveFloor, ITEM_QUANTITY held back from normal export
S38  FirstSourceSlot; -1 if not enumerable/available
S39  FirstSourceQuantity; 0 if not enumerable/available
S40  FirstEmptySlot; -1 if not enumerable/available
```

Current `AccessKind` values are:

```text
HASH("StorageAccess.Vending")
HASH("StorageAccess.LArRE")
HASH("StorageAccess.Direct")
HASH("StorageAccess.SDB")
HASH("ItemAccess.ExportSlot")
```

Policy flags:

```text
bit 0 (1)  DO_NOT_CONSUME        -> publish ExportAvailable = 0
bit 1 (2)  NO_IMPORT             -> publish ImportCapacity = 0
bit 2 (4)  PREFERRED_DESTINATION -> informational preference for later planners
bit 3 (8)  QUARANTINE            -> disable both export and import
```

`ReserveFloor` is subtracted from published export availability before policy gating. It is a stock-retention policy, not a reservation; transaction-specific ownership remains in Generic Resource Reservation.

## 3. Precision semantics

Generic Resource Endpoint precision flags now distinguish exact values from safe conservative lower bounds:

```text
bit 0  ExportAvailable exact
bit 1  ImportCapacity exact
bit 2  MaxRate exact/known
bit 3  ExportAvailable conservative lower bound
bit 4  ImportCapacity conservative lower bound
```

The ITEM reservation selector accepts exact or conservative lower-bound quantities. A lower bound is safe to reserve because it never promises more than is known to exist/can fit. It is **not** proof that no additional inventory exists.

This distinction is essential for SDB Silos: native `Quantity` is occupied-stack count, not total item quantity.

## 4. Generic Resource Reservation storage extension

`ic10/resource-grid-core/resource_reservation_v1_0.ic10` still mirrors Generic Resource Endpoint ABI1 in S2..S12. Item 7 uses formerly unused extension cells for allocator ownership:

```text
S13  build/plan epoch
S14  ReservedExport
S15  ReservedImport
S16  direction lock: 1 export, 2 import
S17  allocator/owner ReferenceId
S18  owner plan epoch
S19  semantic Reservation mirror generation captured by committed ownership
S20  Endpoint PublicationGeneration represented by the current semantic mirror
S21  opaque Endpoint AccessKind mirror
S22  opaque action hint 0 / FirstSourceSlot
S23  opaque action hint 1 / FirstSourceQuantity
S24  opaque action hint 2 / FirstEmptySlot
S25  committed action source slot
S26  committed action quantity
S27  committed action destination slot
```

`S12` is a **semantic** generation-last publication marker. `ic10/resource-grid-core/resource_reservation_v1_0.ic10` may observe a newer Endpoint S11 without advancing S12 when all reservation-relevant base fields and S21..S24 action hints are unchanged. This prevents harmless periodic inventory republishes from invalidating an already committed reservation.

When those semantics change, S12 advances. A committed allocator stores that exact S12 in S19 and snapshots the actionable slot/quantity hints into S25..S27. Movement therefore requires current `S12 == S19` and uses the committed hints. If a physical locker changes before the Reservation mirror refreshes, Cargo LArRE's exact proxy-slot ItemHash/Quantity check still fails before pickup; if a destination becomes occupied after commit, MOVE refuses to overwrite it and enters explicit held-item recovery if pickup has already occurred. `S20` retains the Endpoint publication identity represented by the semantic mirror for diagnostics.

## 5. Resource Reservation Directory

`ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` publishes `DirectorySchema.ResourceReservation v1` through the existing Generic Snapshot Directory infrastructure:

```text
[ResourceClass, ResourceType, ReservationReferenceId]
```

Geometry is width 3, capacity 64. The directory is used for inventory reservation planning, not as an ownership authority. Overflow is a hard planning failure.

## 6. Split reservation quote and commit

### 6.1 Selector — `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10`

The selector is read-only and supports up to six physical reservation legs.

Request:

```text
S11 ResourceType / ItemHash
S12 RequestedQuantity > 0
S13 Direction: 1 export, 2 import
S14 RequiredRoleMask; 0 means no additional role filter
S15 RequestToken, written LAST
```

Response:

```text
S16 ResponseToken, written LAST
S8  status: 1 complete quote, -1 invalid, -2 insufficient, -3 directory overflow
S9  QuotedTotal
S10 LegCount, 1..6 on success
S32..S49  up to six [ReservationRef, Amount, EndpointPublicationGeneration] legs
```

Selection rules:

- ResourceClass must be ITEM and ResourceType must match exactly;
- owned reservations are skipped;
- required roles and direction capability must match;
- export accepts precision bit 0 or bit 3;
- import accepts precision bit 1 or bit 4;
- existing reservations are subtracted;
- the Reservation mirror is revalidated while reading each leg;
- LArRE source withdrawal is whole-stack, so a selected LArRE source leg reserves the entire current `S39 FirstSourceQuantity`, even when that exceeds the remaining logical requirement;
- no more than six physical legs are quoted.

The selector never writes a Reservation.

### 6.2 Allocator — `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10`

The Selector, Allocator, Releaser, and reserved LArRE move client each publish
capability mask `32` (`HAS_ASYNC_REQUEST_V1`).

The allocator consumes one exact selector response. Before mutation it revalidates every Reservation and revalidates every quoted semantic Reservation generation. It then commits:

```text
owner ReferenceId
new PlanEpoch
ReservedExport or ReservedImport
DirectionLock
captured semantic Reservation generation and committed action hints
```

The selected quote's ResponseToken is rechecked immediately before mutation. The allocator may be superseded by another allocator only by overwriting ownership; any earlier physical consumer then fails its owner/generation fence rather than double-spending stock.

### 6.3 Releaser — `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10`

Release is owner-scoped. It clears only Reservations whose `S17 OwnerReferenceId` and `S18 OwnerEpoch` both match the requested owner/epoch. Numeric epoch equality from a different allocator is never treated as authority.

## 7. Cargo LArRE storage service

Program: `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`  
Magic: `HASH("LarreCargoStorageService.v1")`. `d0` is one Cargo LArRE.

One `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` service is the sole native writer for its arm. It owns rail-station movement (`Setting`), Cargo `TargetSlotIndex`, proxy slot 255 inspection, and `Activate`.

Request:

```text
S8  RequestToken LAST
S15 ExpectedQuantity for MOVE
S17 Operation: 1 SCAN, 2 MOVE, 3 RECOVER
S18 source station
S19 source slot / SCAN first slot
S20 SCAN slot count / destination station
S21 SCAN empty-slot MaxStack / destination slot
S22 ItemHash
```

Response:

```text
S9   Status
S10  SCAN ExportAvailable
S11  SCAN actionable ImportCapacity
S12  SCAN FirstSourceSlot
S13  SCAN FirstSourceQuantity / MOVE or RECOVER moved quantity
S14  ResponseToken LAST
S16  SCAN FirstEmptySlot
```

Current status values:

```text
 1  success
-1  native/action fault while hand is empty
-5  invalid/disconnected request
-6  fault while hand remains occupied; explicit recovery required
```

`MOVE` requires an initially empty hand and, immediately before pickup, revalidates `Occupied`, exact `OccupantHash`, and **exact expected Quantity**. A manual locker change therefore fails before pickup. Destination occupancy is checked after pickup; if the target is unexpectedly occupied, status `-6` leaves the held item explicit rather than hiding it.

`RECOVER` places a currently held item at a caller-supplied recovery station/slot. It does not perform a second pickup.

All results are `TERMINAL_RESPONSE`; S14 is written last.

## 8. LArRE ITEM Endpoint and serialized movement

`ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` publishes normal Generic Resource Endpoint ABI1 for one ITEM Resource Profile over one station/slot range.

Configuration:

```text
S20 StorageStation
S21 FirstSlot
S22 SlotCount
S36 PolicyFlags
S37 ReserveFloor
```

The Endpoint serializes its background SCAN and one raw movement stream to `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`; no other movement client should write that Cargo service. SCAN publishes S38/S39/S40 along with the normal Endpoint payload and generation.

Raw movement interface used by `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10`:

```text
S24 Cargo operation: 2 MOVE, 3 RECOVER
S25 source station
S26 source slot
S27 destination station
S28 destination slot
S30 expected quantity
S31 MoveRequestToken LAST
S32 MoveStatus
S33 MovedQuantity
S34 MoveResponseToken LAST
```

## 9. Reservation-authorized LArRE movement

`ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` is intended to be the sole movement client for one `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` Endpoint.

Wiring:

```text
d0  189 LArRE ITEM Storage Endpoint
d1  storage Generic Resource Reservation
d2  external Generic Resource Reservation
```

Configuration:

```text
S15 ExternalStation
S16 ExternalSlot
```

Request operations:

```text
1 OUTBOUND storage -> external/chute import
2 INBOUND  external/chute export -> storage
3 RECOVER  held item -> saved origin
```

For normal movement the client requires:

- storage Reservation belongs to the exact d0 Endpoint;
- both Reservations have the **same positive owner ReferenceId**;
- each Reservation matches its independently supplied PlanEpoch;
- source/sink ResourceType values match;
- direction locks are complementary;
- each Reservation still has `S12 == committed S19` on **both** sides;
- the source reservation covers the physical amount;
- the destination import reservation covers that same amount.

Only then is a raw MOVE published to `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10`.

Immediately before publication the client persists the physical origin station, slot, and quantity in S11..S13. Those values survive a same-housing IC restart and are used by operation 3 to recover a held item back toward its origin without creating another LArRE writer.

## 10. Storage providers

### 10.1 Vending — `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10`

Vending remains the preferred specialization when storage slots are directly visible. It scans slots 2..101, publishes exact export/import quantities, first matching source slot/quantity, first empty slot, policy gates, and ReserveFloor. Its existing `S14 ResourceProfileRef` is preserved.

### 10.2 Direct bounded slots — `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10`

For devices with ordinary readable slots, `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` scans a configured range of 1..16 slots **without yielding inside the scan**. This makes the small device-local snapshot atomic with respect to IC scheduling. It publishes exact availability/capacity and the common storage extension.

Physical movement remains provider-specific; direct readability does not imply a universal writable transport mechanism.

### 10.3 Exact export slot — `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10`

`ic10/material-grid/material_export_slot_endpoint_v1_0.ic10` publishes one device slot 0 as an exact source-only ITEM Endpoint. The intended first use is a Chute Export Bin or equivalent single-item handoff point. This gives inbound LArRE storage placement a reservable external source rather than treating chute arrival as unowned state.

### 10.4 Dedicated SDB Silo — `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10`

SDB exposes native `Quantity` as **number of occupied stacks**, not total quantity across those stacks. The framework therefore does not label SDB inventory exact.

Commissioning requires:

```text
S20 DedicatedResource = 1
S21 GuaranteedMinStackQuantity, 1..ResourceProfile.MaxStack
```

The Silo is locked against manual interaction while managed. Published bounds are:

```text
ExportAvailable lower bound = occupied_stacks * GuaranteedMinStackQuantity - ReserveFloor
ImportCapacity lower bound  = (600 - occupied_stacks) * ResourceProfile.MaxStack
precision = bits 3 + 4 = 24
```

The dedicated-resource assertion is operational policy: all stacks placed in that managed SDB must be the configured ResourceType. `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` cannot prove internal per-stack identity because the native API does not expose those 600 stacks individually.

A lower-bound Endpoint is safe for reservation, but absence of a reservation quote is not proof that no additional material exists. Item 8 dependency planning must account for precision: it may manufacture only the unresolved **known deficit** and should exhaust/probe a managed lower-bound source before concluding that additional production is required when that distinction matters.

## 11. Exact SDB delivery through the existing feeder ABI

`ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` uses the same Material Feeder ABI1 magic (`HASH("StackerFeeder.v1")`) already consumed by Material Resource Link/Executor. It does not introduce a second manufacturing transfer architecture.

Wiring:

```text
d0 dedicated SDB Silo
d1 Stacker
d2 target ITEM Resource Profile View
```

For a request it locks the SDB, exports one FIFO stack at a time using `Open`, waits for Stacker ImportCount to advance, and repeats until the held Stacker quantity is at least the requested quantity. The Stacker then meters the **exact requested quantity** to Output0. Thus SDB aggregate discovery may remain conservative while processor delivery remains exact.

The SDB documentation currently describes `Open` as an action that returns to its default after action; the feeder also fences each action with Stacker ImportCount rather than assuming a fixed transfer delay.

## 12. Failure and concurrency invariants

Item Storage considers these non-negotiable:

1. Inventory discovery is never ownership.
2. A quote is read-only.
3. Mutation occurs only after every quote leg is revalidated.
4. Reservation owner **ReferenceId + epoch** is the authority; epoch alone is insufficient.
5. Physical movement additionally fences the **live Endpoint publication generation** captured at commit.
6. LArRE whole-stack pickup reserves the physical stack quantity, even when that over-satisfies a logical requirement.
7. Destination capacity is reserved before pickup.
8. A manually changed stack fails exact pre-pick quantity validation.
9. A post-pick destination failure is represented as a held-item fault and requires explicit recovery.
10. Only one serialized request chain owns a Cargo LArRE.
11. SDB stack count is never mislabeled as exact item quantity.
12. Exact processor delivery remains downstream in the Stacker/Material Feeder boundary.

`validation/validators/validate_item_storage_contracts.py` checks static conformance. `tests/test_item_storage_protocol.py` adversarially covers split quotes, whole-stack over-reservation, stale Endpoint generations, owner collisions, paired destination capacity, manual mutation, held-item recovery, inbound chute placement, exact owner release, SDB lower-bound math, and exact Stacker metering.

## 13. Roadmap boundary

Item 7 supplies inventory visibility, ownership, and physical movement primitives. Item 8 may now add dependency planning, but it must consume this layer rather than inventing a second inventory table or treating “not found in one storage device” as “must manufacture.”

See `docs/SOURCES.md` for native LArRE, chute, locker, SDB, and Stacker provenance.
