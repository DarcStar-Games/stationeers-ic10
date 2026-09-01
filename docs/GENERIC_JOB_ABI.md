# Generic Job ABI

`GENERIC_JOB_ABI_V1` defines the common runtime job record and lifecycle used by manufacturing transforms, printer work, direct resource transfers, and power-management operations. It is deliberately scheduler-neutral.

The ABI deliberately separates storage/lifecycle law from scheduling policy. Item 5 established one representation for requested work and one legal state machine; Item 6 now implements TRANSFORM/PRINT queue ordering, processor selection, resource planning, and legal lifecycle requests in the Manufacturing Scheduler without moving those policies into the Store.

The production implementation is `ic10/generic-jobs/generic_job_store_v1_0.ic10`. It owns JobId allocation, slot publication, per-job generation changes, queue publication fencing, terminal immutability, and terminal reaping. It does **not** choose processors or validate domain-specific recipes/resources.

`data/generic_job_schema.json` is the machine-readable contract. `framework/job_abi.py` is the executable reference model for intent and lifecycle validation. `tests/test_job_abi.py` verifies both the model and the live IC10 Store behavior. The Store's persistence mechanics implement the `SELECTOR_BANK` profile of `BANKED_TRANSACTION_V1`; see `docs/BANKED_TRANSACTION_STANDARD.md` and `framework/banked_transaction.py`.

## 1. Logical job record

Every published job has exactly eleven logical fields:

```text
[JobId,
 JobType,
 RequiredCapability,
 Identity,
 InputCount,
 OutputCount,
 RequestedQuantity,
 Priority,
 State,
 Generation,
 ErrorStatus]
```

The first eight fields describe immutable **intent**. The final three describe mutable **lifecycle state**.

### JobId

`JobId` is a positive monotonically allocated identity owned by the Generic Job Store. Reaping a job frees its physical slot but never reuses the old JobId. A reused slot receives a new JobId and starts again at Job `Generation=1`.

### JobType

```text
1  TRANSFORM
2  PRINT
3  TRANSFER
4  POWER
```

`POWER` is now consumed by Item 9 as a finite power-policy transaction while the Generic Job ABI remains unchanged.

### RequiredCapability

`RequiredCapability` is a non-negative integer whose interpretation is selected by JobType:

```text
TRANSFORM  Resource Transform RequiredCapabilityMask
PRINT      minimum printer capability tier
TRANSFER   0 unless the selected transfer executor defines a capability contract
POWER      PowerMode: 0 AUTO, 1 ENABLE, 2 SHED, 3 CHARGE, 4 DISCHARGE, 5 HOLD
```

The generic ABI intentionally does not collapse transform bitmasks and printer tiers into one encoding rule. It only guarantees that the value is carried unchanged as part of immutable intent. The domain planner interprets it using JobType.

### Identity

`Identity` is the domain operation/resource identity:

```text
TRANSFORM  TransformType
PRINT      RecipeHash
TRANSFER   ResourceType
POWER      PolicyId of exactly one current managed power endpoint
```

The value may be a signed Stationeers hash, so validity is **non-zero**, not positive-only.

### InputCount / OutputCount

These are integer cardinalities in `0..32`. They describe the logical shape of the work, not physical device screws or Store cells.

Examples:

- a current furnace transform uses `InputCount=1..3`, `OutputCount=1`;
- a print job records the recipe's logical material-input cardinality and one produced output family/item;
- a direct resource transfer normally uses one logical source and one logical destination;
- POWER policy jobs normally use zero cardinalities because they change endpoint policy rather than represent a continuously running electrical load.

Domain services remain responsible for tighter rules. The Generic Job ABI does not assume all future operations are one-output material recipes.

### RequestedQuantity

`RequestedQuantity` is a positive finite scalar. Its unit is determined by JobType/Identity and the catalog/resource schema used by the planner.

For manufacturing it is normally requested output quantity or batch count. For direct resource transfer it may be the requested Resource quantity in the Resource Reservation unit. This field is intentionally not restricted to an integer because transfer quantities and POWER watt caps may be continuous-valued.

### Priority

`Priority` is a finite integer. Higher values mean higher scheduling priority. The canonical deterministic tie-break for equal priority is lower `JobId` first.

The Store does not reorder physical slots. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` scans stable jobs and applies the canonical higher-Priority/lower-JobId rule.

### State / Generation / ErrorStatus

`State` is the lifecycle state below. `Generation` starts at `1` when the job is published and increments on every committed state mutation, including terminal reaping. Writers use expected generation as optimistic concurrency control. `ErrorStatus` is zero during the ordinary lifecycle, may carry a non-negative wait reason in a WAIT state, and must be negative when entering `FAULT`.

## 2. Lifecycle

The ordinary successful path is:

```text
QUEUED -> PLANNING -> RESERVING -> READY -> RUNNING -> VERIFYING -> COMPLETE
   1          2            3          4         5           6           7
```

Explicit wait states are:

```text
8   WAIT_RESOURCE
9   WAIT_PROCESSOR
10  WAIT_CAPACITY
```

Terminal failure/control states are:

```text
11  FAULT
12  CANCELLED
```

### Legal transitions

The canonical rules are:

1. ordinary chain transitions advance exactly one state at a time;
2. `PLANNING`, `RESERVING`, or `READY` may enter any WAIT state;
3. every WAIT state resumes at `PLANNING`, forcing the scheduler to revalidate topology/resources rather than assuming its old plan remains valid;
4. any non-terminal state may enter `FAULT` with a negative ErrorStatus;
5. any non-terminal state may enter `CANCELLED`;
6. `COMPLETE`, `FAULT`, and `CANCELLED` are immutable terminal states;
7. terminal records leave the queue only through `REAP`.

In particular, these are invalid:

```text
RUNNING -> COMPLETE       # VERIFYING may not be skipped
WAIT_RESOURCE -> READY    # planning must be redone
COMPLETE -> PLANNING      # terminal jobs cannot reopen
FAULT -> QUEUED           # retry is a new JobId, not resurrection
```

`job_abi.allowed_transition()` is the executable reference for this table.

## 3. Why waits return to PLANNING

A wait means some assumption used to build the previous plan is not currently satisfiable. Resource inventories, processor state, directory generations, Store capacity, and topology may all have changed while the job was waiting.

Returning to `PLANNING` is therefore deliberately conservative. It prevents a scheduler from treating a previously selected processor or reservation path as still authoritative merely because the missing condition became available later.

## 4. Generic Job Store ABI1

`ic10/generic-jobs/generic_job_store_v1_0.ic10` publishes:

```text
S0   magic = GenericJobStore.v1
S1   ABI = 1
S2   capability mask = 224 (`HAS_ASYNC_REQUEST_V1` + `HAS_BANKED_TRANSACTION_V1` + `HAS_GENERIC_JOB_ABI_V1`)
S8   Store response generation
S9   Store response status; 1 success, <0 rejected
S10  allocated JobId for PUBLISH_NEW; ignore on other commands
S11  Store command
S12  slot ordinal 0..31
S13  expected Job Generation for SET_STATE / REAP
S14  desired State for SET_STATE
S15  desired ErrorStatus for SET_STATE
S16  QueueSequence; odd while a slot mutation is being published, even when stable
S17  QueueGeneration; advances after committed mutations and recovery of committed odd state
S18  capacity = 32
S19  Store request generation
S23  next JobId
S24  last applied request generation / replay marker
S25  in-flight state-metadata base
S26  in-flight old active state bank
```

Recovery interprets the durable slot geometry only when **both** `S0` magic and `S1` Store ABI match. A physical layout change therefore requires a Store ABI bump; an incompatible same-magic stack is reset rather than guessed/migrated.

The Store command set is deliberately small:

```text
1  PUBLISH_NEW
2  SET_STATE
3  REAP
```

The Store is the **single mutation authority** for published JobId/state. A scheduler or ingress writer may populate only an unpublished free slot's immutable staging cells before issuing `PUBLISH_NEW`.

### PUBLISH_NEW

The writer:

1. captures an even `QueueSequence`;
2. finds a slot whose current active `State=0`;
3. writes the seven immutable candidate fields to that slot's unpublished intent cells (`JobType` through `Priority`);
4. confirms QueueSequence is unchanged and even;
5. writes command `1`, SlotOrdinal, then a new Store request generation last;
6. waits for matching Store response generation.

The Store assigns the JobId, publishes `State=QUEUED`, `Generation=1`, `ErrorStatus=0`, and returns the new JobId.

### SET_STATE

The writer first reads the job under a stable QueueSequence and validates the requested lifecycle edge using `GENERIC_JOB_ABI_V1`. It then supplies SlotOrdinal, current Job Generation, desired State, desired ErrorStatus, command `2`, and request generation.

The Store rejects a stale expected Job Generation. It also refuses to reopen `COMPLETE`, `FAULT`, or `CANCELLED`. Legal lifecycle-edge validation remains a required writer contract so the Store can remain domain-neutral and within the IC10 line budget.

### REAP

Command `3` requires the exact current Job Generation. The Store accepts REAP only for `COMPLETE`, `FAULT`, or `CANCELLED`.

Reaping publishes `State=0` in the slot's inactive state bank and flips that state bank active. Old immutable intent cells remain physically present but are **not a job** while active State is zero. A later PUBLISH_NEW may overwrite them before publishing a fresh JobId.

## 5. Physical Store geometry

The 32-slot representation fills one IC stack while keeping mutable state double-buffered per slot.

### Immutable intent region

```text
S32..S287
32 slots x 8 cells

IntentBase(slot) = 32 + 8*slot
+0 JobId
+1 JobType
+2 RequiredCapability
+3 Identity
+4 InputCount
+5 OutputCount
+6 RequestedQuantity
+7 Priority
```

### Mutable state region

```text
S288..S511
32 slots x 7 cells

StateBase(slot) = 288 + 7*slot
+0 active state bank: 0=A, 1=B
+1 A.State
+2 A.Generation
+3 A.ErrorStatus
+4 B.State
+5 B.Generation
+6 B.ErrorStatus
```

The logical eleven-field record is reconstructed from the intent slot plus the active state triplet.

This layout is why capacity is 32. The capacity is a physical Job Store ABI property, not a Job schema version. A future larger queue may shard jobs across several Stores without changing the eleven-field logical record.

## 6. Transactional publication and reflash recovery

A state mutation uses the inactive per-slot state bank:

```text
write journal metadata
QueueSequence -> odd
write inactive [State,Generation,ErrorStatus]
flip slot active state bank
advance QueueGeneration
QueueSequence -> even LAST
publish response generation
```

Readers must:

```text
seq0 = S16
require seq0 even
read intent + active state triplet
seq1 = S16
accept only if seq1 == seq0 and even
```

The active-bank flip is the job-state commit point.

The Store retains `S25/S26` while a mutation is in flight. On same-service reflash with odd QueueSequence:

- if the active state bank still equals the old bank, the mutation did not commit; the Store clears the applied-request marker, repairs QueueSequence, and the unchanged request can retry;
- if the active state bank changed, the new state already committed; the Store advances QueueGeneration, repairs QueueSequence, and acknowledges the existing request without applying it twice.

This is the `SELECTOR_BANK` commit profile in `BANKED_TRANSACTION_V1`. It gives the Job Store a crash boundary comparable to the framework's other transactional services without double-buffering the entire 32-job queue. The shared rule is old-or-new authority plus replay acknowledgement after the commit point; the Job Store's selector/journal geometry remains service-specific.

## 7. Optimistic concurrency

Every SET_STATE and REAP request carries `ExpectedJobGeneration`.

A scheduler therefore follows:

```text
read stable job record
plan from JobGeneration G
perform external planning/reservation work
before state mutation, request SET_STATE with ExpectedJobGeneration=G
```

If another actor cancelled/faulted/advanced the job first, the Store rejects the stale generation. No stale scheduler decision may overwrite the newer state.

The framework's intended ownership model is still one scheduler writer per Job Store. JobGeneration is not a substitute for having several unsynchronized services write the Store request mailbox concurrently.

## 8. Mapping current domains onto the ABI

### Resource transforms

Current material transforms map naturally:

```text
TRANSFORM
Identity             = TransformType
RequiredCapability   = RequiredCapabilityMask
InputCount           = Transform InputCount (currently 1..3)
OutputCount          = 1
RequestedQuantity    = requested transform batch/output quantity
```

The existing 161..165 transaction path remains the execution mechanism. Item 6 wraps that proven transaction with Generic Job planning/state transitions through TransformLane discovery, a generic candidate selector, and a Transform Job Driver; it does not replace Admission, Link Resolver, Reservation Stager, Allocator ABI2, or Runtime.

### Printer work

```text
PRINT
Identity             = RecipeHash
RequiredCapability   = Recipe RequiredCapability / minimum printer tier
```

Item 6 combines Recipe schema-v3 execution metadata with `DirectorySchema.PrinterExecution` v1 to select an exact capacity-guarded printer. The ordinary Printer v2 directory remains the family/capability/live-state source for the execution overlay.

### Direct resource transfer

```text
TRANSFER
Identity             = ResourceType
RequiredCapability   = normally 0
```

The planner resolves actual source/destination Reservations and Links. The Job record does not duplicate topology-specific ReferenceIds because those are plan outputs and can become stale while a job waits.

### Power

`POWER` uses the same lifecycle shape for finite policy transactions; electrical resource/dispatch semantics remain in the power subsystem, not the Job record.

## 9. Job Store responsibility boundary

The Job Store intentionally does **not** own:

- printer or furnace selection;
- manufacturing queue/planning policy;
- dependency expansion;
- resource/processor assignment fields in immutable Job intent;
- a second reservation protocol;
- automatic retry of terminal jobs;
- multi-writer arbitration for the Store command mailbox.

Processor/resource identities are properties of a **plan**, not stable user intent. The implemented Manufacturing Scheduler owns selection and queue policy above this ABI, while dependency expansion remains roadmap Item 7. Keeping plan identities out of the Job record prevents WAIT -> replan from accidentally retaining stale topology identities.

## 10. Completion contract

Item 5 is complete when:

- one eleven-field logical record covers TRANSFORM, PRINT, TRANSFER, and POWER work;
- the ordinary lifecycle and WAIT/FAULT/CANCELLED states are versioned and executable in the reference model;
- a production IC10 Store can publish at least 32 jobs without splitting a record;
- JobId is Store-owned and never reused after reaping;
- state changes use optimistic JobGeneration;
- queue readers have an odd/even publication fence;
- terminal states cannot be reopened and only terminal records can be reaped;
- same-service interruption before and after the state-bank flip is recoverable without double-applying a mutation;
- no processor-selection or manufacturing-policy responsibility is stored in the Job Store; roadmap item 6 owns that policy externally.


## Roadmap boundary

The **Manufacturing Scheduler** in roadmap item 6 is the first production owner of processor selection, queue policy, and legal lifecycle-edge application on top of this ABI. `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` owns TRANSFORM/PRINT lifecycle policy; POWER lifecycle policy is owned by `ic10/power-jobs/power_job_scheduler_v1_0.ic10`. Both serialize mutations through the Job Gateway and sole physical Store command executor; see `docs/MANUFACTURING_SCHEDULER.md` and `docs/POWER_MANAGEMENT.md`.

## Item 9 POWER-job integration

Item 9 reuses `GENERIC_JOB_ABI_V1` without adding power-specific fields. `Identity=PolicyId`, `RequiredCapability=PowerMode`, and `RequestedQuantity` is an optional watt cap. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` plus the `ic10/power-jobs/` policy-resolution/apply/verify/lifecycle services resolve one managed endpoint, apply the requested policy, and complete only after Generic Resource Reservation coherently mirrors the new semantics. Job Gateway ABI3 adds lane D for the Power Scheduler; `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` remains the sole physical Job Store mailbox writer. See `docs/POWER_MANAGEMENT.md`.
