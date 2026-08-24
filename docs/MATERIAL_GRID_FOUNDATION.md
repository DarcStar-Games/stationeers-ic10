# MaterialGrid Foundation

MaterialGrid is the ITEM specialization of the Generic Resource Core. It reuses Resource Profiles, Endpoints, Reservations, Links, directories, transform catalogs, and transaction invariants rather than defining a second control framework for solid materials.

## 1. Current components

The current material path includes:

- `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` — coherent warehouse/vending inventory;
- `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` — processor/import destination endpoint;
- `ic10/resource-grid-core/resource_reservation_v1_0.ic10` — generic Resource Reservation for source and sink capacity;
- `ic10/material-grid/material_resource_link_v1_0.ic10` — material route identity/topology;
- `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` — exact-batch source preparation;
- `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` — committed-epoch gate;
- `ic10/material-grid/material_transfer_executor_v1_0.ic10` — batch release and destination confirmation;
- `ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10` — Resource Endpoint discovery adapter;
- `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` — Resource Link discovery adapter;
- `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` — transform catalog view;
- `ic10/material-transform/material_transform_admission_v1_0.ic10`;
- `ic10/material-transform/material_transform_link_resolver_v1_0.ic10`;
- `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10`;
- `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`;
- `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10`.

There is no separate legacy serialized Material Allocator or Arc-Furnace-only runtime in the current baseline.

## 2. Generic contracts

MaterialGrid uses the same generic resource contracts as pressure/fluid routing:

```text
Resource Profile
Resource Endpoint
Resource Reservation
Resource Link
Directory Adapter
Generic Snapshot Directory
Resource Transform Profile
```

`ResourceClass=ITEM` and the ITEM unit/role conventions specialize semantics without changing the core identity and reservation model.

## 3. ITEM profiles

Material profiles live in the unified Resource Profile catalog. A profile provides the resource identity, class, unit, and domain metadata required by inventory/endpoints/transform descriptors.

The Generic Resource Profile View resolves those records exactly as it resolves fluid profiles. Material code does not carry an independent material-profile ABI.

## 4. Warehouse inventory

`ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` scans vending slots and publishes a coherent snapshot of available material quantity. It records the source native device identity separately from generic Resource Reservation identity.

A source Reservation mirrors this inventory and exposes the generic quantity/capacity/health fields consumed by Links and transaction services.

## 5. Processor import endpoint

`ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` publishes an ITEM sink for a processor import path. It verifies the selected Resource Profile and derives current occupied/free quantity from the native import slot.

A sink Resource Reservation then publishes the generic destination capacity used by route selection and transform admission.

## 6. Exact-batch physical transfer

A Material Link binds:

```text
source Resource Reservation
sink Resource Reservation
resource type
Feeder
Grant Guard
Transfer Executor
source native vending identity
Stacker/Sorter route identity
processor native sink identity
```

The Feeder prepares the exact requested quantity. The Grant Guard will not release it until one committed Allocator ABI2 epoch matches every staged identity. The Executor snapshots destination `ImportCount` before release and confirms exactly one destination delivery event.

This separation prevents reservation, route preparation, and physical release from collapsing into one fragile script.

## 7. Current transaction authority

All current furnace material jobs use the generic transform transaction path:

```text
161 Admission
  -> 162 Link Resolver
  -> 163 Reservation Stager
  -> 164 Multi Material Reservation Allocator ABI2
  -> existing Grant Guards / Executors
  -> 165 Generic Material Transform Runtime
```

The Stager provisionally prepares every required input. Allocator ABI2 publishes one common epoch at S14 **last** only after all staging succeeds. If any input fails, all provisional reservations are cleaned before an epoch can become active.

`ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` requires Allocator ABI2 exactly.

## 8. One-, two-, and three-input transforms

The Resource Transform catalog contains 17 current furnace transforms:

- seven one-input basic smelts;
- five two-input base alloys;
- five three-input advanced alloys/superalloys.

Processor capability masks define placement:

```text
Arc Furnace       1
Furnace           3
Advanced Furnace  7
```

Basic smelts require bit 1, base alloys require bit 2, and advanced alloys require bit 4. Therefore the same generic runtime handles Arc Furnace basic smelts as well as Furnace and Advanced Furnace work.

## 9. Generic Resource Link directory

`ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` publishes `DirectorySchema.ResourceLink` candidates. The Generic Directory Adapter Bridge and Generic Snapshot Directory Host own sorting, exact dedupe, overflow, A/B publication, and generation.

`ic10/material-transform/material_transform_link_resolver_v1_0.ic10` validates the generic directory magic/ABI plus `DirectorySchema.ResourceLink` ID/version before reading the active bank.

No Resource-Link-specific directory magic is part of the current contract.

## 10. What this proves

MaterialGrid demonstrates that the generalized resource architecture can support a domain with very different physical behavior from pressure flow:

- quantities are discrete ITEM counts rather than molar flow;
- physical delivery requires vending/stacking/sorting mechanics;
- transforms may require several input resources atomically;
- completion is verified through destination/output inventory growth;
- the same Endpoint/Reservation/Link/Profile/Directory abstractions remain useful.

This is the main evidence that the framework is not accidentally pressure-specific.


## 10. Manufacturing scheduler integration

Roadmap Item 6's **Manufacturing Scheduler** reuses MaterialGrid rather than creating a manufacturing-only resource ledger. Recipe schema v3 publishes semantic reagent identities, and ITEM Resource Profiles expose optional `ManufacturingReagentHash` so the Print Material Resolver can map those semantics to concrete reachable ResourceTypes. Printing then uses a dedicated physical instance of the existing Multi Reservation Stager / Multi Material Allocator ABI2 protocol.

## 11. Current limitations

The current layer intentionally does not yet include:

- scheduler execution of a Generic TRANSFER Job outside transform execution;
- dependency DAG planning;
- arbitrary N-input transforms beyond the current bounded 1..3 input contract;
- power-aware scheduling.

`GENERIC_JOB_ABI_V1` makes transfers/transforms/printing peers under one lifecycle. Roadmap Item 6 now turns TRANSFORM and PRINT jobs into concrete schema-qualified plans while reusing the same Resource/Directory/Reservation substrate.

## 12. Next evolution

Bounded dependency planning and POWER management are implemented above the same Generic Job/Resource boundaries. TRANSFER remains a valid Generic Job type without a production dispatcher and can reuse the same selector/Gateway pattern if added later.

The existing Resource/Directory/Transform/Manufacturing substrate should remain unchanged unless those milestones expose a genuine missing invariant.
