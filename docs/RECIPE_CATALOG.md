# Printer Recipe Catalog

The Recipe Catalog provides planning/execution metadata for supported non-deprecated printers. Installed GameData remains the authoritative enumeration source; live Printer Directory state remains authoritative for which machine is currently usable.

Supported families:

- Autolathe
- Electronics Printer
- Hydraulic Pipe Bender
- Tool Manufactory
- Security Printer
- Rocket Manufactory

Fabricator semantics remain deliberately unsupported.

## Recipe schema v3

Recipe schema v3 replaces the fixed enumeration-only v2 record with a variable-width, self-contained execution item:

```text
+0  RecipeHash
+1  FamilyHash / PartitionKey
+2  RequiredCapability
+3  FamilyOrdinal
+4  InputCount
+5  Input0 ManufacturingReagentHash
+6  Input0 Quantity
+7  Input1 ManufacturingReagentHash
+8  Input1 Quantity
...
     InputCount x 2 cells
...  zero padding to 4-cell alignment
```

The generator currently permits at most 16 material inputs per recipe. `Time` and `Energy` recipe fields are not material reagents and are excluded from the pair list.

Each logical recipe remains atomic: header, every reagent pair, and alignment padding are one Store item and are never split across Loaders, Stores, migration, or compaction.

`FamilyHash` is the same identity published by `DirectorySchema.Printer` and is also the Store `PartitionKey`, so recipe family is represented once.

## Runtime Store capacity

Store ABI5 has a common 32-cell header, a 2-cell item-directory entry per item, and a downward-growing payload heap. Because schema-v3 recipe payload width depends on InputCount, **recipes per Store are no longer a fixed 80**.

For an item with `N` material inputs:

```text
logical width   = 5 + 2*N
payload width   = align_up(logical width, 4)
Store cost      = payload width + 2 item-directory cells
```

Runtime placement uses the actual complete item widths. The Router/Coordinator claims another same-family Generic Store whenever the next whole recipe does not fit.

The current 11-recipe fixture still derives one Store per family, for six Stores total.

The 780-recipe stress fixture contains 130 synthetic recipes per family. Under schema v3 its actual packing derives:

```text
48 + 48 + 34 recipes per family
3 Stores x 6 families = 18 Stores
```

No Store mixes FamilyHash partitions.

## Loader ABI5

Generated Recipe Loaders are one-shot relocatable Loader ABI5 candidates. Every Loader:

1. clears only its own stack;
2. publishes Loader magic/ABI, Recipe schema v3, CatalogInstanceId, and FamilyHash PartitionKey;
3. writes one or more complete variable-width recipe items;
4. omits explicit semantic-zero/padding writes after the clear;
5. publishes Ready last;
6. terminates.

The generator splits source only between complete recipe items. No generated Loader contains a physical Store ReferenceId or preassigned Store ordinal.

## Browse Lookup ABI3

`ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` publishes magic `31415967`, ABI3.

It is the compact family/ordinal browser and intentionally does not republish reagent arrays.

Request:

```text
S3 FamilyHash
S4 maximum RequiredCapability
S5 FamilyOrdinal
S6 request generation
```

Response:

```text
S7  response generation
S8  status: 1 found, -1 bad request, -2 catalog invalid, -3 not found
S9  eligible recipe count for family/capability
S10 RecipeHash
S11 selected RequiredCapability
```

`d0` may point to any Recipe Store ABI5 node. Lookup walks runtime topology, accepts only Recipe schema v3, skips unrelated FamilyHash partitions, and fences Store/Coordinator revisions before publication.

Security Printer capability remains intentionally machine-driven. A capability-1 Security Printer query excludes Tier-Two recipe metadata that current hardware cannot execute.

## Recipe Execution Profile View ABI1

Roadmap item 6 adds `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` for exact RecipeHash execution planning.

`d0` points to any Store in the Recipe topology.

Request:

```text
S2 RecipeHash
```

Publication:

```text
S0  31415985
S1  ABI 1
S3  FamilyHash
S4  RequiredCapability
S5  InputCount
S6  Store publication generation
S7  status: 1 ready, -2 invalid catalog, -3 missing
S8..S39 [ManufacturingReagentHash, Quantity] pairs; unused cells zero
S40 Coordinator topology generation
S41 resolved RecipeHash echo
```

InputCount is bounded to 16 by the generator and View. Consumers must require `S41 == requested RecipeHash` in addition to ready status so a previous request's publication cannot be mistaken for the current recipe.

The View does not map reagent names to concrete item PrefabHashes. That mapping is provided by ITEM Resource Profile `ManufacturingReagentHash` metadata and reachable Material Links. See `docs/RESOURCE_PROFILES.md` and `docs/MANUFACTURING_SCHEDULER.md`.

## Printer interrogation and why the catalog remains required

A live printer can expose/use a recipe identity it already knows, but the generic IC10 surface does not provide a complete enumerable recipe table with all material requirements. Runtime scheduling therefore uses:

```text
GameData-generated Recipe Catalog
        +
Printer Directory live machine state
```

rather than attempting to discover the recipe universe by mutating a live printer.

## Commissioning

1. Run Coordinator Core, Catalog Store Registry, and Loader Router.
2. Provide enough unclaimed Generic Stores for the generated manifest's runtime minimum plus operational headroom.
3. Generate Recipe Loaders from the installed GameData/source fixture.
4. Program generated Loader ICs anywhere on the discoverable network.
5. Let Router place whole recipe items into live family-partition capacity.
6. Attach `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` and/or `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` to any Recipe Store.
7. For scheduled printing, keep Recipe Execution View online and connect it as documented in `docs/MANUFACTURING_SCHEDULER.md`.

`ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` remains the generic Store/Coordinator diagnostic surface.

## Validation

`tests/test_recipe_catalog.py` verifies:

- deterministic generation;
- Recipe schema v3 and `RECIPE_CATALOG_V6` manifest identity;
- Loader ABI5 sparse/whole-item behavior;
- family partition purity;
- runtime capacity placement;
- capability-filtered ordinal Lookup ABI3;
- exact RecipeHash execution-profile family/capability/reagent publication;
- missing-recipe echo/status behavior;
- 780-recipe / 18-Store stress placement (`48+48+34` per family);
- runtime same-family spill across multiple Stores;
- generated IC10 line limits.
