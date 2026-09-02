# Manufacturing Scheduler

Roadmap item 6 adds the first production scheduler above the Generic Job, Directory, Catalog, and Resource Grid substrates. It schedules **TRANSFORM** and **PRINT** jobs without introducing a second job lifecycle, reservation ledger, recipe database, or processor-discovery mechanism.

The scheduler is deliberately serial at the Job Store lifecycle-writer boundary. Multiple physical processors may exist and the drivers search them dynamically, but one `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` instance owns `SET_STATE` commands for one Generic Job Store mailbox.

## Scope

Item 6 schedules:

```text
JobType.TRANSFORM = 1
JobType.PRINT     = 2
```

`TRANSFER` remains a valid Generic Job type but is not dispatched by the manufacturing scheduler. `POWER` is dispatched by the separate finite policy scheduler documented in `docs/POWER_MANAGEMENT.md`; it reuses the Generic Job Selector but not manufacturing drivers.

The immutable Generic Job record remains unchanged:

```text
[JobId, JobType, RequiredCapability, Identity,
 InputCount, OutputCount, RequestedQuantity, Priority,
 State, Generation, ErrorStatus]
```

For manufacturing:

```text
TRANSFORM Identity = TransformType
PRINT     Identity = RecipeHash
```

Actual processor ReferenceIds, links, reservations, and output-capacity guards are plan results and are never written back into immutable Job intent.

## Scheduler topology

```text
171 Generic Job Store
        |
        +--> 181 Manufacturing Job Selector
        |        coherent queue scan
        |        highest Priority / lower JobId
        |
        +<-- 183 Manufacturing Scheduler ---- 182 Manufacturing Driver Router
                    sole lifecycle writer              |             |
                                                       |             |
                                             179 Transform      180 Print
                                             Job Driver         Job Driver
                                                  |                 |
                                    Transform candidate       Recipe profile
                                         selector             + Print candidate
                                                  |                 selector
                                             175 Transform          |
                                             Candidate Exec    176 Print Candidate Exec
                                                  |                 |
                                         existing 161..165     186 Capacity Client
                                         transform lane        177 Material Resolver
                                                              178 Print Runtime
                                                                   |
                                                              163 Stager
                                                              164 Allocator ABI2
```

`ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` is one reusable **dynamic** selector. Each request supplies the exact Snapshot Directory ReferenceId in `S16`, so the serial manufacturing control plane uses **one physical selector instance** for both domains. Transform Driver points it at `DirectorySchema.TransformLane`; Print Driver points it at `DirectorySchema.PrinterExecution`. The selector captures and revalidates active bank plus generation before publishing.

Similarly, printing reuses `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` and `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` as a **print reservation lane** wired to `ic10/manufacturing/print_material_resolver_v1_0.ic10`. Transform lanes retain their own existing Resolver/Stager/Allocator instances. The protocol is shared; the mutable reservation instances are not multiplexed across simultaneous domains.

## Queue selection

`ic10/generic-jobs/generic_job_selector_v3_0.ic10` performs a read-only coherent scan of the 32-slot Generic Job Store.

It accepts:

```text
S19 scheduling cursor JobId; skip every eligible JobId <= cursor, 0 = start at head
S20 request generation
```

It publishes, after revalidating the Job Store queue sequence:

```text
S21 response generation
S22 status: 1 selected, -2 none, -1 invalid Store
S23 physical Job slot ordinal
S24 JobId
S8  JobType
S9  RequiredCapability
S10 Identity
S11 InputCount
S12 OutputCount
S13 RequestedQuantity
S14 Priority
S15 State
S16 JobGeneration
S17 QueueGeneration
```

Eligible states are `QUEUED` and the three WAIT states. Only TRANSFORM and PRINT jobs are selected.

Ordering is deterministic:

```text
higher Priority first
then lower JobId
```

When a job enters a WAIT state, Scheduler advances the selector cursor to that JobId. The next scan skips every eligible JobId at or below the cursor, so multiple high-priority waiters cannot alternate forever and starve lower-priority runnable work. When the scan reaches the end, Scheduler clears the cursor and wraps to the highest-priority job.

## Lifecycle ownership

`ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` is the TRANSFORM/PRINT lifecycle-policy owner. It requests `SET_STATE` through the Job Gateway; `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the sole physical Job Store mailbox writer.

The scheduler never writes per-slot Job Store banks directly. Every mutation goes through:

```text
Command                = SET_STATE
SlotOrdinal            = selected physical slot
ExpectedJobGeneration  = current committed generation
DesiredState           = one legal next state
ErrorStatus             = driver/wait/fault status
RequestGeneration       = new mailbox token
```

Drivers report a **target** lifecycle state. Scheduler advances only one legal edge at a time. If a driver gets ahead of publication—for example it reports RUNNING while the Store is still RESERVING—the scheduler commits:

```text
RESERVING -> READY -> RUNNING
```

rather than skipping READY. COMPLETE is likewise reached only through VERIFYING.

A stale JobGeneration causes the Job Store request to fail; Scheduler releases the selection and replans rather than overwriting a newer cancellation/fault/state change.

## Driver normalization

`ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` hides domain-specific driver ABIs from Scheduler.

It reads the selected immutable fields from Job Selector and dispatches them to:

```text
JobType TRANSFORM -> ic10/manufacturing/transform_job_driver_v2_0.ic10
JobType PRINT     -> ic10/manufacturing/print_job_driver_v2_0.ic10
```

The Router republishes only:

```text
TargetState
ErrorStatus
```

so Scheduler does not contain transform/printer-specific branches beyond selecting the normalized router request.

## Common processor selection

Printer and transform discovery share a packed `ProcessorSpec` contract.

Base bits:

```text
bits 0..7  capability value
bit 8      Power
bit 9      Busy / Active / reserved
bit 10     Error
```

Printer v2 additionally carries:

```text
bit 11     On
bit 12     Lock
```

PrinterExecution v1 additionally overlays:

```text
bit 13     output slot occupied
bit 14     output capacity known
bits 16..18 Execution Bank pin index
```

`ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` supports two capability comparison modes:

```text
1 = mask containment       # TransformLane
2 = minimum tier           # PrinterExecution
```

Every request supplies the exact expected DirectorySchemaId and schema version. Overflowed snapshots, wrong widths, wrong versions, unpowered/busy/error processors, and print candidates without known/free output capacity fail closed.

## Transform scheduling

### Transform Lane Directory

`ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` publishes:

```text
DirectorySchema.TransformLane v1
[RuntimeReferenceId, ProcessorReferenceId, ProcessorSpec]
```

The adapter discovers `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` services and derives processor capability from the actual attached furnace:

```text
Arc Furnace       = 1
Furnace           = 3
Advanced Furnace  = 7
```

Busy state includes both live `Activate` and a Runtime request that has not yet completed.

### Transform readiness + candidate execution

`ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` owns planning readiness for one selected Transform Runtime. It requires Transform Profile View ABI4 to echo the requested TransformType (`S68`) with ready status (`S69`), then waits for **new Admission and Resolver publication generations**. There is no fixed tick timeout: a valid three-input route may scan a full 64-link directory under automatic IC10 preemption.

Readiness classifies failures at their authoritative layer: Admission rejection => `WAIT_PROCESSOR`, Resolver rejection => `WAIT_RESOURCE`, and output shortfall => `WAIT_CAPACITY`.

`ic10/manufacturing/transform_candidate_executor_v2_0.ic10` is consequently small: it delegates readiness to `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10`, launches the exact selected Runtime only after readiness succeeds, and mirrors Runtime progress only when Runtime ABI2 publishes the matching current request token.

The path still reuses the existing transaction chain:

```text
161 Admission
 -> 162 Link Resolver
 -> 163 Multi Reservation Stager
 -> 164 Multi Material Allocator ABI2
 -> 165 Generic Transform Runtime
```

The driver iterates TransformLane candidates. If all compatible lanes fail, it preserves the strongest reason encountered:

```text
WAIT_RESOURCE
WAIT_CAPACITY
WAIT_PROCESSOR
```

### Environmental conditions

Pressure and temperature requirements are transform data, not furnace-class exceptions.

`ic10/material-transform/material_transform_admission_v1_0.ic10` always enforces the selected profile's:

```text
MinPressureKPa
MaxPressureKPa       # <=0 means no upper limit
MinTemperatureK
MaxTemperatureK      # <=0 means no upper limit
```

for Arc Furnace, Furnace, and Advanced Furnace alike after capability matching. Choosing a different compatible processor cannot bypass declared transform environmental bounds.

### Item 11 process-condition preparation

Manufacturing still treats processor pressure/temperature as a hard live admission requirement, but those conditions no longer have to be prepared manually. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` republishes the selected Transform Profile pressure/temperature window as `ProcessCondition ABI1`. `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` projects the furnace chamber as an ordinary PressureDomain, `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` exposes Advanced Furnace embedded inlet/outlet pumps through the existing PressureTransfer/GrantGuard path, and the process-gas-preparation controllers can prepare composition/temperature buffers.

This does **not** move utility authority into the scheduler. A not-yet-conditioned furnace remains `WAIT_PROCESSOR`; the utility layer converges independently, then the normal retry reaches `ic10/material-transform/material_transform_admission_v1_0.ic10`, which revalidates the exact physical P/T bounds before any material reservation/execution proceeds. Utility readiness never substitutes for Admission. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Recipe execution metadata

Recipe Catalog schema v3 extends each recipe from enumeration-only metadata into an execution profile while keeping the same catalog/Store infrastructure.

Logical item:

```text
RecipeHash
FamilyHash
RequiredCapability
FamilyOrdinal
InputCount
Input[0..N-1] = [ManufacturingReagentHash, Quantity]
zero padding to 4-cell alignment
```

`ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` resolves an exact RecipeHash and publishes:

```text
S2  capability mask = 0
S11 FamilyHash
S12 RequiredCapability
S13 InputCount
S14 Store publication generation
S15 status: 1 ready, -2 invalid catalog, -3 missing
S16..S47 reagent/quantity pairs, up to 16 inputs
S48 Coordinator topology generation
S49 resolved RecipeHash echo
```

The explicit `S49` echo prevents a consumer from accepting a ready response belonging to the previous RecipeHash request.

`ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` remains the ordinal/browse Lookup ABI3 service. It understands Recipe schema v3 but intentionally returns the same compact family/ordinal result surface.

## Manufacturing reagent identity

The framework does not maintain a second table mapping recipe words such as Iron or Steel to concrete item PrefabHashes.

ITEM Resource Profile `ProfileSchema=2` uses parameter cell 2 as:

```text
ManufacturingReagentHash
```

for printable ingot/material resources. `ic10/material-grid/material_resource_link_v1_0.ic10` republishes that semantic identity in `S27` while retaining the exact concrete ResourceType in `S31`.

`ic10/manufacturing/print_material_resolver_v1_0.ic10` therefore matches:

```text
Recipe ManufacturingReagentHash
        -> reachable Material Link S27
        -> exact concrete ResourceType / reservations
```

The resolver emits the same four-cell per-input surface used by Transform Link Resolver:

```text
[MaterialLinkRef, PerOutputQuantity, ResourceType, Unit]
```

The Multi Material Reservation Stager and Allocator can consequently stage/commit printing materials unchanged. RequestedQuantity is applied by the common Stager.

## Printer execution capacity

IC10 can read ordinary logic/stack state by a discovered ReferenceId, but the framework does not rely on direct ReferenceId slot access for printer output-slot occupancy.

### Execution Bank

`ic10/printer-directory/printer_execution_bank_v2_0.ic10` locally pins up to six printers on `d0..d5` and is the only service that calls `ls` for their output slots.

For each pin it separates three concepts:

```text
S16..S21 current Printer ReferenceIds
S24..S29 local capacity/status bits
S32..S37 ExpectedPrinterRef requests
S40..S45 RequestToken (positive reserve, negative release)
S48..S53 ResponseStatus
S56..S61 ResponseToken                # written after status
S64..S69 OwnerPrinterRef
S72..S77 OwnerToken
```

A reserve succeeds only if the live pin still contains `ExpectedPrinterRef`. Failed reservations never create ownership. A fresh/reset Bank does **not** clear external Lock state it cannot prove it owns; a valid release clears Lock only when the currently attached printer still equals the persisted OwnerPrinterRef.

Multiple Execution Bank instances may be deployed for more than six printers.

### Printer Execution Directory

`ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` joins the ordinary Item-4 Printer Directory against all live Execution Banks and publishes:

```text
DirectorySchema.PrinterExecution v1
[PrinterReferenceId, FamilyHash, ProcessorSpec]
```

The overlay **reuses** Printer Directory v2 family/capability/live-state metadata and adds only locally verified output-capacity and pin information.

The record identity is the exact Printer ReferenceId, not the Execution Bank identity.

### Capacity Client

`ic10/printer-directory/printer_capacity_client_v2_0.ic10` receives the exact selected PrinterReferenceId plus ProcessorSpec pin bits. Reserve/release are acknowledged transactions. While waiting, the client safely reasserts ExpectedPrinterRef + RequestToken, so an Execution Bank reboot cannot lose an outstanding request. After reserve success it rechecks live pin identity plus persisted OwnerPrinterRef/OwnerToken before exposing success.

This closes the directory-to-reservation swap race:

```text
snapshot selected Printer A
Printer A removed / Printer B inserted on same bank pin
capacity reservation for A -> WAIT_PROCESSOR
```

The replacement printer is never silently used for A's job.

## Print scheduling

`ic10/manufacturing/print_job_driver_v2_0.ic10` first resolves RecipeHash through Recipe Execution Profile View and requires immutable Job intent to match the recipe:

```text
RequiredCapability == recipe RequiredCapability
InputCount          == recipe InputCount
OutputCount         == 1
```

It then iterates PrinterExecution candidates matching FamilyHash and minimum capability tier.

`ic10/manufacturing/print_candidate_executor_v2_0.ic10` performs one candidate attempt:

1. verify RecipeHash/profile echo and required capability;
2. reserve exact printer output capacity through Capacity Client;
3. ask Print Material Resolver to resolve every reagent;
4. launch Generic Print Runtime only after capacity and resource planning succeed;
5. release printer capacity on completion, wait, or fault.

### Generic Print Runtime

`ic10/manufacturing/generic_print_runtime_v2_0.ic10` uses the same Multi Material Allocator ABI2 completion contract as transforms.

Once materials are committed it issues the printer's native execute-recipe stack instruction, chunks requested output count to the native 255 limit, watches `ExportCount`, and reports:

```text
RESERVING
READY
RUNNING
VERIFYING
COMPLETE
```

A printer Error faults the job. A RUNNING printer that stops making progress for the bounded stall interval faults rather than moving backward into a WAIT state, preserving Generic Job lifecycle legality.

## Wait semantics

Domain drivers normalize planning failures into Generic Job wait states:

```text
WAIT_RESOURCE   = required source material not currently reachable/available
WAIT_PROCESSOR  = no compatible/live processor, stale exact printer identity, or processor loss
WAIT_CAPACITY   = destination/output capacity unavailable
```

WAIT jobs return to PLANNING when selected again, so directories, topology, recipes, resource availability, and processor capacity are all revalidated.

## Deployment

Minimum scheduler control plane for one Job Store:

1. `ic10/generic-jobs/generic_job_store_v1_0.ic10`.
2. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` with `d0 -> Job Store` (default S18=0 manufacturing mode).
3. `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` with `d0 -> Job Store`, `d1 -> Job Selector`, `d2 -> Driver Router`.
4. `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` with `d0 -> Transform Job Driver`, `d1 -> Print Job Driver`, `d2 -> Job Selector`.
5. Deploy **one** `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10`; connect both domain drivers to that shared selector. Transform Driver `d2` points to the TransformLane Snapshot Host and Print Driver `d3` points to the PrinterExecution Snapshot Host; each driver writes the appropriate directory RefId to selector `S16` with its request.
6. Configure Transform Driver `d1 -> 175 Transform Candidate Executor`; configure `175 d0 -> 187 Transform Candidate Readiness`; configure `187 d0 -> selected Transform Runtime dependencies` through the runtime's published refs.
7. Configure Print Job Driver `d1 -> 172 Recipe Execution Profile View`, `d2 -> 176 Print Candidate Executor`.
8. Configure Print Candidate Executor `d0 -> Recipe Execution Profile View`, `d1 -> 177 Print Material Resolver`, `d2 -> 178 Print Runtime ABI2`, `d3 -> 186 Capacity Client ABI2`.
9. Configure Print Material Resolver `d0 -> Recipe Execution Profile View`, `d1 -> ResourceLink Snapshot Directory`.
10. Configure Print Runtime `d0 -> Print Material Resolver`, `d1 -> print-lane Multi Material Allocator ABI2`; wire that Allocator and its `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` to the same Print Material Resolver.
11. Deploy TransformLane directory path: `173 Adapter -> 169 Bridge -> dedicated 166 Snapshot Host`.
12. Keep ordinary Printer Directory v2 running and deploy PrinterExecution path: one or more `ic10/printer-directory/printer_execution_bank_v2_0.ic10` instances ABI2, `185 Adapter -> 169 Bridge -> dedicated 166 Snapshot Host`.
13. Attach each printer that may execute scheduled work to exactly one Execution Bank pin. A bank protects up to six printers.
14. Keep Recipe, Resource Profile, ResourceLink, Transform, and Job substrate services required by the selected jobs online.

The scheduler does not submit jobs. Job ingress may be manual or provided by a later UI/control service; once a valid job is published, Scheduler owns its manufacturing lifecycle transitions.

## Production source footprint

Item 6 plus its hardening pass adds 16 production source programs, ordinals 172 through 187. Every one is at or below the framework's 120-line target. Physical deployment count depends on topology because several generic programs are instantiated more than once:

- one dynamic Candidate Selector instance is shared by the serial Transform/Print scheduler;
- one Generic Snapshot Host/Bridge pair is required per new directory schema;
- one Execution Bank handles at most six printers;
- transform and print reservation lanes use separate mutable Stager/Allocator instances.

## Validation

`validation/validators/validate_manufacturing_contracts.py` checks the static cross-service contracts.

`tests/test_manufacturing_scheduler.py` executes:

- coherent priority selection;
- lower-JobId tie breaking;
- cursor-based WAIT fairness across multiple waiters;
- normalized Transform/Print routing;
- legal one-edge-at-a-time lifecycle publication through the actual Job Store.

`tests/test_manufacturing_execution.py` checks:

- schema/version-qualified processor selection;
- recipe reagent resolution through MaterialGrid;
- distinct resource/capacity wait reasons;
- Generic Print Runtime material commit and output verification;
- TransformLane ProcessorSpec publication.

`tests/test_printer_execution_capacity.py` checks:

- six locally guarded printers per Execution Bank;
- exact output-slot occupancy;
- failed-reservation ownership isolation;
- exact-ref swap rejection between request publication and Bank processing;
- Bank reboot request reassertion and acknowledged release;
- Printer Directory metadata reuse;
- exact PrinterReferenceId preservation;
- fail-closed printer replacement after directory selection.

`tests/test_material_transform_protocol.py` checks universal pressure/temperature bound enforcement and the existing 1..3-input atomic transform transaction.

`tests/test_recipe_catalog.py` checks Recipe schema v3, exact reagent metadata, and large runtime Store placement.


## Item 8 dependency-planner integration

Item 8 preserves the Scheduler's queue/lifecycle policy while removing direct multiwriter access to the Generic Job Store command mailbox. Current `ic10/generic-jobs/generic_job_command_gateway_v4_0.ic10` has five independent producer lanes: Scheduler lifecycle, Planner cancellation, Child creation, POWER lifecycle, and stock-target root ingress. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the **sole physical Job Store mailbox writer** for those production paths.

The scheduler's execution boundary is now:

```text
181 selector -> 183 scheduler -> ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10
                                      | ready
                                      v
                           ic10/manufacturing/manufacturing_driver_router_v2_0.ic10
```

While a job is `PLANNING`, the Dependency Gate asks the Item-8 Planner whether existing inventory is sufficient or a bounded dependency plan must run. Only a dependency-ready response reaches the existing Driver Router. TRANSFORM/PRINT driver semantics, candidate selection, physical resource reservations, pressure/temperature enforcement, and printer capacity ownership remain unchanged.

`ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` remains the manufacturing lifecycle-policy owner: it decides legal Job ABI edges and wait/fault outcomes. It publishes those decisions through Job Command Gateway ABI4 lane A rather than writing `ic10/generic-jobs/generic_job_store_v1_0.ic10` directly. Planner cancellation uses lane B; Child Creator uses lane C; power uses lane D; stock-target ingress publishes only new roots through lane E. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` serializes all five into the one Job Store request mailbox.

See `docs/DEPENDENCY_PLANNING.md` for bounded depth, future-output claims, Plan Store ABI2, cancellation, and restart semantics.
