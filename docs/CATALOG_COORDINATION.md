# Catalog Coordination Control Plane

## Purpose

The Catalog Coordinator is the control plane for generic catalog storage. It owns physical Store membership, runtime placement, topology, capacity reservations, health, recovery, migration, retirement, and aggregate telemetry. Stores remain authoritative for their own durable payload; Loaders remain immutable candidate producers.

Current services:

- `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` — **Coordinator ABI3**, claims Generic Stores and commits topology/assignment epochs;
- `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` — **on-demand import service**; Router ABI3 assigns each pending Loader item to live capacity;
- `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` — Directory Adapter ABI3 for Generic Store discovery;
- `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` — persistent 64-node Store registry;
- `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` — **optional observability**, aggregate lifecycle/capacity telemetry;
- `ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10` — **optional diagnostic** selectable directory view;
- `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` — **on-demand lifecycle** higher-epoch Coordinator takeover/rebinding;
- `ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` — **on-demand lifecycle** whole-item drain/compaction planning;
- `ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` — **on-demand lifecycle** whole-item copy/commit worker;
- `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` — **on-demand lifecycle** empty Store unlink/retirement.

```text
                       one global control plane

                    Coordinator Core ABI3
                    /        |          \
        Registry Directory   |        Recovery
          + Telemetry        |        Migration
                             |        Retirement
                         Loader Router
                             |
                  runtime capacity placement
                             |
                  Generic Store ABI5 nodes
                             ^
                             |
                 relocatable Loader ABI4 items
```

## One global claimant

There is one global claimant for Generic Store nodes. This prevents two catalog-specific authorities from racing to claim the same unassigned physical IC housing.

A Store is initially identified only by:

- Store magic/ABI;
- human-assigned NodeId `1..64`;
- State = UNCLAIMED;
- current free capacity.

The Coordinator supplies CatalogSchemaId, CatalogSchemaVersion, CatalogInstanceId, PartitionKey, StoreOrdinal, Prev/Next links, Coordinator identity/epoch, and AssignmentEpoch.

## Persistent 64-node directory

Store membership uses the Generic Directory infrastructure described in `docs/DIRECTORY_STANDARD.md`.

`ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` publishes Directory Adapter ABI3 candidates. `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` indexes them by NodeId and persists one 6-cell record per possible node:

```text
[ReferenceId, State, UsedCells, AssignmentEpoch, CatalogInstanceId, LastSeenEpoch]
```

The Adapter detects duplicate NodeIds, faults both live Store instances, and publishes one DUPLICATE-state candidate; the Registry marks previously known but absent nodes MISSING. `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` aggregates active/unclaimed/draining/fault/missing/duplicate counts and total used/free/capacity cells.

## Coordinator ABI3

Key Coordinator fields used by the current control plane include:

```text
S0   magic = 31415970
S1   ABI = 3
S2   CoordinatorId
S3   CoordinatorEpoch
S4   service generation
S6   placement/migration generation
S7   topology seqlock; stable even
S8..S13 aggregate directory health/capacity summary
S20  AssignmentEpoch counter
S23  Registry Directory ReferenceId
```

### Capacity request mailbox

When the Router cannot place an item, it posts a capacity request in S25..S32:

```text
S25  request pending
S26  PartitionKey
S27  CatalogSchemaId
S28  CatalogSchemaVersion
S29  CatalogInstanceId
S30  previous/tail StoreRef, or 0
S31  requested next StoreOrdinal
S32  required unreserved cells
```

Core scans the 64-node Registry for an UNCLAIMED Store whose S29 free cells satisfy S32, assigns it, links it after the current partition tail, advances AssignmentEpoch, and activates the Store.

The request contains no generator-defined physical ReferenceId.

## Loader Router ABI3

The Router discovers Ready Loader ABI4 producers. For the Loader's current `S15` item index it reads that item's size from the Loader item directory and computes:

```text
required cells = ItemCellCount + 2
```

It searches ACTIVE Stores matching schema/version/instance/partition. A Store is eligible only when:

- S29 free cells >= required cells;
- S27 in-flight capacity reservation is zero;
- Store state is ACTIVE;
- CoordinatorRef matches the current Coordinator.

The Router reserves S27 before writing Loader TargetStoreRef/assignment token. This prevents multiple pending items from oversubscribing the same capacity snapshot.

If no eligible Store exists, the Router asks Core to claim another Generic Store. Store ordinals therefore emerge from runtime capacity rather than generated topology.

After the intended Loader set has been fully imported and Store health is stable, the Catalog Loader Router and the one-shot Loader housings may be powered/reprogrammed. Bring Router back when adding/rebuilding catalog content. Core, Store Adapter, Registry Host, and the assigned Stores remain the membership/storage substrate.

## Recovery

Stores persist catalog assignment metadata independently of Coordinator runtime state. A replacement Coordinator with the same CoordinatorId and a strictly higher CoordinatorEpoch can run `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` to rebind reachable assigned Stores.

The recovery service does not rewrite payload. It updates CoordinatorRef/Epoch only when the persistent Store belongs to the same Coordinator identity and has an older epoch.

## Draining, migration, and compaction

Mark a Store DRAINING before removal. The Router refuses new placement to DRAINING Stores.

`ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` selects the newest complete item from a DRAINING Store and finds compatible ACTIVE capacity. If none exists it posts a normal capacity request to Core.

`ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` then:

1. uses the destination S27 reservation;
2. copies the full block-aligned item;
3. publishes the destination directory entry and stable metadata;
4. removes the source tail item only afterward;
5. reclaims the source heap boundary;
6. advances Coordinator generation/topology state;
7. releases destination S27.

Repeated moves compact the draining Store until empty. `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` then unlinks it and marks it RETIRED.

The current policy intentionally moves newest items first. Arbitrary hole-producing heap moves are not used.

## Store telemetry and diagnostics

`ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` accepts any Store ABI5 node and reports:

- schema/version/instance;
- Store RefId and CoordinatorRef;
- NodeId/state/ordinal/partition;
- LocalItemCount and Store revision;
- Prev/Next links;
- used/free capacity;
- import generation and AssignmentEpoch;
- Registry state/last-seen values;
- Coordinator aggregate active/unclaimed/draining/fault/missing counts and capacity.

`ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10` provides the directory-oriented commissioning view.

## Fail-closed rules

The control plane rejects or defers work when:

- NodeId is invalid or duplicated;
- Store state is not ACTIVE;
- schema/version/instance/partition do not match;
- free capacity is insufficient;
- capacity is already reserved by another in-flight operation;
- topology sequence is odd/changing;
- Coordinator identity/epoch is stale;
- a Store is MISSING/FAULT;
- a migration destination cannot hold the complete item.

No fallback is allowed to split an item or silently overcommit Store capacity.
