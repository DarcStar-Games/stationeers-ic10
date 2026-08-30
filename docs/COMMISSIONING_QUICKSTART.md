# Commissioning Quick Start

This file is the shortest human-oriented path from an empty deployment to a working controller/configuration/diagnostics setup. For every deployable family use `USER_DEPLOYMENT_GUIDE.md`; for exact stack-cell contracts use `docs/ABI_REFERENCE.md`; for the full dependency sequence use `docs/DEPLOYMENT.md`.

## Before you start

- Treat all scripts in this bundle as a fresh v1 deployment; there is no legacy migration path.
- Record ReferenceIds as you wire services together. Most cross-script dependencies are ReferenceIds stored in stack cells or device screws.
- A service advertising the expected magic but the wrong ABI must be treated as incompatible.
- When a step says “ready,” look for the documented positive status (`1` in most selector/bridge services) before continuing.

## PI configuration

### Minimum components

- Generic Persistent Config Host
- PI Config Policy
- PI Runtime
- Controller Directory + Controller Selector (64-controller discovery capacity; grouping is derived directly)
- Generic Config Editor + Loader + Committer
- Generic Input Scanner + Resolver + Config Input Bridge
- optional PI Input Profile for Dial/Switch-based editing

### Wiring and commissioning sequence

1. **Program Generic Persistent Config Host.** This is the durable configuration endpoint paired with the PI controller.
2. **Program PI Config Policy; connect Policy `d0` to Host.** Wait for Policy metadata/default publication so the Host knows type, schema, block masks, and signature.
3. **Program PI Runtime.** Connect Runtime `d2` to Host, `d0` to the process-input device, and `d1` to the actuator.
4. **Deploy discovery/selection.** Controller Directory publishes sorted telemetry controllers; Controller Selector derives type/member groups directly and resolves the PI instance you want to edit. Use `docs/CONTROLLER_DIRECTORY_GETTING_STARTED.md` to prove the directory publication path independently first.
5. **Program Generic Config Editor, Loader, and Committer.** Point their documented selector/editor dependencies at the shared services.
6. **Program Generic Input Scanner.** Attach Field Dial, Value Dial, optional Logic Memory, optional Switch, and optional PI Input Profile to its six screws.
7. **Program Generic Input Resolver and set Resolver `S2` to Scanner ReferenceId.**
8. **Program Config Input Bridge.** Set Bridge `S2` to Editor RefId and `S3` to Resolver RefId. Set Loader `S3` to Scanner RefId so Loader can discover/validate the controller Profile.
9. **Select the PI controller and load it into Editor.** Loader should derive the PI active field count and ordinal -> stable slot map from the Host masks.
10. **Edit fields.** Field Dial selects the logical field. Resolver chooses Value Dial/Switch/Memory according to the PI Profile and fallback rules. Save stages the resolved value.
11. **Apply.** Committer publishes the candidate to Host. Policy validates it. Host durably commits the inactive A/B bank.
12. **Confirm durable success.** Successful Apply is not considered complete until the Generic Host has finished the A/B commit and published success/effective generation.

### What success looks like

- Controller Selector reports a valid resolved controller.
- Editor reports staging ready after Loader completes.
- Resolver reports ready and publishes a changing snapshot generation as controls change.
- Host operational status is positive.
- Apply produces a successful transaction result (`5` for accepted PI config).
- Host effective generation/revision advances only after durable commit.
- PI telemetry reflects the new effective configuration.

### Common PI commissioning problems

| Symptom | First checks |
|---|---|
| No controller appears | Runtime telemetry magic/ABI, Directory RefId/generation, Selector ABI2, ControllerType hash. |
| Field Dial does not cover expected fields | Resolver logical count, Scanner `S9/S10`, Loader active-field count, validated Profile. |
| Value Dial ignored | Profile InputKind, Scanner capability bitmask, Resolver status, Memory fallback taking precedence because preferred input is missing. |
| Apply rejected | Host/Policy result code; for PI see error meanings in `docs/ABI_REFERENCE.md`. |
| Apply appears to work then reverts after restart | Check Host bank revisions/signature and whether Apply reached durable commit. |

## Input Profile Catalog prerequisite

The configuration and diagnostic Profile Views share the coordinated Input Profile catalog. Run `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` and `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` (`d0` -> Coordinator), add one `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` with a unique positive `S18 NodeId`, then deploy sparse Loader candidates `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` through `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10`. The Store advertises UNCLAIMED; the Coordinator claims it when the Router sees the pending Input Profile loaders. Wait for an ACTIVE Input Store with `S9=6` and stable even `S17`, then attach `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` to the Store/Coordinator and set `S2/S3`. PI uses `HASH("ControllerPI")/1`; diagnostics uses `HASH("DiagnosticMapping")/1`.

## Sequencer configuration

ControllerSequencer uses the same generic commissioning path as PI; only the family Runtime, Policy, and Profile change.

### Minimum components

- Generic Persistent Config Host
- `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10`
- `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10`
- Controller Directory + Controller Selector
- Generic Config Editor + Loader + Committer
- Generic Input Scanner + Resolver + Config Input Bridge
- optional `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`

### Runtime wiring

- Runtime `d0` -> process/input device
- Runtime `d1` -> fill/action-A actuator
- Runtime `d2` -> drain/action-B actuator
- Runtime `d3` -> paired Generic Host
- Policy `d0` -> the same Host

### First commissioning pass

1. Leave `Enabled=0` while wiring and staging the first config.
2. Set Input LogicType and the Low/High thresholds. Policy requires `Low < High`.
3. Set Fill and Drain LogicTypes to writable action properties supported by the two target devices. Common choices are `On`, `Open`, or `Activate`.
4. Set `SettleTicks` and `TimeoutTicks`. Timeout applies independently to FILL and DRAIN.
5. Choose `Repeat=0` for one shot or `Repeat=1` for continuous cycling.
6. Apply and confirm Host success/durable revision.
7. Enable the controller. Telemetry state should progress `0 (fill) -> 1 (settle) -> 2 (drain)`, then either return to `0` or enter `3 (complete)`.
8. If a phase cannot reach its threshold before TimeoutTicks, state becomes `4` and outputs are commanded off. Disable the controller to acknowledge/reset the terminal fault state.

See `docs/SEQUENCER_CONTROLLER.md` for exact fields, status codes, and telemetry.

## Phase-pressure configuration

ControllerPhasePressure uses the same Host/Policy/Profile/shared-input path as PI and Sequencer, plus one PHASE_MEDIUM Resource Profile View on the Runtime.

### Runtime wiring

- Runtime `d0` -> phase-change device / enclosed process device exposing `Pressure` and `Temperature`
- Runtime `d1` -> `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` configured with `S2=1` and `S3=HASH(<medium>)`; View anchored to any ACTIVE Resource Profile Store plus the Coordinator after the generated FLUID Resource Profile loader candidates have been placed/imported (`S9=9` on the FLUID Store and stable even `S17`)
- Runtime `d2` -> paired Generic Host
- Policy `d0` -> same Host

### First commissioning pass

1. Start in `Mode=HOLD` and choose a conservative `StandbyPressure` inside the configured Min/Max bounds.
2. Choose `OutputLogicType`. The supplied Profile offers `Setting` and `PressureSetting`. Verify the actual target device supports the selected property before enabling direct writes.
3. Keep the default `EvaporationFactor=0.95` and `CondensationFactor=1.05` initially; these place the request 5% below/above the phase boundary.
4. Set deployment-specific `MinimumPressure` and `MaximumPressure`. These are plant limits, not merely medium phase-curve limits.
5. Normally keep `DirectWrite=1` so PhasePressure owns the phase device's pressure setpoint even when the external buses are grid-managed. Use `DirectWrite=0` only for publish-only commissioning or when another explicit owner writes that same property.
6. Apply and confirm Host durable success.
7. Change Mode to EVAPORATE or CONDENSE only while telemetry temperature is within the selected PHASE_MEDIUM record's supported liquid window and status is non-negative.
8. Verify channel 3 (boundary) and channel 4 (request) move with temperature. For evaporation, request should be below the boundary; for condensation, above it, unless an operational clamp is active.

See `docs/PHASE_PRESSURE_CONTROLLER.md` and `docs/PHASE_MEDIUM_PROFILE.md` for the complete contract.

## Pressure-domain configuration

PressureDomain is the first shared infrastructure layer for phase-change devices. Commission LOW and HIGH domains first; runtime revision 1.1 also supports passive STORAGE domains for the transfer grid.

### Minimum components

- Generic Persistent Config Host + `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10`
- `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` for the shared config panel
- one PHASE_MEDIUM Resource Profile View matching the domain medium
- `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10`
- Controller Directory
- pressurizing and depressurizing pressure-setpoint devices
- optional Pipe Analyzer on the controlled domain
- at least one `ControllerPhasePressure` producer with valid telemetry; its chamber `DirectWrite` setting is independent of domain arbitration

### Runtime wiring

- Runtime `d0` -> Pipe Analyzer / readable `Pressure` device on the domain (optional observation)
- Runtime `d1` -> PHASE_MEDIUM Resource Profile View
- Runtime `d2` -> dedicated PhasePressure Request Arbiter
- Runtime `d3` -> pressurizing setpoint device
- Runtime `d4` -> depressurizing setpoint device
- Runtime `d5` -> paired Generic Host
- Arbiter `d0` -> Controller Directory

### First commissioning pass

1. Start with `DirectWrite=0` on PressureDomain. Confirm the family can arbitrate requests before it owns actuators.
2. Choose the correct PHASE_MEDIUM Resource Profile View selection and confirm telemetry channel 5 identifies the expected medium.
3. Choose exactly one role: `1=LOW/EVAP`, `2=HIGH/CONDENSE`, or `3=STORAGE`. Commission STORAGE separately because it bypasses the Arbiter.
4. Set `MinimumPressure`, `MaximumPressure`, and `StandbyPressure` to the safe limits of the actual local plant, not merely to the medium phase limits.
5. For LOW/HIGH, configure matching PhasePressure devices with the same medium and put at least one in the corresponding EVAPORATE/CONDENSE mode. Their chamber `DirectWrite` may remain 1.
6. Wait for a complete Arbiter directory pass. Telemetry channel 3 should become the number of valid matching request producers.
7. For LOW, verify channel 2 equals the lowest compatible PhasePressure request. For HIGH, verify it equals the highest.
8. Verify a wrong-medium, HOLD, faulted, or opposite-mode PhasePressure controller does not affect the target.
9. Wire the source/sink devices, verify their pressure-setting LogicTypes, power state, and physical direction. For the reference pair, use a Pressure Regulator into the domain and Back Pressure Regulator out of the domain.
10. Set PressureDomain `DirectWrite=1`. Confirm both setpoint devices receive the same safe target.
11. Deliberately request outside the domain's safe capability: LOW below Minimum or HIGH above Maximum. The target must clamp to the plant bound and status must become `-8`.
12. Remove all matching requests. The target must return to StandbyPressure.

See `docs/PRESSURE_DOMAIN_CONTROLLER.md` for scan latency, exact status meanings, Arbiter ABI, and topology assumptions.

## Pressure-grid transfer and routing configuration

After one LOW and one HIGH domain are behaving correctly, add Level 3.

### Minimum components

Global discovery:

- shared 64-controller Controller Directory published by a dedicated Generic Snapshot Directory Host
- one additional `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` for the Pressure Grid Link Directory, one `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` (`d1` -> Controller Directory Host), and one `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` (`d0` -> Pressure adapter, `d1` -> Pressure Link Host)

Per working medium:

- one `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10`
- one `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10`
- one `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10`
- one `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10`
- one `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10`
- one `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10`
- one `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10`
- one `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10`
- one `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10`

Per participating pressure domain:

- one `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10`
- one `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10`
- one `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10`
- one Pipe Analyzer on the represented gas network
- the matching PHASE_MEDIUM Resource Profile View

Per physical directed edge:

- one `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` + Host/Policy
- one `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10`
- a gas Volume Pump or Turbo Volume Pump physically oriented source -> sink

### Service wiring

```text
Controller Directory
    -> Grid Link Directory d0

Grid Link Directory
    -> Path Enumerator d0
    -> Single-Hop Builder d0
    -> Planner d0

Cost Profile -> Route Ranker d0
Path Enumerator -> Route Selector d0
Route Ranker -> Route Selector d1

Reservation Allocator
    -> Path Allocator d1
    -> Single-Hop Builder d1

Route Selector -> Path Allocator d0
Single-Hop Builder -> Plan Builder d0
Path Allocator -> Plan Builder d1
Plan Builder -> Planner d2
Resource Profile View -> Planner d1

Planner -> every same-medium Transfer Grant Guard d1
Transfer -> its Grant Guard d0
Grant Guard -> Transfer d3
```

Inventory/Reservation wiring remains one-per-domain:

```text
PressureDomain       -> Inventory d0
Pipe Analyzer         -> Inventory d1
Pipe Analyzer         -> Purity Guard d0
Resource Profile View -> Purity Guard d1
Purity Guard          -> Inventory d2
Inventory             -> Reservation d0
```

A Transfer wires `d0` to its source Reservation, `d1` to its sink Reservation, `d2` to the physical pump, `d3` to its Grant Guard, and `d4` to its Generic Host. The Grant Guard wires `d0` back to that Transfer and `d1` to the medium-specific Planner.

### First commissioning pass

1. Commission every Inventory/Reservation endpoint first. Require Inventory `S11=1`, matching medium identity, and plausible export/import moles.
2. Deploy the Grid Link Directory and wait until its active count reflects the expected PressureTransfer runtimes. Its topology generation should remain stable when the set of transfer endpoints has not changed.
3. Commission one direct LOW->HIGH link. Confirm Transfer `S101=1`, `S103=1` when capacity exists, and Planner ABI2 is accepted.
4. Confirm the Planner publishes `S7=max(64,4*N+16)` for `N` grid links, stages direct work first, and changes `S14` only after the Plan Builder completes.
5. Confirm endpoint Reservation ledgers are populated before Planner `S14` changes. After commit, the Transfer Grant Guard must publish `S4=1`, `S5` equal to the committed epoch, and decrement its `S3` remaining-lease counter; the Transfer pump should follow only that coherent Guard output.
6. Force current capacity below the active lease rate. The Transfer must throttle to the current `S100` ceiling or turn the pump off; the lease is never permission to ignore current evidence.
7. Add one STORAGE domain and two links `LOW->STORAGE` and `STORAGE->HIGH`. Confirm the Path Enumerator/Route Selector/Path Allocator can stage both as one 2-hop route when direct reuse is unavailable or insufficient. Both pumps should receive the same normalized staged mol/tick rate.
8. Add a second STORAGE domain and a physical `STORAGE A->STORAGE B` link. Confirm that link advertises route class `4` and is never granted by ordinary fallback, but can participate in `LOW->A->B->HIGH`.
9. During a routed path, inspect the intermediate STORAGE Reservation ledger: simultaneous reserved import/export is expected because it is transit. Repeat with only fallback opportunities and confirm the Single-Hop Builder keeps the anti-circulation direction check.
10. Add two disjoint multi-hop routes and confirm the Plan Builder can stage more than one path in the same build. Links already staged in the current epoch must not be reused by another path.
11. Create endpoint contention so one hop receives a lower allocator grant. Confirm the Path Allocator rewrites every staged hop to the minimum granted path rate before the Planner commits.
12. Make a later hop impossible after an earlier hop was staged. Confirm the Path Allocator invalidates earlier staged epochs/rates and the Planner does not activate the partial route.
13. Break a dependency during plan construction. Planner status should become negative, but `S14` must remain at the previous committed epoch. This is the critical partial-build safety check.
14. Verify mixed-medium links, liquid-bearing gas buses, invalid pump `Maximum`, and wrong role orientation remain rejected as before.

The automatic routed reuse limit is currently three physical links: `LOW->STORAGE->HIGH` or `LOW->STORAGE A->STORAGE B->HIGH`. With at least two competing routes, verify Route Selector `S11` and Route Ranker `S19..S24`; changing Cost Profile weights should change route preference without changing reservation safety. See `docs/PRESSURE_MULTI_HOP_ROUTING.md` and `docs/PRESSURE_ROUTE_COST_MODEL.md`.

## Diagnostics

### Minimum components

- Controller Directory + Controller Selector
- Console Registry + Console Selector
- Diagnostic Renderer + Mapping Editor
- Generic Input Scanner + Resolver
- Diagnostic Input Profile
- Diagnostic Input Bridge + Diagnostic Selector Bridge

### Wiring and commissioning sequence

1. Use a Scanner + Resolver pair with the Diagnostic Input Profile.
2. Point Diagnostic Input Bridge at Resolver/Profile.
3. Point Diagnostic Selector Bridge at Input Bridge + Controller/Console Selectors.
4. Point Mapping Editor `S7` at Diagnostic Input Bridge and wire its selector/renderer dependencies.
5. Use the Field Dial to choose Type, Member, Console, Channel, Mode, Color, or Commit.
6. Use Value Dial for numeric controls. Commit uses the Switch and triggers only on an OFF->ON edge.
7. Commit the mapping. Mapping Editor records the fully resolved mapping and asks Console Selector to advance exactly once.
8. Leave the Console control untouched to verify stale desired state does not roll the auto-advanced selection back.

### What success looks like

- Controller Selector and Console Selector both report valid identities.
- Diagnostic Input Bridge status is ready.
- Commit generation advances once per switch rising edge, not every tick while ON.
- Renderer contains a record `[displayRef, controllerRef, channel, Mode, Color]`.
- The committed display updates from the selected controller telemetry channel.
- Console selection advances once after commit.

## Sharing one physical panel

A single Scanner/Resolver pair should have one active domain bridge at a time. If you want configuration and diagnostics active simultaneously, use separate Scanner/Resolver pairs. If you reuse one physical panel, power only the desired domain bridge so two contexts do not compete over Resolver control count/Profile selection.

## Test controller family

ControllerTest is a **test-only** family. Its Runtime/Policy/Profile fixtures live under `tests/ic10/` and are not part of the production Input Profile Catalog; deploy them temporarily when isolating framework behavior.

Use:

- `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`
- `tests/ic10/framework_test_config_policy_v1_0.ic10`
- `tests/ic10/framework_test_controller_v1_0.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`

Test Policy `d1` is optional fault injection:

- approximately `1` rejects the next candidate with result `-90`;
- approximately `2` withholds the Policy response to exercise an in-flight/held transaction.

Use the test family when validating framework behavior before attaching the PI runtime to a real process.


### Hardening wiring additions

For every grid pressure domain, deploy `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10`: `d0` -> the same Pipe Analyzer used by Inventory, `d1` -> the domain's PHASE_MEDIUM Resource Profile View. Inventory `d2` -> that Purity Guard.

For every PressureTransfer, deploy `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10`: Guard `d0` -> that Transfer, Guard `d1` -> the medium-specific Grid Reservation Planner. Transfer `d3` -> its Guard (not directly to the Planner).


## Generic Resource / MaterialGrid smoke test

The Resource Core is optional for an existing PressureGrid installation. Use the first steps to validate the shared contracts, then continue into active material movement.

### A. Shared Resource Core

1. Wire `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10 d0` to a healthy PressureDomain Inventory ABI2. Confirm Generic Resource Endpoint class `FLUID`, unit `MOLE`, matching medium identity, and a positive publication generation.
2. Mirror it through `ic10/resource-grid-core/resource_reservation_v1_0.ic10` and confirm the Reservation contains the same class/type/unit and coherent export/import capacities.
3. Configure a Resource Profile View for an ITEM record (for example `S2=2`, `S3=1758427767` for Iron Ore), wire View `d0` to the shared Resource Profile Catalog Store, and wire the View to `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10 d1`; wire Inventory `d0` to a Vending Machine containing a known mixture of items.
4. Confirm the material Endpoint reports only the selected ItemHash quantity. Empty slots contribute one profile-sized stack of import capacity; occupied slots containing another ItemHash contribute neither selected quantity nor selected capacity.
5. Move an item while a full 100-slot scan is in progress. The Endpoint must discard that scan when `ImportCount` or `ExportCount` changes and publish only after a stable rescan.
6. Deploy `ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10`, a dedicated `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`, and `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` (`d0` -> Adapter, `d1` -> Host), then verify both the pressure adapter and material inventory appear in the Host's typed Endpoint snapshot. For generalized Links, deploy `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` with another Snapshot Host + Bridge.
7. If testing `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10`, point `d0` at an existing PressureTransfer and `d1/d2` at Generic Resource Reservations that ultimately reference its native source/sink inventories. Repoint either generalized Reservation to a different endpoint and confirm the Link adapter refuses publication rather than silently changing topology identity.

### B. Exact material route

Build one observable input leg:

```text
Vending -> Stacker -> Logic Sorter -> processor/import sink
```

1. Deploy `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` on those three physical devices.
2. Publish source and sink Generic Resource Reservations for the same ItemHash. For a furnace sink, use `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` plus `ic10/resource-grid-core/resource_reservation_v1_0.ic10`.
3. Deploy `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10`, `ic10/material-grid/material_transfer_executor_v1_0.ic10`, and `ic10/material-grid/material_resource_link_v1_0.ic10` using `docs/MATERIAL_TRANSFER_SYSTEM.md`.
4. Publish the Link through `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` -> `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` -> a dedicated `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`.
5. Confirm the Host reports magic `31415981`, ABI1, schema `DirectorySchema.ResourceLink`, schema version 1, and no overflow.
6. Confirm Link `S2/S3` are the **source/sink Reservation ReferenceIds** and Link `S19..S22` identify Vending, Stacker, Logic Sorter, and sink native device separately.
7. Manually verify the Sorter's accepted chute route reaches the intended sink.

The route is transaction-authorized by `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`; there is no standalone legacy material allocator in the current baseline.

### C. Furnace transform smoke test

1. Ensure Coordinator Core/Router are running, provide Generic Store capacity, and deploy the generated Resource Transform loader candidates. Wait for the 17 Transform items to reside in ACTIVE Store capacity.
2. Deploy `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` and select a TransformType. Require View ABI4, a matching S68 request echo with S69 status 1, and a positive S74 publication generation.
3. Provide a healthy output Resource Reservation with capacity for the declared output.
4. Deploy/wire the current path:

```text
161 Admission:      d0 Transform View, d1 Processor, d2 Output Reservation
162 Link Resolver:  d0 Admission, d1 Transform View, d2 Resource Link directory
163 Stager:         d0 Link Resolver, d1 Multi Allocator
164 Allocator ABI2: d0 Link Resolver, d1 Stager
165 Runtime:        d0 Processor, d1 Admission, d2 Link Resolver,
                    d3 Multi Allocator, d4 Output Reservation
```

5. Wire every Material Grant Guard `d1` to the same Allocator ABI2 used by the Runtime.
6. Request one batch by incrementing Runtime request generation with a positive batch count.
7. Confirm Allocator `S14` remains zero while staging and becomes one positive common epoch only after every input stages successfully.
8. Confirm every required Material Link completes that same epoch before the processor activates.
9. Confirm Runtime completes only after a newer coherent output Reservation snapshot grows by the declared output quantity.
10. Force the final input of a multi-input job to lack quantity/capacity and confirm earlier provisional reservations roll back with no `S14` commit.
11. Repoint a staged Link/topology identity and confirm the Grant Guard consumes/rejects the epoch.
12. Jam one physical route and confirm Executor/Runtime fault rather than reporting false completion.

Capability smoke checks:

- a basic `Smelt*` transform should admit on Arc Furnace, Furnace, and Advanced Furnace only while its declared pressure/temperature bounds are satisfied;
- a two-input base alloy should reject Arc Furnace and admit Furnace/Advanced Furnace;
- a three-input advanced alloy should admit only Advanced Furnace.
