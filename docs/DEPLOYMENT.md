# Fresh Deployment

There are no predecessor deployments to migrate. Configure every IC from this v1 bundle as a fresh installation.

This document gives the dependency-aware deployment order. `docs/COMMISSIONING_QUICKSTART.md` is the shortest operator checklist; `USER_DEPLOYMENT_GUIDE.md` is the complete per-family install/health/reflash/reclaim manual; `docs/ABI_REFERENCE.md` contains exact stack cells.

## ABI policy

Public services publish explicit integer ABI versions. Most controller/configuration surfaces remain ABI 1, while hardened discovery, reservation, catalog, and recipe services deliberately use ABI 2 or 3 where their contracts changed. Implementation revision may change without changing ABI.

A filename such as `v1_1` is an implementation revision. It does **not** mean ABI 1.1. Consumers must check the published ABI cell, not parse filenames. See `docs/ABI_REFERENCE.md` for the exact current version of each service.

## Recommended deployment order

Deploy from the bottom of the dependency graph upward. That way each new service can immediately validate the services it depends on.

### 1. Controller family core

For each controller instance:

1. Program `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`.
2. Program the family Config Policy and connect its `d0` to that Host.
3. Program the family Runtime and point it at the same Host.
4. Wire the Runtime's process/actuator devices as required by that controller family.

For PI specifically:

- Policy: `ic10/controller-pi/pi_config_policy_v1_0.ic10`
- Runtime: `ic10/controller-pi/controller_pi_runtime_v1_1.ic10`
- Runtime `d0`: process input
- Runtime `d1`: actuator
- Runtime `d2`: Generic Host

For ControllerSequencer:

- Policy: `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10` (`d0` -> Host)
- Runtime: `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10`
- Runtime `d0`: process/input device
- Runtime `d1`: fill/action-A actuator
- Runtime `d2`: drain/action-B actuator
- Runtime `d3`: Generic Host

The Sequencer defaults to disabled. Configure its thresholds, LogicTypes, settle/timeout ticks, and repeat behavior before enabling it. See `docs/SEQUENCER_CONTROLLER.md`.

For ControllerPhasePressure:

- Policy: `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10` (`d0` -> Host)
- Runtime: `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10`
- Runtime `d0`: Phase Change device / enclosed process device exposing `Pressure` and `Temperature`
- Runtime `d1`: Resource Profile View selecting the phase medium (`S26=1`, `S27=HASH(<medium>)`)
- Runtime `d2`: Generic Host

Start in HOLD. Choose deployment pressure clamps and StandbyPressure before selecting EVAPORATE/CONDENSE. `DirectWrite=1` makes the runtime own the phase device's own pressure setpoint and is usually still the correct choice in a grid deployment. `DirectWrite=0` is publish-only/alternate-actuation mode and should be used only when another explicit owner writes that same chamber property. See `docs/PHASE_PRESSURE_CONTROLLER.md`.

For ControllerPressureDomain:

- Policy: `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10` (`d0` -> Host)
- Runtime: `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10`
- Runtime `d0`: optional pressure-observation device, normally a Pipe Analyzer on the controlled domain
- Runtime `d1`: Resource Profile View selecting the domain working medium
- Runtime `d2`: dedicated `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10`
- Runtime `d3`: pressurizing pressure-setpoint device
- Runtime `d4`: depressurizing pressure-setpoint device
- Runtime `d5`: Generic Host
- Arbiter `d0`: Controller Directory

Deploy the Controller Directory before expecting the Arbiter to return a request. PhasePressure telemetry is visible to the Arbiter regardless of its `DirectWrite` value; grid transfer of the external LOW/HIGH buses does not require giving up ownership of the chamber's own pressure-setting property.

For the first physical prototype, use a Pressure Regulator from an already-higher-pressure source into the domain and a Back Pressure Regulator from the domain into an already-lower-pressure sink. Power/enable both devices and verify orientation manually. PressureDomain changes their pressure Setting; it does not create compression. See `docs/PRESSURE_DOMAIN_CONTROLLER.md`.

For Level-3 pressure transfer and routing:

- deploy one dedicated `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` for the Pressure Grid Link Directory, one `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` with `d1` -> the shared Controller Directory Host, and one `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` with `d0` -> the Pressure adapter and `d1` -> the Pressure directory Host. The adapter owns discovery/candidate publication; the Bridge/Host own sorted A/B publication, dedupe, overflow, and generation. Point path/grid consumers at the Generic Host;
- per working medium deploy one `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10`, `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10`, `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10`, `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10`, `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10`, `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10`, `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10`, `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10`, and `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10`;
- wire Path Enumerator `d0` -> Grid Link Directory; Route Ranker `d0` -> Cost Profile; Route Selector `d0` -> Path Enumerator and `d1` -> Route Ranker; Path Allocator `d0` -> Route Selector and `d1` -> Reservation Allocator; Single-Hop Builder `d0` -> Grid Link Directory and `d1` -> Reservation Allocator; Plan Builder `d0` -> Single-Hop Builder and `d1` -> Path Allocator; Planner `d0` -> Grid Link Directory, `d1` -> matching Resource Profile View, `d2` -> Plan Builder;
- deploy one `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10` for every LOW/HIGH/STORAGE domain that participates in Level 3; Inventory `d0` -> PressureDomain runtime, `d1` -> Pipe Analyzer on that exact gas network, and `d2` -> that domain's Pressure Medium Purity Guard;
- each grid-participating Inventory gets one `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10`; each physical pump edge uses `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` plus `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10`;
- its Policy remains `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10` and optional Profile remains `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`;
- deploy one `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` per participating pressure domain: Guard `d0` -> the same Pipe Analyzer, Guard `d1` -> matching PHASE_MEDIUM Resource Profile View; Inventory `d2` -> that Guard;
- deploy one `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` per physical transfer: Grant Guard `d0` -> that Transfer runtime, `d1` -> the medium-specific Planner ABI2;
- Transfer Runtime `d0` -> source PressureInventory Reservation, `d1` -> sink PressureInventory Reservation, `d2` -> gas Volume Pump/Turbo Volume Pump, `d3` -> its Transfer Grant Guard, `d4` -> paired Generic Host;
- physical route classes are LOW->HIGH, LOW->STORAGE, STORAGE->HIGH, and STORAGE->STORAGE. The last class is valid only inside a complete multi-hop path.

For STORAGE, set PressureDomain `Role=3`, wire its `d0` to a Pipe Analyzer on the tank/network and `d1` to the matching Resource Profile View; `d2/d3/d4` are not required. `MinimumPressure` becomes the reserve floor and `MaximumPressure` the import ceiling. Wire the same PressureDomain and Pipe Analyzer to its Inventory service.

Before enabling a link, require Inventory `S11=1` on both endpoints and inspect `S16/S17` for plausible export/import moles. Inventory ABI2 intentionally faults if liquid is present in the observed pressure network and advertises zero capacity when the Purity Guard is not good. Commission Transfer links with modest flow caps first. The grid now builds each medium-specific plan in priority order: parallel direct LOW->HIGH reuse first, then complete 2- or 3-link LOW->STORAGE[..]->HIGH paths, then ordinary LOW->STORAGE / STORAGE->HIGH fallback. Endpoint reservation ledgers bound aggregate molar commitments across every admitted link, and all staged grants remain inert until the Planner publishes the build epoch as its final commit token. See `docs/PRESSURE_INVENTORY_MODEL.md`, `docs/PRESSURE_RESERVATION_MODEL.md`, `docs/PRESSURE_MULTI_HOP_ROUTING.md`, `docs/PRESSURE_ROUTE_COST_MODEL.md`, and `docs/PRESSURE_GRID_CONTROLLER.md`.

At this point the runtime should advertise generic telemetry and the Host/Policy should agree on type/schema/geometry.

### 2. Controller discovery

1. Deploy one `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` for the Controller Directory, one `ic10/controller-discovery/controller_directory_adapter_v4_0.ic10`, and one `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` with `d0` -> the Controller adapter and `d1` -> the Host. The adapter publishes Adapter ABI3 candidates on its own stack; the Bridge/Host publish Controller Directory ABI2.
2. Deploy `ic10/controller-discovery/controller_selector_v3_0.ic10` and set its `S14` directly to the Controller Directory **Host**. Selector ABI2 derives type/member groups from the sorted snapshot; there is no Controller Type Catalog.

Wait for at least one complete discovery generation before assuming a missing controller is a configuration problem.

### 3. Generic configuration services

Deploy:

- `ic10/controller-config/generic_config_editor_v1_0.ic10`
- `ic10/controller-config/generic_config_loader_v1_2.ic10`
- `ic10/controller-config/generic_config_committer_v1_1.ic10`

Wire their documented selector/editor dependencies according to `docs/ABI_REFERENCE.md`.

The Loader is the component that validates the selected controller's Host/Profile and builds Editor's active ordinal -> physical slot map. Do not bypass it by hand-populating Editor schema metadata.

### 4. Shared input commissioning panel

Commission the global catalog control plane before any catalog-backed commissioning profiles:

1. Program `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` and leave it running.
2. Program `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10`; connect Router `d0` -> Coordinator Core.
3. Program at least one `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` as available catalog capacity. Before first service, set only Store `S18` to a unique NodeId `1..64`; it advertises UNCLAIMED. Do not assign schema/partition/ordinal manually.
4. Program the three one-shot relocatable candidates `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` through `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10` anywhere on the same discoverable network. They have no Store screw, clear only their own stack, publish complete whole-profile items, write Ready last, and terminate.
5. The Router places each profile item into compatible live capacity. If no Store has room, Coordinator Core claims an UNCLAIMED Generic Store and assigns the next runtime ordinal. For the current six profiles one Store is sufficient. Wait for an ACTIVE Input Store with `S9=6` and a stable even `S17`; do not treat `S15` as a fixed Loader-count contract.
6. Program `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`; connect View to the ACTIVE Input Profile Store and Coordinator as documented by the View ABI, then set `S8/S9` for the desired context. Common contexts are `HASH("ControllerPI")/1`, `HASH("ControllerSequencer")/1`, `HASH("ControllerPhasePressure")/1`, `HASH("ControllerPressureDomain")/1`, and `HASH("ControllerPressureTransfer")/1`. Diagnostics uses `HASH("DiagnosticMapping")/1`.
7. Program `ic10/shared-input/generic_input_scanner_v1_1.ic10` and attach commissioning inputs plus the configured View.
8. Program `ic10/shared-input/generic_input_resolver_v1_0.ic10`; set Resolver `S8` to Scanner ReferenceId.
9. For configuration, deploy `ic10/controller-config/config_input_bridge_v1_0.ic10`; set `S8` to Editor RefId and `S9` to Resolver RefId.
10. Set Generic Config Loader `S9` to Scanner RefId so it discovers/validates the Profile ABI published by the View.

Reconfigure View `S8/S9` when intentionally reusing one physical panel for another controller family, and require a positive View generation before editing.

### 5. Establish first durable config

Select the controller, load it, stage desired values, and Apply once. The first successful Apply establishes a valid durable A/B bank using the current Policy signature.

Until a durable bank exists, defaults are the recovery source. This is normal on a fresh deployment.

### 6. Diagnostic services

1. Deploy `ic10/diagnostics/console_registry_v1_1.ic10` and enroll displays with the expected NameHash (default `HASH("DiagAuto")` when registry `S9` is zero).
2. Deploy `ic10/diagnostics/console_selector_v1_1.ic10` and point it at Console Registry.
3. Deploy `ic10/diagnostics/diagnostic_renderer_v1_1.ic10`.
4. Deploy `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` and wire Renderer + Controller/Console selectors.
5. Deploy a Scanner + Resolver pair for diagnostics.
6. Deploy or reuse `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`, connect `d0` to the shared Input Profile Catalog Store, set `S8=HASH("DiagnosticMapping")`, `S9=1`, and attach the View to the diagnostic Scanner.
7. Deploy `ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10`; set `S8` to Resolver and `S9` to the Diagnostic Input Profile View.
8. Deploy `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10`; set `S8` to Diagnostic Input Bridge, `S9` to Controller Selector, `S10` to Console Selector.
9. Set Mapping Editor `S13` to Diagnostic Input Bridge.

Use Field Dial to choose diagnostic control, Value Dial/Switch to set it, then select Commit and toggle the Switch OFF->ON.

## Fresh PI deployment checklist

A useful dependency checklist is:

```text
[controller instance]
Host <- PI Policy
  ^
  |
PI Runtime -> generic telemetry

[discovery]
Directory ----------------> Controller Selector

[configuration]
Scanner -> Resolver <- PI Profile
             |
       Config Input Bridge
             |
Selector -> Loader -> Editor -> Committer -> Host

[diagnostics]
Console Registry -> Console Selector
Scanner -> Resolver <- Diagnostic Profile
             |
      Diagnostic Input Bridge -> Selector Bridge
                                   /        \
                        Controller         Console
                         Selector           Selector
                              \             /
                               Mapping Editor -> Renderer
```

## Verification checkpoints

After each layer, check one simple invariant before adding more components:

| Layer | Check |
|---|---|
| Host/Policy | Host type/schema/masks/signature match the family Policy. |
| Runtime | Telemetry magic/ABI/type are published and paired Host RefId is correct. |
| Discovery | Directory generation advances and Selector can resolve a valid type/member directly from the sorted snapshot. |
| Config input | Scanner finds expected devices; Resolver reports ready and correct logical field/value. |
| Editor/Loader | Active field count and ordinal->slot mapping match Host masks. |
| Commit | Apply request gets Policy/Host success and effective revision advances. |
| Persistence | One A/B bank has a positive revision matching the current signature. |
| Diagnostics | Console and controller selectors resolve; Commit creates renderer mapping and advances console once. |

## Avoid these deployment mistakes

- Do not share one active Scanner/Resolver across configuration and diagnostics simultaneously.
- Do not treat a filename revision as an ABI version.
- Do not manually pack config fields contiguously when masks contain holes.
- Do not point multiple controller instances at one Host unless that is explicitly the intended single configuration identity.
- Do not interpret a Policy acceptance as durable success before Host completes its bank commit.
- Do not use stale ReferenceIds after reflashing/replacing devices without letting discovery/selection converge again.
- Do not share one PhasePressure Request Arbiter between simultaneously active PressureDomain runtimes; v1 Arbiter context has one owner.
- Do not expect LOW/HIGH local PressureDomain regulator pairs to create arbitrary compression. Active cross-domain pressure transfer belongs to PressureTransfer links and their volume pumps.
- Do not disable PhasePressure chamber writes merely because the external buses are grid-managed. Keep one actuation owner per physical property: normally PhasePressure owns the chamber setpoint, PressureDomain owns optional local regulators, and PressureTransfer owns its pump.



## Steady-state residency and reclaimable IC housings

A source being production-capable does not imply it must remain powered. After commissioning:

- a standalone controller normally keeps only its **Generic Host + Config Policy + Runtime** resident;
- Generic Config Editor/Loader/Committer, Generic Input Scanner/Resolver, Config Input Bridge, and `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` are configuration-time services and can be powered/reprogrammed until configuration changes are needed;
- Console Registry, Console Selector, Mapping Editor, Diagnostic Input/Selector Bridges, and their Scanner/Resolver panel are mapping-time services; `ic10/diagnostics/diagnostic_renderer_v1_1.ic10` can continue from committed mappings without them;
- Controller Directory Adapter + Generic Directory Adapter Bridge + Snapshot Host + Controller Selector are commissioning-only for installations with no live discovery consumer, but must remain resident when services such as PhasePressure Request Arbiter / pressure-grid topology consume live controller discovery;
- Loader ABI5 programs are immutable one-shot producers. Reclaim their housings after their items are imported and durable Store health has been verified;
- The Catalog Loader Router is likewise on-demand after the current import set is complete; Coordinator Core + Catalog Store discovery Adapter + Generic Registry Directory Host remain the catalog membership/control-plane substrate;
- Catalog Inspector, Catalog Directory Telemetry/View, Catalog Coordinator Recovery, Item Migration Planner/Worker, and Store Retirement Manager are optional/on-demand unless the operator explicitly wants continuous observability or is performing lifecycle work;
- `ic10/generic-jobs/generic_job_store_v1_0.ic10` is resident only when the installation accepts/retains Generic Jobs. It is not needed by controller-only deployments that do not use manufacturing/direct-transfer scheduling.

The production source inventory is **173 IC10 programs**; a normal steady-state installation uses only the subset required by its active controller/resource domains. Test-only ControllerTest programs live under `tests/ic10/` and are not counted here.

## Printer Directory / manufacturing discovery

For live supported-printer discovery deploy one directory stack:

```text
170 Printer Directory Adapter
        |
169 Generic Directory Adapter Bridge
        |
166 Generic Snapshot Directory Host
```

Set Bridge `d0` to the Printer Adapter and `d1` to the dedicated Snapshot Host. The Host publishes `DirectorySchema.Printer` v2 records `[ReferenceId, FamilyHash, ProcessorSpec]` with capacity 64. No printer-specific Host or compatibility ABI exists.

Keep this stack resident while the Manufacturing Scheduler needs current processor capability/availability. It may be reclaimed when no live printer-directory consumer exists. Recipe Catalog Stores remain durable and independent of live printer discovery. See `docs/PRINTER_DIRECTORY.md`.

## Generic Job Store

Deploy `ic10/generic-jobs/generic_job_store_v1_0.ic10` when the installation needs queued manufacturing/transfer work. It has no device screws. The Store owns 32 physical job slots and publishes `GENERIC_JOB_ABI_V1` with identity `HASH("GenericJobStore.v1")`.

The logical record is:

```text
[JobId, JobType, RequiredCapability, Identity,
 InputCount, OutputCount, RequestedQuantity, Priority,
 State, Generation, ErrorStatus]
```

The Store API is a low-level single-writer interface used by the Manufacturing Scheduler:

1. capture an even Store `S16 QueueSequence`;
2. for a new job, find a free slot (`active State=0`) and stage the seven immutable fields `JobType..Priority` into that unpublished intent slot;
3. revalidate unchanged even QueueSequence;
4. issue `S11=1 PUBLISH_NEW`, the slot ordinal in S12, then write a new S7 request generation last;
5. for state changes use `S11=2`, SlotOrdinal, exact ExpectedJobGeneration S13, DesiredState S14, and ErrorStatus S15;
6. use `S11=3 REAP` only for COMPLETE/FAULT/CANCELLED jobs and with the exact current JobGeneration;
7. accept Store responses only when `S8` matches the request generation and `S9=1`.

Every reader captures even QueueSequence before reading an intent slot + its active A/B state triplet and requires the same even sequence afterward. The Job Store mechanically rejects stale generations, terminal reopening, non-terminal reaping, occupied PUBLISH_NEW slots, and slot ordinals outside `0..31`.

The writer must additionally enforce the legal lifecycle table in `docs/GENERIC_JOB_ABI.md` / `data/generic_job_schema.json`. `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` is the first production writer and owns TRANSFORM/PRINT priority ordering, processor selection, reservation planning, and wait-state transitions. Do not bypass that lifecycle contract by using SET_STATE as an arbitrary state setter.

## Manufacturing Scheduler deployment

Roadmap item 6 composes Generic Jobs, Recipe/Transform catalogs, MaterialGrid, and generic directories. Full cell contracts and diagrams are in `docs/MANUFACTURING_SCHEDULER.md`; the deployment-critical instance wiring is:

1. Keep `ic10/generic-jobs/generic_job_store_v1_0.ic10` resident. Deploy `ic10/generic-jobs/generic_job_selector_v3_0.ic10` (`d0 -> Job Store`), `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` (`d0 -> Job Gateway`, `d1 -> Job Selector`, `d2 -> Dependency Gate`), and `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` (`d0 -> Transform Driver`, `d1 -> Print Driver`, `d2 -> Job Selector`).
2. Deploy a TransformLane directory: `173 Adapter -> 169 Bridge -> dedicated 166 Snapshot Host`.
3. Deploy one `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` instance with `d0 -> TransformLane Snapshot Host`; wire the Transform Job Driver `d0` to that selector and `d1 -> ic10/manufacturing/transform_candidate_executor_v2_0.ic10`.
4. Keep Printer Directory v2 running. For scheduled printers, attach each eligible printer to one `184 Printer Execution Bank` pin (`d0..d5`, at most six printers per bank).
5. Deploy `185 Printer Execution Directory Adapter -> 169 Bridge -> dedicated 166 Snapshot Host`. The resulting `DirectorySchema.PrinterExecution` v1 records preserve exact PrinterReferenceId and add local output-capacity state.
6. Deploy a second `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` instance with `d0 -> PrinterExecution Snapshot Host`; wire the Print Job Driver `d0` to that selector, `d1 -> ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10`, and `d2 -> ic10/manufacturing/print_candidate_executor_v2_0.ic10`.
7. Wire `ic10/manufacturing/print_candidate_executor_v2_0.ic10`: `d0 -> Recipe Execution View`, `d1 -> Print Material Resolver`, `d2 -> Generic Print Runtime`, `d3 -> Printer Capacity Client`. Capacity Client discovers Execution Banks and revalidates exact PrinterReferenceId at reservation time.
8. Wire `177 d0 -> Recipe Execution View`, `d1 -> ResourceLink Snapshot Directory`.
9. Deploy a print-specific `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` and `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`. Wire both to the print resolver exactly as the transform lane wires them to its resolver; then wire Generic Print Runtime `d0 -> Print Material Resolver`, `d1 -> print Allocator`.
10. Keep Recipe schema-v3 Stores/View, ITEM Resource Profile infrastructure, Resource Endpoints/Reservations/Links, and any transform lanes required by queued jobs live.

A single source program may have several physical instances. In particular, normal mixed manufacturing uses two Manufacturing Candidate Selector instances and separate mutable Stager/Allocator instances for transform and print lanes.

The manufacturing scheduler selects only TRANSFORM and PRINT JobTypes. TRANSFER remains a Generic Job ABI type without a dispatcher; POWER uses the separate finite policy scheduler from Item 9.

## Optional Generic Resource / MaterialGrid deployment

The generalized Resource Core is additive and is not required for an existing pressure-grid deployment. MaterialGrid uses one current transform path for Arc Furnace, Furnace, and Advanced Furnace work.

### A. Deploy shared Resource Profile infrastructure

1. Ensure the global Coordinator Core is running. Start Loader Router only for the import/rebuild window.
2. Provide Generic Store capacity by programming `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` on unclaimed IC housings and assigning each a unique `S18 NodeId` from 1..64. The current profile catalog needs at least three Stores under Store ABI6 geometry, but no Store is preassigned to FLUID or ITEM.
3. Deploy the generated FLUID and ITEM Resource Profile loader candidates. They contain relocatable whole 16-cell profile items and require no Store wiring or Store ordinal.
4. The Router places each item into matching runtime capacity; the Coordinator claims/links more Stores only when needed.
5. Verify the 39 profiles settle into healthy ACTIVE Stores with stable even `S17`. Use Coordinator telemetry/View rather than Loader counts to determine readiness.
6. Deploy `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` for each simultaneously selected resource and wait for `S28=1` with positive `S29` before wiring consumers.

### B. Deploy ITEM sources and processor sinks

For each source ITEM identity:

1. select the ITEM Resource Profile;
2. deploy `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10`: `d0` Vending, `d1` Resource Profile View;
3. deploy `ic10/resource-grid-core/resource_reservation_v1_0.ic10`: `d0` source Endpoint;
4. wait for a coherent healthy source Reservation.

For each processor input identity:

1. deploy `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10`: `d0` processor/import device, `d1` matching Resource Profile View;
2. deploy another `ic10/resource-grid-core/resource_reservation_v1_0.ic10`: `d0` import Endpoint.

### C. Deploy each physical material route

Physical chute path:

```text
Vending Machine -> Stacker -> Logic Sorter -> processor/import sink
```

For each usable resource route deploy:

1. `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10`: `d0` Vending, `d1` Stacker, `d2` Logic Sorter;
2. `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10`;
3. `ic10/material-grid/material_transfer_executor_v1_0.ic10`;
4. `ic10/material-grid/material_resource_link_v1_0.ic10`: `d0` source Reservation, `d1` sink Reservation, `d2` Feeder, `d3` Guard, `d4` Executor;
5. Guard `d0` -> Link, `d1` -> `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`, `d2` -> Executor;
6. Executor `d0` -> Link, `d1` -> Feeder, `d2` -> Guard.

The Link must publish **Reservation ReferenceIds** in Generic Link `S28/S29`; native Vending/Stacker/Sorter/sink identities are separate extension fields. Manually verify that the Sorter's accepted physical chute reaches the intended sink because IC10 cannot discover invisible chute connectivity.

### D. Publish Resource Link discovery

Deploy one logical Resource Link directory as:

```text
ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10
        |
ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10
        |
ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10
```

The Host publishes Generic Snapshot Directory identity `HASH("GenericSnapshotDirectoryHost.v1")`, with `DirectorySchema.ResourceLink` schema version 1, width 1, capacity 64. Use a separate Host IC for a Resource Endpoint directory if needed; the Host program is reusable but each logical directory owns a separate stack.

### E. Commission the Resource Transform catalog

1. Ensure Coordinator Core/Router are running and there is available Generic Store capacity.
2. Deploy Transform Loader candidates `ic10/transform-catalog/resource_transform_catalog_loader_00_v6_0.ic10` through `ic10/transform-catalog/resource_transform_catalog_loader_04_v6_0.ic10`.
3. Wait for the current 17 transform items to reside in ACTIVE Store capacity with stable even store sequence.
4. Deploy `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` and select the desired TransformType; require View ABI4, a matching S68 request echo with S69 status 1, and a positive S74 publication generation.
5. Publish a healthy output Resource Reservation for the transform output identity.

### F. Deploy the one current material transform transaction path

For every transform processor use:

```text
161 Admission:      d0 Transform View, d1 Processor, d2 Output Reservation
162 Link Resolver:  d0 Admission, d1 Transform View, d2 Resource Link generic directory
163 Stager:         d0 Link Resolver, d1 Multi Allocator
164 Allocator ABI2: d0 Link Resolver, d1 Stager
165 Runtime:        d0 Processor, d1 Admission, d2 Link Resolver,
                    d3 Multi Allocator, d4 Output Reservation
```

Each selected Material Link must already have its Feeder, Guard, Executor, source/sink Reservations, and exact processor native sink wired as above. `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` requires **Allocator ABI2 exactly**.

Processor capability masks determine which transforms can run:

```text
Arc Furnace       1  -> basic one-input smelts
Furnace           3  -> basic smelts + two-input alloys
Advanced Furnace  7  -> all current one/two/three-input transforms
```

The same 161..165 path handles every case. There is no separate Arc-Furnace-only runtime in the current baseline.

### G. Optional Generic Resource projection for PressureGrid

Use `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` and `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` when projecting hardened pressure resources into the same Generic Resource Core. Publish them through the appropriate schema-qualified Generic Snapshot directories.

Material Allocator ABI2 serializes one transform allocation per allocator instance while allowing one-to-three inputs to commit under a common epoch. Generic Job ABI now supplies the common TRANSFORM/PRINT/TRANSFER lifecycle. General direct-transfer execution and broader manufacturing concurrency are deferred to the Manufacturing Scheduler rather than a second allocator protocol.

## Catalog control-plane v3 commissioning

Deploy one control-plane set on the catalog network:

- `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` — persistent directory stack;
- `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` — publishes live Store candidates on its own stack;
- `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` `d0` -> Store Directory Adapter;
- `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` — `d0 -> Directory Host`; set CoordinatorId/CoordinatorEpoch before first initialization when non-default values are desired;
- start `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` (`d0 -> Coordinator Core`) only while importing or rebuilding Loader items;
- optional observability: `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` (`d0 -> Registry Host`), `ic10/catalog-control-plane/catalog_inspector_v4_0.ic10`, and `ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10`;
- on-demand lifecycle services: Catalog Coordinator Recovery, Item Migration Item Migration Planner + Item Migration Worker, and Store Retirement Manager.

For every physical catalog-storage IC, program `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` and set only `S18 NodeId` to a unique value 1..64. Scanner should show it UNCLAIMED. Loaders can then be programmed independently; Router/Core select capacity at runtime and Stores pull assigned relocatable whole items. No Loader or generator preassigns a Store ordinal or physical Store ReferenceId.

A replacement Coordinator uses the same CoordinatorId and a higher CoordinatorEpoch, then runs Catalog Coordinator Recovery against the persistent Directory. To remove/compact a Store, mark it DRAINING: Item Migration Planner and Item Migration Worker migrate complete tail items into compatible ACTIVE capacity (claiming another Store if necessary); Store Retirement Manager unlinks the Store only after it is empty. Never physically remove a live non-empty Store before migration completes.

## Material transform deployment summary

The canonical material transform wiring is documented in Optional Generic Resource / MaterialGrid deployment section F above and in `docs/ORE_PROCESSING_TRANSFORMS.md`. All one-, two-, and three-input furnace transforms use the semantic services under `ic10/material-transform/`; every Material Grant Guard requires Material Allocator ABI2 exactly.


## Manufacturing Scheduler and dependency-planner deployment

Deploy the manufacturing control plane only after Generic Job Store, ITEM Resource Reservation discovery, recipe/transform catalogs, processor directories, and material execution paths are healthy. The dependency layer is a control-plane guard above the existing scheduler; it is not another scheduler or physical reservation owner.

Recommended resident chain:

1. `ic10/generic-jobs/generic_job_store_v1_0.ic10` Generic Job Store.
2. `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` four-lane command arbiter.
3. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10`, the sole physical Job Store mailbox writer for Scheduler/Planner/Child/Power commands.
4. Dependency-planning services under `ic10/dependency-planning/`, plus the shared Generic Job Gateway/Store Executor.
5. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` (default manufacturing mode) and `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10`.
6. `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` between Scheduler and `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10`.
7. Existing Transform/Print drivers, reservation lanes, and printer-capacity services.

Printer execution still uses `ic10/printer-directory/printer_execution_bank_v2_0.ic10` as the exact local capacity/ownership authority. Dependency planning never substitutes its logical future-output claims for Item-7 or printer physical reservations.

The Gateway lanes must have one producer each: lane A Scheduler, lane B dependency Planner cancellation, lane C Child Creator, lane D Power Scheduler. Do not connect two writers to one lane.


## Cross-domain process utility deployment

Item 11 is optional unless a deployment wants automatic furnace conditioning or fuel-backed generation. See `docs/PROCESS_UTILITY_ORCHESTRATION.md` for the complete contracts.

For one Advanced Furnace:

1. Deploy `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10`: `d0` -> selected Transform Profile View, `d1` -> Furnace/Advanced Furnace; set S16 semantic prepared medium, S17 enable, S18 strategy.
2. Deploy `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10`: `d0` -> `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10`, `d1` -> the same furnace. Attach ordinary Pressure Domain Inventory + Pressure Inventory Reservation and a matching purity guard so PressureGrid sees the chamber as a process STORAGE domain.
3. For an Advanced Furnace embedded pump, deploy one `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` per direction: source/sink pressure Reservations on d0/d1, furnace d2, `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` d3; select S17=1 inlet or S17=2 outlet.
4. If thermal preparation is needed, deploy `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` with hot/cold source analyzers, conditioned output analyzer, Gas Mixer, and the furnace ProcessCondition. Commission the conditioned output network as a PressureDomain STORAGE source.
5. Keep `ic10/material-transform/material_transform_admission_v1_0.ic10` as final transform P/T admission authority; do not wire utility status as permission to bypass it.

For H2/O2 fuel-backed GFG generation:

1. Load Resource Profile `Fuel.H2O2` (kind 5) through the ordinary Resource Profile catalog.
2. Deploy `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` on the prepared-fuel output network; connect it to a Resource Profile View selecting `Fuel.H2O2`.
3. Deploy `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` with GFG d0, Power Plan Store d1, ambient sensor d2, mixture guard d3; configure S16 medium, S17/S18 fuel pressure envelope, S19 shortage trigger, S20 enable.
4. Feed the GFG utility controller's ProcessCondition to `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` d5. That mixer controller uses d0/d1 for pure Volatiles/Oxygen sources, d2 for the prepared-fuel buffer, d3 for the Gas Mixer, and d4 for the `Fuel.H2O2` profile.
5. Expose the prepared-fuel buffer and GFG fuel-side network through ordinary PressureDomains/Reservations/PressureTransfers. PressureGrid, not the gas-mixer or GFG utility controller, owns physical delivery.

Do not configure an Electrolyzer to start recursively from the same GFG shortage. Surplus-power-to-fuel operation requires a separate storage policy that prevents simultaneous charge/discharge justification.

## Item-12 live commissioning tools

After automated validation, deploy `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` only when a field case benefits from coherent read-only capture. It is an on-demand diagnostic, not a resident control-plane dependency. Configure its six descriptors, advance `S14 DescriptorGeneration`, then publish `S10 RequestToken` last. Record the resulting values/status together with the physical action in a `tools/live_commission.py` session. Do not leave the probe wired as an actuator intermediary and do not treat its observations as reservation authority. See `docs/LIVE_COMMISSIONING.md`.
