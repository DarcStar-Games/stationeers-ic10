# Unified Resource Profiles

`data/resource_profiles.json` is the canonical source for **39 Resource Profiles**: nine PHASE_MEDIUM pure-gas FLUID profiles, one prepared-mixture FLUID profile, 27 ITEM_STACK material profiles, one POWER service profile, and one ENERGY storage profile. `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` republishes the stable Resource Profile View ABI1.

## Catalog schema

Resource Profile payload schema is **v2**. Every profile is one fixed 16-cell relocatable item:

```text
+0  ResourceType
+1  ResourceClass
+2  Unit
+3  ProfileKind
+4  ProfileSchema
+5..+13 nine schema parameters
+14..+15 zero padding
```

The semantic width is 14 cells; physical width is 16 cells and the fixed-unit mask is `0x3fff`.

PartitionKey is ResourceClass:

- `1` FLUID;
- `2` ITEM;
- `4` POWER;
- `5` ENERGY.

### Prepared-mixture profiles

`ProfileKind=5`, `ProfileSchema=1` is the first cross-domain prepared-mixture shape. Its nine parameters are `Component1LogicType`, `Component1Fraction`, `Component2LogicType`, `Component2Fraction`, `RatioTolerance`, `MinTemperature`, `MaxTemperature`, `ReferenceWatts`, and `Flags`. `Fuel.H2O2` uses `RatioVolatiles=2/3` and `RatioOxygen=1/3`. The profile describes semantic composition; physical creation is owned by the gas-mixer utility and physical transport remains PressureGrid-owned. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Runtime placement

Resource Profile Loaders are **Loader ABI5** relocatable candidates:

- `ic10/resource-profile-catalog/resource_profile_loader_fluid_00_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_fluid_01_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_item_00_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_item_01_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_item_02_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10`

They do not contain Store ordinals or physical Store ReferenceIds. Each Loader self-clears, writes only non-zero cells, keeps every 16-cell profile intact, writes Ready last, and terminates.

With Store ABI6 geometry, each 16-cell profile consumes 18 Store cells: 16 payload + 2 item-directory cells. An empty Store has 480 cells after the 32-cell header, so one Store can hold 26 profiles.

The current runtime outcome is therefore:

```text
FLUID partition: 10 items -> 1 Store
ITEM partition:   27 items -> 2 Stores (26 + 1)
POWER partition:   1 item  -> 1 Store
ENERGY partition:  1 item  -> 1 Store
```

This is a **capacity-derived runtime result**, not a generated Store assignment. Adding/removing physical Generic Stores does not require regenerating existing Loaders.


## Current POWER/ENERGY set

Item 9 proves the same catalog/view substrate is not material-specific. The POWER partition contains the canonical electrical service profile (`Unit.WATT`); the ENERGY partition contains the canonical stored-electrical-energy profile (`Unit.JOULE`). Live reserve, priority, charge/discharge, and shedding policy remains on Power Endpoints rather than being embedded in static profiles. See `docs/POWER_MANAGEMENT.md`.

## Current ITEM set

The ITEM partition contains 27 material profiles:

- ores: Coal, Cobalt, Copper, Gold, Iron, Lead, Nickel, Silicon, Silver, Uranium;
- basic ingots: Copper, Gold, Iron, Lead, Nickel, Silicon, Silver;
- alloys: Constantan, Electrum, Invar, Solder, Steel;
- advanced alloys: Astroloy, Hastelloy, Inconel, Stellite, Waspaloy.

Generated Loader writes include inline human-readable comments for each profile item.

### Manufacturing reagent alias

ITEM `ProfileSchema=2` uses schema parameter 2 (`+7` in the 14-cell semantic record) as `ManufacturingReagentHash`. Current printable ingot/alloy profiles populate this with the Recipe Catalog reagent identity such as `HASH("Iron")`, `HASH("Copper")`, or `HASH("Steel")`; profiles that are not direct printer reagents leave it zero.

This field deliberately does **not** replace `ResourceType`. `ResourceType` remains the exact concrete item PrefabHash used by Resource Endpoints/Reservations/Links. The reagent hash is a semantic alias used only to match Recipe schema-v3 requirements to reachable concrete resources.

`ic10/material-grid/material_resource_link_v1_0.ic10` republishes the sink/source profile's manufacturing alias in Link `S27`. The print material resolver therefore matches:

```text
Recipe ManufacturingReagentHash
        -> Material Link S27
        -> concrete Link ResourceType S5
```

This keeps manufacturing resource planning inside the existing Resource Profile/Material Grid architecture rather than maintaining a second Iron->ingot mapping table.

## View ABI1

`ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` accepts any Store ABI6 node from the Resource Profile catalog on `d0`. It follows PreviousStoreRef to the head, scans Store item-directory entries, follows NextStoreRef, and checks stable Store/Coordinator revisions.

Request:

```text
S2 desired ResourceClass
S3 desired ResourceType
```

Publication remains:

```text
S0  31415963
S1  ABI 1
S4  status: 1 found, -2 catalog invalid, -3 missing
S5  publication generation / Store revision
S8..S21 selected 14 semantic cells
S22 CatalogInstanceId
S23 Coordinator topology/catalog generation
```

Consumers therefore do not need to know how many Stores the Coordinator selected.

## Deployment

1. Start `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10`, the Catalog Store Registry path, and `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10`.
2. Add at least five `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` nodes for the current 39-profile commissioning estimate. Give each a unique S18 NodeId 1..64; leave them UNCLAIMED.
3. Program the generated `ic10/resource-profile-catalog/resource_profile_loader_*_v4_0.ic10` set anywhere on the discoverable network. They need no Store screw.
4. Wait for runtime placement to produce one FLUID Store, two ITEM Stores, one POWER Store, and one ENERGY Store with all 39 items committed.
5. Point the Resource Profile View at any Store in the catalog and select class/type through S2/S3.

Extra unclaimed Store capacity may remain available for later catalog growth.
