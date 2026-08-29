# Catalog Schema Standard

## Independent version dimensions

Catalog transport/storage protocols and payload semantics are versioned separately:

```text
StoreABI              common durable Store protocol
LoaderABI             immutable candidate protocol
CoordinatorABI        membership/allocation protocol
CatalogSchemaId       domain payload family
CatalogSchemaVersion  meaning and physical representation of one item
CatalogInstanceId     stable logical catalog incarnation
```

Adding a Loader, claiming another Store, or moving an item does **not** change CatalogSchemaVersion. The schema version changes only when the representation or semantics of a logical item change.

## Standard cell block

All catalog item payloads are aligned to:

```text
CELL_BLOCK_WIDTH = 4
```

A logical item occupies one or more complete four-cell blocks. Semantic fields that do not fill the final block are padded with canonical zero cells.

`SchemaCellMask` and `TailCellMask` remain the standard way to describe which cells in a fixed-width schema unit are semantically valid. Cells outside the relevant mask must be zero. Store ABI6 catalogs use **self-contained relocatable items** rather than cross-item absolute region pointers. No alternate region-pointer storage contract is part of the current baseline.

## Why self-contained items

Store ABI6 performs runtime placement and item-level migration. Therefore a logical item must be movable without fixing addresses in another Store region.

Current rule:

> Every pointer/ordinal needed to interpret an item is local to the item or derived from counts in its header.

A Loader may contain multiple complete items, but an item is never split across Loaders or Stores.

## Resource Profile schema v2

Resource Profiles use a fixed 16-cell item:

```text
+0  ResourceType
+1  ResourceClass
+2  Unit
+3  ProfileKind
+4  ProfileSchema
+5..+13  nine schema parameters
+14..+15 canonical zero padding
```

Semantic width is 14 cells, physical width is 16 cells, and the fixed-unit SchemaCellMask is `0x3fff`.

PartitionKey is ResourceClass:

- `1` = FLUID;
- `2` = ITEM;
- `4` = POWER;
- `5` = ENERGY.

The current 39 profiles require a commissioning estimate of five Stores under Store ABI6 geometry: one FLUID Store (10 profiles), two ITEM Stores (26+1), one POWER Store, and one ENERGY Store. That estimate is not a generated placement assignment. FLUID `ProfileKind=5`, schema 1 is the prepared two-component mixture shape introduced by Item 11; see `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Input Profile schema v3

Each Input Profile is one variable-length self-contained item:

```text
+0  ProfileType
+1  schema
+2  FieldCount
+3  EnumPairCount
+4..  FieldCount descriptors, each 4 cells
...   EnumPairCount pairs, each 2 cells
...   zero padding to the next 4-cell boundary
```

No descriptor or enum pool lives in another absolute Store region. A complete profile therefore migrates atomically.

The consumer-facing Generic Input Profile View remains magic `31415929`, ABI1.

## Resource Transform schema v4

Each transform is one self-contained variable-length item:

```text
+0  TransformType
+1  RequiredCapabilityMask
+2  InputCount
+3  OutputCount
+4  MinPressureKPa
+5  MaxPressureKPa
+6  MinTemperatureK
+7  MaxTemperatureK
+8  Flags
+9..+11 reserved zero
+12..  InputCount x 4-cell resource descriptors
...    OutputCount x 4-cell resource descriptors
...    zero padding to 4-cell alignment
```

A resource descriptor is:

```text
[ResourceClass, ResourceType, Unit, Quantity]
```

The current View supports up to six inputs and eight outputs. Current furnace transforms use one, two, or three inputs and one output.

Processor requirements are capability masks rather than exact processor PrefabHash:

```text
SMELT_BASIC    = 1
FURNACE_ALLOY  = 2
ADVANCED_ALLOY = 4

Arc Furnace      advertises 1
Furnace          advertises 3
Advanced Furnace advertises 7
```

## Recipe schema v3

Each recipe is one variable-width, block-aligned logical item:

```text
+0  RecipeHash
+1  FamilyHash / PartitionKey
+2  RequiredCapability
+3  FamilyOrdinal
+4  InputCount
+5..  InputCount x [ManufacturingReagentHash, Quantity]
...  zero padding to 4-cell alignment
```

The generator permits at most 16 material inputs. `Time` and `Energy` source fields are execution metadata rather than material reagents and are not stored as reagent pairs.

Recipe storage remains partitioned by printer family. Runtime capacity may add additional same-family Stores without changing Recipe schema version. Because payload width now depends on InputCount, Store capacity is calculated from whole item widths rather than a fixed recipes-per-Store constant.

`ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` resolves exact RecipeHash execution metadata. `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` remains the compact family/capability/ordinal Lookup ABI3 surface.

## Loader ABI5 item directory

A Loader has its own item directory beginning at S16:

```text
[LoaderItemBase, ItemCellCount]
```

Payloads are placed independently in the Loader's upper stack. Runtime Store placement fields S13/S14 are zero in generated source and are written only by the live Router.

The Loader self-clears before sparse writes, so every unwritten semantic zero and padding cell is deterministically zero.

## Store ABI6 item directory

Committed Store items are indexed from S32:

```text
[StoreItemBase, ItemCellCount]
```

Views scan these directory entries and interpret each payload using CatalogSchemaId + CatalogSchemaVersion. They do not depend on generator-known Store boundaries or fixed region bases.

## Schema evolution rule

Compatible content growth:

```text
same CatalogSchemaVersion
new Loader / new Store / moved item
```

Representation change:

```text
new CatalogSchemaVersion
new CatalogInstanceId when the catalog incarnation cannot safely mix versions
```

Existing Stores in one active catalog chain remain schema-homogeneous.
