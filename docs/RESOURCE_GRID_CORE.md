# Generic Resource Grid Core

The pressure-grid work exposed a set of control-system concepts that are not specific to pressure, gases, or phase change. This document defines those concepts explicitly so fluids, stored materials, manufacturing inputs/outputs, and eventually electrical power can share the same planning vocabulary without pretending their physical behavior is identical.

The design rule is:

> **Generalize contracts and transaction semantics first. Keep physical implementations specialized.**

`ControllerPhasePressure`, `ControllerPressureDomain`, gas inventory, pumps, and the pressure router remain pressure-specific. The new Resource Core sits above those services as a normalized planning surface.

## 1. Universal resource model

A resource-planning problem has four recurring elements:

```text
RESOURCE ENDPOINT
    what resource exists here?
    how much can leave?
    how much can enter?

RESOURCE RESERVATION
    what portion of that capacity is already promised?

RESOURCE LINK
    what real physical path connects two reservations?
    how quickly can it move the resource?

RESOURCE TRANSFORM
    what inputs can a processor convert into what outputs?
```

The first three are already present in the pressure grid under pressure-specific names. The fourth is required for ore processing and manufacturing.

## 2. Resource classes and units

The Generic Resource Endpoint ABI does not assume all quantities are interchangeable.

Current resource classes:

| Value | ResourceClass | Typical ResourceType | Unit |
|---:|---|---|---|
| 1 | `FLUID` | working-medium hash | moles |
| 2 | `ITEM` | Stationeers ItemHash | item/stack quantity |
| 3 | `REAGENT` | reagent hash | grams/reagent quantity |
| 4 | `POWER` | normally one electrical service class | watts |
| 5 | `ENERGY` | battery/storage identity | joules |

Current unit identifiers:

| Value | Unit |
|---:|---|
| 1 | mole |
| 2 | item quantity |
| 3 | reagent quantity / gram-equivalent |
| 4 | watt |
| 5 | joule |

The ABI carries both `ResourceClass` and `Unit` because identical numeric values must never make moles, item quantities, watts, or joules appear substitutable.

## 3. Generic Resource Endpoint ABI v1

Magic: `HASH("ResourceEndpoint.v1")`

```text
S0   magic = ResourceEndpoint.v1
S1   ABI = 1
S2   capability mask = 0
S8   status; >0 usable, <0 invalid/unavailable
S9   NativeProvider ReferenceId
S10  NativeGeneration / native snapshot identity
S11  PublicationGeneration; payload written first, generation LAST
S12  Unit
S13  precision flags
S52  ResourceClass
S53  ResourceType
S54  role/capability bitmask
S55  ExportAvailable
S56  ImportCapacity
S57  MaxRate; 0 means unknown/not represented at endpoint layer
```

Role bits:

```text
bit 0 = export/source capable
bit 1 = import/sink capable
bit 2 = storage/buffer semantics
```

Common values:

```text
1 = source only
2 = sink only
3 = source + sink
7 = source + sink + storage
```

Precision flags use:

```text
bit 0 = ExportAvailable exact for this snapshot
bit 1 = ImportCapacity exact for this snapshot
bit 2 = MaxRate exact/known
bit 3 = ExportAvailable conservative lower bound
bit 4 = ImportCapacity conservative lower bound
```

Exact and lower-bound values are both safe reservation inputs, but they are not equivalent facts. A lower bound proves at least that much resource/capacity exists; it does not prove that no additional amount exists.

The generation-last rule is mandatory. Consumers that combine endpoint fields capture `S11`, read the payload, then require the same positive `S11` afterward.

## 4. Pressure specialization

`ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` maps the hardened `PressureDomain Inventory ABI2` into the generic endpoint contract.

Mapping:

```text
Pressure medium             -> ResourceType
moles                       -> Unit MOLE
LOW                          -> source
HIGH                         -> sink
STORAGE                      -> source + sink + storage
ExportableMoles              -> ExportAvailable
ImportCapacityMoles          -> ImportCapacity
Inventory ReferenceId        -> NativeProvider
Inventory generation         -> NativeGeneration
```

No existing PressureGrid service consumes this adapter yet. This is intentional: the current hardened pressure scheduler remains the proven production specialization while the generic layer matures alongside it.

## 5. Generic Resource Reservation ABI v1

Magic: `HASH("ResourceReservation.v1")`

The reservation service mirrors one Generic Resource Endpoint into a stable mutable planning surface.

```text
S0   magic = ResourceReservation.v1
S1   ABI = 1
S2   capability mask = 0
S8   MaxRate
S9   endpoint status
S10  Unit
S11  precision flags
S12  mirror generation; payload written first, generation LAST

S13  build/transaction epoch; allocator-owned
S14  ReservedExport; allocator-owned
S15  ReservedImport; allocator-owned
S16  direction lock; allocator-owned
S17  allocator/owner ReferenceId
S18  owner plan epoch
S19  semantic Reservation mirror generation captured by committed ownership
S20  Endpoint PublicationGeneration represented by the current semantic mirror
S21..S24  opaque Endpoint action-hint mirror used by ITEM storage
S25..S27  allocator-committed action hints
S28..S31  opaque Endpoint slot-hint mirror
S32  Generic Resource Endpoint ReferenceId
S33  ResourceClass
S34  ResourceType
S35  role/capability bitmask
S36  ExportAvailable
S37  ImportCapacity
```

`S12` is the Reservation's semantic generation-last publication marker. `ic10/resource-grid-core/resource_reservation_v1_0.ic10` observes Endpoint `S11`, but advances S12 only when reservation-relevant base fields or the mirrored action hints actually change. This prevents harmless identical endpoint republishes from invalidating ownership. A committed Item Storage allocator stores S12 in S19 and snapshots the action hints; movement requires current `S12 == S19`. Native actuators still perform their own final physical checks.

`ic10/resource-grid-core/resource_reservation_v1_0.ic10` contains no pressure magic or pressure-role knowledge. The same service can therefore mirror a fluid endpoint or a material endpoint.

The pressure scheduler still uses its hardened pressure-specific Reservation/Allocator ABI. MaterialGrid uses the same Generic Resource Reservation cells through Multi Material Allocator ABI2, which stages one to three exact-quantity ITEM routes and publishes one shared commit epoch. A single cross-domain Generic Resource Allocator should still be promoted only after more discrete-material cases prove which admission semantics are truly universal across continuous flow and item batches.

## 6. Generic Resource Link ABI v1

Magic: `HASH("ResourceLink.v1")`

```text
S0   magic = ResourceLink.v1
S1   ABI = 1
S2   capability mask = 0
S8   generic cost hint; 0 when the specialization has no normalized value
S9   status
S10  NativeLink ReferenceId
S11  NativeLink generation
S12  PublicationGeneration; written LAST
S13  link flags
S28  source Generic Resource Reservation ReferenceId
S29  sink Generic Resource Reservation ReferenceId
S30  ResourceClass
S31  ResourceType
S32  native route/link class
S33  current maximum transferable resource units/tick
```

`ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` is the first implementation. It verifies that its generic source/sink Reservations ultimately resolve to the same PressureDomain Inventories used by the native PressureTransfer before publishing the generalized link.

`ic10/material-grid/material_resource_link_v1_0.ic10` is the second and physically unrelated implementation. It publishes a Vending/Stacker/Logic-Sorter route through the same Generic Link ABI while keeping material-specific topology in extension cells. It verifies that the source/sink Reservation identities, their Endpoint identities, the Feeder, Grant Guard, Executor, Vending source, and destination remain coherent before publishing the route.

In both specializations, topology binding prevents the generic graph from claiming a route whose endpoints or physical execution path disagree with the native controller that will actually move the resource.

## 7. Resource discovery plane

Resource services are not forced into Controller Directory. This prevents a future material/power grid from consuming controller-discovery capacity or pretending every resource service is a configurable controller.

`ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10` discovers Generic Resource Endpoints and feeds `[ResourceClass, ResourceType, ReferenceId]` candidates to `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`. The shared Host owns sorted double-buffered 64x3 publication and explicit overflow.

`ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` discovers Generic Resource Links and feeds ReferenceId candidates to the same Generic Snapshot Directory Host. The published record stores only the Link ReferenceId because each Link ABI already publishes source/sink/type/rate metadata coherently.

`ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` publishes `DirectorySchema.ResourceReservation v1` as `[ResourceClass, ResourceType, ReservationReferenceId]`, width 3, capacity 64. Item Storage uses that directory for read-only multi-location quote selection; the directory is discovery, not ownership authority.

All directories use the same principle as Controller Directory: a snapshot that overflows is visibly incomplete and must not be treated as authoritative by a future planner.

## 7a. Item storage specializations

Item 7 completes a storage-mechanism-neutral ITEM inventory layer behind Generic Resource Endpoint/Reservation:

- `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10`: exact Vending storage;
- `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` over sole-arm owner `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`: exact LArRE-accessible passive storage plus serialized whole-stack movement;
- `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10`: exact bounded directly readable slots;
- `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10`: exact one-slot source such as a chute export handoff;
- `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10`: dedicated SDB conservative lower-bound inventory/capacity.

Material ITEM Endpoints preserve `S14 ResourceProfileViewRef`. Storage metadata uses S35..S40: AccessKind, PolicyFlags, ReserveFloor, FirstSourceSlot, FirstSourceQuantity, and FirstEmptySlot. Policy flags support DO_NOT_CONSUME, NO_IMPORT, PREFERRED_DESTINATION, and QUARANTINE.

`ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` quotes up to six matching ITEM Reservations without mutation; `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` commits one coherent quote with owner identity/epoch and semantic mirror generation and committed physical action hints; `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` releases only exact owner+epoch. `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` will not start a LArRE pickup until both source and destination reservations are current and cover the physical stack quantity. Manual source mutation is rejected by both semantic Reservation-generation fencing and `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`'s exact pre-pick quantity check. A post-pick obstruction is an explicit held-item fault recoverable through the persisted origin path.

SDB native `Quantity` is occupied-stack count, so `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` deliberately publishes precision bits 3/4 lower bounds rather than false exact quantities. `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` reuses Material Feeder ABI1 to export FIFO stacks into a Stacker and meter the exact requested processor quantity.

See `docs/ITEM_STORAGE_SYSTEM.md`.

## 8. Resource Transform Profile ABI v3

Magic: `HASH("ResourceTransformProfileView.v4")`

A transfer preserves resource identity. A transformation changes it. The current Profile ABI is declarative but is now consumed by both compact and generic executable paths.

Examples:

```text
Iron Ore -> Arc Furnace -> Iron Ingot
Iron Ore + Coal -> Furnace -> Steel
Steel + Copper + Cobalt -> Advanced Furnace -> Astroloy
materials -> printer -> manufactured item
```

`ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` publishes
its identity in the common `S0`/`S1` header cells (magic = ResourceTransformProfileView.v4, ABI = 4)
and serves resolved requests through the `S68..S75` mailbox:

```text
S8..S31   input descriptors, 1..6 slots available
S32..S63  output descriptors, current execution path requires 1
S64..S67  pressure/temperature bounds
S68  request echo
S69  resolve status (1 = resolved)
S70  TransformType request cell, written by the consumer
S71  RequiredCapabilityMask; -2/-3 publish resolution errors
S72  InputCount
S73  OutputCount
S74  coherent publication generation
S75  condition flags
```

Each four-cell resource descriptor is `[ResourceClass, ResourceType, Unit, Quantity]`. Capability bits are `SMELT_BASIC=1`, `FURNACE_ALLOY=2`, and `ADVANCED_ALLOY=4`; Arc Furnace advertises `1`, Furnace `3`, and Advanced Furnace `7`. The current catalog contains 17 transforms: seven basic smelts, five base alloys, and five advanced alloys/superalloys.

The programs under `ic10/material-transform/` are the only current furnace execution path. They execute one-, two-, and three-input ITEM transforms through condition-aware admission, route resolution, atomic reservation staging/commit, synchronized delivery, and coherent output confirmation. Pressure and temperature bounds are transform requirements: Admission enforces the declared bounds on Arc Furnace, Furnace, and Advanced Furnace alike rather than inferring condition semantics from processor class. The Profile remains the declarative source of process requirements; execution services own live machine and transaction state.

## 9. Why transformation is not a funny kind of link

A physical link answers:

> Can X move from A to B?

A transformation answers:

> Can processor P consume X and produce Y under a set of conditions?

Those have different invariants. A manufacturing transaction may need to atomically reserve several inputs, output capacity, processor capacity, and power before execution begins. Encoding that as a link would hide the very resource dependencies the scheduler needs to reason about.

## 10. Generic transaction rules

The Resource Core inherits the hardened rules that proved useful in PressureGrid:

1. **payload first, generation last** for observable multi-cell snapshots;
2. **quote before mutation** when determining whether a reservation is feasible;
3. **exact commit** after a common quantity/rate is selected;
4. **identity binding** between reservations and the physical topology that will execute them;
5. **commit authority is separate from execution ownership**;
6. failures bias toward **under-utilization**, never over-allocation;
7. a ResourceType/ResourceClass/Unit mismatch is a hard incompatibility, not a conversion opportunity.

## 11. Current proof of generality

The contract is no longer pressure-only because two unrelated physical systems now publish the same Endpoint ABI:

```text
PressureDomain Inventory
        |
Pressure Endpoint Adapter
        |
        +---- Generic Resource Endpoint ABI1

Vending Machine + Item Profile
        |
Material Vending Inventory
        |
        +---- Generic Resource Endpoint ABI1
```

Both can feed the same `ic10/resource-grid-core/resource_reservation_v1_0.ic10` without changes.

The Link contract has distinct physical implementations in `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` and `ic10/material-grid/material_resource_link_v1_0.ic10`. Material transforms use the single generic transaction chain Admission -> Link Resolver -> Multi Reservation Stager -> Material Allocator ABI2 -> Generic Transform Runtime. Movement preserves resource identity; the Transform changes the reserved inputs into the declared output and confirms it through coherent Resource Reservation state.

The direct IC10 execution harness verifies pressure/material endpoint cases, a complete committed material batch, capability-based one-to-three-input transforms across the supported furnace classes, output confirmation, and interruption/reflash behavior.

## 12. What remains specialized

The following remain deliberately specialized:

- pressure-domain thermodynamics;
- gas purity;
- volume-pump control;
- Vending/Stacker/Logic-Sorter batch preparation and delivery confirmation;
- printer-specific physical execution details behind the generic manufacturing driver;
- furnace-specific physical process behavior beyond the catalog-declared pressure/temperature/capability contract;
- electrical load shedding and transformer behavior.

The generic layer should describe **requirements, capacities, reservations, identity, and topology**. It should not erase physical rules.

## 13. Current progression boundary

The reusable resource/manufacturing substrate is now implemented through queue-driven TRANSFORM/PRINT execution:

```text
Generic Resource Endpoint/Reservation/Link          DONE
Material warehouse inventory                       DONE
Exact material link + Multi Material Allocator ABI2 DONE
Capability-based 1..3-input transform runtime      DONE
Printer directory + Recipe execution metadata      DONE
Manufacturing scheduler + capacity/readiness       DONE
        |
Bounded dependency planner                         COMPLETE
        |
Power endpoint/link specialization
        |
Cross-resource admission transaction
```

Live-game material hardening remains an evidence task alongside these roadmap milestones rather than a missing architecture layer.

The cross-resource transaction is the long-term payoff. A manufacturing job should eventually commit only after material inputs, output storage, processor availability, and power have all been admitted.

## Item 9 proof of generality

Power management now exercises the same Resource Profile / Endpoint / Reservation / Link / Directory / Job concepts for watts and joules. Producer supply, consumer demand, bidirectional batteries, transformer overhead, load shedding, coherent dispatch epochs, and finite POWER jobs are implemented under the semantic `ic10/power-grid/` and `ic10/power-jobs/` families; see `docs/POWER_MANAGEMENT.md`. This is the primary evidence that ResourceGrid is not accidentally material-specific. Item 10 broad interruption/fault injection is complete, and Item 12 live-game commissioning is the current active milestone.


## 14. Cross-domain ProcessCondition

Item 11 adds one concept above Resource Endpoint/Reservation/Link/Transform: a process may require an environmental/utility **condition** that is neither inventory nor mutation authority. `ProcessCondition ABI1` (`HASH("ProcessCondition.v1")`) carries target identity, semantic FLUID ResourceType, pressure/temperature windows, live unmet bits, strategy, status, and generation.

The distinction is important:

```text
Resource Endpoint/Reservation/Link  -> owns/authorizes resource capacity and movement
Resource Transform                 -> changes typed resource identity
ProcessCondition                   -> declares/verifies what a physical process needs
```

A prepared H2/O2 mixture demonstrates why these must stay separate. The Gas Mixer changes pure-gas ResourceTypes into `Fuel.H2O2`, so it is a type-changing utility producer rather than a Generic Resource Link. Once prepared, the mixture is an ordinary FLUID resource and PressureGrid can inventory/reserve/route it unchanged.

`ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` proves a ProcessCondition target can project into PressureDomain ABI2; `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` proves an Advanced Furnace embedded pump can project into PressureTransfer ABI2 under the existing GrantGuard. The process contract never carries reservation ownership. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.
