# Correctness Hardening Pass

This pass deliberately paused new grid features and concentrated on correctness boundaries that become important once the framework behaves like a distributed resource scheduler. The architecture remains the same; the changes tighten identity, snapshot coherence, reservation admission, and fault visibility.

## 1. Transactional telemetry ABI2

`ControllerPhasePressure`, `ControllerPressureDomain`, and `ControllerPressureTransfer` now publish Generic Telemetry ABI2. They clear `S115` before mutating related telemetry fields and publish a new positive generation in `S115` last.

Consumers that combine multiple cells use:

```text
generationBefore = S115
require generationBefore > 0
read payload
generationAfter = S115
accept only if generationAfter == generationBefore
```

This protects compound facts such as:

- `{RequestedPressure, Mode, Status, MediumType}`;
- `{PressureDomain target, Role, MediumType, Status}`;
- `{Transfer source, sink, route, medium, candidate rate}`.

PI, Test, and Sequencer telemetry remain ABI1 because current consumers do not require their displayed channels to form an invariant-bearing transaction.

## 2. Unified Resource Profiles and coherent publication

`data/resource_profiles.json` is now the single source of truth for phase-medium and material-item profile metadata. `generate_resource_profiles.py` produces ResourceClass-partitioned active Stores plus one-shot sparse whole-profile Loader candidates; the Coordinator-selected Generic Store imports assigned candidate ranges transactionally while `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` resolves one typed record and publishes it with `S5` as the positive commit token. Dedicated per-medium and per-item profile programs were removed.

`ControllerPhasePressure` captures and rechecks Resource Profile View `S5`; a catalog/view that is incomplete, being reflashed, or changes during the read cannot be consumed as a valid thermodynamic snapshot.

The generated library contains Water, Pollutant, Silanol, Nitrous Oxide, Nitrogen, Methane, Carbon Dioxide, Oxygen, and Hydrogen.

## 3. Actual working-medium purity is verified

A configured `MediumType` is an intention, not evidence about what gas is physically in a pipe network. Earlier Inventory code multiplied the analyzer's `TotalMoles` by the assumption that every mole belonged to the configured medium.

For `ProfileKind=PHASE_MEDIUM`, Resource Profile View schema 2 publishes:

```text
S19 GasRatioLogicType
S20 MinimumPurity
S21 LatentHeat
```

`ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` reads the selected ratio dynamically from the Pipe Analyzer. For a nonempty bus it requires:

```text
ObservedRatio >= MinimumPurity
```

The default generated threshold is `0.995`. Inventory ABI2 advertises zero transfer capacity when the guard fails or the guard's medium identity does not match the PressureDomain.

An empty bus is considered composition-safe because it contains no contaminating material.

## 4. Transfer grants are bound to reserved topology

A reservation is only valid for the endpoints and route that were used when it was calculated. Allocator ABI3 stages these identities with every grant:

```text
S117 source Reservation RefId
S118 sink Reservation RefId
S119 MediumType
S120 RouteKind
S109 staged epoch LAST
```

`ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` reads a coherent current Transfer telemetry snapshot and compares current source, sink, medium, and route to the staged identities. It also requires the staged Planner ReferenceId and epoch to match the Planner's committed epoch.

If a Transfer is rewired or reconfigured between planning and activation, the grant stays OFF rather than consuming capacity that was reserved against different endpoints.

## 5. Multi-hop reservation is quote then exact commit

Earlier path allocation could reserve an early hop at a larger rate and later normalize all hops downward. That was safe but wasted endpoint capacity until the next build epoch.

Allocator ABI3 supports:

```text
S16 = 1  QUOTE
S16 = 0  COMMIT
```

A QUOTE computes currently admissible mol/tick without changing endpoint counters or staged grant state. Path Allocator now:

1. quotes every hop;
2. takes the minimum quoted rate;
3. commits every hop at exactly that common rate.

A failed quote consumes no endpoint capacity. An unexpected commit-stage failure remains safe because the Planner commit epoch is unchanged and already-staged grants are invalidated.

## 6. Route ranking sees remaining reservations

Route Ranker ABI2 no longer scores only the raw physical candidate rate. For every hop it caps throughput by:

```text
(ExportableMoles - ReservedExportMoles) / LeaseTicks
(ImportCapacityMoles - ReservedImportMoles) / LeaseTicks
```

A path exhausted by allocations already made in the same build becomes inadmissible before Path Allocator attempts it. This prevents a low-cost route from repeatedly winning based on capacity that has already been reserved by the direct-reuse phase.

The Ranker also explicitly rejects NaN cost weights and a NaN candidate budget.

## 7. Directory overflow is fail-visible

The Controller Directory still has a deliberate 64-controller maximum, but valid provider 65+ no longer disappears silently.

Generic Snapshot Directory publishes one overflow flag per A/B bank. Controller Selector ABI2 reads it directly and returns `-3`; PhasePressure Arbiter and Grid Link Directory also refuse incomplete snapshots.

The operational rule is:

> A known-incomplete directory is not an authoritative discovery snapshot.

For very large bases, keep controller discovery on a dedicated data network so the incremental scanner is not delayed by hundreds of unrelated devices.

## 8. Actual IC10 execution tests

The existing Python protocol models remain useful for exhaustive interruption/state cases, but they are independent reimplementations. A model and an IC10 script can theoretically share the same mistaken design assumption.

`framework/ic10_harness.py` is therefore a small deterministic interpreter for the instruction subset used by transaction-critical tests. It is not intended to emulate the whole game.

`tests/test_ic10_execution.py` currently executes the real IC10 source for:

- generated Resource Profile Catalog + Pollutant View publication;
- successful purity validation and contaminated-gas rejection;
- one-shot pressure Grant Guard activation, staging, commit, expiry, and topology consumption;
- pressure-to-generic Endpoint/Link adapters;
- coherent 100-slot Material Vending inventory;
- Generic Resource Reservation mirroring a material endpoint;
- a complete exact material transaction from Multi Material Allocator ABI2 through Guard, Feeder/Stacker/Sorter, Executor, and destination ImportCount;
- the Material Link Reservation-vs-native-topology identity boundary;
- valid Arc Furnace Transform Admission;
- Arc Furnace Transform Runtime progression through material delivery, activation, mid-job reflash, and coherent output confirmation.

The intent is to expand this executable layer gradually around the most dangerous transaction boundaries rather than build a complete Stationeers simulator.

## Deployment changes

Every grid pressure domain now has:

```text
Resource Profile View PHASE_MEDIUM record
        |
Pipe Analyzer -> Pressure Medium Purity Guard
        |                |
        +---------> PressureDomain Inventory ABI2
                         |
                 Inventory Reservation
```

Every physical transfer now has:

```text
PressureTransfer ABI2 <---- Allocator staged grant
       |
       +----> Transfer Grant Guard <---- Grid Planner
       |               |
       <---------------+
       |
   physical pump
```

The Transfer runtime's `d3` points to its Grant Guard. Grant Guard `d0` points to the Transfer and `d1` points to the medium-specific Planner.

## Remaining limits

This hardening does not change the intentional limits of the current grid:

- automatic routed paths remain two or three physical links;
- the route score is dimensionless rather than a claimed energy calculation;
- inventory is gas-only and rejects liquid-bearing pressure buses;
- one scheduler stack per simultaneously scheduled medium is still operationally expensive;
- a last-moment change between ranking and exact commit can still cause a route to fail safely rather than immediately retrying the next candidate.

Those are optimization and deployment-scaling questions. They should be addressed after live-game commissioning confirms the transaction changes above.


## Generic Resource and MaterialGrid transactions inherit the hardened rules

The generalized Resource Core does not relax the transaction discipline established by PressureGrid. Generic Resource Endpoint uses `S11` as a generation-last commit token, Generic Resource Reservation mirrors with its own `S12` generation-last token, and Generic Resource Link publishes `S12` last. Material Vending Inventory additionally treats `ImportCount`, `ExportCount`, and Material Profile generation as a long-scan coherence barrier; any change during the 100-slot scan discards the candidate snapshot.

MaterialGrid adds its own discrete-transaction invariants:

1. Generic Link S2/S3 identify the **mutable source/sink Resource Reservations**; native device topology is separate extension state.
2. The Material Allocator writes exact source/sink quantity reservations, stages a topology-bound Guard payload, writes the staged epoch after that payload, then commits the Allocator epoch last.
3. Material Grant Guard rechecks source/sink Reservation class/type/unit/status plus Link/Feeder/Sorter/sink/Executor/Allocator identity before exposing a committed batch.
4. The Feeder prepares the exact committed quantity with a Stacker; any excess Vending-emitted stack remains buffered instead of being silently delivered.
5. Executor snapshots destination `ImportCount` **before** telling Feeder to release. This ordering was added after executable testing exposed a race in the opposite ordering.
6. Transform Admission validates one Resource Transform Profile against one physical processor, output Resource Reservation, and Material Allocator before execution can proceed.
7. Transform Link Resolver resolves one to three typed input Material Links; Multi Reservation Stager prepares every source/sink Reservation and Guard before Material Allocator ABI2 publishes the shared commit epoch.
8. Transform Runtime considers a job complete only after every committed input delivery is satisfied and a newer output Reservation generation shows the expected typed output quantity increase.
9. Feeder and Transform Runtime preserve in-flight state across same-service reflash using persistent stack markers.

The direct IC10 harness executes these actual services as an interleaved transaction. It deliberately simulates an immediate destination arrival after Stacker release, which verifies the pre-release counter snapshot rather than relying on a slow-chute assumption.



## Shared banked transaction invariant

`BANKED_TRANSACTION_V1` now names the recovery theorem shared by the Generic Persistent Config Host and Generic Job Store. Config uses the whole-image `REVISION_BANK` profile; Job Store uses per-record `SELECTOR_BANK`. In both profiles the authority marker is the commit point, recovery is old-or-new only, and an outstanding request that already equals the recovered durable logical generation is acknowledged rather than recommitted. Job recovery additionally requires Store magic **and ABI** before interpreting physical slot geometry. `tests/test_banked_transaction.py` executes these shared rules against both actual IC10 services.

## Generic Job publication and lifecycle fencing

`GENERIC_JOB_ABI_V1` adds a scheduler-neutral transaction layer above the existing Resource, Transform, Printer Directory, and Recipe Catalog contracts. `ic10/generic-jobs/generic_job_store_v1_0.ic10` is deliberately a mechanical publication authority rather than a scheduler.

The Job Store enforces these storage invariants:

1. **Intent is immutable after publication.** JobId, JobType, capability, identity, cardinalities, requested quantity, and priority are written before the initial state becomes visible and are not rewritten by lifecycle updates.
2. **State uses per-slot A/B banks.** State, Generation, and ErrorStatus are written to the inactive state bank and the active-bank selector is flipped only after that bank is complete.
3. **Generation is optimistic concurrency control.** A writer must supply the exact current JobGeneration; a stale update cannot overwrite a newer scheduler/executor decision.
4. **Terminal state is immutable.** COMPLETE, FAULT, and CANCELLED can be reaped but cannot be reopened.
5. **Queue-wide reads are fenced.** `S2` is odd during mutation and even when stable; `S3` advances after committed queue mutations. Multi-slot readers must read an even sequence before the scan and require the same even sequence afterward.
6. **Same-service reflash is old-or-new.** The Store journals the in-flight state-bank base and old active bank. A reboot before the bank flip retries the request; a reboot after the flip preserves and acknowledges the committed mutation without double-applying it.
7. **There is one request-mailbox writer.** The Store does not arbitrate concurrent command producers. `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` owns TRANSFORM/PRINT lifecycle policy, but Gateway ABI3 serializes command lanes and `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the sole physical Job Store mailbox writer.

Lifecycle-edge legality is a writer contract in `data/generic_job_schema.json` / `framework/job_abi.py`: normal progress follows QUEUED -> PLANNING -> RESERVING -> READY -> RUNNING -> VERIFYING -> COMPLETE; planning/reservation/readiness may enter explicit wait states; FAULT/CANCELLED are terminal. Keeping that policy outside the 120-line Store prevents processor-specific scheduling behavior from leaking into the generic storage ABI.


## Manufacturing scheduler correctness boundary

Roadmap Item 6 composes existing transactional substrates instead of relaxing their invariants. The scheduler is the TRANSFORM/PRINT lifecycle-policy owner; selector, router, domain drivers, candidate executors, resource resolvers, and runtimes report progress but do not mutate Job Store state directly.

Manufacturing planning is schema-qualified and fail-closed:

- TransformLane and PrinterExecution selections require exact Directory schema ID/version and stable active-bank generation;
- scheduler applies at most one legal Job ABI edge per accepted driver observation;
- Transform Admission enforces every catalog pressure/temperature bound for all furnace classes;
- Recipe Execution Profile publishes a resolved-RecipeHash echo so stale success cannot be consumed for another request;
- Recipe schema v3 reagent semantics resolve to concrete MaterialGrid ResourceTypes before reservation;
- print and transform inputs share Multi Reservation Stager / Multi Material Allocator ABI2, but use separate physical lane instances because their resolver state is mutable;
- printer output capacity is guarded by locally pinned Execution Banks, and the capacity client requires the exact selected Printer ReferenceId still occupy the advertised pin before Lock/reservation;
- a printer swap, stale directory generation, missing capacity, missing resource, or stale JobGeneration prevents execution rather than silently selecting a substitute.


## Cross-domain utility correctness boundary

Item 11 adds ProcessCondition without weakening any existing ownership rule:

1. ProcessCondition is coherent demand/verification state only; it has no reservation owner or epoch.
2. Furnace P/T demand is copied from the current Transform Profile, but `ic10/material-transform/material_transform_admission_v1_0.ic10` independently rechecks live processor pressure/temperature before material execution.
3. Process chambers and Advanced Furnace embedded pumps reuse PressureDomain/PressureTransfer identities; movement remains gated by PressureGrid reservation and GrantGuard authority.
4. Two-component gas preparation changes ResourceType and is therefore not represented as a Generic Resource Link.
5. Composition and thermal mixer controllers re-fence Profile/ProcessCondition generation before physical writes and safe-off on inactive/malformed demand.
6. The GFG utility observes PowerPlan but never mutates it, and re-fences PowerPlan plus fuel-purity generation immediately before `On=1`.
7. An Electrolyzer is not recursively started from a GFG deficit; POWER-to-fuel-to-POWER operation requires time-separated surplus/storage policy.

See `docs/PROCESS_UTILITY_ORCHESTRATION.md` and `tests/test_process_utility.py`.
