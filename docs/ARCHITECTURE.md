# Architecture

The framework is designed around a simple rule: **generic services move and persist state; family-specific services define what that state means.** This keeps controller implementations small while allowing the same discovery, editing, persistence, and diagnostics infrastructure to work for different controller families.

## Layers

A useful way to read the system is as five layers:

1. **Discovery** — finds controller and console instances and publishes stable, generation-stamped directories.
2. **Physical input** — discovers the commissioning controls and resolves them into logical control/value pairs.
3. **UI/selection** — converts logical user intent into selected controller/console identities or staged config edits.
4. **Configuration/persistence** — validates controller-specific semantics and durably commits accepted images.
5. **Runtime/telemetry** — runs the controller algorithm and exposes generic telemetry for diagnostics.

No layer should reach downward and duplicate another layer's responsibility. For example, a selector should never start reading a Dial directly, and a runtime should never implement A/B recovery.

## Shared input layer

```text
physical devices -> Generic Input Scanner -> Generic Input Resolver <- Input Profile
                                             |
                         +-------------------+-------------------+
                         |                                       |
                  Config Input Bridge                    Diagnostic Input Bridge
                         |                                       |
                  Generic Config Editor                  Diagnostic Selector Bridge
```

The Scanner owns device discovery/classification and the Field Dial. The Resolver owns Profile interpretation and value resolution. The bridges translate the resulting domain-neutral snapshot into domain-specific state.

This split is what lets configuration and diagnostics share the same hardware behavior without teaching the Scanner or Resolver what “Kp,” “Console,” or “Commit” means.

## Shared discovery and diagnostics

```text
Controller Directory ----------------> Controller Selector <- Diagnostic Selector Bridge
Console Registry ---------------------> Console Selector    <- Diagnostic Selector Bridge
                                                       \       /
Diagnostic Input Bridge ----------------> Mapping Editor
                                             |
                                      Diagnostic Renderer
```

### Controller discovery

The Controller Directory finds telemetry-capable IC housings and stores sorted `[ControllerType, ReferenceId]` pairs. Because records are already sorted by `(ControllerType, ReferenceId)`, Controller Selector ABI2 derives contiguous type/member groups directly while scanning the selected coherent bank; no intermediate Type Catalog is deployed.

The shared Generic Snapshot Directory supports **64 controllers** in two pair banks at `S32..S287`. Selector validates Controller schema/version, rejects overflow, scans the sorted bank, and revalidates active bank + generation before publishing the exact ReferenceId. This removes an entire discovery IC without weakening coherent selection.

Sorting and generation checks matter because network enumeration order is not a stable identity contract.

### Printer discovery

Manufacturing discovery uses the same generic snapshot substrate:

```text
170 Printer Adapter -> 169 Generic Bridge -> 166 Generic Snapshot Host
                                           -> DirectorySchema.Printer v2
```

The Adapter maps six supported printer families to the same FamilyHash identities used by Recipe Catalog partitions and packs common manufacturing `ProcessorSpec` capability/Power/Busy/Error plus printer On/Lock state into the third cell. Item 6 adds `DirectorySchema.PrinterExecution` v1 as a locally capacity-verified overlay while preserving exact Printer ReferenceId. Generic directory code remains unaware of printer semantics. See `docs/PRINTER_DIRECTORY.md` and `docs/MANUFACTURING_SCHEDULER.md`.

### Console discovery

Console Registry finds enrolled display devices and publishes a stable sorted registry. Console Selector resolves a desired ordinal and also supports an independent **advance** request stream used after a mapping is committed.

Desired-selection generation and advance generation are separate on purpose: an old desired Console value must not undo the automatic “move to next console” behavior.

## Shared configuration

```text
Generic Input Resolver -> Config Input Bridge -> Generic Config Editor
                                                  |
Controller Selector --------------------------> Loader / Committer
                                                  |
                                       Generic Persistent Config Host
                                                  ^
                                                  |
                                             Config Policy
                                                  |
                                           Controller Runtime
```

The configuration path has three distinct representations:

- **logical field ordinal** — what the human selected (1..N);
- **physical image slot** — stable schema location (0..31);
- **effective image** — durable accepted values consumed by the runtime.

Loader derives the ordinal-to-slot mapping from Host validity masks. Config Input Bridge uses that mapping when publishing resolved values into Editor. Committer copies only valid physical slots into the Host candidate image.

## End-to-end configuration transaction

A normal edit/apply cycle is:

1. Controller Selector resolves a concrete controller instance.
2. Loader validates the paired Host and optional Input Profile.
3. Loader copies the Host effective image to Editor staging and builds the active ordinal -> physical slot map.
4. Scanner/Resolver resolve the current physical commissioning input.
5. Config Input Bridge maps the logical ordinal to a physical slot and publishes the resolved value to Editor.
6. The user saves one or more staged values.
7. Apply captures the selected controller and staging revision.
8. Committer writes valid candidate slots to the Host and publishes a request generation last.
9. Config Policy validates and canonicalizes the candidate, then publishes its response generation last.
10. Generic Host writes the inactive durable bank and publishes its bank revision last.
11. Only after durable success does Host replace the effective image and publish success.
12. Runtime observes the new effective generation and uses the accepted config.

The important property is that a UI Apply is not considered successful merely because the candidate was syntactically copied. Success means the durable bank commit completed.

## Reusable asynchronous request boundary

Multi-tick services use `ASYNC_REQUEST_V1` rather than inventing domain-specific stale-result rules. The protocol is field-location independent and has two profiles: `LIVE_CURRENT` resets request-specific state/error before publishing the accepted request token, while `TERMINAL_RESPONSE` publishes a complete result/status before its response token. Consumers interpret request-specific cells only after exact token equality. The rule now covers manufacturing, material-feeder, diagnostics, pressure routing/reservation, Config/Policy, Recipe Lookup, Job Store, Printer Execution Bank, and directory command/freeze handshakes. Transaction commit epochs, directory/snapshot generations, reservation epochs, and ownership tokens remain separate authorities; the async token fences observation rather than replacing those protocols. See `docs/ASYNC_REQUEST_STANDARD.md`.

## End-to-end diagnostic transaction

A diagnostic mapping cycle is:

1. Scanner/Resolver expose one of the seven Diagnostic Profile controls.
2. Diagnostic Input Bridge retains the latest logical values and turns Commit into a rising-edge generation.
3. Diagnostic Selector Bridge publishes desired controller and console selections transactionally.
4. Selectors resolve the desired ordinals to exact device ReferenceIds using coherent discovery generations and publish status/result before their handled request tokens.
5. Mapping Editor first requires Controller handled generation = current Diagnostic Input controller request, Console handled desired generation = current desired request, and Console handled advance generation = current advance request.
6. Only after those exact-token fences does Mapping Editor snapshot resolved controller, display, channel, Mode, and Color.
7. Mapping Editor appends/updates the renderer record.
8. Mapping Editor increments the Console Selector advance generation.
9. Mapping Editor finally marks the Commit generation handled.
10. Renderer refreshes committed records within its per-tick work quota.

If a dependency is temporarily unavailable, the unhandled Commit generation remains pending rather than being silently lost.

## Responsibility boundaries

**Generic Input Scanner**

- owns six-screw discovery/classification;
- publishes exact ReferenceIds, capability/pin masks, and Field Dial ordinal;
- knows no controller/config/diagnostic semantics.

**Generic Input Resolver**

- interprets Profile descriptors;
- resolves Memory, Linear Dial, Integer Dial, Switch, and Enum Dial values;
- implements preferred-device -> Memory fallback;
- publishes a coherent generation-stamped logical snapshot.

**Domain bridges**

- convert logical snapshots into configuration or diagnostic state;
- own transaction-generation changes caused by user intent;
- never rediscover physical devices themselves.

**Selectors**

- resolve desired ordinal state to exact device identities;
- protect against discovery-generation changes;
- do not own physical UI screws.

**Generic Persistent Config Host**

- owns Config ABI v1 endpoint;
- owns candidate/effective images;
- owns A/B persistence and recovery;
- coordinates transaction publication;
- has no controller-family semantic special cases.

**Config Policy**

- owns ControllerType/schema/masks/defaults;
- validates cross-field semantics;
- canonicalizes accepted values;
- publishes the persistence signature.

**Runtime**

- owns the real-time algorithm and telemetry;
- reads effective config only;
- owns no editing or persistence behavior.

## Phase knowledge versus control

`ControllerPhasePressure` adds a second kind of family-specific dependency: a **PHASE_MEDIUM Resource Profile View**. This does not change the generic configuration architecture. It separates thermodynamic constants from the control algorithm:

```text
Resource Profile Catalog -> Resource Profile View -> ControllerPhasePressure -> RequestedPressure
                                 |                       |
                         chamber setpoint write          +-> pressure/grid telemetry
```

The controller owns the decision "operate below/above the phase boundary by this configured margin." The medium profile owns the curve parameters and valid liquid-temperature window. `ControllerPressureDomain` owns local pressure-domain arbitration and plant bounds; `ControllerPressureTransfer` plus the Reservation/Allocator/Planner services now own the physical inter-domain transfer layer.

The phase-change chamber's own pressure setpoint is distinct from the external LOW/HIGH buses. For a normal grid deployment, `ControllerPhasePressure.DirectWrite=1` is therefore still usually appropriate: the PhasePressure runtime owns the chamber setpoint while the grid owns movement between external pressure domains. `DirectWrite=0` remains useful for commissioning or when another explicit owner writes the chamber property.

## Pressure requirements versus pressure domains

The first grid-facing composition is:

```text
ControllerPhasePressure instances
        |
        | generic telemetry: medium/mode/request/status
        v
Controller Directory
        |
        v
PhasePressure Request Arbiter
        |
        | one coherent aggregate request
        v
ControllerPressureDomain
        |
        +--> pressurize-side setpoint
        +--> depressurize-side setpoint
        |
        v
one local pressure bus
```

The Request Arbiter is a family-adjacent infrastructure service rather than a discoverable controller. It exists because bounded incremental scanning of multiple PhasePressure producers is a separate responsibility from physical domain actuation and would push the runtime beyond the IC10 size budget if combined.

A LOW pressure domain filters matching EVAPORATE requests and selects the minimum requested pressure. A HIGH domain filters matching CONDENSE requests and selects the maximum. The domain Runtime then applies plant safety bounds and reports `-8` if those bounds prevent satisfying the most demanding request in the required direction.

This distinction is important:

- **PhasePressure** owns thermodynamic requirement derivation and, normally, the phase-device setpoint.
- **Request Arbiter** owns request-set filtering/reduction.
- **PressureDomain** owns one local bus target and plant bounds; role `3` exposes passive STORAGE reserve/ceiling semantics.
- **PressureDomain Inventory** owns gas-network resource accounting for one domain: exportable moles, import capacity, and pressure/volume conversion factors.
- **PressureInventory Reservation** mirrors one Inventory endpoint into an addressable capacity/reservation ledger.
- **Pressure Reservation Allocator** is the sole writer of endpoint reservations and staged transfer grants.
- **Grid Link Directory** derives a stable 64-link transfer-only topology snapshot from the shared Controller Directory.
- **Grid Path Enumerator** incrementally enumerates available two/three-hop LOW-to-HIGH paths through STORAGE vertices.
- **Grid Route Ranker/Selector** assigns a bounded route-quality score and chooses the best candidate examined.
- **Grid Path Allocator** QUOTEs every hop in a selected path, chooses the common bottleneck mol/tick rate, then exact-COMMITs every hop at that same rate.
- **Grid Single-Hop Builder** stages direct reuse and storage fallback without admitting free-standing STORAGE->STORAGE movement.
- **Grid Plan Builder** orders direct reuse, routed reuse, and fallback construction.
- **PressureTransfer** owns one real source->sink pump edge, computes its current physical mol/tick ceiling, and executes only its committed bounded-rate lease.
- **Grid Reservation Planner ABI2** owns the medium-specific build epoch and is the only component allowed to publish the final plan-activation commit token.

The current Level-3 policy is `direct LOW->HIGH`, then automatic `LOW->STORAGE[->STORAGE]->HIGH` routed reuse, then `LOW->STORAGE` / `STORAGE->HIGH` fallback. Several direct or routed paths may be staged in one epoch as long as allocator-owned endpoint reservations stay within observed molar capacity. STORAGE may carry simultaneous import/export only inside a complete routed path; ordinary fallback keeps the anti-circulation direction check.

See `docs/PRESSURE_DOMAIN_CONTROLLER.md`, `docs/PRESSURE_INVENTORY_MODEL.md`, `docs/PRESSURE_GRID_CONTROLLER.md`, `docs/PRESSURE_RESERVATION_MODEL.md`, `docs/PRESSURE_MULTI_HOP_ROUTING.md`, and `docs/PRESSURE_ROUTE_COST_MODEL.md` for the full contracts.

## Ownership rules for shared state

When multiple scripts can see the same stack cells, there is still one logical owner:

- Scanner owns its hardware snapshot and Field Dial mechanics.
- Resolver owns resolved logical snapshot publication.
- Loader owns Editor schema/profile/mapping metadata.
- Config Bridge owns the Editor's current resolved input publication.
- Editor owns staging state.
- Policy owns schema metadata/defaults and validation response.
- Host owns effective/candidate/durable configuration state.
- Diagnostic Input Bridge owns diagnostic desired UI state and its generations.
- Selectors own resolved selected identity.
- Mapping Editor owns committed mapping records handed to Renderer.
- PhasePressure Request Arbiter owns one incremental request-set scan and its reduced result publication.
- PressureDomain Runtime owns the safe local-domain target or STORAGE reserve/ceiling publication and optional LOW/HIGH local actuator writes.
- PressureDomain Inventory owns one domain's gas-only molar capacity publication.
- PressureInventory Reservation owns the mirrored endpoint ledger surface; its reservation cells are written only by the paired Allocator.
- Pressure Reservation Allocator owns endpoint reservation mutation and staged link-grant publication.
- Grid Link Directory owns the stable transfer-topology snapshot.
- Grid Path Enumerator owns candidate discovery only; it cannot reserve or actuate.
- Grid Route Ranker owns route scoring; Grid Route Selector owns bounded best-candidate selection. Neither can reserve, commit, or actuate.
- Grid Path Allocator owns path-level staging/normalization but cannot commit a plan.
- Grid Single-Hop Builder owns direct/fallback sweep staging.
- Grid Plan Builder owns construction order and staged-plan summary.
- PressureTransfer Runtime owns one physical pump-edge candidate calculation plus committed lease execution.
- Grid Reservation Planner owns the build epoch and final committed reservation epoch; a build fault must not advance that token.
- Generic Job Store owns JobId allocation, immutable-intent publication, per-job Generation/state mutation, terminal immutability, and terminal reaping; schedulers own lifecycle-edge policy and planning decisions.
- Generic Persistent Config Host and Generic Job Store share `BANKED_TRANSACTION_V1` old-or-new/replay semantics but remain distinct runtime ICs: Config uses whole-image `REVISION_BANK`; Jobs use per-record `SELECTOR_BANK`.

Writing outside these ownership boundaries is a strong sign that a change is coupling layers that were intentionally separated.

## Coherence pattern: payload first, generation last

Many records span several stack cells. They are published with the same pattern:

```text
write payload cell A
write payload cell B
write payload cell C
write generation/change marker LAST
```

A consumer captures the generation, reads the payload, and often rechecks the source generation before accepting it. This is the framework's lightweight transaction pattern for avoiding torn multi-cell state in IC10.

## Failure containment

The architecture intentionally degrades locally:

- a missing Value Dial can fall back to Memory when allowed by the Resolver;
- a changing discovery generation causes a selector retry instead of publishing the wrong identity;
- a Policy rejection leaves the previous effective/durable configuration intact;
- a power interruption during bank write leaves the previous bank valid until the new bank's final revision token exists;
- a renderer can lag due to refresh quota without changing committed mapping state.

These are not independent conveniences; they are consequences of keeping ownership and publication boundaries explicit.


## Cross-family proof of the abstraction boundary

The production bundle contains five controller families with deliberately different purposes; the synthetic ControllerTest family is retained only under `tests/ic10/`:

| Family | Runtime shape | Why it matters architecturally |
|---|---|---|
| ControllerPI | Continuous feedback loop | Exercises numeric configuration, bounds, stateful integration, actuator output, and tuning telemetry. |
| ControllerSequencer | Discrete state machine | Exercises state transitions, timers, two outputs, timeout/complete states, and one-shot/repeat behavior. |
| ControllerPhasePressure | Thermodynamic pressure-requirement controller | Exercises external domain profiles, phase-boundary math, mode-dependent target derivation, direct-vs-publish actuation, and a grid-facing request contract. |
| ControllerPressureDomain | Shared pressure-domain infrastructure | Exercises multi-controller request arbitration, medium/role filtering, incremental discovery consumption, plant-limit clamping, and paired source/sink setpoint ownership. |
| ControllerPressureTransfer | Physical pressure-grid edge controller | Exercises screw-bound topology identity, staged reservation/grant consumption, per-link flow control, deadband/gain limits, and topology-bound transfer telemetry. |

All five production controller families use the same Generic Persistent Config Host, Loader, Committer, Editor, Scanner, Resolver, selectors, discovery, and diagnostics. The test-only ControllerTest fixtures exercise the same boundaries without occupying the production Input Profile Catalog. The addition of ControllerSequencer required no family-specific logic in those generic services. This is stronger evidence of the framework boundary than adding another PI/PID-like algorithm would have been, because a sequencer has a fundamentally different execution model.


## Transaction hardening layer

The pressure-grid path now treats several multi-cell surfaces as transactions rather than informal telemetry. `ControllerPhasePressure`, `ControllerPressureDomain`, and `ControllerPressureTransfer` publish telemetry ABI2 with `S115` committed last. Resource Profile Views publish a positive `S5` generation only after resolving a complete catalog; consumers recheck that generation after reading the fields they combine.

Actual gas identity is checked separately from intended identity: a Medium Profile supplies the ratio LogicType and purity threshold, a Pipe Analyzer supplies the observed composition, and `Pressure Medium Purity Guard` gates Inventory publication.

Grid grants are also identity-bound. Allocator ABI3 stages source Reservation, sink Reservation, MediumType, and RouteKind with each grant; `Transfer Grant Guard` compares them with current coherent Transfer topology and the Planner commit epoch before a pump can run. Multi-hop admission uses non-mutating QUOTE requests followed by exact common-rate COMMITs. See `docs/CORRECTNESS_HARDENING.md`.


## Resource-orchestration generalization

PressureGrid now has an additive normalization layer above it. The goal is not to make pressure-specific code generic; the goal is to reuse the transactional resource concepts that survived hardening.

```text
                      GENERIC RESOURCE CORE

Endpoint -> Reservation -> Link -> plan/commit -> executor
    |                                      |
    +---------------- Transform -----------+

       /                              \
      /                                \
Pressure specialization            Material specialization
(moles, pumps, purity)             (item quantity, storage slots, chutes)
```

The proof is now executable on both sides. PressureDomain Inventory is normalized by `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10`; Vending Machine inventory is published directly by `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10`; both share Endpoint ABI1 and Resource Reservation ABI1. `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` projects a topology-bound PressureTransfer into Generic Resource Link ABI1. `ic10/material-grid/material_resource_link_v1_0.ic10` publishes the same Link ABI for a physically different discrete route built from Vending + Stacker + Logic Sorter.

The material execution chain is intentionally specialized below that contract:

```text
source Endpoint -> Reservation ----+                         +-> sink Reservation <- Endpoint
                                   |                         |
                                   v                         |
                              Material Link -----------------+
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
                 Allocator      Grant Guard     Executor
                                                   |
                                              Material Feeder
                                                   |
                                  Vending -> Stacker -> Sorter -> sink
```

The Allocator reserves an exact discrete quantity; the Guard binds the commit to Reservation/resource/device identity; the Feeder creates the exact batch; and the Executor confirms destination ImportCount after taking its completion snapshot before release.

Resource Transform payload now uses the shared Generic Store/Loader control plane and `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` republishes Transform Profile ABI4. The semantic services under `ic10/material-transform/` provide the only one-to-three-input atomic transform execution path, including the one-input Arc Furnace case. The processor is not modeled as a Link: Material Links preserve input resource identity while Transform Runtime changes those resources into the declared output and confirms it through a coherent Resource Reservation.

This layer deliberately does not replace PressureGrid's Allocator ABI3, path planner, or Grant Guard. MaterialGrid uses Multi Material Allocator ABI2 as its single material commit authority for both one-input and multi-input catalog transforms. The ABI2 path stages every reservation/Guard first and publishes one common commit epoch only after all inputs are ready. Parallel unrelated item jobs remain intentionally serialized per allocator instance while retained Stacker buffers, chute occupancy, and route contention are hardened in-game.

## Generic Job control plane

Roadmap item 5 adds a scheduler-neutral layer above the existing Directory/Catalog/Resource transactions:

```text
user / automation intent
        |
        v
Generic Job record
        |
        +--> JobType TRANSFORM -> Transform Catalog + MaterialGrid transaction
        |
        +--> JobType PRINT ----> Recipe Catalog + Printer Directory
        |
        +--> JobType TRANSFER --> Resource Directory/Reservation/Link
        |
        `--> JobType POWER -----> Power policy scheduler -> PowerGrid
```

`ic10/generic-jobs/generic_job_store_v1_0.ic10` is the only new production IC for this layer. It stores 32 logical eleven-field jobs. The first eight fields are immutable intent; the mutable `[State,Generation,ErrorStatus]` triplet is double-buffered per slot. A queue-wide odd/even sequence fences readers while one slot's inactive state bank is written and flipped active.

The Job Store deliberately does not select a printer, furnace, resource path, or power device. Those identities are plan results and can become stale while a job is waiting. The Job intent instead carries stable operation identity (`TransformType`, `RecipeHash`, `ResourceType`, or POWER `PolicyId`), required capability, cardinality, requested quantity, and priority.

The canonical lifecycle is `QUEUED -> PLANNING -> RESERVING -> READY -> RUNNING -> VERIFYING -> COMPLETE`. `WAIT_RESOURCE`, `WAIT_PROCESSOR`, and `WAIT_CAPACITY` return to PLANNING. `FAULT` and `CANCELLED` are terminal. Every mutation uses expected JobGeneration; terminal jobs cannot be reopened and can leave the Store only through REAP.

`data/generic_job_schema.json` and `framework/job_abi.py` remain the lifecycle-law source. Roadmap Item 6 supplies manufacturing lifecycle policy through `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10`; current physical Job Store mailbox mutation is serialized by Gateway ABI3 and `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10`. The Job Store still owns publication mechanics and does not absorb processor/resource policy. The current material-transform transaction remains unchanged below the Job layer rather than being replaced by a second reservation protocol. See `docs/GENERIC_JOB_ABI.md` and `docs/MANUFACTURING_SCHEDULER.md`.

## Manufacturing scheduling layer

Item 6 composes the existing substrates instead of introducing manufacturing-specific copies:

```text
Job Store -> Job Selector -> Manufacturing Scheduler -> Driver Router
                                          |                |
                                          |         +------+------ +
                                          |         |              |
                                          |     Transform       Print
                                          |      Driver         Driver
                                          |         |              |
                                          |   TransformLane   Recipe Profile
                                          |   + 161..165      + PrinterExecution
                                          |                    + MaterialGrid
```

The scheduler is the TRANSFORM/PRINT lifecycle-policy owner; it requests mutations through Gateway lane A, while `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` remains the sole physical Job Store mailbox writer. It selects the highest Priority eligible job with lower JobId as the deterministic tie-break, gives a WAIT job a one-cycle skip to avoid monopolization, and advances driver targets one legal lifecycle edge at a time.

Processor selection is generic. `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` is instantiated once against `DirectorySchema.TransformLane` v1 and once against `DirectorySchema.PrinterExecution` v1. Transform and printer directories share `ProcessorSpec` capability/Power/Busy/Error bits; capability comparison is mask containment for transforms and minimum tier for printers.

Printing extends Recipe schema to v3 so exact RecipeHash execution metadata includes bounded reagent requirements. ITEM Resource Profile schema 2 supplies `ManufacturingReagentHash`, and Material Links republish that semantic alias while retaining exact ResourceType. The print resolver therefore produces the same four-cell input records consumed by the existing Multi Reservation Stager/Allocator ABI2 protocol.

Output-slot capacity is intentionally local. `ic10/printer-directory/printer_execution_bank_v2_0.ic10` may pin up to six printers and is the only manufacturing service that reads printer slots directly. `ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` overlays exact Printer ReferenceId plus capacity state into `DirectorySchema.PrinterExecution`; `ic10/printer-directory/printer_capacity_client_v2_0.ic10` re-resolves that exact printer on a live Execution Bank before reservation, so a printer swap between directory publication and reservation fails closed.

Transform environmental conditions are profile-driven: `ic10/material-transform/material_transform_admission_v1_0.ic10` enforces declared pressure and temperature bounds for every compatible Arc/Furnace/Advanced Furnace class. See `docs/MANUFACTURING_SCHEDULER.md`.

## Catalog coordination control plane

Catalog metadata/storage uses a separate control plane. `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` is the single global membership authority for Generic Store ABI5 nodes, while `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` discovers immutable Loader ABI4 candidates and places whole Loader items into live Store capacity and requests additional Generic Stores when needed. Every physical catalog Store runs the same `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` program and advertises a human-assigned positive `S18 NodeId` as UNCLAIMED before assignment.

Coordinator ABI3 owns physical membership, schema/catalog/partition assignment, runtime Store ordinals, capacity reservations, Prev/Next topology, assignment epochs, and topology publication. A persistent 64-node Generic Registry Directory plus Adapter/Telemetry services owns membership health and aggregate used/free capacity. Store ABI5 nodes own durable whole-item payloads in a generic item directory + downward heap and pull Router-assigned Loader ABI4 items into their own stack. Loaders own only their zero-initialized immutable relocatable candidate stack and terminate after Ready publication. Views read committed Store data under Store revision plus Coordinator topology sequence.

This makes physical Store identity independent from payload schema and generated Loader source. Adding a Generic Store for capacity does not require a payload schema change or Loader regeneration. Coordinator ABI3 supports higher-epoch recovery, empty Store retirement, and whole-item migration/compaction from non-empty DRAINING nodes into runtime-selected compatible capacity under the topology seqlock. Duplicate NodeIds and missing nodes are explicit health states rather than silent topology corruption.

## Storage access plane

Generic ITEM inventory is no longer limited to directly readable Vending devices. Cargo LArRE is modeled as a specialized storage-access actuator behind an async service. `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` serializes arm movement, proxy-slot inspection, pickup, and placement; `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` converts one configured storage location/resource into Generic Resource Endpoint ABI1 and automatically participates in ResourceEndpoint discovery. This keeps manufacturing/dependency planning independent of whether the physical source is Vending-backed or LArRE-accessed.


## Cross-domain process utility layer

Item 11 adds a horizontal composition layer above the independent resource domains:

```text
                    ProcessCondition
                    /      |      \
                   /       |       \
          PressureGrid  manufacturing  PowerGrid
               |             |            |
               +------ physical process --+
```

The contract is deliberately weaker than a reservation: it declares a target, semantic medium, pressure/temperature envelope, unmet bits, strategy, status, and generation. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` derives it from Transform Profile conditions; `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` derives it from coherent PowerPlan shortage.

Physical specializations then reuse existing authorities. `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` makes a process chamber an ordinary PressureDomain, `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` makes an Advanced Furnace embedded pump an ordinary PressureTransfer under GrantGuard, and prepared gas mixtures remain FLUID Resource Profiles after purity validation. The gas-preparation controllers own only their Gas Mixer writes. `ic10/material-transform/material_transform_admission_v1_0.ic10` remains final furnace admission authority and PowerPlan remains read-only to the GFG utility. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Field-evidence plane

Item 12 adds no new control authority. `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` is a read-only observer and `tools/live_commission.py` is an offline evidence recorder. Production ownership remains with the same Hosts, directories, reservation allocators, planners, guards, executors, and domain runtimes. A field PASS therefore documents observed behavior; it cannot authorize a physical mutation or repair a missing reservation.

## Operator deployment metadata

Executable ownership and operator deployment ownership are deliberately connected but not conflated. `data/source_manifest.json` `SOURCE_MANIFEST_V3` records each hand-maintained deployable program's architecture layer/purpose plus one `deployment_family` and one deployment class. Generated-file rules provide the same metadata for catalog-generated IC10 programs whose concrete file count may change.

`docs/SCRIPT_INDEX.md` is generated from that metadata for engineering navigation. `USER_DEPLOYMENT_GUIDE.md` is the operator-facing view: its generated program inventories are refreshed by `tools/generate/update_user_deployment_inventory.py`, while its procedures remain human-authored. `validation/validators/validate_user_deployment_guide.py` requires every deployable IC10 program to appear exactly once and requires every family to retain the standard install/health/commission/reflash/reclaim sections.

This prevents a recurring failure mode in large IC10 deployments: adding a technically correct service that has no clear physical deployment home, residency rule, or commissioning procedure.
