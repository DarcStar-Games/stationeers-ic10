# Pressure Grid Transfer and Routing Layer

The pressure grid is Level 3 of the phase-change architecture. It does not decide what phase a device should enter and it does not decide the safe target pressure of a local bus. Its job is to move a working medium between already-defined pressure domains using real installed pump links.

The current grid supports:

- 64 shared controller-discovery entries;
- a separate stable directory of up to 64 physical pressure-transfer links;
- gas inventory/capacity accounting in moles;
- shared endpoint reservations;
- parallel direct transfers;
- automatic two-hop and three-hop LOW-to-HIGH reuse through STORAGE domains;
- direct-reuse priority before routed reuse, and routed reuse before storage fallback;
- staged plan construction with one final commit epoch;
- runtime throttling below a lease when live capacity shrinks.

The current automatic routed path limit is:

```text
LOW -> STORAGE -> HIGH
LOW -> STORAGE A -> STORAGE B -> HIGH
```

Direct `LOW -> HIGH` remains a one-link fast path.

## Architectural position

```text
ControllerPhasePressure
  derives thermodynamic pressure requirement
             |
             v
PhasePressure Request Arbiter
  reduces same-medium device requirements
             |
             v
ControllerPressureDomain
  owns LOW/HIGH target or STORAGE bounds
             |
             v
PressureDomain Inventory
  converts physical gas state to molar capacity
             |
             v
PressureInventory Reservation
  mutable endpoint reservation ledger
             |
             +-----------------------------------+
             |                                   |
             v                                   v
ControllerPressureTransfer                 Grid scheduling services
  one physical pump edge                    topology/path/reservation
             |                                   |
             +----------------+------------------+
                              v
                     committed plan epoch
                              |
                              v
                     one or many active pumps
```

The boundaries are deliberate:

- **PhasePressure** answers “what pressure does phase change require?”
- **PressureDomain** answers “what pressure should this bus safely maintain?”
- **Inventory** answers “how many moles can this domain export or accept?”
- **Transfer** answers “what can this physical pump edge move right now?”
- **routing/scheduling** answers “which real edges should operate together?”

## Current files

Controller family:

- `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10`
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` — select `S8=HASH("ControllerPressureTransfer")`, `S9=1` from the shared Input Profile Catalog
- `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10`

Inventory/reservation:

- `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10`
- `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10`
- `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10`

Topology/routing/build services:

- `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10`
- `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10`
- `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10`
- `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10`
- `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10`
- `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10`
- `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10`
- `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10`
- `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10`

See `docs/PRESSURE_MULTI_HOP_ROUTING.md` for route enumeration/reservation, `docs/PRESSURE_ROUTE_COST_MODEL.md` for route ranking, and `docs/PRESSURE_RESERVATION_MODEL.md` for endpoint accounting/commit semantics.

## Why one Transfer still equals one physical edge

A `ControllerPressureTransfer` is not an abstract path. It represents one actual directed gas pump installation:

```text
source gas network
      |
      v
Volume Pump / Turbo Volume Pump
      |
      v
sink gas network
```

This keeps topology grounded in what physically exists. The router may compose several Transfer controllers into a path, but it cannot invent a connection.

The pump direction must agree with the Transfer wiring. `d0` is always source and `d1` is always sink.

## PressureDomain roles

### LOW — role 1

A LOW domain is the external pressure environment used to accept vapor from evaporation-side devices. It can export grid inventory when its actual gas inventory is above the amount required by its current target pressure.

Inventory publication:

```text
ExportableMoles > 0
ImportCapacityMoles = 0
```

LOW can be the source of:

```text
LOW -> HIGH
LOW -> STORAGE
```

### HIGH — role 2

A HIGH domain is the external pressure environment that supplies condensation-side devices. It can accept grid inventory while its gas inventory is below the amount required by its current target pressure.

Inventory publication:

```text
ExportableMoles = 0
ImportCapacityMoles > 0
```

HIGH is a terminal sink in the current routed-reuse model.

### STORAGE — role 3

A STORAGE domain is a passive medium-specific gas reservoir. Its PressureDomain configuration interprets:

```text
MinimumPressure = export reserve floor
MaximumPressure = import ceiling
```

Inventory can therefore expose both:

```text
ExportableMoles
ImportCapacityMoles
```

A STORAGE node can be:

- a fallback sink for LOW excess;
- a fallback source for HIGH demand;
- an intermediate vertex in a complete LOW-to-HIGH route.

## Transfer route classes

PressureTransfer v2.0 publishes four topology classes at `S101`:

| Route | Source | Sink | Meaning |
|---:|---|---|---|
| 1 | LOW | HIGH | Direct phase-cycle reuse |
| 2 | LOW | STORAGE | Buffer or first routed hop |
| 3 | STORAGE | HIGH | Restore or final routed hop |
| 4 | STORAGE | STORAGE | Intermediate routed hop only |

Route 4 is never admitted by the ordinary fallback builder. It only becomes executable after the Path Allocator has admitted a complete routed path.

## Inventory-aware candidate calculation

A Transfer consumes two `PressureInventory Reservation` endpoints. Each Reservation mirrors the corresponding Inventory state and owns mutable reservation counters.

The Transfer first calculates:

```text
UsefulTransferMoles = min(
    Source.ExportableMoles,
    Sink.ImportCapacityMoles
)
```

It converts that into a source-equivalent pressure gap using:

```text
EquivalentGapKPa = UsefulTransferMoles / Source.MolesPerKPa
```

Then the configured tuning remains familiar:

```text
PlannedFlowLPerTick = min(
    (EquivalentGapKPa - DeadbandKPa) * GainLPerKPa,
    ConfiguredMaximumFlowLPerTick,
    Pump.Maximum
)
```

Finally:

```text
PlannedMolesPerTick =
    PlannedFlowLPerTick * Source.MolesPerLiter
```

`S100` publishes `PlannedMolesPerTick` when `S103=1`.

The volume-pump equation follows current Stationeers behavior: moles moved by a volume setting depend on source pressure and temperature, not merely liters/tick.

## Transfer configuration schema

The four-field durable config schema remains unchanged:

| Ordinal | Field | Default | Validation |
|---:|---|---:|---|
| 1 | `Enabled` | 1 | normalized to 0/1 |
| 2 | `DeadbandKPa` | 5 | 0..500 |
| 3 | `GainLPerKPa` | 0.05 | >0..1 |
| 4 | `MaximumFlowLPerTick` | 10 | >0..100 |

Persistence signature:

```text
CFG1|ControllerPressureTransfer|1|1|15|0|0|0
```

## Transfer wiring

`ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10`:

| Screw | Device | Purpose |
|---|---|---|
| `d0` | source PressureInventory Reservation | export capacity + source ledger |
| `d1` | sink PressureInventory Reservation | import capacity + sink ledger |
| `d2` | gas Volume Pump / Turbo Volume Pump | physical directed actuator |
| `d3` | Pressure Transfer Grant Guard ABI1 | topology-bound active lease authority |
| `d4` | paired Generic Persistent Config Host | tuning/config |
| `d5` | unused | reserved |

The runtime validates the pump's `Maximum`, `Setting`, and `On` surfaces before active use.

## Transfer telemetry ABI v2

Generic telemetry header:

```text
S96  magic = 27182818
S97  telemetry ABI = 2
S98  channel mask = 30
S99  ControllerType = HASH("ControllerPressureTransfer")
```

Grid/public fields:

```text
S100 PlannedMolesPerTick     meaningful when S103=1
S101 RouteClass              1..4
S102 MediumType
S103 CandidateStatus         1 valid candidate, 0 inactive/no capacity, -1 fault
S106 SourceReservationRef
S107 SinkReservationRef
S115 TelemetryGeneration       written LAST
```

Allocator-owned staged fields:

```text
S108 StagedGrantMolesPerTick
S109 StagedEpoch             written after staged payload
S110 StagedPlannerRef
S111 StagedLeaseTicks
S117 StagedSourceReservationRef
S118 StagedSinkReservationRef
S119 StagedMediumType
S120 StagedRouteKind
```

The Transfer runtime does not own lease lifecycle state anymore. `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` validates the staged topology against one coherent Transfer ABI2 snapshot, requires Planner commit, tracks remaining lease ticks, and publishes the active grant to Transfer `d3`. The physical runtime consumes only that coherent Guard output and re-caps it by current local capacity.

## Grid Link Directory

The shared Controller Directory can contain PI, Sequencer, PhasePressure, PressureDomain, PressureTransfer, and future families. Route search does not need to repeatedly filter all of them.

`ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` derives a transfer-only topology index:

```text
Controller Directory ABI2
        |
        v
Grid Link Directory ABI1
```

It supports 64 transfer records and uses two coherent banks:

```text
A = S32..223
B = S224..415
record = [TransferRef, SourceReservationRef, SinkReservationRef]
```

A significant behavior change from the general Directory is that an identical topology rebuild does **not** advance the Link Directory generation. That stable generation is useful for route search.

## Scheduling hierarchy

Per working medium, one plan is built in this order:

```text
DIRECT
  all eligible LOW -> HIGH links

ROUTED REUSE
  LOW -> STORAGE -> HIGH
  LOW -> STORAGE -> STORAGE -> HIGH
  repeat until no additional path is found

FALLBACK
  LOW -> STORAGE
  STORAGE -> HIGH
```

This ordering has resource-policy meaning. Direct reuse is the cheapest/least buffered topology and gets first reservation rights. Routed reuse then tries to satisfy remaining LOW/HIGH opportunities before storage-only fallback consumes the remaining capacity.

## Single-Hop Builder

`ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` scans the Grid Link Directory and serially asks the Reservation Allocator to stage links.

Request modes:

```text
2 direct: route 1 only
1 fallback: routes 2 and 3 only
```

Fallback also keeps a STORAGE anti-circulation guard:

- do not add LOW->STORAGE import if that storage already has reserved export;
- do not add STORAGE->HIGH export if that storage already has reserved import.

That guard intentionally does not apply to a complete routed path, where simultaneous import/export is expected transit behavior.

## Multi-hop path discovery

`ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` enumerates currently usable routes of length two or three, one complete candidate per request.

Supported forms:

```text
LOW -> STORAGE -> HIGH
LOW -> STORAGE A -> STORAGE B -> HIGH
```

The Path Enumerator requires the correct medium and valid current Transfer candidate status. It also ignores any link already staged by the same Planner/build epoch, which makes the set of routed paths edge-disjoint within one plan.

Multiple paths may still share endpoint domains if molar reservation capacity remains.

## Path reservation and rate normalization

The Path Allocator asks the endpoint Reservation Allocator to reserve every hop in sequence.

Because earlier direct paths or earlier multi-hop paths may already own endpoint capacity, individual hop grants can differ from the selected route's initial proposal.

The final route rate is therefore:

```text
PathRate = min(granted hop rates)
```

Every staged Transfer in that path is rewritten to `PathRate` before the path is reported complete.

Path allocation now QUOTEs every hop before mutating anything. If any quote fails, the candidate consumes no endpoint reservation. Once every hop is admissible, every hop is exact-COMMITted at one common route rate. An unexpected COMMIT-stage failure still leaves the new Planner epoch uncommitted and invalidates already-staged hop grants.

## Endpoint reservation invariant

For one build epoch and Planner owner:

```text
ReservedExportMoles <= ExportableMoles
ReservedImportMoles <= ImportCapacityMoles
```

The allocator calculates a lease rate from remaining capacity:

```text
GrantRate = min(
    Transfer.PlannedMolesPerTick,
    RequestedMaximumRate,
    RemainingSourceMoles / LeaseTicks,
    RemainingSinkMoles / LeaseTicks
)
```

Then:

```text
ReservedMoles = GrantRate * LeaseTicks
```

and writes those endpoint counters before staging the Transfer epoch.

## Plan Builder and Planner commit barrier

`ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` orchestrates the direct/path/fallback stages and returns a staged-plan summary.

It is intentionally **not** the activation authority.

`ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` is the only plan commit authority. It publishes:

```text
S0   magic = PressureGridReservationPlanner.v2
S1   ABI = 2
S11  LeaseTicks
S8   staged physical-link count
S9   reserved end-to-end moles summary
S10  status
S12  MediumType
S13  persistent build epoch
S14  committed epoch; written LAST
S15  Plan-Builder request generation
```

The commit sequence is:

```text
all endpoint reservations
all staged link grants
all multi-hop normalization
all fallback staging
plan summary
Planner S14 = build epoch   <-- last
```

A Planner fault does not write `S14`.

That means partial build state can exist without becoming executable.

## Lease duration

The current Planner uses:

```text
LeaseTicks = max(64, 4 * GridLinkCount + 16)
```

At 64 physical transfer links:

```text
LeaseTicks = 272
```

This remains a conservative bridge between planning work and execution. It is not a claim that route discovery always completes inside the lease window. If a very dense topology makes route search slower, active leases can expire and pumps can pause safely until the next commit.

Longer path-search-aware lease design is intentionally deferred because making the lease arbitrarily long also lowers the rate permitted by finite endpoint inventory.

## Runtime revalidation

A committed lease is an upper bound.

Every active Transfer recomputes current physical capacity from its source/sink Reservation mirrors and pump `Maximum`.

Execution uses:

```text
ActualCommandMolesPerTick = min(
    ActiveGrantMolesPerTick,
    CurrentPlannedMolesPerTick
)
```

If current capacity reaches zero, the pump turns off even if lease ticks remain.

This protects the system when pressure, temperature, or inventory changes faster than planning.

## Worked routed example

Suppose Pollutant has no direct LOW->HIGH physical pump, but these links exist:

```text
LOW -> STORAGE A      candidate 8 mol/tick
A   -> STORAGE B      candidate 6 mol/tick
B   -> HIGH           candidate 7 mol/tick
```

The Route Selector proposes:

```text
min(8,6,7) = 6 mol/tick
```

Path Allocator instead QUOTEs the three hops. If the current admissible quotes are:

```text
hop 1 = 6
hop 2 = 5
hop 3 = 6
```

then it selects:

```text
PathRate = 5 mol/tick
```

and exact-COMMITs **all three hops at 5 mol/tick**. The endpoint ledgers therefore reserve the same rate the path is staged to execute.

After the full plan is built, Planner `S14` changes. Only then may all three pumps load the route lease.

## Interaction with PhasePressure DirectWrite

The pressure grid moves working medium between external pressure domains. It normally does not replace the pressure setting on the actual phase-change chamber.

Typical ownership remains:

```text
ControllerPhasePressure.DirectWrite = 1
    owns phase-device pressure Setting

PressureGrid
    owns external medium movement among LOW/HIGH/STORAGE buses
```

`ControllerPhasePressure.DirectWrite=0` remains a publish-only/alternate-owner mode, not a required grid setting.

## What the grid can now do

The current system can:

- reuse vapor directly from LOW to HIGH;
- route vapor through one or two STORAGE buses when a direct edge is absent;
- buffer excess LOW material;
- restore HIGH from storage;
- run several direct/routed physical links concurrently;
- share one source or sink without exceeding molar reservations;
- keep physical pump ownership local to each Transfer runtime;
- recover safely from uncommitted partial builds through fresh build epochs.

## Deliberate limits

### Gas-only inventory model

A PressureDomain Inventory rejects positive `VolumeOfLiquid`. Two-phase transport requires a different resource model.

### Maximum automatic routed depth

Routed reuse is currently capped at three physical links/two intermediate STORAGE domains.

This bound keeps route discovery and path state feasible inside IC10's register/line constraints. It already covers a useful district-grid form:

```text
local LOW -> local storage -> backbone storage -> HIGH district
```

### Multi-hop starts at LOW and ends at HIGH

Automatic path search currently targets phase-cycle reuse. Multi-hop STORAGE-root restore and remote-storage-only buffering remain future extensions.

### Exact path admission and last-moment races

The previous reserve-first/normalize-later over-reservation has been removed. Path Allocator now QUOTEs every hop and exact-COMMITs one common path rate. A last-moment change between QUOTE/ranking and COMMIT can still cause admission to fail safely; the current Plan Builder then abandons routed reuse for that iteration rather than immediately retrying the next-ranked path. This is an optimization limitation, not a reservation-safety violation.

### Bounded cost-aware route quality

Routed reuse is now ranked rather than accepted in raw discovery order. The Path Enumerator supplies complete candidates, the Route Ranker scores them, and the Route Selector chooses the lowest-cost candidate among up to the configured budget (32 by default).

The default score considers hop count, intermediate STORAGE count, positive pressure lift, and bottleneck mol/tick. It is deliberately dimensionless; it is not presented as electrical energy.

See `docs/PRESSURE_ROUTE_COST_MODEL.md` for exact fields and tuning.

### No arbitrary graph-cost optimizer

There is still no Dijkstra/A*/min-cost-flow solver in IC10. Path depth remains bounded to 2/3 links, and route ranking examines a bounded candidate set. This keeps planning cost predictable enough for IC10 while improving route quality materially.

## Recommended next evolution

Add **energy/thermal-aware link metadata**: trustworthy pump/compressor electrical work, thermal source/sink capacity, and latent-energy opportunity. Those signals can extend the existing Cost Profile/Ranker without changing reservation safety. Longer arbitrary paths should still wait for evidence that real world layouts require them.


## Process-utility reuse

Item 11 reuses PressureGrid as the gas-movement authority for process conditioning. `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` publishes the existing ControllerPressureDomain ABI2 from a coherent ProcessCondition, and `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` publishes the existing ControllerPressureTransfer ABI2 for an Advanced Furnace embedded inlet/outlet pump. Existing Inventory, Reservation, directory, route selection, Planner epoch, and GrantGuard logic therefore remain unchanged.

Prepared mixtures such as `Fuel.H2O2` are ordinary FLUID Resource Profiles once composition is valid. `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` deliberately publishes the same PurityGuard ABI consumed by Pressure Inventory. Mixing itself is type-changing and stays outside Resource Link semantics. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.
