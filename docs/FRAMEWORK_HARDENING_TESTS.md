# Framework Hardening Tests

The Python validators/model tests prove important static and protocol properties, but they cannot reproduce every Stationeers runtime/device behavior. This file is the human live-game test plan that complements automated validation.

For a new deployment or major framework change, run the automated tests first. Then use these cases to verify that the same invariants hold with real IC execution, device removal/reflash, and game power interruption.

## Automated prerequisites

Before live testing, run the complete release suite:

```text
python run_validation.py
```

For focused diagnosis, the component checks include:

```text
python validation/validators/validate_ic10.py
python validation/validators/validate_abi_contracts.py
python validation/validators/validate_config_contracts.py
python validation/validators/validate_input_contracts.py
python tests/test_shared_input_protocol.py
python tests/test_persistence_protocol.py
python tests/test_sequencer_protocol.py
python tests/test_resource_profiles.py
python tests/test_phase_pressure_protocol.py
python tests/test_pressure_domain_protocol.py
python tests/test_pressure_inventory_protocol.py
python tests/test_pressure_grid_protocol.py
python tests/test_pressure_reservation_protocol.py
python tests/test_controller_directory_scale.py
python tests/test_pressure_route_cost.py
python tests/test_ic10_execution.py
python validation/validators/validate_source_catalog.py
python validation/validators/validate_documentation.py
python validation/validators/validate_power_management_contracts.py
python tests/test_power_management.py
python validation/validators/validate_fault_injection_contracts.py
python tests/test_fault_injection.py
```

A failing automated contract should be fixed before treating a live-game symptom as a Stationeers timing issue.


## Automated interruption campaign

`fault_injection.py`, `validation/validators/validate_fault_injection_contracts.py`, and `tests/test_fault_injection.py` implement Roadmap Item 10. The campaign injects restart after every ordered transaction prefix for catalog migration and POWER replacement, exhaustively checks Generic Job cancellation states, and exercises actual Power Dispatch Plan Store IC10 at many instruction boundaries.

The automated safety criterion is old-complete/new-complete/invalid only. A torn state may cause a safe outage, but it may not become mutation or actuation authority. Physical live-game cases below remain required for Stationeers-specific device/network behavior. See `docs/INTERRUPTION_FAULT_INJECTION.md`.

## Static contracts

`validation/validators/validate_config_contracts.py` proves:

- the Generic Persistent Config Host contains no controller-family special case for PI, Test, Sequencer, PhasePressure, PressureDomain, or PressureTransfer;
- PI Policy/Profile/Runtime agree on type and block geometry;
- Test Policy/Profile/Runtime agree on type and block geometry;
- Sequencer Policy/Profile/Runtime agree on type and block geometry;
- PhasePressure Policy/Profile/Runtime agree on type and block geometry;
- PressureDomain Policy/Profile/Runtime agree on type and block geometry;
- PressureTransfer Policy/Profile/Runtime agree on type and block geometry;
- persistence signature source strings agree with controller schema geometry.

`validation/validators/validate_input_contracts.py` proves:

- Scanner and Resolver contain no Config/Diagnostic family special cases;
- Config Bridge preserves Loader-derived logical ordinal -> physical slot mapping;
- Diagnostic Profile exposes exactly seven generic controls;
- Controller Selector, Console Selector, and Mapping Editor own zero physical screws;
- Controller Type/Member requests publish values before generation;
- Console desired-selection and automatic-advance generations remain independent;
- Mapping Editor consumes commit generation and requests Console advance only after a complete mapping record exists.

## Model persistence tests

`tests/test_persistence_protocol.py` drives the shared `REVISION_BANK` reference profile through every simulated write boundary. Before destination `bankRevision` is written, recovery must select the old bank. After that final write, recovery must select the new bank. It also verifies that a changed schema signature rejects both old banks.

`tests/test_banked_transaction.py` cross-checks both BANKED_TRANSACTION profiles and executes the real Config Host/Job Store recovery paths. It proves that Config reflash after a durable commit acknowledges the request without another bank revision, and that Job Store refuses to interpret same-magic durable cells written under an incompatible Store ABI.

## Sequencer model tests

`tests/test_sequencer_protocol.py` models the new discrete controller independently of the IC10 runtime. It checks a complete one-shot cycle, repeating behavior, cycle counting, phase timeout, missing-input safe-off behavior, numeric-fault safe-off behavior, and disable/reset semantics.


## Unified resource-profile tests

`tests/test_resource_profiles.py` regenerates the unified catalog deterministically, executes every generated linked store and loader fragment and the actual Resource Profile View, resolves all 36 current records exactly, verifies incomplete-catalog and not-found invalidation, retains phase latent heat, and rejects any surviving pre-consolidation phase/material profile sources or dedicated profile ICs.

## Phase-pressure model tests

`tests/test_phase_pressure_protocol.py` checks all nine PHASE_MEDIUM records in `resource_profiles.json`, deterministic Resource Profile Catalog generation, ratio LogicType, purity threshold, and finite in-range phase boundaries. `tests/test_ic10_execution.py` additionally executes the generated catalog and real Resource Profile View before exercising the Purity Guard and material inventory consumers.

## Pressure-domain model tests

`tests/test_pressure_domain_protocol.py` checks the PhasePressure Request Arbiter and LOW/HIGH PressureDomain contract independently of game devices. It verifies LOW=min and HIGH=max reduction, filtering by controller type/medium/mode/status, NaN rejection, no-request standby, safe-direction pressure clamping, unsatisfied-demand status `-8`, coherent Arbiter result consumption, and paired output-property guards.

`tests/test_pressure_inventory_protocol.py` checks the gas-domain resource-accounting layer: coherent PressureDomain ABI2 input, actual-medium purity enforcement, LOW export moles, HIGH import demand, STORAGE reserve/ceiling capacity, volume scaling, finite empty-sink demand, required analyzer properties, and liquid/two-phase rejection.

`tests/test_pressure_grid_protocol.py` checks the hardened Level-3 contracts: coherent Transfer ABI2 publication, topology-bound Grant Guard activation, Allocator quote/topology staging, reservation-aware Ranker behavior, and coherent Grid Link Directory snapshots. `tests/test_pressure_route_cost.py` checks the bounded cost model, pressure-lift behavior, hop/storage preference, throughput tradeoffs, and candidate budget. `tests/test_pressure_reservation_protocol.py` separately checks payload-before-epoch ordering and verifies that Planner faults never commit a partially staged build.

`tests/test_pressure_reservation_protocol.py` checks Allocator ABI3 quote/exact-commit, staged topology-before-epoch ordering, whole-path quote before exact commit, Grant Guard topology consumption, and Planner commit-last ordering.


## Direct IC10 execution tests

`tests/test_ic10_execution.py` uses `ic10_harness.py` to execute selected **actual IC10 source**, not a Python reimplementation. It currently checks generated profile publication, successful and failed purity checks, staged-next-epoch isolation, commit-only lease activation, one-shot lease expiration, and topology-mismatch epoch consumption without later reactivation.

## Controller-directory scale model

`tests/test_controller_directory_scale.py` checks the discovery ABI 2 geometry and worst-case capacity: two 64-record Directory banks, direct Selector/Arbiter/Planner stride agreement, stack addresses remaining below `S512`, direct selection across 64 providers/64 distinct controller types, and Planner lease scaling through the 64-provider ceiling.

## Live-game PressureGrid cases

- Deploy one Inventory service and one Reservation service for each LOW/HIGH/STORAGE domain. Verify Reservation `S10=1`, correct role/medium, plausible mirrored `S6/S7`, and initially zero `S12/S13` before enabling pumps.
- Deploy one Purity Guard for each grid pressure domain. Verify a sufficiently pure bus reports Guard `S5=1`; deliberately select a wrong profile or introduce contamination and verify Guard rejects it and Inventory advertises zero capacity.
- Compare a 6000 L and 50000 L isolated STORAGE network at the same temperature/pressure/bounds. Verify Inventory molar capacity scales with network volume.
- Test an empty/near-vacuum HIGH sink with known volume/temperature. Verify Inventory publishes finite import demand.
- Introduce liquid into an isolated pressure network. Verify Inventory status becomes `-4`, Reservation mirrors the fault, and no attached transfer receives a lease.
- Deploy one LOW and one HIGH domain of the same medium plus one direct PressureTransfer. Verify Transfer candidate status becomes `1`, `S100` is a plausible planned mol/tick ceiling, Planner `S14` advances, Grant Guard `S4` becomes active only for the matching staged topology/epoch, and the Transfer pump runs only from a coherent Guard publication.
- Add a second HIGH sink sharing the same LOW source. Force both links to be useful. Verify both can run in the same committed epoch and source Reservation `S12` never exceeds mirrored `S6`.
- Add two LOW sources feeding one HIGH sink. Verify both can be granted concurrently and sink Reservation `S13` never exceeds mirrored `S7`.
- Add two completely independent LOW->HIGH pairs. Verify all eligible pumps may run together from one committed epoch.
- Add LOW->HIGH and LOW->STORAGE links sharing one LOW source. Verify direct reuse receives reservation capacity during pass 2 before storage fallback is allocated during pass 1.
- Add LOW->STORAGE and STORAGE->HIGH links touching the same STORAGE domain. Verify ordinary fallback never independently creates opposing storage reservations. Then admit them as one routed path and verify simultaneous import/export is allowed only under the complete path commit.
- Run several repeated epochs with a contended source. Verify the epoch-rotated starting position prevents the same first directory entry from permanently receiving all capacity.
- While plan N is active, observe the Allocator stage plan N+1. Verify Grant Guard continues publishing the current active lease and does not adopt the staged N+1 rate until Planner `S14` commits N+1.
- Interrupt/reflash the Allocator after source reservation, after sink reservation, and after staged payload writes but before staged epoch. Verify no new pump lease becomes active.
- Interrupt/reflash the Planner after all grants are staged but before `S14`. Verify staged grants remain inert and the prior active leases either continue until their lease expires or stop from current local conditions.
- Restart the Planner after an abandoned build. Verify a new `S13` build epoch causes Reservation `S12/S13` to reset lazily when endpoints are reused.
- Change endpoint pressure sharply during an active lease. Verify Transfer current-state calculation can reduce the pump rate or turn it Off before the current Planner-advertised lease ticks are exhausted.
- Reduce a pump's `Maximum`. Verify `S100` falls consistently and the active lease cannot drive Setting above the new physical maximum.
- Rewire one Reservation endpoint to a wrong-medium service. Verify the allocator rejects the link and no matching staged epoch is published.
- Stage and commit one Transfer lease, let it expire, and keep Planner `S14` unchanged. Verify the Grant Guard does not reactivate that same epoch. Repeat with a topology mismatch during commit, then restore the original wiring; the consumed epoch must remain inactive.
- Power-cycle or reflash Transfer/Reservation/Allocator/Planner ICs and confirm retained stack/register state does not create an uncommitted active lease.
- Populate Controller Directory ABI 2 progressively through 16, 32, 48, and 64 providers. Measure full two-pass plan latency and verify Planner `S7` follows `max(64,4*N+16)` (80, 144, 208, 272 ticks respectively) without lease-expiry gaps.
- Add a 65th valid telemetry controller. Verify the inactive Directory bank publishes overflow, Controller Selector reports `-3` directly, and Arbiter/Grid Link Directory refuse the incomplete snapshot instead of silently omitting a controller.

## Live-game persistence cases

Use a known old configuration A and a visibly different new configuration B. After each interruption/restart, verify which image becomes effective and that no mixed A/B image is accepted.

| Case | Expected result |
|---|---|
| Power cut after destination invalidation | Previous bank/image A recovers. |
| Power cut midway through image write | Previous bank/image A recovers. |
| Power cut after signature but before config revision | Previous bank/image A recovers. |
| Power cut after config revision but before bank revision | Previous bank/image A recovers. |
| Power cut immediately after bank revision but before effective mirror publication | New bank/image B recovers. |
| Reflash Policy with changed signature | Old banks no longer match; Policy defaults are used unless a new config is committed. |
| Reflash Generic Host while leaving Policy/banks intact | Host reconstructs effective image from newest valid matching bank. |
| Test Policy injected reject | Previous effective/durable image remains unchanged. |
| Test Policy held response | Transaction remains pending; it must not report success or partially replace effective config. |

For every case, inspect bank revision/signature if the observed behavior is surprising. The final bank revision is the durable commit boundary.

## Model shared-input tests

`tests/test_shared_input_protocol.py` models diagnostic control-state transitions. It verifies that unchanged controls do not churn request generations, Commit is a true rising-edge generation, stale desired Console values do not undo automatic advance, and a genuinely new user Console request intentionally overrides the advanced selection.

## Live-game shared-input cases

### Device fallback and removal

- Remove Value Dial while editing a Dial control. Memory fallback should take over when a compatible Memory-like input is available.
- Remove Switch while Commit is selected. Resolver should report invalid unless Memory fallback is available for that descriptor/path.
- Reinsert the device and verify Scanner publishes a new coherent hardware snapshot and Resolver recovers without requiring domain-specific reset logic.

### Snapshot coherence

- Reflash Scanner during a value read. Resolver must discard the torn snapshot and retry.
- Reflash Profile during descriptor/enum resolution. Resolver must discard and retry.
- Change Controller Type while Directory/Catalog swaps generation. Selector must reject torn identity and only publish an identity from one coherent discovery generation.

### Commit retention and console advance

- Press Commit while selectors are temporarily not ready. Mapping Editor must retain the unhandled commit generation and complete once dependencies recover.
- Commit a mapping and verify Console advances exactly once.
- Leave Console control unchanged after advance. Stale desired value must not roll selection back.
- Change Console afterward. The new desired-generation request must override the advanced selection.
- Leave Commit Switch ON for several ticks. No repeated mapping commits should occur until the switch is toggled OFF then ON again.

### Shared-panel ownership

- Share one physical Scanner/Resolver between config and diagnostics only by powering one domain bridge at a time.
- Deliberately enable both contexts once during testing and verify/document that simultaneous writers are unsupported rather than treating resulting control-count/Profile contention as a framework bug.

## Live-game Sequencer cases

Use a harmless test volume/process before attaching the sequencer to a high-energy or high-pressure system.

- Start disabled and verify both outputs are commanded off.
- Enable below HighThreshold and verify only the Fill output is active.
- Cross HighThreshold and verify both outputs turn off for the settle interval.
- After settling, verify only Drain is active.
- Cross LowThreshold with Repeat=1 and verify cycle count increments and Fill resumes.
- Repeat with Repeat=0 and verify state becomes COMPLETE with both outputs off.
- Prevent FILL from reaching HighThreshold and verify TIMEOUT occurs at the configured phase limit with both outputs off.
- Repeat the timeout test during DRAIN.
- Remove the process device during an active phase and verify both outputs go safe-off without advancing the timer/state; reconnect and verify recovery.
- Feed/produce NaN if a suitable test path exists and verify NUMERIC FAULT is latched safe-off until disable.
- Remove/reflash an actuator and verify the Runtime continues executing without an invalid-store halt; if the process cannot progress, verify the phase subsequently times out.
- Apply a new effective configuration while enabled and verify the Runtime resets to the start of the sequence using the new coherent image.


## Live-game PhasePressure cases

Use a harmless Water test chamber before applying the controller to a high-pressure or scarce-medium installation.

- Wire the Resource Profile View selecting Water and verify telemetry channel 7 reports the expected medium hash.
- In HOLD, verify channel 4 equals StandbyPressure and direct mode writes that same value.
- At a stable in-range temperature, select EVAPORATE and verify boundary channel 3 is finite and request channel 4 is lower than the boundary unless MinimumPressure clamps it.
- Select CONDENSE and verify request is higher than the boundary unless MaximumPressure clamps it.
- Change temperature and verify the boundary/request change continuously without changing controller configuration.
- Set `DirectWrite=0`; verify telemetry continues updating while the phase device Setting remains under external/manual ownership.
- Return `DirectWrite=1`; verify the configured `OutputLogicType` receives the request.
- Disconnect the Resource Profile View and verify status `-6`, StandbyPressure publication, and best-effort standby direct write.
- Move temperature below the Profile freezing endpoint or above the critical endpoint and verify status `-7` rather than an extrapolated phase request.
- Disconnect the process device or make Pressure/Temperature unavailable and verify operational fault status plus standby fallback.
- Select an unsupported output LogicType in a controlled test and verify status `-2` without an IC halt.
- Repoint the Runtime to a different Host and verify Host identity forces coherent reload rather than reusing a same-numbered generation from the old Host.
- In publish-only mode, have a test consumer honor channel 4 only when channel 6 status is valid; confirm a fault removes the active grid request rather than silently preserving it.

## Live-game PressureDomain cases

Commission with `DirectWrite=0` first and use a harmless isolated pressure network.

- Deploy one LOW domain and two same-medium PhasePressure producers with different EVAPORATE requests. Verify channel 2 becomes the lower request and channel 3 reports two contributors after a complete Arbiter pass.
- Add a wrong-medium PhasePressure producer with a more extreme request. Verify it is ignored.
- Put one matching producer into HOLD or a fault state. Verify it stops contributing on the next completed pass.
- Change a producer from EVAPORATE to CONDENSE. Verify a LOW domain drops it and a HIGH domain can consume it.
- Repeat with a HIGH domain and verify the highest matching CONDENSE request wins.
- Change Controller Directory generation during an Arbiter pass. Verify the partial pass is discarded/restarted rather than committed.
- Change PressureDomain config/Host generation during a pass. Verify the Runtime waits for a result echoing the new Host generation.
- Change the Resource Profile View to a different medium while preserving catalog generation. Verify the Runtime rejects old Arbiter output until the echoed MediumType matches.
- Set LOW MinimumPressure above the raw minimum request. Verify command clamps to MinimumPressure and status becomes `-8`.
- Set HIGH MaximumPressure below the raw maximum request. Verify command clamps to MaximumPressure and status becomes `-8`.
- Test the opposite clamp direction and verify status remains active when the resulting bus is still pressure-compatible with the request direction.
- Remove all valid requests and verify StandbyPressure is published/commanded.
- With `DirectWrite=0`, verify no actuator setpoint changes while arbitration telemetry continues.
- With `DirectWrite=1`, disconnect or choose an unsupported property on one actuator. Verify status `-2` and neither actuator receives a half-applied write that tick.
- Reference topology: Pressure Regulator from high-pressure source into domain, Back Pressure Regulator from domain to low-pressure sink. Verify both are powered/On and receive the same target Setting.
- Starve the pressurizing source or saturate the depressurizing sink. Confirm target telemetry remains valid while actual pressure fails to converge; record this as a capacity/convergence limitation rather than an arbitration failure.
- Populate the Controller Directory through its 64-provider ceiling and measure worst-case request refresh latency; expected Arbiter design bound is roughly setup + one tick/provider + commit (~66 ticks at 64).

## Test-controller isolation strategy

When a failure could be generic or PI-specific:

1. Reproduce it with ControllerTest.
2. If ControllerTest also fails, debug Scanner/Resolver/Editor/Host/transaction infrastructure.
3. If ControllerTest passes, focus on PI Policy/Profile/Runtime semantics or PI physical process wiring.

ControllerTest remains the smallest isolation target. ControllerSequencer adds a stronger architectural check: if PI and Sequencer both fail in the same generic path, the problem is very likely infrastructure rather than control-law semantics. The presence of continuous, synthetic, state-machine, thermodynamic-requirement, shared pressure-domain, and physical pressure-transfer families gives humans six distinct fault surfaces during commissioning.

## Recording live results

For each case, record:

- script revisions under test;
- relevant ReferenceIds;
- precondition generations/revisions;
- exact interruption/action;
- observed status/result/generation afterward;
- whether behavior matched the expected invariant.

Do not edit files under `validation/evidence/` by hand to record live results. They are machine-generated release evidence; store manual observations separately so automated and human evidence remain distinguishable.


## Item 12 field-evidence workflow

Item 12 makes the recording rule above executable. `live_commissioning_cases.json` defines the required field suites; `live_commission.py` creates release-fingerprint-bound sessions and records append-only PASS/FAIL/BLOCKED observations; `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` can capture up to six read-only LogicType/stack observations during a live test. See `docs/LIVE_COMMISSIONING.md`.

A live session becomes stale when the framework input fingerprint or commissioning catalog changes. Item 12 remains ACTIVE until every required suite has a current PASS. Automated validators and `ic10_harness.py` remain prerequisites and regression tools, not substitutes for those physical results.


## Live multi-hop route hardening

Run these after single-link and reservation commissioning:

1. Build `LOW -> STORAGE -> HIGH` with no direct LOW->HIGH edge. Confirm both pumps stay off while the route is staged and start only after Planner `S14` changes.
2. Build `LOW -> STORAGE A -> STORAGE B -> HIGH`. Confirm the middle Transfer reports route class 4 and never receives a fallback-only grant.
3. Constrain the middle hop below the other two. Confirm every staged hop is normalized to the middle hop's lower mol/tick rate before commit.
4. Disable/remove the final hop while a new plan is being built. Confirm earlier staged hops are invalidated and the Planner does not advance `S14` for the failed build.
5. Reflash the Planner during path construction. Confirm the next build uses a fresh epoch and abandoned endpoint reservations do not activate.
6. Add two edge-disjoint routed paths for the same medium. Confirm both can be present in one committed plan while shared endpoint reservation totals remain within published molar capacity.
7. Try to configure a STORAGE->STORAGE link as the only useful movement. Confirm it remains inactive outside a complete LOW-to-HIGH path.

## Live cost-aware route hardening

Run these with pump actuation disabled or with a harmless test medium first:

1. Build two valid 2-hop routes with similar pressure/rate. Confirm the lower-cost route is selected and `Route Selector S11` matches `Route Ranker S21`.
2. Increase `HopWeight`; verify 2-hop routes dominate otherwise similar 3-hop routes.
3. Increase `LiftWeightPerKPa`; create two routes with different positive pressure lifts and verify the lower-lift route wins.
4. Increase `FlowScarcityWeight`; constrain one path's bottleneck rate and confirm the higher-throughput alternative becomes preferred.
5. Set `CandidateBudget=1`; verify selection behaves as bounded first-candidate ranking. Restore 32 and confirm a better later candidate can win.
6. Reorder/reflash unrelated controllers without changing Grid Link Directory topology. Verify route cost/search remains stable apart from the build-epoch rotation used for fairness.
7. Change endpoint pressure after route selection but before allocation. Reservation safety must still dominate: an inadmissible selected route must fail staging and never activate.
8. Interrupt the Route Selector/Ranker during candidate comparison. No pump may activate because route ranking is upstream of Path Allocator and Planner commit.


## Executable IC10 protocol tests

`ic10_harness.py` is a small deterministic interpreter for the instruction subset required by transaction-critical tests. `tests/test_ic10_execution.py` executes actual IC10 for the generated Resource Profile Catalog + Pollutant View, Purity Guard, Pressure Transfer Grant Guard, Generic Resource adapters, the complete committed MaterialGrid batch path, and the Arc Furnace Transform Admission/Runtime. This complements, rather than replaces, the broader model tests.

Additional hardening models verify directory overflow, telemetry generation coherence, Medium Profile generation-last publication, purity gating, Allocator ABI3 quote/commit behavior, topology-bound grants, and reservation-aware route ranking.


## Generic Resource / MaterialGrid model and execution checks

Automated checks now include `tests/test_resource_generalization.py`, `tests/test_material_grid_protocol.py`, and expanded cases in `tests/test_ic10_execution.py`.

The model/static layer verifies:

- pressure and material providers publish the same Generic Resource Endpoint ABI;
- Generic Resource Reservation contains no pressure-specific dependency;
- starter material/transform profiles reproduce their JSON sources of truth;
- a 100-slot material inventory scan invalidates on import/export churn;
- Material Link S2/S3 are Reservation ReferenceIds, while native Vending/Stacker/Sorter/sink identities are separate topology extensions;
- Material Allocator reserves exact ITEM quantity at source/sink and commits its epoch last;
- Material Grant Guard binds quantity + Reservation + ResourceType + Feeder + Sorter + sink + Link + Executor identity;
- Executor captures destination ImportCount before releasing the Feeder, preventing the fast-delivery race found during development;
- Transform Admission validates typed input Link/output Reservation/processor/allocator identity;
- Transform Runtime has a persistent reflash marker and uses coherent output Reservation growth as completion evidence.

The direct execution layer runs the actual IC10 and currently proves:

- a 10-unit request can be satisfied from a simulated 20-unit Iron Ore Vending stack;
- Stacker releases exactly 10 while retaining 10;
- Logic Sorter receives the requested ItemHash filter;
- source ReservedExport and sink ReservedImport both equal exactly 10;
- destination ImportCount completion is detected even when delivery occurs immediately after Stacker release;
- a real Arc Furnace Admission accepts a valid typed Iron-smelting job;
- Transform Runtime requests input, waits for the committed material epoch, activates the furnace, survives a simulated mid-job reflash, and completes only after coherent output inventory growth.

### Live-game MaterialGrid hardening still required

Inventory:

- verify Vending Machine internal slots remain `2..101` on the target game build;
- add/remove target and non-target stacks during an active scan and confirm only a later coherent scan publishes;
- verify `MaxQuantity` behavior for partial ore/ingot stacks;
- test memory/counter-reset behavior during a scan;
- measure practical scan latency on heavily automated data networks.

Transport:

- test source stacks smaller than, equal to, and larger than the committed quantity;
- verify a larger Vending-emitted stack is split by Stacker exactly as modeled;
- reflash Feeder in FILL, WAIT_IMPORT, READY, and WAIT_EXPORT states;
- unplug/replug Vending, Stacker, Sorter, Guard, Executor, source Reservation, and sink Reservation at each state;
- alter Link topology after allocation but before commit and verify Guard consumes the epoch;
- confirm a consumed epoch cannot execute after restoring the original wiring;
- test a very short chute route where destination import can occur effectively immediately after Stacker output;
- jam/block the chute after Stacker export and verify Executor times out rather than falsely completing;
- route a nonmatching item to the Stacker and verify Feeder faults;
- test retained Stacker buffer over several sequential transactions and compare planner inventory with physical material location;
- verify the configured Logic Sorter filter and accepted physical output path on the target game build.

Transform:

- verify basic Iron, Copper, and Gold Arc Furnace transforms with real machine output routing;
- remove furnace power between Admission and execution and confirm safe fault behavior;
- create furnace Error during WAIT_OUTPUT and confirm Activate is cleared;
- remove output capacity before a new job and confirm Admission refuses it;
- change output Reservation generation without quantity growth and confirm Runtime does not claim completion;
- reflash Runtime during WAIT_ALLOC, WAIT_INPUT, and WAIT_OUTPUT;
- verify 512-tick output timeout is reasonable for the actual furnace process or revise it based on measured data;
- processor-condition adapters now exist in Item 11; keep complex thermochemical strategy selection bounded until the live Item-11 cases below are proven.


## Generic Job Store hardening

`tests/test_job_abi.py` executes the real `ic10/generic-jobs/generic_job_store_v1_0.ic10` through `ic10_harness.py` and cross-checks lifecycle semantics against `generic_job_schema.json` / `job_abi.py`.

Automated checks prove:

- `PUBLISH_NEW` assigns a Store-owned monotonically increasing JobId and publishes `QUEUED`, Generation 1, ErrorStatus 0;
- immutable intent survives every later lifecycle update unchanged;
- `SET_STATE` requires an exact expected JobGeneration, so stale scheduler writes fail without mutating the slot;
- `COMPLETE`, `FAULT`, and `CANCELLED` are terminal and cannot be reopened through the Store;
- only terminal jobs can be reaped and a reaped physical slot can be reused with a new JobId;
- all 32 slots can be populated and slot ordinal 32 is rejected;
- a reflash before the inactive state-bank flip leaves the old state authoritative and causes the outstanding request to retry;
- a reflash after the state-bank flip retains the new state and acknowledges it without applying the mutation twice;
- same magic with an incompatible Job Store ABI resets the physical queue instead of interpreting old geometry;
- queue publication uses the Store-wide odd/even sequence and QueueGeneration so readers can fence a multi-slot scan;
- lifecycle legality, wait-state rules, terminal status requirements, and JobType-specific intent validation remain synchronized between the machine-readable schema and reference model.

### Live-game Generic Job checks

For the Item-6 Manufacturing Scheduler, perform these live-game Generic Job checks:

1. Fill all 32 Job slots and confirm a 33rd publish is rejected without modifying an existing slot.
2. Reflash the Job Store immediately before and immediately after a `SET_STATE` request; confirm the observed state matches the old-or-new atomic outcome, never a mixed state.
3. Reissue a stale `(slot, expected Generation)` update and confirm it is rejected.
4. Complete, fault, and cancel separate jobs; confirm none can transition back to a nonterminal state and all can be reaped.
5. Reuse a reaped slot and confirm the new JobId differs from the prior occupant even though the physical slot is identical.
6. Scan all slots while another job is changing state; fence the read with `S2` and reject/retry if the sequence is odd or changes.
7. Route every lifecycle mutation through Gateway ABI3; `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the sole physical Job Store mailbox writer. Do not wire Scheduler, dependency, or POWER producers directly to Store request cells.


## Manufacturing Scheduler hardening

Automated Item-6 tests exercise the actual selector/router/scheduler and execution services through `ic10_harness.py`. They prove:

- coherent queue scans choose highest Priority and lower JobId on ties;
- a WAIT job receives bounded backoff so it cannot monopolize every scheduler cycle;
- domain lifecycle policy applies Job Store changes only through Gateway/Executor, with expected JobGeneration;
- a domain driver target is reduced to one legal lifecycle edge at a time;
- TransformLane and PrinterExecution consumers validate DirectorySchemaId **and version** and fence active bank + generation;
- signed Stationeers hashes are treated as valid when non-zero rather than incorrectly requiring positive values;
- Transform Admission enforces catalog Min/Max Pressure and Temperature for Arc Furnace, Furnace, and Advanced Furnace alike;
- Recipe Execution Profile echoes the resolved RecipeHash before publishing ready state, preventing stale profile reuse;
- PRINT immutable InputCount/OutputCount must match the selected recipe shape;
- printer output-slot capacity is inspected only through a locally pinned Printer Execution Bank;
- PrinterExecution retains exact Printer ReferenceId and a pin swap after selection fails closed before reservation;
- output capacity reservation precedes print material allocation and retries are idempotent by request token;
- print reagent semantics resolve through `ManufacturingReagentHash` to concrete ResourceTypes before the existing Multi Reservation Stager / Allocator ABI2 commit;
- RUNNING printer stalls fault rather than moving the job backward into a wait state;
- `ASYNC_REQUEST_V1` LIVE_CURRENT services publish initial state/error before current request identity, and invalid accepted Transform Runtime/Material Feeder requests still publish matching identity plus fault instead of stranding callers;
- terminal async services publish result/status before their response token across diagnostics, pressure, Config/Policy, Recipe Lookup, Job Store, Printer capacity/execution, and directory handshakes;
- Mapping Editor rejects stale Controller Selector success, stale Console desired success, and a pending Console auto-advance until their exact handled tokens catch up;
- Material Transfer Executor ignores a stale Feeder fault until Feeder current token equals the active grant epoch, and Feeder request payload publication is token-last.

### Live manufacturing checks

1. Queue several TRANSFORM/PRINT jobs with mixed priorities and confirm the same deterministic ordering as the model.
2. Make the highest-priority processor/resource unavailable and confirm lower runnable jobs still progress while the blocked job waits/retries.
3. Change a Transform processor's Pressure/Temperature just outside each declared bound and confirm Admission refuses execution for every furnace class.
4. Fill a managed printer output slot and confirm the job enters `WAIT_CAPACITY` before material reservations commit.
5. Select a printer, physically replace that pinned printer before capacity reservation, and confirm the request fails closed on ReferenceId mismatch.
6. Reflash Scheduler, selector, driver, capacity client, and printer runtime at representative yields; confirm JobGeneration prevents stale duplicate lifecycle application.
7. Remove a Material Link/resource after recipe resolution but before allocation; confirm planning returns to the appropriate WAIT state rather than executing partially.

## Item storage reservation and movement hardening

Static and model tests require:

- `DirectorySchema.ResourceReservation` overflow to fail closed;
- split ITEM quotes to remain read-only and bounded to six physical legs;
- allocator commit to revalidate every quoted semantic Reservation generation before ownership mutation;
- owner ReferenceId + epoch, never epoch alone, to gate release and movement;
- source and destination capacity Reservations before LArRE pickup;
- exact pre-pick ItemHash/Quantity validation against proxy slot 255;
- manual source mutation to fail before pickup;
- post-pick obstruction to surface a held-item `-6` state and explicit recovery;
- persisted origin information to survive a same-housing movement-client restart;
- direct-slot scans to remain bounded/no-yield;
- SDB inventory to remain lower-bound precision and exact processor delivery to occur at the Stacker feeder boundary.

## Power-management evidence

`validation/validators/validate_power_management_contracts.py` protects PowerGrid structural/ABI invariants and `tests/test_power_management.py` exercises endpoint capacity, Reservation mirroring, source/sink/link selection, coherent power plans, load shedding/battery behavior, allocator authority, break-before-make execution, and POWER Job policy completion.


## Item 11 cross-domain process utility hardening

Automated model/direct-harness evidence proves ProcessCondition generation fencing, transform-bound P/T demand, PressureDomain/PressureTransfer projection, GrantGuard authority, two-component purity, temperature-corrected composition mixing, thermal mixing, GFG fuel demand/start/stop, and IC10 `bdnvs` writable-property semantics.

Live-game commissioning still must verify:

1. On Furnace and Advanced Furnace, compare `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10`'s P/T unmet bits and hints against live `Pressure`/`Temperature` and the selected transform's recipe window.
2. Confirm `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` + ordinary Inventory/Reservation makes the furnace chamber routable without bypassing pressure purity or overflow checks.
3. Confirm `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` inlet and outlet modes drive only the intended `SettingInput`/`SettingOutput`, safe-off on Grant withdrawal, and respect the Advanced Furnace's real pump limits.
4. With unequal source temperatures, compare `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10`'s computed Gas Mixer setting to the live output mole ratio; verify the mixer remains active until both target composition and demanded output pressure are visible.
5. Verify `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` treats an empty prepared-fuel buffer as import-admissible and rejects off-ratio H2/O2 after gas arrives.
6. Verify `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` reaches the requested temperature window and maintains demanded output pressure across drainage into a furnace.
7. Route a prepared conditioned buffer into an Advanced Furnace; confirm manufacturing remains in WAIT until `ic10/material-transform/material_transform_admission_v1_0.ic10` independently observes the recipe P/T window, then proceeds without any special scheduler override.
8. For the Gas Fuel Generator, verify the live surrounding-atmosphere limits, fuel-side `Pressure`, mixture ratios, error behavior, and safe shutdown when the coherent PowerPlan shortage clears.
9. Measure actual GFG watts versus input moles/temperature/mixture; do not infer an exact watt-to-pressure conversion until that characterization is recorded.
10. Reflash the Item-11 `ic10/process-furnace/`, `ic10/process-gas-preparation/`, and `ic10/process-gfg/` services at active/inactive boundaries and verify physical mixers, embedded pumps, and GFG converge to safe state before reacquiring current authority.
11. Mutate ProcessCondition/Profile/PowerPlan generation between observation and actuation and confirm final generation fences prevent stale writes.
12. If an Electrolyzer is later added, prove surplus-power charging and GFG discharge cannot recursively enable one another in the same planning epoch.
