# Completed Framework Milestones

This document preserves the detailed acceptance criteria and implementation notes for completed Roadmap Items 1–11. `ROADMAP.md` contains only the active/future milestones.

## 1. Runtime Store placement — COMPLETE

Remove generated physical Store boundaries from catalog data.

A Loader publishes one or more complete relocatable items. For each pending item, the Loader Router determines at runtime whether an ACTIVE Store with matching catalog/schema/partition has enough available capacity. If one exists, the item is assigned there. Otherwise the Coordinator claims an UNCLAIMED Generic Store, assigns its schema/catalog/partition and the next logical Store ordinal, and the Router continues.

Storage uses a generic Store item directory and a block-aligned payload heap. Generators estimate minimum commissioning capacity but do not assign items to Store ordinals.

Completion criteria:

- no Loader contains a preassigned Store ReferenceId or Store ordinal;
- placement is based on live Store free capacity;
- concurrent Loader assignments cannot oversubscribe one Store;
- a new Store can be added without regenerating existing Loaders;
- catalog Views discover records through the runtime Store topology.

## 2. Item-level migration and compaction — COMPLETE

Replace whole-Store-only migration with relocation of complete logical items.

A DRAINING Store receives no new Loader allocations. The migration planner selects a whole item and a compatible ACTIVE destination with enough capacity, or asks the Coordinator to claim additional capacity. The migration worker copies the item, publishes the destination first, removes the source location only after successful destination publication, and advances the catalog topology revision. Repeated moves drain a Store until the retirement manager can safely unlink it.

The first implementation migrates the newest item from a Store so the downward-growing payload heap can reclaim space without leaving holes. Repeated newest-item moves provide safe compaction while preserving simple Store geometry.

Completion criteria:

- no record is split during migration;
- destination publication precedes source removal;
- interrupted migration cannot make the only committed copy disappear;
- DRAINING Stores receive no new Loader allocations;
- empty Stores can be retired after item migration;
- compaction can reduce the number of active Stores when compatible capacity exists elsewhere.

## 3. Generic Directory Adapter ABI — COMPLETE

Standardize the boundary between domain-specific discovery and generic directory publication.

A Directory Adapter publishes a coherent candidate snapshot on its own stack using `DIRECTORY_ADAPTER_ABI_V2`. Generic directory infrastructure consumes that snapshot and owns ordering, exact deduplication, overflow, stable generations, snapshot publication, and registry state.

Directory schemas remain versioned data in `directory_schemas.json`. Controller, Pressure Grid Link, Resource Endpoint, Resource Link, and Catalog Store Node discovery all publish through generic Snapshot/Registry host ABIs; consumers identify record semantics by DirectorySchemaId/Version rather than domain-specific directory magic values.

Completion criteria:

- adapters never write directly into Directory Host storage;
- candidate publication has an odd/even sequence and generation;
- a freeze request/ack handshake holds one stable candidate generation across multi-tick consumers;
- whole directory records are never split;
- generic Snapshot and Registry paths consume the same Adapter ABI;
- Registry publication is fenced by an odd/even sequence and consumers revalidate it around reads;
- unchanged candidate sets do not spuriously advance a stable snapshot generation;
- overflow preserves complete records and publishes an explicit overflow condition.

## 4. Printer Directory — COMPLETE

Add `DirectorySchema.Printer` and a thin Printer discovery adapter for supported non-deprecated printers:

- Autolathe
- Electronics Printer
- Hydraulic Pipe Bender
- Tool Manufactory
- Security Printer
- Rocket Manufactory

Use the three-cell snapshot record:

```text
[ReferenceId, FamilyHash, ProcessorSpec]
```

`FamilyHash` is also the Recipe Catalog `PartitionKey`, so family and partition are one semantic field rather than duplicated cells. Printer schema v2 uses the common manufacturing `ProcessorSpec`: bits 0..7 capability, bit 8 Power, bit 9 Busy/Active, bit 10 Error, plus printer-specific On/Lock flags. This preserves the Generic Snapshot Host's universal width<=3 / capacity<=64 geometry and lets Item 6 reuse the same processor-selection semantics for printers and transform lanes.

Completion criteria:

- all six supported non-deprecated printer families publish through `DIRECTORY_ADAPTER_ABI_V2`;
- Fabricator devices are excluded;
- `FamilyHash` exactly matches the Recipe Catalog partition identity;
- tier/capability and Power/Busy/Error/On/Lock state fit in one `ProcessorSpec`;
- the ordinary Generic Adapter Bridge + Snapshot Host own sorting, exact dedupe, overflow and transactional publication;
- printer discovery passes mixed-family, status-bit, unsupported-device and 65-device overflow tests.

## 5. Generic Job ABI — COMPLETE

Define one scheduler-neutral job record and lifecycle for transforms, printing, direct resource transfers, and POWER operations.

`GENERIC_JOB_ABI_V1` uses the eleven-field logical record:

```text
[JobId, JobType, RequiredCapability, Identity,
 InputCount, OutputCount, RequestedQuantity, Priority,
 State, Generation, ErrorStatus]
```

The ordinary lifecycle is:

`QUEUED -> PLANNING -> RESERVING -> READY -> RUNNING -> VERIFYING -> COMPLETE`

with explicit `WAIT_RESOURCE`, `WAIT_PROCESSOR`, `WAIT_CAPACITY`, `FAULT`, and `CANCELLED` states. WAIT states return to PLANNING so topology, resources, capacity, and processor choice are revalidated rather than resumed from a stale plan.

`ic10/generic-jobs/generic_job_store_v1_0.ic10` provides 32 crash-safe physical slots. Immutable intent and per-slot A/B state banks fit in one 512-cell stack. JobId is Store-owned, state mutation uses expected JobGeneration, queue readers fence on an odd/even QueueSequence, terminal states are immutable, and only terminal records can be reaped. The Store owns mechanical publication; lifecycle legality is the versioned writer contract in `generic_job_schema.json` / `job_abi.py`.

Completion criteria:

- TRANSFORM, PRINT, TRANSFER, and POWER work share one eleven-field logical record;
- JobType-specific Identity/RequiredCapability semantics are explicit without embedding stale processor/resource ReferenceIds in intent;
- the normal chain plus WAIT/FAULT/CANCELLED transitions are versioned and executable in the reference model;
- at least 32 jobs fit one production Store without splitting logical records;
- JobId is monotonically allocated and not reused after slot reaping;
- optimistic JobGeneration rejects stale state mutation;
- queue publication is fenced by QueueSequence/QueueGeneration;
- terminal jobs cannot be reopened and only terminal jobs can be reaped;
- same-service interruption before/after the per-slot active-bank flip recovers without double application;
- the Store remains scheduler-neutral; processor-selection and queue policy are supplied externally by Item 6.

## 6. Manufacturing scheduler — COMPLETE

Compose Printer Directory, Recipe Catalog, Transform Catalog, Material Grid, reservation protocols, and Generic Jobs into one production scheduler without duplicating their storage/discovery/transaction responsibilities.

The completed implementation uses:

- `ic10/generic-jobs/generic_job_selector_v3_0.ic10` for coherent priority ordering with lower JobId as the deterministic tie-break; default manufacturing mode filters TRANSFORM/PRINT while exact-JobType mode is reusable by POWER;
- `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` as the TRANSFORM/PRINT lifecycle-policy owner through Gateway lane A;
- `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` to normalize TRANSFORM and PRINT drivers behind one scheduler-facing surface;
- `DirectorySchema.TransformLane` v1 and `DirectorySchema.PrinterExecution` v1 plus one dynamically targeted generic candidate selector;
- Recipe schema v3 execution profiles with bounded reagent requirements;
- Resource Profile `ManufacturingReagentHash` aliases to map recipe semantics onto concrete reachable MaterialGrid ResourceTypes;
- the existing Multi Reservation Stager + Multi Material Allocator ABI2 transaction for both transform inputs and print reagents;
- a six-printer local `Printer Execution Bank` plus exact-ReferenceId capacity reservation, because IC10 cannot safely read arbitrary device slots by discovered ReferenceId;
- universal transform pressure/temperature enforcement for Arc Furnace, Furnace, and Advanced Furnace processors.

Completion criteria:

- scheduler selection is coherent across the 32-slot Job Store and deterministic by Priority then JobId;
- WAIT jobs use a JobId scheduling cursor so multiple high-priority waiters cannot permanently starve lower-priority runnable work;
- manufacturing lifecycle policy is owned by `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10`, while all physical Job Store mailbox mutation is serialized through the Generic Job Gateway and Store Command Executor;
- scheduler advances lifecycle state one legal Job ABI edge at a time even if a domain driver advances faster;
- TRANSFORM candidates are schema-qualified and capability/environment/resource/output-capacity validated before execution;
- PRINT candidates use the Item-4 Printer metadata plus the PrinterExecution capacity overlay rather than rediscovering printer family/capability;
- printer swaps even after request publication but before Bank processing fail closed because ExpectedPrinterRef is part of the reservation transaction;
- `ASYNC_REQUEST_V1` is reusable across LIVE_CURRENT and TERMINAL_RESPONSE services; state/result cells are consumed only after exact request-identity match and publication ordering is validated; the consolidation pass registers diagnostics, Material Feeder, pressure, Config/Policy, Recipe Lookup, Job Store, Printer Execution Bank, and directory command/freeze handshakes;
- Transform Profile View ABI4 echoes the resolved TransformType and transform readiness is generation-qualified with no fixed planning timeout;
- Printer Execution Bank ABI2 separates response tokens from exact-ref ownership and never clears an external lock without persisted ownership proof;
- RecipeHash execution metadata includes exact bounded reagent semantics and is fenced against stale responses;
- print reagent planning resolves semantic reagent hashes into concrete reachable MaterialGrid resources before committing reservations;
- output capacity is reserved before print material commitment;
- transforms enforce every declared pressure and temperature bound independent of furnace class;
- all Item-6 production programs remain at or below the 120-line framework ceiling;
- direct execution/model tests cover queue ordering, wait backoff, stale generation, lifecycle edges, processor routing, transform conditions, printer capacity, printer replacement, reagent resolution, and terminal completion.

## Item 7 — Generic Item Inventory & Storage Discovery — COMPLETE

Item 7 made physical ITEM storage a first-class ResourceGrid input before dependency planning.

Implemented:

- Vending, direct-slot, LArRE-accessible passive storage, exact export-slot/chute handoff, and dedicated SDB Silo providers all publish Generic Resource Endpoint ABI1;
- common storage extension at S35..S40 preserves the existing material S14 Resource Profile reference;
- storage policy flags and reserve floors allow do-not-consume, no-import, preferred-destination, quarantine, and retained-stock behavior;
- Generic Resource Reservation now carries allocator owner ReferenceId/epoch plus the semantic Reservation generation plus coherently mirrored storage action hints;
- `DirectorySchema.ResourceReservation v1` exposes up to 64 typed Reservation mirrors through the Generic Snapshot Directory substrate;
- `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` produces bounded read-only six-leg ITEM reservation quotes and handles LArRE whole-stack withdrawal explicitly;
- `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` exact-commits a coherent quote only after semantic Reservation-generation revalidation;
- `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` releases only an exact owner ReferenceId + epoch;
- `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` requires paired source/destination reservations, matching owner identity, plan epochs, direction locks, ResourceType, and live Endpoint generations before moving a LArRE stack;
- `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` revalidates exact item identity and quantity immediately before pickup and exposes explicit held-item recovery;
- the reserved LArRE move client persists the physical origin before pickup so recovery remains possible after a same-housing client restart;
- `ic10/item-storage-common/material_export_slot_endpoint_v1_0.ic10` makes chute/export handoff state reservable for inbound storage placement;
- `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` supports bounded directly readable slot storage without LArRE;
- `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` models dedicated SDB inventory as conservative lower-bound quantity/capacity rather than misinterpreting native occupied-stack count as exact item quantity;
- `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` reuses Material Feeder ABI1 to export FIFO SDB stacks into a Stacker and meter the exact requested processor quantity.

Acceptance evidence covers multi-location split fulfillment, duplicate-reservation exclusion, exact owner/epoch release, destination-capacity reservation before pickup, stale semantic Reservation generation, player mutation between scan/reservation/pickup, post-pick destination obstruction/held-item recovery, inbound chute-to-storage movement, policy gates, lower-bound SDB math, and exact Stacker metering.

Item 8 consumes these reservations as coherent planning quotes while leaving physical reservation authority in the execution layer; it does not create a parallel warehouse inventory model.


## Item 8 — Simple Dependency Planning — COMPLETE

Item 8 adds bounded dependency expansion above Generic Job Store and the Item-7 storage/reservation substrate without changing `GENERIC_JOB_ABI_V1` or introducing a second scheduler.

Implemented:

- `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` is the current four-lane Gateway; Item 8 consumes lanes A/B/C for Scheduler lifecycle, Planner cancellation, and Child creation, while Item 9 later adds independent POWER lane D;
- `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the sole physical Job Store mailbox writer and atomically validates parent JobId, JobGeneration, and `PLANNING` state before allocating/publishing a child;
- `ic10/dependency-planning/job_requirement_view_v1_0.ic10`, `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10`, and generated `ic10/dependency-planning/item_producer_resolver_v1_0.ic10` normalize TRANSFORM/PRINT requirements and producers;
- `ic10/dependency-planning/job_inventory_preflight_v1_0.ic10` consumes Item-7 coherent quotes, preserves exact/lower-bound precision, rejects quote overflow, and publishes two ordered quote fingerprints for liveness;
- `ic10/dependency-planning/dependency_plan_store_v2_0.ic10` owns 32 committed eight-cell plans with `ParentJobId` published last and interrupted odd-sequence recovery;
- `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` shares only active future work and subtracts aggregate per-parent claims so future output cannot be overbooked;
- `ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10` permits root -> child -> grandchild while rejecting deeper expansion and immediate ancestor/self cycles;
- `ic10/dependency-planning/dependency_child_validity_v1_0.ic10` revalidates live child output semantics against current catalogs;
- `ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10` requires both child completion and coherent inventory visibility, and replans when a completed child's short inventory quote materially changes;
- `ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10` makes child cancellation reference-aware, while `ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10` requests cleanup for terminal/reaped parents without becoming another store writer;
- `ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10` and `ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10` separate read/decision work from the bounded `ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10`, which remains the sole Plan Store mutation coordinator;
- `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` sits ahead of the unchanged Driver Router so only dependency-ready jobs reach ordinary TRANSFORM/PRINT execution.

Acceptance evidence covers independent-lane mailbox arbitration, sole Store mutation authority, parent-stale child rejection, Plan Store torn-write recovery, exact/lower-bound inventory semantics, six-leg quote overflow, bounded depth/cycles, active-only shared claims, aggregate claim accounting, completed-child inventory publication/consumption races, catalog-output invalidation, reference-aware cancellation, restart/replay behavior, and legal scheduler lifecycle integration.

The planner uses coherent Item-7 inventory quotes plus logical future-output claims; physical resource ownership remains in the execution allocators. This avoids long-lived planner locks and reservation handoff semantics.


## 9. Power-management reuse — COMPLETE

Item 9 proves the Directory/Profile/ResourceGrid/Reservation/Job abstractions against electrical power rather than materials. `resource_profiles.json` now carries POWER/WATT and ENERGY/JOULE semantics; live policy remains in endpoints rather than static catalog records.

Implemented:

- semantic producer, managed-consumer, and bidirectional-battery POWER Endpoints under `ic10/power-grid/`; batteries enforce reserve/target/rate policy and optionally respect external physical Off as a hard lockout;
- passive electrical and transformer Generic Resource Links under `ic10/power-grid/`, with transformer self-consumption charged to source-side watts;
- `ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10` publishes `DirectorySchema.PowerReservation` through the ordinary Generic Snapshot Directory stack, including foreign-owner filtering and persistent policy-addressability for zero-capacity managed targets;
- the Power Plan Store, selectors/builders, sweep, and dispatch-cycle services implement bounded coherent critical-first dispatch planning, alternative-source/link retry, load shedding, and surplus battery charging;
- the Power Plan Validator, Reservation Committer, and Reservation Allocator implement full-plan revalidation, aggregate Generic Resource Reservation commit, common allocator epoch, old/new-epoch cleanup, and fail-closed publication;
- `ic10/power-grid/power_load_executor_v1_0.ic10` and `ic10/power-grid/power_link_executor_v1_0.ic10` provide break-before-make consumer/battery and transformer actuation with exact plan, Reservation owner/epoch/generation, and Link-generation authority;
- `ic10/generic-jobs/generic_job_selector_v3_0.ic10` plus the semantic `ic10/power-jobs/` services implement finite `JobType.POWER` policy transactions using `Identity=PolicyId`, `RequiredCapability=PowerMode`, optional watt cap, Gateway ABI3 lane D, and Generic Reservation mirror verification before COMPLETE.

Review fixes included the Generic Reservation `S6 ExportAvailable` / `S7 ImportCapacity` offset distinction, battery self-lock avoidance, foreign reservation ownership, partial-commit epoch cleanup, exact transformer source+sink authority, allocator reflash reacquisition, final-write authority re-fencing, Generic Job Selector reuse/cursor fairness, WAIT/FAULT termination, and corrected POWER job intent mapping.

Acceptance evidence is in `validation/validators/validate_power_management_contracts.py` and `tests/test_power_management.py`; full framework release evidence is generated by `run_validation.py`. See `docs/POWER_MANAGEMENT.md`.


## 10. Broad interruption and fault-injection suite — COMPLETE

Item 10 applies one reusable cut-at-every-boundary fault-injection method across the combined framework rather than introducing another runtime transaction layer.

Implemented:

- `fault_injection.py` provides deterministic deep-copied restart injection after every prefix of an ordered mutation sequence;
- `tests/test_fault_injection.py` covers catalog migration, directory mutation/Store loss, processor replacement, ITEM quote/commit/action, LArRE held-item recovery, dependency cancellation and live-output invalidation, deterministic Job Gateway replay, POWER plan replacement, allocator reflash/reacquisition, final-write authority withdrawal for load/transformer executors, and cancellation from every nonterminal Generic Job state;
- the campaign executes actual `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` COMMIT logic at dozens of instruction cut points;
- `validation/validators/validate_fault_injection_contracts.py` statically checks critical destination-before-source-removal, persisted-origin-before-move, inactive-before-payload, deterministic replay-token, POWER recovery, and commit-before-authority ordering;
- `docs/INTERRUPTION_FAULT_INJECTION.md` records the campaign matrix, recovery rules, and live-game boundary.

The campaign exposed a POWER Plan Store restart defect: reflash during COMMIT could leave the publication sequence odd, and a later COMMIT could transiently make it even while copying. `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` now detects odd boot state, invalidates plan authority/header state, and advances to an even sequence before accepting new work. The post-completion review then found two additional authority/liveness defects: `ic10/power-grid/power_reservation_allocator_v1_0.ic10` could remain safely inactive forever after reflash if PlanGeneration was unchanged, and the load/link executors could actuate after allocator authority changed between their initial check and final write. The allocator now forces current-plan revalidation while preserving the old epoch for cleanup; both executors re-fence allocator authority immediately before actuation. Recovery intentionally prefers a safe outage over stale authority.

Acceptance evidence requires all injected cuts to expose only old-complete, new-complete, or explicitly invalid state; no partial state may authorize mutation or physical actuation. The complete release suite includes the new campaign and static validator in addition to all prior Item 1–9 tests.


## 11. Cross-domain process & utility orchestration — COMPLETE

Item 11 proves that the previously independent PressureGrid, manufacturing, Resource Profile, and PowerGrid layers can coordinate complementary physical systems without a parallel planner.

Implemented:

- `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` publishes `ProcessCondition ABI1` directly from the selected Transform Profile pressure/temperature bounds and live Furnace/Advanced Furnace state;
- `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` projects an active process target into the existing `ControllerPressureDomain` ABI2 so ordinary PressureGrid inventory/reservation/routing can satisfy the requested pressure envelope;
- `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` projects Advanced Furnace `SettingInput` or `SettingOutput` as a standard `ControllerPressureTransfer` and writes only under the existing PressureGrid GrantGuard epoch;
- Resource Profile kind 5 adds prepared two-component FLUID mixtures without creating another profile catalog; `Fuel.H2O2` is the first profile at 2/3 Volatiles + 1/3 Oxygen;
- `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` validates two-component mixtures while publishing the existing PurityGuard ABI1 consumed by Pressure Inventory;
- `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` converts desired mole fraction plus unequal source temperatures into the correct Gas Mixer setting and continues preparation until composition and demanded output pressure are both visible;
- `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` blends hot/cold gas to the requested ProcessCondition temperature window while maintaining enough output pressure for PressureGrid delivery;
- `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` observes coherent PowerPlan shed/critical-shortage state, publishes a prepared-fuel ProcessCondition, verifies fuel/ambient safety, starts the Gas Fuel Generator only after current readiness, and safe-offs it when shortage disappears;
- the IC10 harness was corrected to model `bdnvs` as branch-if-not-valid-to-store, matching current IC10 semantics; direct regressions protect that interpreter boundary.

Reference proofs:

1. **Advanced Furnace conditioning:** Transform P/T bounds -> ProcessCondition -> Process PressureDomain -> prepared/thermal gas buffer -> PressureGrid reservation/route -> GrantGuard-authorized embedded furnace pump -> existing Transform Admission revalidation.
2. **Fuel-backed POWER:** coherent PowerPlan shortage -> GFG ProcessCondition -> demand-driven `Fuel.H2O2` preparation -> PressureGrid delivery -> mixture/ambient verification -> GFG generation -> safe shutdown when shortage clears.

Correctness boundaries:

- ProcessCondition is demand/verification state, never a resource reservation;
- gas mixing changes ResourceType and therefore is not represented as a type-preserving Generic Resource Link;
- PressureGrid remains the sole gas movement/route authority;
- `ic10/material-transform/material_transform_admission_v1_0.ic10` remains the final authority for furnace pressure/temperature before material execution;
- `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` reads but never mutates PowerPlan;
- GFG deficit handling does not recursively start an Electrolyzer, avoiding an immediate POWER -> fuel -> POWER dependency cycle; surplus-power chemical storage remains a future policy;
- every new production IC10 remains at or below the 120-line ceiling.

See `docs/PROCESS_UTILITY_ORCHESTRATION.md` for topology, ABI, formulas, commissioning boundaries, and future extensions.
