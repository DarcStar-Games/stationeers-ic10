# Power Management Reuse

Item 9 applies the framework's existing Resource Profile, Generic Resource Endpoint/Reservation/Link, Generic Directory, and Generic Job concepts to electrical power. The design intentionally avoids a parallel power-only inventory or queue model.

## 1. Resource identities

The unified Resource Profile catalog now includes two additional ResourceClass partitions: `ResourceClass.POWER = 4` and `ResourceClass.ENERGY = 5`.

| ResourceClass | ResourceType | Unit | Purpose |
|---:|---|---:|---|
| 4 `POWER` | `HASH("Power.Electrical")` | 4 `WATT` | instantaneous electrical supply/demand |
| 5 `ENERGY` | `HASH("Power.Electrical")` | 5 `JOULE` | stored electrical energy identity/telemetry |

`tools/generate/generate_resource_profiles.py` produces Loader ABI5 candidates `ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10` and `ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10`. POWER/ENERGY are ordinary Resource Profile items; Store ABI6 and Coordinator ABI4 are unchanged.

Stationeers reports Station Battery `Charge`/`Maximum` in its game-energy convention (commonly documented as watt*tick/J-equivalent storage) and electrical transfer rates in watts. The framework never substitutes an ENERGY quantity for a POWER quantity merely because both are numeric.

For Station Batteries, dispatch uses a **one-game-tick horizon**: the safe instantaneous watt ceiling is `min(stored-energy delta available in one tick, configured charge/discharge watt cap)`. Stationeers explicitly allows a battery to take/provide up to its storage delta in one tick, so the numeric delta is a valid one-tick power ceiling in the game convention. This rule is specific to devices with those semantics; APC documentation reports `Charge`/`Maximum` differently, so APC binding remains a live-verification boundary rather than an assumed alias.

## 2. POWER Endpoint extension

All live power providers use Generic Resource Endpoint ABI1 (`magic 31415949`). The ordinary Endpoint cells retain their generic meaning:

```text
S2  ResourceClass = POWER
S3  ResourceType = HASH("Power.Electrical")
S4  role bits
S5  ExportAvailable watts
S6  ImportCapacity watts
S7  generic current quantity/capacity summary
S8  health
S9  native physical provider ReferenceId
S11 publication generation
S12 Unit = WATT
S13 precision/direction metadata
```

Power-specific metadata uses the existing generic extension copied by `ic10/resource-grid-core/resource_reservation_v1_0.ic10`:

```text
Endpoint S35  PowerNodeKind: 1 producer, 2 consumer, 3 battery
Endpoint S38  DomainId
Endpoint S39  PolicyId
Endpoint S40  priority*16 + flags

Reservation S28  mirrored PowerNodeKind
Reservation S29  mirrored DomainId
Reservation S30  mirrored PolicyId
Reservation S31  mirrored priority/flags
```

The Reservation semantic generation changes when these power-relevant fields or the underlying export/import capacities change.

### Producer endpoint — `ic10/power-grid/power_producer_endpoint_v1_0.ic10`

`ic10/power-grid/power_producer_endpoint_v1_0.ic10` publishes one electrical supply domain as exact POWER export capacity. `S16` selects the readable LogicType; a typical deployment points it at `PowerPotential` on a Cable Analyzer so multiple generators on one physical supply network are represented by one aggregate supply Endpoint. `S17` may cap advertised watts. `S18` is DomainId, `S19` PolicyId, and `S20` is source preference (lower values are preferred within the producer class).

The endpoint observes physical `On` when available. An off or faulted source publishes zero export.

### Consumer endpoint — `ic10/power-grid/power_consumer_endpoint_v1_0.ic10`

`ic10/power-grid/power_consumer_endpoint_v1_0.ic10` publishes managed demand as exact import capacity. Demand can be configured directly or read from one selected LogicType. The physical load's current `On` state is deliberately not used to erase desired demand; the dispatcher must be able to turn a shed load back on later.

```text
S16  DemandLogicType; 0 = use configured demand
S17  configured demand watts
S18  DomainId
S19  PolicyId
S20  priority 0..999; higher values run first within a load class
S21  flags: CRITICAL=1, SHEDDABLE=2, AUTO_MANAGED=8
S50  policy override: 0 AUTO, 1 ENABLE, 2 SHED
S51  optional job watt override/cap
```

Only AUTO_MANAGED consumers are inserted into the power-dispatch directory. A managed noncritical consumer must also be SHEDDABLE.

### Battery endpoint — `ic10/power-grid/power_battery_endpoint_v1_0.ic10`

`ic10/power-grid/power_battery_endpoint_v1_0.ic10` publishes one Station Battery-compatible storage node as a bidirectional POWER endpoint. APC-style devices must not use this adapter until live-game verification confirms equivalent `Charge`/`Maximum` delta semantics. Reserve and target thresholds are local policy; the general dispatcher only sees the resulting export/import capacities.

```text
S16  max charge watts
S17  max discharge watts
S18  reserve ratio 0..1
S19  target ratio, clamped >= reserve
S20  DomainId
S21  PolicyId
S22  priority
S50  override: 0 AUTO, 3 CHARGE, 4 DISCHARGE, 5 HOLD
S51  optional requested watt cap
S41  current stored energy telemetry
S42  maximum stored energy telemetry
S43  reserve energy
S44  target energy
S45  PowerPotential telemetry
S46  PowerActual telemetry
S47  charge ratio
```

By default the framework treats battery `On` as an actuator it owns, so an executor-created Off state must not erase the capacity needed to turn the battery back on later. `S23 RespectPhysicalOn=0` is therefore the default. Set `S23=1` only when physical/external Off is intended as a hard operator lockout; in that mode an off battery advertises neither charge nor discharge capacity. The battery never advertises discharge below its reserve or charge above its target. Override direction is reflected in Endpoint capacity before any dispatch plan can consume it.

## 3. PowerReservation directory

`ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10` consumes ordinary Generic Resource Reservations and publishes `DirectorySchema.PowerReservation v1` through the ordinary Snapshot Directory substrate.

Record:

```text
[DispatchKey, PolicyId, ReservationReferenceId]
```

Capacity is 64 records. DispatchKey sorts ascending:

```text
1,000,000 + sourcePreference        producer source
2,000,000 + batteryPreference       battery discharge source
3,000,000 + (999-priority)          critical load
4,000,000 + (999-priority)          sheddable load
5,000,000 + (999-priority)          battery charge sink
```

Thus generation is used before battery discharge; critical loads are considered before sheddable loads; battery charging consumes only surplus after managed loads. A battery may appear once as a source candidate and once as a sink candidate, but the plan builder prevents simultaneous use in both directions. Managed consumers and batteries remain discoverable even when current capacity is zero so a later POWER policy job can resolve a previously SHED/HOLD target; source/sink selectors, not directory membership, reject zero capacity. `S14` binds the adapter to the current Power Reservation Allocator and filters reservations owned by a different authority.

## 4. Generic Resource Links for electricity

Power topology remains Generic Resource Link ABI1 (`magic 31415953`, ResourceClass POWER).

### Static path — `ic10/power-grid/power_static_link_v1_0.ic10`

`ic10/power-grid/power_static_link_v1_0.ic10` represents a commissioned passive cable-domain path between one source Reservation and one sink Reservation. `S20` is the commissioned safe watt ceiling and `S21` an optional nonnegative cost hint. Source overhead is zero.

### Transformer path — `ic10/power-grid/power_transformer_link_v1_0.ic10`

`ic10/power-grid/power_transformer_link_v1_0.ic10` represents an actuated Transformer. Its delivered ceiling is the smaller of native `Maximum` and the commissioned safe ceiling. Native `RequiredPower` is carried at Link `S14` as source-side overhead.

The planner therefore distinguishes:

```text
SinkW   = watts delivered downstream
SourceW = SinkW + transformer self-power
```

A plan that budgets only SinkW against the upstream source is invalid.

## 5. Bounded dispatch transaction

The power dispatcher publishes at most eight physical flows per plan. This is a deliberate IC10/storage bound, not a general graph theorem.

Flow record:

```text
[LinkRef,
 SourceReservationRef,
 SinkReservationRef,
 SinkW,
 SourceW,
 SourceReservationGeneration,
 SinkReservationGeneration,
 LinkGeneration]
```

### Selection

- `ic10/power-grid/power_sink_selector_v1_0.ic10` reads sinks in PowerReservation dispatch order. It uses Reservation **S7 ImportCapacity** as demand.
- `ic10/power-grid/power_source_selector_v1_0.ic10` selects sources from a cursor and uses Reservation **S6 ExportAvailable** as available supply. It subtracts source watts already staged in the same plan and rejects battery direction conflicts.
- `ic10/power-grid/power_link_selector_v1_0.ic10` requires a live `DirectorySchema.ResourceLink v1`, verifies exact source/sink Reservation identities, checks Link generation, and computes transformer overhead.
- `ic10/power-grid/power_sink_flow_builder_v1_0.ic10` retries later source candidates when a preferred source has no usable path.

The current bounded runtime expects one producer Endpoint to represent the aggregate available supply of its commissioned source domain. A Cable Analyzer's network `PowerPotential` is the intended direct aggregate measurement. The planner does not sum independent source Endpoints to satisfy one indivisible managed load; deploy one aggregate producer Endpoint per electrical source domain rather than one Endpoint per parallel generator when combined capacity is required.

### Priority sweep

`ic10/power-grid/power_dispatch_sweep_v1_0.ic10` traverses critical loads, sheddable loads, then battery charging. Managed loads are on/off allocations: a critical or sheddable load is not intentionally run below its requested demand. Battery charging may accept a partial allocation.

The sweep reports total shed watts and separately marks critical shortage. Plan capacity overflow is explicit and fail-closed.

### Publication

`ic10/power-grid/power_dispatch_cycle_v1_0.ic10` owns:

```text
PlanStore BEGIN
  -> priority sweep / staged flows
PlanStore COMMIT
```

`ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` uses an odd/even publication sequence. Readers consume only an even stable sequence and exact PlanGeneration. On boot, an odd sequence means COMMIT was interrupted; the Store invalidates PlanGeneration/flow-count/status headers and advances the sequence to even before accepting another request. It does not expose the torn payload as the prior plan.

## 6. Reservation commit and execution authority

Planning is read-only until the complete plan validates.

`ic10/power-grid/power_plan_validator_v1_0.ic10` rechecks:

- exact PlanGeneration and even publication sequence;
- Resource Reservation magic/class/health/generation;
- Resource Link class/source/sink/health/generation;
- positive SinkW and `SourceW >= SinkW`;
- transformer overhead arithmetic;
- no Reservation is simultaneously a source and sink.

`ic10/power-grid/power_reservation_committer_v1_0.ic10` writes one common allocator epoch. When one source feeds multiple flows, its ReservedExport is the **sum** of all SourceW entries; a later flow never overwrites an earlier source reservation.

`ic10/power-grid/power_reservation_allocator_v1_0.ic10` performs:

```text
validate complete plan
-> commit new Reservation epoch
-> release previous owner epoch
-> publish [PlanGeneration, Epoch, ACTIVE]
```

A crash after Reservation mutation but before allocator publication grants no physical actuation authority. The allocator explicitly cleans the newly staged epoch if commit fails part-way or if replacement of the old epoch cannot complete, preventing orphaned same-owner reservations from accumulating.

### Break-before-make executors

`ic10/power-grid/power_load_executor_v1_0.ic10` is the actuator for managed consumer/battery `On` state. `ic10/power-grid/power_link_executor_v1_0.ic10` is the sole Transformer `Setting`/`On` actuator.

Both require exact agreement among:

- stable Plan Store generation;
- active allocator PlanGeneration;
- allocator epoch;
- Reservation owner/epoch/generation;
- Link generation where applicable.

The transformer executor validates **both** source and sink Reservation owner, epoch, and reserved semantic generation before changing `Setting` or `On`.

Any mismatch causes immediate safe-off. A newly committed Plan Store therefore cannot energize a load or transformer before the corresponding Reservation epoch is published.

## 7. POWER jobs

`GENERIC_JOB_ABI_V1` already reserves `JobType.POWER = 4`; Item 9 uses it unchanged. A POWER job is a finite **policy transaction**, not an indefinitely-running electrical load.

Job intent:

```text
JobType              = POWER
Identity             = PolicyId
RequiredCapability   = PowerMode
RequestedQuantity    = optional watt override/cap
```

PowerMode:

```text
0 AUTO
1 ENABLE       consumer
2 SHED         consumer
3 CHARGE       battery
4 DISCHARGE    battery
5 HOLD         battery
```

The job completes after the endpoint accepts the override and the ordinary Generic Resource Reservation mirror coherently reflects the resulting export/import semantics.

### Job control services

- `ic10/generic-jobs/generic_job_selector_v3_0.ic10` is the shared coherent Job selector. POWER Scheduler configures exact `JobType.POWER` mode and uses its JobId cursor for fairness.
- `ic10/power-jobs/power_policy_target_resolver_v1_0.ic10` resolves PolicyId to exactly one current power Reservation/Endpoint. Duplicate rows for the same Reservation are harmless (battery dual roles); different Reservations with the same PolicyId are ambiguous and fail closed.
- `ic10/power-jobs/power_job_policy_apply_v1_0.ic10` revalidates the exact READY JobId/generation/type/PolicyId before writing Endpoint override cells.
- `ic10/power-jobs/power_job_policy_verify_v1_0.ic10` waits for the Reservation mirror to match the requested consumer/battery semantics.
- `ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10` uses Job Gateway lane D. On successful `SET_STATE`, it returns `ExpectedJobGeneration + 1`; it does not reinterpret the Job Store's PUBLISH_NEW-only return cell as a lifecycle generation.
- `ic10/power-jobs/power_job_prepare_v1_0.ic10` advances `QUEUED/WAIT -> PLANNING -> RESERVING -> READY`, maps a temporarily missing target to `WAIT_RESOURCE`, faults invalid/ambiguous policy intent, applies the policy, then advances to RUNNING.
- `ic10/power-jobs/power_job_finalize_v1_0.ic10` verifies the Resource Reservation mirror and advances `RUNNING -> VERIFYING -> COMPLETE`; an incomplete mirror returns pending so selector cursor fairness can service another POWER job.
- `ic10/power-jobs/power_job_scheduler_v1_0.ic10` coordinates selection, prepare/apply and verify/finalize.

`ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` now has four independent producer lanes: manufacturing lifecycle, dependency cancellation, child creation, and POWER lifecycle. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` remains the sole physical Generic Job Store mailbox writer.

## 8. Correctness boundaries

Power management deliberately retains these boundaries:

1. Resource Profiles define POWER/ENERGY semantics; they do not contain live priority or reserve policy.
2. Endpoints describe current supply/demand willingness; Reservations own mutable watt claims.
3. Directory order is discovery/policy order, not allocation authority.
4. Links describe actual source-to-sink reachability; a preferred source with no compatible link is skipped rather than falsely satisfying a load.
5. Plan Store publication is not actuation authority; the allocator epoch is required too.
6. Transformer self-power is always source-side overhead.
7. Battery export/import are mutually exclusive within one plan.
8. Battery reserve/target constrain capacity before planning; `RespectPhysicalOn` optionally turns external Off into a hard lockout without creating a framework self-lock.
9. POWER jobs change policy; they do not bypass dispatch/reservation safety.
10. Stale JobGeneration, Reservation generation, Link generation, plan generation, directory generation, or allocator epoch fails closed.

## 9. Validation and adversarial coverage

`validation/validators/validate_power_management_contracts.py` protects the structural contract, including the Generic Reservation **S6 export / S7 import** direction regression, foreign-ownership filtering, allocator cleanup, exact transformer authority, POWER intent mapping, and Gateway lifecycle-generation interpretation.

`tests/test_power_management.py` covers:

- battery reserve/target rate math;
- optional `RespectPhysicalOn` battery lockout without framework self-lock;
- critical-first shedding and partial battery charging;
- source selector exact Reservation S6 export capacity;
- sink selector exact Reservation S7 import capacity;
- wrong ResourceLink schema rejection;
- transformer overhead accounting;
- PowerReservation dual battery roles;
- coherent Plan Store BEGIN/ADD/COMMIT;
- live Plan -> validate -> Reservation commit -> allocator epoch;
- foreign Reservation ownership rejection and source aggregation within a plan;
- committed load/transformer actuation;
- orphan-epoch cleanup plus break-before-make safe-off on stale plan authority;
- POWER Job SHED through Job Store, Gateway lane D, exact `Identity=PolicyId` / `RequiredCapability=PowerMode` / watt-cap mapping, WAIT-state resumption, endpoint apply, Reservation verification and COMPLETE.

Item 10 broad interruption testing is complete and now includes allocator reflash reacquisition plus direct interleaving tests that revoke allocator authority between executor validation and the final load/transformer write.


## 10. Fuel-backed generation integration

Item 11 closes the first POWER -> process-utility feedback loop without giving PowerGrid ownership of gas. `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` observes the coherent Power Dispatch Plan Store. Shed watts above its commissioned trigger or a critical-shortage flag causes it to publish `ProcessCondition ABI1` for a prepared fuel medium such as `Fuel.H2O2`.

The demand can drive `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10`; its output is purity-gated by `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` and transported through the ordinary PressureGrid. `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` starts the Gas Fuel Generator only after fuel pressure/composition, ambient pressure/temperature, generator identity/error, PowerPlan sequence, and mixture-guard generation are all current. When shortage disappears it safe-offs the generator and withdraws fuel demand.

PowerPlan remains read-only to this utility controller. There is deliberately no immediate Electrolyzer dependency during deficit because POWER -> Electrolyzer -> fuel -> GFG -> POWER is a cycle. Surplus-power chemical storage requires a separate time-separated energy-arbitrage policy. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.
