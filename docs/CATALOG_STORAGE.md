# Catalog Storage Standard — Store ABI6 / Loader ABI5

## Core invariant

Catalog payload semantics, Loader source capacity, Store storage capacity, and physical Store membership are independent concerns.

> **Schemas define self-contained logical items. Loaders publish immutable relocatable items. Stores own durable item storage. The Coordinator owns placement and topology.**

The ownership rule is strict:

- Loader writes Loader.
- Store writes Store.
- Coordinator owns membership, allocation, topology, and lifecycle.
- Views and lookup services read stable Store snapshots.

The current common protocols are:

- Catalog Store magic `31415968`, **Store ABI6**;
- Catalog Loader magic `31415969`, **Loader ABI5**;
- Catalog Coordinator magic `31415970`, **Coordinator ABI4**;
- 4-cell payload alignment;
- canonical zero padding;
- whole logical items only;
- runtime Store placement;
- whole-item migration and compaction.

See `docs/CATALOG_COORDINATION.md`, `docs/CATALOG_SCHEMA.md`, and `ROADMAP.md`.

## Generic Store ABI6

Every physical catalog data node runs `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10`. There are no Resource/Input/Transform/Recipe-specific Store programs.

| Cell | Meaning |
|---:|---|
| S0 | StoreMagic = `31415968` |
| S1 | StoreABI = `5` |
| S2 | CatalogSchemaId |
| S3 | CatalogSchemaVersion |
| S4 | CatalogInstanceId |
| S5 | CoordinatorId |
| S6 | PreviousStoreRef |
| S7 | NextStoreRef |
| S8 | StoreOrdinal assigned at runtime |
| S9 | LocalItemCount |
| S10 | ItemDirectoryBase = `32` |
| S11 | CoordinatorRef |
| S12 | CoordinatorEpoch |
| S13..S14 | reserved |
| S15 | committed item-import generation/count |
| S16 | StoreState |
| S17 | Store data seqlock; odd while mutating, even stable |
| S18 | human-assigned NodeId `1..64` |
| S19 | next free item-directory cell |
| S20 | payload heap top / next free payload boundary |
| S21 | reserved |
| S22 | used cells including header, item directory, and payload |
| S23 | PartitionKey; zero for unpartitioned catalogs |
| S24..S25 | reserved |
| S26 | AssignmentEpoch used by directory telemetry |
| S27 | in-flight capacity reservation in cells |
| S28 | local fault/status detail |
| S29 | currently unreserved free cells between directory and heap |
| S30 | reserved |
| S31 | committed AssignmentEpoch mirror |
| S32.. | 2-cell item-location directory growing upward |
| ...S511 | item payload heap growing downward |

A newly programmed Store requires only a unique positive `S18 NodeId`. It advertises `UNCLAIMED`; the Coordinator assigns catalog/schema/partition/topology metadata later.

## Runtime item geometry

Store ABI6 does not contain schema-specific fixed regions. Each committed item has a 2-cell directory entry:

```text
[ItemBase, ItemCellCount]
```

The directory grows upward from S32. Payload blocks grow downward from S511. A new item of `N` payload cells therefore consumes:

```text
N payload cells + 2 directory cells
```

All payload item sizes are multiples of the 4-cell framework block width. The exact available capacity is published in S29. S27 subtracts capacity already promised to an in-flight Loader or migration so two control-plane operations cannot oversubscribe the same Store.

The Store publishes the destination payload first, then the directory entry, then updates LocalItemCount/geometry and finishes the even Store revision. Readers only accept stable even revisions.

## Loader ABI5

A Loader is a one-shot immutable candidate image. It does **not** know a physical Store or Store ordinal when generated.

| Cell | Meaning |
|---:|---|
| S0 | LoaderMagic = `31415969` |
| S1 | LoaderABI = `4` |
| S2 | CatalogSchemaId |
| S3 | CatalogSchemaVersion |
| S4 | CatalogInstanceId |
| S5 | PartitionKey |
| S6 | stable LoaderId |
| S7 | Loader publication generation/version |
| S8 | ItemCount |
| S9 | Loader item-directory base = `16` |
| S10 | total payload cells |
| S11 | payload signature |
| S12 | Ready; `1` written LAST |
| S13 | runtime-assigned TargetStoreRef; initially zero |
| S14 | runtime assignment token/epoch; initially zero |
| S15 | next item index already imported by the Store |
| S16.. | Loader item directory `[ItemBase, ItemCellCount]` |
| upper stack | zero-initialized sparse item payloads |

Generated Loaders follow this lifecycle:

```text
clr db                 # Loader's own stack only
write ABI header
write item locations
write non-zero payload cells only
poke 12 1              # Ready LAST
END
```

Because the Loader stack starts at zero, semantic zero values and padding require no explicit instructions. The Store copies the complete declared item range, including zero cells.

## Whole-item invariant

A logical item may never be split across:

- two Loader ICs;
- two Store nodes;
- a migration transaction;
- a compaction operation.

A Loader source-size boundary may occur only between complete items. Variable-length Input Profiles and Resource Transforms are encoded as self-contained block-aligned items specifically so this rule remains true.

## Runtime placement

`ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` examines each pending whole item, not a generator-assigned Store target.

For each item the Router:

1. matches CatalogSchemaId, schema version, CatalogInstanceId, and PartitionKey;
2. searches ACTIVE Stores for sufficient **unreserved** S29 capacity;
3. reserves the required `ItemCellCount + 2` cells in Store S27;
4. assigns Loader S13/S14;
5. otherwise asks Coordinator Core to claim an UNCLAIMED Generic Store and assign the next StoreOrdinal.

Generators publish `runtime_min_store_count` only as a commissioning estimate. The actual physical placement and Store count are runtime outcomes.

For the current Resource Profile catalog this produces one FLUID Store and, because 27 ITEM records no longer fit one Store under the generic item-directory overhead, two ITEM Stores.

## Item migration and compaction

`ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` and `ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` move complete items from DRAINING Stores to compatible ACTIVE Stores.

The current safe compaction policy migrates the newest item from the source. Because the payload heap grows downward, removing the newest item reclaims contiguous heap space without holes.

Transaction order:

```text
reserve destination capacity in S27
copy complete payload
publish destination directory entry
advance destination stable metadata
remove source directory tail entry
reclaim source heap boundary
advance source stable metadata
advance Coordinator topology/catalog generation
release S27
```

Destination publication precedes source removal. An item therefore never loses its only committed copy during the move.

When a DRAINING Store reaches zero items, `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` repairs Prev/Next topology and marks it RETIRED.

## Store lifecycle

StoreState values are:

| Value | State |
|---:|---|
| 1 | UNCLAIMED |
| 2 | ACTIVE |
| 3 | DRAINING |
| 4 | FAULT |
| 5 | RETIRED |
| 6 | MIGRATING |
| 7 | MISSING, directory-observed |
| 8 | DUPLICATE, directory-observed |

DRAINING Stores receive no new Loader placement. MISSING and DUPLICATE are fail-closed directory health states.

## Consumer behavior

A View may start from any Store belonging to the catalog. It follows PreviousStoreRef to the head, walks NextStoreRef, and validates both:

- Store S17 stable even revision before/after reads;
- Coordinator topology sequence stable before/after traversal.

Domain Views therefore remain independent of the number of Stores selected at runtime.

## Current payload schemas

Current schema versions are:

- Resource Profile schema **v2**;
- Input Profile schema **v3**;
- Resource Transform schema **v4**;
- Recipe schema **v2**.

See `docs/CATALOG_SCHEMA.md` for exact item layouts.
