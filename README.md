# Stationeers IC10 Generic Controller Framework v1

This bundle is the first deployable baseline of the framework. There are no supported pre-v1 deployments and no legacy compatibility paths.

The framework separates **controller-specific behavior** from **generic infrastructure**. A new controller family normally supplies a runtime, a configuration policy, and optionally an input profile. Discovery, selection, editing, persistence, physical commissioning inputs, diagnostics, and transaction handling are shared.

## Start here

If you are new to the framework, read the documents in this order:

1. **README.md** — mental model, major components, and terminology.
2. **docs/ARCHITECTURE.md** — component ownership and end-to-end data flow.
3. **docs/PI_CONTROLLER_GETTING_STARTED.md** — smallest creative-mode PI controller bench test using existing scripts.
4. **docs/STACK_ABI_ENVELOPE.md** and **docs/STACK_CELL_MONITOR_GETTING_STARTED.md** — common service discovery contract and reusable visible inspection of production IC stack cells.
5. **docs/CONTROLLER_DIRECTORY_GETTING_STARTED.md** — isolated Controller Directory discovery, publication, removal, and recovery test.
6. **docs/COMMISSIONING_QUICKSTART.md** — shortest path to a full PI deployment and diagnostics panel.
7. **USER_DEPLOYMENT_GUIDE.md** — operator-facing per-family deployment manual covering all production IC10 programs, residency/reclaim rules, health checks, restart behavior, and live proof.
8. **docs/DEPLOYMENT.md** — full fresh-install sequence and dependency order.
9. **docs/SHARED_INPUT_SYSTEM.md** — physical commissioning inputs and catalog-backed logical values.
10. **docs/CATALOG_COORDINATION.md**, **docs/CATALOG_STORAGE.md**, and **docs/CATALOG_SCHEMA.md** — generic catalog control/data plane.
11. **docs/DIRECTORY_STANDARD.md** — reusable live-directory infrastructure and schemas.
12. **docs/ASYNC_REQUEST_STANDARD.md** and **docs/BANKED_TRANSACTION_STANDARD.md** — request fencing and durable transaction semantics.
13. **docs/GENERIC_JOB_ABI.md** — common job record, lifecycle, Job Store geometry, and generation fencing.
14. **docs/MANUFACTURING_SCHEDULER.md** — TRANSFORM/PRINT queue policy and execution routing.
15. **docs/ITEM_STORAGE_SYSTEM.md** — Generic ITEM inventory, split reservations, LArRE/direct/SDB storage, and chute handoff.
16. **docs/DEPENDENCY_PLANNING.md** — bounded dependency expansion, shared future-output claims, cancellation, and Job Store command serialization.
17. **docs/POWER_MANAGEMENT.md** — POWER/ENERGY profiles, dispatch, reservations, electrical actuation, and finite POWER jobs.
18. **docs/PROCESS_UTILITY_ORCHESTRATION.md** — cross-domain ProcessCondition, furnace atmosphere preparation, gas mixing, and fuel-backed POWER.
19. **docs/INTERRUPTION_FAULT_INJECTION.md** — reusable restart campaign and cross-subsystem fault matrix.
20. **docs/LIVE_COMMISSIONING.md** — Item-12 field-evidence workflow, read-only snapshot probe, stack-cell monitor, and release-bound commissioning sessions.
21. **docs/CONTRACT_COMMISSIONING.md** — contract-aware validation and field evidence for explicit in-world screw-terminal wiring.
22. **ROADMAP.md** and **docs/COMPLETED_MILESTONES.md** — Items 1–11 completion records plus the active Item-12 field milestone.
23. **docs/RESOURCE_GRID_CORE.md**, **docs/MATERIAL_GRID_FOUNDATION.md**, **docs/MATERIAL_TRANSFER_SYSTEM.md**, and **docs/ORE_PROCESSING_TRANSFORMS.md** — resource/material execution model.
24. **docs/RECIPE_CATALOG.md** and **docs/PRINTER_DIRECTORY.md** — printer recipe/discovery metadata.
25. **docs/CONFIG_INPUTS.md**, **docs/CONFIG_BLOCKS.md**, **docs/CONFIG_POLICY.md**, and **docs/PERSISTENCE_STANDARD.md** — configuration system.
26. **docs/SCRIPT_CONTRACTS.md**, **docs/DIAGNOSTIC_INPUTS.md**, and **docs/ABI_REFERENCE.md** — machine-readable contracts, diagnostics, and exact wiring contracts.
27. **docs/SEQUENCER_CONTROLLER.md**, **docs/PHASE_PRESSURE_CONTROLLER.md**, **docs/PHASE_MEDIUM_PROFILE.md**, **docs/PRESSURE_DOMAIN_CONTROLLER.md**, **docs/PRESSURE_INVENTORY_MODEL.md**, **docs/PRESSURE_GRID_CONTROLLER.md**, **docs/PRESSURE_RESERVATION_MODEL.md**, **docs/PRESSURE_MULTI_HOP_ROUTING.md**, and **docs/PRESSURE_ROUTE_COST_MODEL.md** — worked controller/resource specializations.
28. **docs/CORRECTNESS_HARDENING.md**, **docs/ADDING_CONTROLLERS.md**, **docs/SCRIPT_INDEX.md**, **docs/SOURCES.md**, and **docs/TEST_CONTROLLER.md** — extension, audit, and provenance material.
29. **docs/CI.md** — required GitHub validation check, clean-tree policy, failure evidence, and branch-protection setup.

`VALIDATION_SUMMARY.txt` summarizes the latest clean release run; per-script machine evidence is generated under `validation/evidence/`. `docs/FRAMEWORK_HARDENING_TESTS.md` lists the live-game cases that still need physical verification; `docs/LIVE_COMMISSIONING.md` defines how those results are bound to a release and recorded without contaminating automated evidence.



## Project layout

The repository uses **semantic paths**, not historical source ordinals. Production filenames keep their explicit version suffixes (`_v<major>_<minor>`), while deployment family and class live in `data/source_manifest.json`. Generated catalog page indices such as `_00` remain because they identify meaningful generated partitions rather than source ordering.

```text
ic10/<deployment-family>/     versioned production IC10 programs
contracts/                    generated per-script contracts, protocol/envelope registries, and definitions
schemas/                      JSON Schema definitions for generated contract documents
docs/                         engineering/reference documentation
framework/                    executable protocol reference models
data/                         JSON sources of truth: schemas, profiles, manifests
tests/                        executable protocol/model tests
tests/ic10/                   test-only IC10 fixtures (ControllerTest family)
tests/fixtures/               non-IC10 fixture input consumed by tests
validation/validators/        structural and release-contract validators
validation/evidence/          generated per-check machine evidence
tools/                        command-line entrypoints
tools/generate/               code generators driven by data/
```

Do not infer execution order, ABI identity, or deployment order from a filename. Use the semantic path, version suffix, `data/source_manifest.json`, `contracts/index.json`, `contracts/stack_envelope_inventory.json`, `docs/SCRIPT_INDEX.md`, and `USER_DEPLOYMENT_GUIDE.md`.

## Mental model

There are six different kinds of state in the system. Keeping them separate makes the architecture easier to reason about:

- **Physical input state** — which dials/switches/memory devices exist and what they currently read. Scanner/Resolver own this.
- **UI/staging state** — which controller or console is selected and what configuration values are being edited. Selectors, bridges, and Editor own this.
- **Durable configuration state** — the committed controller configuration that must survive reflash/power interruption. Generic Persistent Config Host + Config Policy own this.
- **Runtime/telemetry state** — the live controller algorithm and values exposed to diagnostics. Controller Runtime owns this.
- **Resource-grid state** — typed export/import capacity, reservations, physical links, transformations, and cross-domain process-condition demands. PressureGrid remains the fluid specialization; Generic Resource Endpoint/Reservation/Link contracts now provide a domain-neutral planning surface, and MaterialGrid supplies the non-fluid implementation with coherent warehouse inventory, exact discrete-batch movement, capability-based one-to-three-input Furnace/Advanced-Furnace transforms, and the TRANSFORM/PRINT manufacturing scheduler above the shared reservation substrate.
- **Job intent/lifecycle state** — scheduler-neutral requested work, priority, lifecycle state, optimistic JobGeneration, and error/wait status. Generic Job Store owns publication; Manufacturing Scheduler owns TRANSFORM/PRINT queue policy, planning, and legal lifecycle transitions.

A ReferenceId points at a specific device instance. A hash such as `ControllerType` identifies a family/type. A generation number means “this snapshot or request is newer than the previous one.” Generation values are normally written **last** so consumers never accept a partially updated record.

## Core architecture

```text
Physical commissioning devices
        |
Generic Input Scanner
        |
Generic Input Resolver <---- Generic Input Profile
        |
        +---- Config Input Bridge ----> Generic Config Editor
        |
        +---- Diagnostic Input Bridge ----> Diagnostic Selector Bridge
                                             |              |
                                      Controller Selector  Console Selector
                                             \              /
                                              Mapping Editor
                                                   |
                                                Renderer

Controller Selector -> Generic Editor / Loader / Committer
                                |
                     Generic Persistent Config Host <---- Config Policy
                                |
                         Controller Runtime
```

The Scanner/Resolver pair is deliberately domain-neutral. Configuration and diagnostics share the same input kinds, Dial scaling, enum handling, Switch mapping, Memory fallback, generation checks, and physical-device classification.

## What is generic vs controller-specific

### Generic infrastructure

These components should not need controller-family changes:

- Generic Controller Directory (Adapter + Bridge + Snapshot Host);
  - up to 64 controllers are stored as sorted `[ControllerType, ReferenceId]` records;
- Console Registry;
- Controller Selector ABI2, which derives type/member groups directly from the sorted Controller Directory, plus Console Selector;
- Generic Input Scanner and Resolver;
- Config Input Bridge, Editor, Loader, and Committer;
- Generic Persistent Config Host;
- Diagnostic Input/Selector Bridges, Mapping Editor, and Renderer.

### Controller-family components

A normal family supplies:

- a **Runtime** that reads the effective config and performs the control algorithm;
- a **Config Policy** that defines schema geometry, defaults, validation, and normalization;
- optionally an **Input Profile** that describes a convenient physical editing experience.

This distinction matters: configuration *values* live in a Host instance, while configuration *meaning* lives in the Policy/Profile. Multiple controllers can therefore use the same framework without baking their stored values into generic scripts.

### Deployment classes

The source bundle contains **173 production-capable IC10 programs**, but they are not all resident services. `USER_DEPLOYMENT_GUIDE.md` maps every one to exactly one operational family and deployment class; release validation rejects undocumented programs. Treat them as five deployment classes:

- **resident runtime/control-plane** — controller Runtime/Host/Policy that normally stays powered whenever its family is installed;
- **conditional resident** — resource, directory, scheduler, and domain services that stay powered only while their optional subsystem/live consumer is enabled;
- **commissioning** — discovery selectors, configuration UI/input services, and diagnostic mapping services; power/reprogram them after commissioning when no live consumer needs them;
- **one-shot catalog producers** — Loader ABI5 programs; reclaim those housings after all intended items are durably imported. Loader Router is on-demand during import/rebuild rather than a one-shot data producer;
- **on-demand diagnostics/lifecycle** — Catalog Inspector, Directory Telemetry, Directory View, Recovery, Item Migration Planner + Worker, Store Retirement Manager, the read-only Live Commission Snapshot Probe, and the visible Stack Cell Monitor.

`ControllerTest` is no longer a production family/profile. Its Runtime, Policy, and standalone test Input Profile live under `tests/ic10/` and are deployed only for framework isolation testing.

## Catalog coordination control plane

Static catalogs use one global coordination control plane plus generic data-plane Stores. Keep `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10`, `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10`, and `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` resident while catalog membership must remain live. Program `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` only while importing/rebuilding catalog items, and deploy `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` wherever catalog capacity is needed. Set each new Store's `S18 NodeId` to a unique positive ID; it advertises UNCLAIMED and the Coordinator assigns schema, catalog instance, partition, ordinal, topology, and AssignmentEpoch when pending Loader data requires capacity. Loaders remain one-shot sparse immutable candidates; Stores pull assigned ranges. See `docs/CATALOG_COORDINATION.md`.

## Generic Resource Core

The hardened PressureGrid is now treated as the first specialization of a broader resource-orchestration model rather than being renamed or weakened. `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` normalizes pressure inventory into Generic Resource Endpoint ABI1, while `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` publishes that exact same Endpoint ABI for one ItemHash in a Vending Machine. Both feed `ic10/resource-grid-core/resource_reservation_v1_0.ic10` unchanged.

A Generic Resource Link ABI is also defined; `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` proves that an existing PressureTransfer can be projected into that contract while preserving topology identity. Resource Transform Profile ABI4 adds resolved-request fencing plus variable-length typed input/output descriptors, process bounds, and processor capability requirements for ore processing and manufacturing.

Live printer discovery uses `ic10/printer-directory/printer_directory_adapter_v1_0.ic10` plus the ordinary Generic Directory Bridge/Host. `DirectorySchema.Printer` v2 publishes `[ReferenceId, FamilyHash, ProcessorSpec]`; the family hash is exactly the Recipe Catalog partition key and the packed ProcessorSpec shares capability/Power/Busy/Error semantics with TransformLane discovery. Scheduled printing overlays locally verified output capacity through `DirectorySchema.PrinterExecution` v1 rather than attempting remote slot access by ReferenceId. See `docs/PRINTER_DIRECTORY.md` and `docs/MANUFACTURING_SCHEDULER.md`.

Generic jobs use `GENERIC_JOB_ABI_V1`. `ic10/generic-jobs/generic_job_store_v1_0.ic10` stores 32 logical eleven-field jobs with Store-owned JobIds, immutable intent, per-slot A/B lifecycle state, optimistic JobGeneration, and a queue-wide odd/even publication sequence. Job persistence is the `SELECTOR_BANK` profile of `BANKED_TRANSACTION_V1`; Store magic **and ABI** must match before existing durable geometry is interpreted. `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` owns TRANSFORM/PRINT lifecycle policy through Job Gateway lane A, while `ic10/power-jobs/power_job_scheduler_v1_0.ic10` uses independent lane D for finite POWER policy jobs. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` supplies the shared coherent Priority/JobId/cursor selection primitive for both domains. `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` arbitrates four producer lanes and `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` remains the sole physical Job Store mailbox writer. TRANSFER remains outside these schedulers. See `docs/GENERIC_JOB_ABI.md`, `docs/MANUFACTURING_SCHEDULER.md`, `docs/DEPENDENCY_PLANNING.md`, and `docs/POWER_MANAGEMENT.md`.

Offline lifecycle, crash-recovery, optimistic-generation, and slot-reuse behavior is exercised by `tests/test_job_abi.py`.

Recipe schema v3 uses common **Store ABI6 / Loader ABI5** and partitions runtime storage by **printer family first**. Each recipe is a variable-width, 4-cell-aligned whole item carrying RecipeHash, FamilyHash, capability tier, ordinal, InputCount, and bounded `[ManufacturingReagentHash, Quantity]` pairs. Runtime Store capacity is therefore derived from actual whole-item widths rather than a fixed 80 recipes. `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` remains Lookup ABI3 for family/ordinal browsing, while `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` resolves exact RecipeHash execution metadata for the scheduler. The 780-recipe stress fixture now derives 18 Stores (`48+48+34` per family). See `docs/CATALOG_COORDINATION.md`, `docs/CATALOG_STORAGE.md`, `docs/CATALOG_SCHEMA.md`, `docs/RECIPE_CATALOG.md`, and `docs/MANUFACTURING_SCHEDULER.md`.

MaterialGrid uses one canonical one-to-three-input transform transaction backed by the 17-transform catalog. `ic10/material-transform/material_transform_admission_v1_0.ic10` validates capability, universal declared pressure/temperature bounds, and output capacity; `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` resolves typed routes; `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` stages reservations/Guards; `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` publishes one common epoch only after every input stages; and `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` waits for all inputs and confirms coherent output growth. Item 6 now adds queue scheduling and parallel processor discovery above this unchanged transaction. Printing reuses the same Stager/Allocator protocol through a print-specific resolver, while Recipe schema-v3 reagent identities are matched to concrete MaterialGrid resources through Resource Profile `ManufacturingReagentHash`. Gas/fuel strategy remains a separate domain concern; bounded dependency expansion is implemented in Item 8 and electrical PowerGrid reservation/load shedding is implemented in Item 9. See `docs/RESOURCE_GRID_CORE.md`, `docs/MATERIAL_GRID_FOUNDATION.md`, `docs/MATERIAL_TRANSFER_SYSTEM.md`, `docs/ORE_PROCESSING_TRANSFORMS.md`, and `docs/MANUFACTURING_SCHEDULER.md`.

## Input hardware reduction

A commissioning panel can use one shared physical control set:

```text
Field Dial
Value Dial
optional Logic Memory fallback
Switch
Generic Input Profile
```

The Field Dial chooses the logical field/control. The Value Dial, Switch, or Memory device supplies the value according to the active Profile descriptor. Controller Selector, Console Selector, Mapping Editor, and Generic Config Editor no longer own physical input screws.

For diagnostics, the Field Dial chooses one of seven controls: Controller Type, Controller Member, Console, Telemetry Channel, LED Mode, LED Color, or Commit.

## Configuration standard

- fixed block width: 8 physical slots;
- maximum 4 blocks / 32 physical slots;
- Host validity masks are authoritative schema geometry;
- Loader derives active ordinal -> physical-slot mapping;
- Committer transports only valid slots;
- Config Policy owns defaults and semantic validation/normalization;
- Generic Host owns A/B persistence and transaction publication.

“Physical slot” is the stable schema address. “Active ordinal” is the human-facing 1..N field number after reserved holes are removed. They are intentionally different concepts.

## Persistence

Each Generic Host owns two 32-slot banks. Each bank footer contains `schemaSignature`, `controllerConfigRevision`, and `bankRevision/commit token`. Destination revision is invalidated before writes; the new revision is written last. Recovery selects the newest valid bank matching the current Policy signature. If the recovered `controllerConfigRevision` already equals the outstanding Host request generation, the Host acknowledges that durable request rather than committing the same image again. Config persistence is the `REVISION_BANK` profile of `BANKED_TRANSACTION_V1`.

The key consequence is that an interrupted write should leave either the old committed configuration or the new committed configuration recoverable — never a half-written bank treated as valid.

## Shared Input Profile Catalog

Controller and diagnostic input metadata is catalog-backed through Store ABI6 / Loader ABI5. Deploy the global Coordinator/Router and at least one unclaimed `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` with a unique `S18 NodeId`, then program the three one-shot sparse Loader candidates `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` through `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10`. The Router places the six self-contained schema-v3 production/diagnostic profiles into compatible runtime capacity; they currently fit one Generic Store. `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` then selects the desired context and republishes the unchanged Generic Input Profile ABI expected by Scanner/Resolver/Config Loader.

Examples: `S2=HASH("ControllerPI"), S3=1` for PI configuration; `HASH("ControllerSequencer")/1`, `HASH("ControllerPhasePressure")/1`, `HASH("ControllerPressureDomain")/1`, or `HASH("ControllerPressureTransfer")/1` for those families; `HASH("DiagnosticMapping")/1` for diagnostics. All profiles share the one catalog store.

## PI deployment

The PI family uses:

- `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`
- `ic10/controller-pi/pi_config_policy_v1_0.ic10` (`d0` -> Host)
- `ic10/controller-pi/controller_pi_runtime_v1_1.ic10` (`d2` -> Host)
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` (optional commissioning Profile)
- shared Scanner + Resolver + Config Input Bridge for physical editing

See `docs/COMMISSIONING_QUICKSTART.md` for the minimum deployment path and `docs/DEPLOYMENT.md` for the full dependency-aware sequence.

## Sequencer deployment

`ControllerSequencer` is intentionally unlike PI. It implements a discrete `FILL -> SETTLE -> DRAIN` state machine with repeat/complete behavior, per-phase timeout protection, two mutually-exclusive action outputs, and state/fault telemetry. It uses the same Generic Host, configuration pipeline, shared inputs, discovery, and diagnostics without any generic-service special cases.

Family files:

- `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`
- `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10`

See `docs/SEQUENCER_CONTROLLER.md` for wiring, state semantics, schema fields, result/status codes, telemetry, and commissioning examples.

## Phase-pressure deployment

`ControllerPhasePressure` is the hybrid thermodynamic controller family. It derives a **pressure requirement** from the working medium's current temperature and phase boundary, then either writes that requirement directly to a pressure-setpoint device or publishes it for the shared PressureDomain layer, whose Inventory/Reservation services now feed the world-grid scheduler.

Family/profile files:

- `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`
- `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10`
- `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10`
- `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10`
- `data/resource_profile_catalog_manifest.json`
- `data/resource_profiles.json`
- `tools/generate/generate_resource_profiles.py`

Working-medium constants remain outside the controller runtime, but they no longer require one IC10 program per medium. The same unified catalog also owns material-item profile metadata. Configure a Resource Profile View with `S2=FLUID` and `S3=HASH(<medium>)`, connect its `d0` to any Store in the runtime Resource Profile topology after the Coordinator has placed the profile items, and connect the controller or purity service to the View. The current runtime topology derives one FLUID Store, two ITEM Stores, one POWER Store, and one ENERGY Store from capacity; loader filenames are authoritative in `data/resource_profile_catalog_manifest.json`. See `docs/RESOURCE_PROFILES.md` for the shared catalog/view ABI and `docs/PHASE_MEDIUM_PROFILE.md` for thermodynamic selection guidance.

The runtime always publishes `RequestedPressure`, phase mode, status, and medium identity. `DirectWrite=0` is a publish-only/alternate-actuation mode, but a normal grid deployment will usually keep `ControllerPhasePressure.DirectWrite=1` because the phase-change chamber still needs its own pressure setting. The grid manages the external LOW/HIGH pressure buses and transfer paths; it does not automatically replace the chamber-setpoint owner.

## Pressure-domain deployment

`ControllerPressureDomain` provides the shared **pressure-grid domain infrastructure**. It consumes requests from multiple `ControllerPhasePressure` instances through a dedicated PhasePressure Request Arbiter, filters them by working medium and domain role, and derives one safe local pressure-domain target.

Files:

- `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10`
- `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`
- `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10`

A LOW domain serves evaporation requests and chooses the minimum compatible requested pressure. A HIGH domain serves condensation requests and chooses the maximum. Runtime revision 1.1 adds a third `STORAGE` role: a passive medium-specific reservoir whose `MinimumPressure` is its export reserve floor and whose `MaximumPressure` is its import ceiling. LOW/HIGH can still use paired local setpoint devices or publish their targets only; STORAGE is intentionally passive.

See `docs/PRESSURE_DOMAIN_CONTROLLER.md` for arbitration semantics, role-specific telemetry, wiring, status codes, safety-limit behavior, and STORAGE commissioning.

## Pressure-grid transfer deployment

The Level-3 grid now supports **parallel single-hop reservations plus automatic multi-hop reuse paths**. Direct `LOW -> HIGH` links remain the preferred fast path. When no direct physical edge can satisfy all remaining demand, the grid can route the same working medium through one or two STORAGE domains:

```text
LOW -> STORAGE -> HIGH
LOW -> STORAGE A -> STORAGE B -> HIGH
```

Current files:

- `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` — commit authority, Planner ABI2
- `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` — one physical pump edge; routes 1..4
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`
- `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10`
- `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10`
- `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10`
- `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` — endpoint reservation/staged-grant writer
- `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` — stable 64-link transfer-only topology snapshot
- `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` — resumable 2/3-hop LOW-to-HIGH path enumeration
- `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` — whole-path staging and common-rate normalization
- `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` — direct/fallback sweeps
- `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` — direct -> routed reuse -> fallback orchestration
- `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` — bounded candidate comparison and best-route selection
- `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` — tunable hop/storage/lift/throughput weights and candidate budget
- `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` — reservation-aware route scoring and per-search best-candidate retention
- `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` — actual-medium purity verification for each grid pressure domain
- `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` — topology-bound committed lease activation

One global Grid Link Directory derives transfer topology from the shared 64-controller Controller Directory. For each working medium, deploy one Planner stack: Plan Builder, Single-Hop Builder, Path Enumerator, Route Selector/Ranker, Cost Profile, Path Allocator, Reservation Allocator, and matching PHASE_MEDIUM Resource Profile View.

Planning order is:

```text
1. LOW -> HIGH direct reuse
2. LOW -> STORAGE [-> STORAGE] -> HIGH routed reuse
3. LOW -> STORAGE / STORAGE -> HIGH fallback
```

`STORAGE -> STORAGE` is route class 4 and is admitted only inside a complete multi-hop path. Ordinary fallback retains the anti-circulation rule and will not independently charge and discharge the same STORAGE resource in one build.

All capacity accounting remains molar. Single-hop grants reserve their endpoints before staging. Multi-hop paths use a non-mutating whole-path QUOTE and then exact-COMMIT every hop at one common mol/tick rate. The Plan Builder may stage several direct and multi-hop paths, and the top-level Planner publishes `S14` **last**. A failed build never advances `S14`, so partial route construction cannot activate pumps.

The current maximum automatic routed path is three physical links (two intermediate STORAGE domains). Route choice is now cost-aware across a bounded candidate set using hop count, storage transit, positive pressure lift, and bottleneck molar throughput. Exact energy/thermal optimization and arbitrary-length routing remain future work. See `docs/PRESSURE_GRID_CONTROLLER.md`, `docs/PRESSURE_INVENTORY_MODEL.md`, `docs/PRESSURE_RESERVATION_MODEL.md`, `docs/PRESSURE_MULTI_HOP_ROUTING.md`, and `docs/PRESSURE_ROUTE_COST_MODEL.md`.

## Important invariants

When debugging or extending the framework, preserve these rules:

1. **ABI version is exact.** Discovery uses ABI2; transactional PhasePressure/PressureDomain/PressureTransfer telemetry uses ABI2; simple display-only telemetry families remain ABI1; Allocator is ABI3.
2. **Generation/request markers are published last.** Payload first, generation last.
3. **A/B bank revision is the durable commit token.** It is invalidated before writing and finalized last.
4. **Validity masks define configuration geometry.** Generic code must not infer meaning from contiguous slots.
5. **Stable physical slots are never repurposed.** Removed fields become reserved holes.
6. **Schema identity is explicit.** Generic directories and catalogs are consumed only when magic, ABI, schema ID, and schema version match the expected contract.
7. **Selectors resolve identity; they do not read physical UI hardware.** Domain bridges own UI transactions.
8. **Transactional telemetry is generation-stamped.** Consumers capture `S115`, read the payload, and require the same positive `S115` afterward.
9. **Transfer grants are topology-bound and one-shot per commit epoch.** Current source/sink/medium/route must equal the staged reservation identities; an invalidated/expired epoch cannot reactivate merely because Planner `S14` remains unchanged.
10. **Inventory is purity-gated.** A domain cannot advertise capacity unless the analyzer gas ratio meets the selected PHASE_MEDIUM Resource Profile View threshold.
11. **Multi-hop reservation is quote then exact commit.** No endpoint is intentionally over-reserved merely because a later hop has a smaller bottleneck.
12. **Job lifecycle policy is domain-owned but physical mutation is serialized.** `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` owns TRANSFORM/PRINT lifecycle policy and `ic10/power-jobs/power_job_scheduler_v1_0.ic10` owns finite POWER policy jobs; both use Job Gateway lanes, while `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the sole physical Job Store mailbox writer. Each domain advances only legal generation-checked Job ABI edges.
13. **Banked transaction authority is written last.** Config `REVISION_BANK` and Job `SELECTOR_BANK` recovery must expose old-or-new complete state only; a request already represented by recovered durable state is acknowledged rather than recommitted.
14. **Directory overflow is explicit.** Controller 65+ marks the snapshot incomplete; selectors/arbiters/grid topology refuse it.
15. **Runtime does not own persistence.** It consumes the Host effective image.
16. **Scanner/Resolver are domain-neutral.** Do not add PI/diagnostic special cases there.
17. **Generic Resource Link identity separates reservations from native topology.** S2/S3 are Resource Reservation refs; specialization-specific device identities must be bound separately.
18. **Discrete material delivery is commit-bound and evidence-based.** Prepare exact quantity first, snapshot destination completion before release, and report success only after the destination observes the batch.
19. **Transforms are not links.** A Link preserves ResourceType; a Transform changes typed resource identity and must admit input, output capacity, processor, and execution evidence separately.
20. **Async results are request-identity fenced.** `ASYNC_REQUEST_V1` is the reusable request/response rule across manufacturing, diagnostics, pressure, Config/Policy, catalog lookup, Job Store, printer capacity, and directory handshakes: payload precedes request token, LIVE_CURRENT services reset state/error before publishing current identity, TERMINAL_RESPONSE services publish result before response identity, and stale prior state must never advance a caller.
21. **Dependency completion requires usable inventory.** Child COMPLETE is not parent readiness; live output meaning and coherent ITEM inventory are revalidated.
22. **POWER execution authority is exact.** Electrical actuation requires stable PlanGeneration plus the allocator's active epoch and exact Reservation/Link generations; staged reservations alone are never authority.
23. **Interrupted publication is fail-closed.** Any odd/torn publication found after reflash is invalidated or kept unreadable until recovery establishes a complete state; Item 10 tests this rule across subsystem boundaries.
24. **Live evidence is release-bound.** A field PASS belongs only to the framework/case-catalog fingerprint that produced it; automated model/harness evidence is never relabeled as a physical Stationeers PASS.
25. **Device-port wiring is declared, not inferred.** Every port names its intended peer in `data/script_wiring.json` (see `docs/SCRIPT_WIRING.md`). Validation holds the declaration to the source: a port's magic/ABI checks must agree with its declared provider, and no consumer may read or write a migrated peer's `S0..S7` envelope — literally or through a dynamic range — without a reviewed `header_reads` declaration. Relocating payload above the envelope is a planning-time concern: `tools/plan_header_migration.py` lists every declared inbound edge (and every unattributable reference access) before a family moves.

## Terminology

| Term | Meaning |
|---|---|
| **Host** | Per-controller Generic Persistent Config Host instance containing effective, candidate, and durable config state. |
| **Policy** | Controller-family-specific schema/default/validation logic paired with a Host. |
| **Profile** | Optional metadata describing how logical controls should be edited with Dial/Switch/Memory hardware. |
| **Physical slot** | Stable 0..31 configuration storage address. |
| **Active ordinal** | Contiguous 1..N UI field number derived from validity masks. |
| **ReferenceId** | Identity of one concrete game device instance. |
| **ControllerType** | Hash identifying a controller family. |
| **Generation** | Monotonic change/request marker used to make multi-cell publication coherent. |
| **Effective image** | Last accepted configuration exposed to the runtime. |
| **Candidate image** | Proposed configuration awaiting Policy validation/commit. |
| **Bank revision** | Final durable token establishing that an A/B bank is complete. |

## Validation

Run the complete validator/protocol suite from the bundle directory:

```text
python3 tools/run_validation.py
```

This runs the complete validator/test inventory defined in `tools/run_validation.py`, writes per-script machine evidence under `validation/evidence/`, writes the pass/fail inventory to `validation/FULL_VALIDATION_RUN.txt`, and regenerates `VALIDATION_SUMMARY.txt`.

GitHub Actions runs the same command without `--resume` for every pull request and push to `main`, then requires the checkout to remain clean. Protect `main` with the **Clean validation** status check described in `docs/CI.md`.

To produce a verified release archive in the required ordering—generated index, validation, evidence, deployment hashes, archive manifest, ZIP integrity—run:

```text
python3 tools/build_release.py --output <release.zip>
```

`ARCHIVE_MANIFEST.sha256` exists only inside the resulting ZIP. It records the
SHA-256 digest of every packaged repository file and is generated and verified
during that build; no checkout-level copy is maintained.

These checks validate static contracts, model the important transaction/persistence protocols, and execute selected transaction-critical IC10 source directly through `framework/ic10_harness.py`. They do not replace live-game commissioning tests; see `docs/FRAMEWORK_HARDENING_TESTS.md`.

When working from a git clone, enable the evidence-sync pre-commit hook once per clone:

```text
git config core.hooksPath .githooks
```

It runs the suite before each commit and stages the refreshed evidence, so committed evidence always matches the source it attests to. Validation hashes the working tree rather than the index, so the hook refuses to run against a tree with unstaged or untracked files; bypass it with `git commit --no-verify`. VCS and automation tooling (`.git`, `.github`, `.claude`, `.githooks`) is excluded from the validation input fingerprint and from release archives, so workflow, hook, or editor configuration never invalidates recorded live commissioning evidence.


## Catalog Coordinator v3

Catalog storage now uses one global control plane and generic Store nodes. Set only a unique `S18 NodeId` (1..64) on `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10`; Coordinator Core ABI3 claims the node, assigns catalog/schema/partition/runtime ordinal metadata, and publishes topology/capacity state. A persistent 64-node Directory tracks current ReferenceId, lifecycle state, used capacity, assignment epoch, CatalogInstanceId, and last-seen scan epoch. Scanner/Telemetry services detect missing and duplicate nodes. Recovery rebinds Stores to a higher-epoch replacement Coordinator. Item Migration Planner/Worker compact whole items out of a DRAINING Store into runtime-selected capacity before Retirement unlinks the empty node. See `docs/CATALOG_COORDINATION.md`.

## Cross-domain process utilities

Item 11 adds `ProcessCondition ABI1` as a demand/verification surface above the existing domain authorities. Furnace transform pressure/temperature windows can now be actively prepared through PressureGrid; prepared two-component FLUID mixtures share the Resource Profile catalog; Advanced Furnace embedded pumps project as ordinary PressureTransfers; and coherent POWER shortage can request H2/O2 fuel and safely start a Gas Fuel Generator after fuel and ambient verification. `ProcessCondition` never authorizes movement, so PressureGrid reservations/GrantGuard, Transform Admission, and PowerPlan retain their existing mutation/acceptance roles. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Generic material transforms

The Resource Transform schema v4 is executable for the current one-, two-, and three-input material recipes. Capability masks allow basic smelts on Arc/Furnace/Advanced, two-input base alloys on Furnace/Advanced, and advanced alloys on Advanced Furnace without duplicating transforms per processor type. Admission validates processor conditions/output capacity on every compatible furnace class, Link Resolver resolves exact input routes, Multi Reservation Stager prepares all source/sink reservations and Guards, Material Allocator ABI2 commits one shared epoch last, and Generic Transform Runtime waits for all input deliveries before activating the processor and confirming output growth. The same semantic material-transform transaction path handles the one-input Arc Furnace case; no separate compatibility runtime remains.

## Generic ITEM storage access

Item 7 is complete. Vending (`ic10/item-storage-vending/material_vending_inventory_v1_0.ic10`), LArRE-accessible passive storage (`ic10/item-storage-larre/`), bounded direct-slot storage (`ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10`), exact export/chute handoff (`ic10/material-grid/material_export_slot_endpoint_v1_0.ic10`), and dedicated SDB Silos (`ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10`) all publish Generic ITEM Resource Endpoint state. `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` exposes Resource Reservations through the Generic Snapshot Directory; the item reservation selector/allocator plus generic releaser provide read-only split quote, exact owner/epoch commit, and exact-owner release. `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` will not move a LArRE stack until both source and destination Reservations match the same allocator owner and their committed semantic Reservation generations are still current.

SDB native `Quantity` is occupied-stack count, so `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` advertises conservative lower-bound availability/capacity rather than false exact totals. `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` reuses Material Feeder ABI1 and a Stacker to meter exact processor quantities after FIFO SDB export. See `docs/ITEM_STORAGE_SYSTEM.md`.
