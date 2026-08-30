# Material Transfer System

This document describes the physical exact-batch ITEM transfer leg used by the current MaterialGrid transform executor. The framework has **one current material commit authority**: `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`. The removed serialized allocator and Arc-Furnace-only transaction path are not part of this baseline.

The transport problem differs from pressure flow. A pump can be granted a mol/tick rate for many ticks; items move as discrete stacks, and a Vending Machine may eject a larger stack than one transform requires. MaterialGrid therefore separates **reservation**, **exact-batch preparation**, **grant activation**, **physical release**, and **destination confirmation**.

## 1. Components

The physical material leg is built from:

- `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` — coherent ITEM source inventory;
- `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` — processor/import destination Endpoint;
- `ic10/resource-grid-core/resource_reservation_v1_0.ic10` — generic source/sink reservation surfaces;
- `ic10/material-grid/material_resource_link_v1_0.ic10` — route identity and topology publication;
- `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` — exact-batch preparation/release;
- `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` — validates one committed Allocator ABI2 epoch;
- `ic10/material-grid/material_transfer_executor_v1_0.ic10` — releases a prepared batch and confirms arrival;
- `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` — provisionally stages every transform input;
- `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` — sole current ITEM commit authority.

Transform orchestration is completed by `ic10/material-transform/material_transform_admission_v1_0.ic10`, `ic10/material-transform/material_transform_link_resolver_v1_0.ic10`, and `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10`. See `docs/ORE_PROCESSING_TRANSFORMS.md` for the complete transform lifecycle.

## 2. Physical route and wiring

A normal physical route is:

```text
Vending Machine -> Stacker -> Logic Sorter -> processor/import sink
```

### Feeder

`ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10`

```text
d0 -> Vending Machine
d1 -> Stacker
d2 -> Logic Sorter
```

The Feeder prepares an exact requested batch even when Vending emits a larger physical stack.

### Material Resource Link

`ic10/material-grid/material_resource_link_v1_0.ic10`

```text
d0 -> source Generic Resource Reservation
d1 -> sink Generic Resource Reservation
d2 -> Material Feeder
d3 -> Material Grant Guard
d4 -> Material Transfer Executor
```

Generic Link `S2/S3` are the **source/sink Reservation ReferenceIds**. Native Vending, Stacker, Sorter, and sink identities remain separate extension fields. Endpoint ReferenceIds must not be substituted for Reservation ReferenceIds because the transaction services mutate reservation state.

### Grant Guard

`ic10/material-grid/material_transfer_grant_guard_v1_0.ic10`

```text
d0 -> Material Resource Link
d1 -> Multi Material Reservation Allocator ABI2
d2 -> Material Transfer Executor
```

The Guard additionally dereferences the staged source and sink Reservations by ReferenceId.

### Transfer Executor

`ic10/material-grid/material_transfer_executor_v1_0.ic10`

```text
d0 -> Material Resource Link
d1 -> Material Feeder
d2 -> Material Grant Guard
```

The sink native device is obtained from the Link and is used to observe destination `ImportCount`.

## 3. Current reservation and commit protocol

Direct user-facing transfer jobs do not have a separate allocator protocol in the current baseline. Material allocations are created by the generic transform path:

```text
161 Admission
      |
162 Link Resolver
      |
163 Multi Reservation Stager
      |
164 Multi Material Reservation Allocator ABI2
      |
81 Grant Guards -> 77 Executors -> 82 Feeders
      |
165 Generic Material Transform Runtime
```

Runtime submits to Allocator ABI2:

```text
S8   BatchCount
S20  Runtime ReferenceId
S21  RequestGeneration
```

The Allocator validates a stable Link Resolver publication, allocates a new candidate epoch, and commands the Stager to prepare all one-to-three inputs.

For each input quantity `Q`, the Stager provisionally writes:

```text
source Reservation S13 = epoch
source Reservation S14 = Q
source Reservation S16 = export lock

sink Reservation S13 = epoch
sink Reservation S15 = Q
sink Reservation S16 = import lock
```

It also stages the Guard with the exact quantity, epoch, Allocator identity, source/sink Reservation identities, ResourceType, Feeder, Sorter, sink native provider, Link, and Executor.

Only after **every input** stages successfully does Allocator ABI2 write its common active epoch to `S14` **last**. That is the transaction commit point.

```text
stage input 1 reservation + Guard
stage input 2 reservation + Guard
stage input 3 reservation + Guard
verify resolver generation still matches
        |
        v
Allocator S14 = common epoch   <-- COMMIT LAST
```

If any input fails before commit, the Stager clears all partial source/sink reservations and no active epoch is published.

## 4. Grant Guard invariants

The Guard requires Material Allocator identity `HASH("MultiMaterialReservationAllocator.v2")` with **ABI2 exactly**. It never trusts a matching epoch alone.

Before activation it verifies that staged identity still matches the live Link and execution path:

- Allocator ReferenceId;
- source Resource Reservation;
- sink Resource Reservation;
- ResourceType;
- Feeder;
- Logic Sorter;
- sink native device;
- Material Link;
- Transfer Executor;
- source/sink Reservation publication health.

It activates only when its staged epoch equals the Allocator's committed `S14` epoch. If identity changed after staging, the Guard consumes that epoch as invalid; restoring previous wiring later cannot resurrect it.

This prevents partially staged or topology-stale material from being released.

## 5. Feeder state machine

The Feeder is an `ASYNC_REQUEST_V1 / LIVE_CURRENT` service. Executor publishes ResourceType/quantity/release-reset first and request epoch `S18` last. Feeder resets request status, initializes the new physical preparation state, and publishes current epoch `S7` last; even an immediate device fault binds that epoch before the caller consumes the fault. Transfer Executor requires `Feeder S7 == active grant epoch` before reading Feeder status, so stale ready/emitted/fault state from the prior batch is ignored.

The Feeder's active lifecycle is:

```text
IDLE
  |
  v
FILL
  |
  v
WAIT_IMPORT
  |       \
  |        -> FILL until enough target material is buffered
  v
READY
  |
  | Executor publishes release epoch
  v
WAIT_EXPORT
  |
  v
IDLE with EmittedEpoch published
```

### FILL / WAIT_IMPORT

The Feeder examines Stacker slot 2. If insufficient target material is buffered, it snapshots Stacker `ImportCount`, requests the ItemHash from Vending, and waits for a changed import counter before reevaluating the buffer.

The Logic Sorter filter is rebuilt for the requested resource before filling. IC10 still cannot infer invisible chute connectivity; commissioning must ensure the sorter's accepted route actually reaches the intended processor.

### READY

Once at least the requested quantity is buffered:

```text
ReadyEpoch = RequestEpoch
Status = READY
```

Prepared material is not released merely because it is ready.

### RELEASE

The Executor first snapshots destination `ImportCount` and then writes the release epoch to Feeder `S19`. The Feeder programs the Stacker for the exact requested quantity and waits for Stacker `ExportCount` to change.

If Vending emitted 20 Iron Ore for a committed request of 10:

```text
Vending emits 20
       |
Stacker buffers 20
       |
Executor releases exact 10
       |
Stacker retains 10
```

The retained amount is visible through Link extensions but is not yet promoted to a separate planning Endpoint.

## 6. Why destination ImportCount is captured before release

The required ordering is:

```text
snapshot sink ImportCount
        |
release exact Stacker batch
        |
wait for Feeder EmittedEpoch
        |
wait for sink ImportCount != snapshot
```

A short chute can deliver an item before the Executor observes a later snapshot. Capturing the counter **before** release makes both fast and slow physical delivery observable and prevents a false timeout after a successful delivery.

## 7. Transfer Executor lifecycle

Executor state `S9`:

```text
0 IDLE
1 WAIT_READY
2 WAIT_EMIT
3 WAIT_SINK
```

For one valid Guard grant the Executor:

1. requests ResourceType, exact quantity, and epoch from the Feeder;
2. waits for matching `ReadyEpoch`;
3. snapshots destination `ImportCount`;
4. issues the release epoch;
5. waits for matching `EmittedEpoch`;
6. waits for destination `ImportCount` to change;
7. publishes completed epoch and observed ITEM_QUANTITY/tick.

A Feeder fault terminates the Executor immediately rather than waiting for the global transfer timeout.

## 8. Material Link extensions

Generic Resource Link ABI1 remains `S0..S13`. Material Link adds:

```text
S14  Material Grant Guard ReferenceId
S15  Material Transfer Executor ReferenceId
S16  Material Feeder ReferenceId
S17  current Feeder buffer quantity
S18  current Feeder buffer ResourceType
S19  source Vending ReferenceId
S20  Stacker ReferenceId
S21  Logic Sorter ReferenceId
S22  sink native provider ReferenceId
S23  Executor completed epoch
S24  Executor execution status
S25  observed achieved ITEM_QUANTITY/tick
S26  Executor elapsed ticks
```

These cells are material-domain execution metadata. Generic Resource consumers must not require them unless they intentionally implement ITEM transport.

## 9. Completion and cleanup

Allocator ABI2 watches every resolved Link for `S23 == common epoch`. It does not complete the material allocation until **all** input Executors report that epoch.

After completion—or after cancellation/failure—the Allocator clears its active `S14` before commanding the Stager to clean the provisional reservation cells. The completed epoch is recorded separately in Allocator `S15`.

The transform Runtime does not activate the processor until the material allocation has committed and every required input Link has completed the common epoch.

## 10. Failure behavior

The path favors stopping over guessing. Examples include:

- missing Feeder/Stacker/Sorter/Guard/Executor -> Link unusable;
- ResourceType mismatch -> route cannot satisfy the transform input;
- insufficient source quantity or sink capacity -> Stager rollback;
- any failed input in a multi-input job -> all partial reservations cleared, no commit epoch;
- topology/identity change after staging -> Guard consumes epoch;
- wrong buffered item -> Feeder fault;
- no Vending-to-Stacker arrival -> Feeder fault;
- no Stacker export -> Feeder fault;
- no destination import after emission -> Executor fault/timeout;
- stale Resource Link directory or overflow -> Resolver cannot authorize the transform route.

## 11. Reflash and interruption behavior

The Feeder uses a persistent marker in `S31` and preserves its in-flight prepared batch across same-service reflash. Grant Guard records consumed epochs so a previously invalid/used transaction cannot activate twice.

Allocator ABI2 publishes no committed `S14` until staging succeeds. This gives interruption handling a clear boundary:

```text
before S14 commit -> partial staging may be rolled back
at/after S14      -> exact committed epoch is authoritative
```

The broader fault-injection roadmap item will systematically exercise every transition, but the current transfer path already fails closed at its commit and release boundaries.

## 12. Commissioning checklist

Before enabling automatic material transforms:

1. verify source and sink Reservations publish ResourceClass ITEM, the same ResourceType, and unit ITEM_QUANTITY;
2. verify source export availability and sink import capacity are positive;
3. verify Link `S28/S29` are Reservation ReferenceIds, not Endpoint ReferenceIds;
4. verify Link `S19..S22` identify the intended Vending, Stacker, Sorter, and processor/import sink;
5. verify Guard `d1` points to `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` and observes ABI2;
6. verify the physical accepted chute route from Sorter reaches the intended sink;
7. publish the Link through the Generic Snapshot Resource Link directory;
8. request a transform whose required quantity is smaller than a source stack and confirm excess remains buffered;
9. confirm destination `ImportCount` changes and Executor publishes the committed epoch;
10. change a staged topology identity before commit and confirm Guard consumes/rejects the epoch;
11. force one input of a multi-input transform to fail and confirm no Allocator `S14` commit is published and earlier reservations are cleared;
12. jam the chute/no-delivery path and confirm the transfer faults rather than reporting false completion.

## 13. Current scalability boundary

Allocator ABI2 supports up to **three input Links in one atomic transform transaction**, matching the current Resource Transform schema. It serializes one material transform allocation per Allocator instance.

The Generic Job ABI now defines TRANSFER intent and the common lifecycle, but the current substrate still does not provide the Manufacturing Scheduler that resolves a TRANSFER job into source/sink Reservations and a physical Link, nor dependency DAG planning or arbitrary parallel material traffic. Those remain scheduler/planner work instead of adding another material-specific allocator protocol.

## Warehouse inventory and SDB feed integration

Item 7 now supplies a complete reservation-authorized warehouse boundary rather than only a LArRE extraction primitive. Vending, direct-slot, LArRE-accessible storage, chute export slots, and dedicated SDB Silos all publish Generic ITEM Resource Endpoints and are mirrored by Generic Resource Reservations. The Item Resource Reservation Selector/Allocator can split a requirement across up to six physical Reservations; ownership is bound to allocator ReferenceId + epoch + semantic Reservation generation plus committed physical action hints.

For LArRE movement, `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` requires both source and destination reservations before issuing a raw movement request through `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` to sole-arm owner `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`. The common path therefore supports both locker -> chute intake and chute export -> locker placement. Whole-stack LArRE extraction remains warehouse transport; exact transform quantity is still metered downstream.

Dedicated SDB Silos use a different physical specialization. `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` advertises conservative lower-bound inventory because native SDB `Quantity` is occupied-stack count, not total per-stack item quantity. `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` deliberately exposes the existing Material Feeder ABI1: it exports FIFO SDB stacks one at a time into a Stacker until enough quantity is buffered, then the Stacker emits exactly the requested committed quantity. Existing `76/77/81` Link/Executor/Grant semantics therefore remain the exact processor-delivery boundary.

See `docs/ITEM_STORAGE_SYSTEM.md`.
