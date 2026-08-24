# Pressure-Grid Route Cost Model

## Purpose

The multi-hop grid can have more than one physically valid `LOW -> ... -> HIGH` path for the same working medium. Earlier versions accepted the first usable path discovered by the bounded-depth search. That was safe, but route quality depended on discovery order.

The current grid adds a bounded cost-aware selection layer. Safety and resource feasibility remain hard constraints handled by Transfer candidates and Reservation Allocator. Cost is consulted only after a route is already physically valid.

The result is intentionally a **ranking score**, not a claim to calculate joules or thermodynamic work exactly.

## Components

Three services participate:

- `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` — enumerates usable 2/3-hop routes one candidate at a time;
- `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` — requests candidates and returns the best candidate examined;
- `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` — evaluates each candidate and retains the best route for one search;
- `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` — publishes human-tunable ranking weights and candidate budget.

`ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` now consumes the Route Selector rather than accepting discovery-order output directly.

## Default score

For a candidate path:

```text
Cost =
    HopWeight * HopCount
  + StorageWeight * IntermediateStorageCount
  + LiftWeight * SumPositivePressureLiftKPa
  + FlowScarcityWeight / BottleneckMolesPerTick
```

The defaults are:

```text
HopWeight             = 100
StorageWeight         = 25
LiftWeight             = 0.01 per kPa
FlowScarcityWeight    = 100
CandidateBudget       = 32 complete routes
```

Lower cost wins. If two candidates have exactly the same score, the higher bottleneck mol/tick route wins.

### Hop count

Each physical pump edge costs 100 points by default. This gives a strong preference for simpler topology and fewer simultaneously active devices.

A 2-hop route therefore starts with a lower structural cost than a 3-hop route.

### Storage count

For the currently supported routed forms, intermediate storage count is `HopCount - 1`:

```text
LOW -> STORAGE -> HIGH
2 hops, 1 intermediate storage node

LOW -> STORAGE A -> STORAGE B -> HIGH
3 hops, 2 intermediate storage nodes
```

Storage is useful, but unnecessary storage transit creates additional inventory dependencies and another place where a later plan may become constrained. The default score therefore gives it a modest penalty rather than forbidding it.

### Positive pressure lift

For each physical hop the Ranker reads the current pressure from the source and sink PressureDomain Inventory behind the endpoint Reservation services.

Only positive lift contributes:

```text
Lift = max(SinkPressure - SourcePressure, 0)
```

A pressure drop contributes zero lift cost.

This is an **operational pressure-lift penalty**, not a physical electrical-energy equation. The standard Stationeers Volume Pump currently consumes power as its liter setting multiplied by 20 W; its documented electrical demand is not pressure-lift dependent. The lift term therefore expresses preference for routes that demand less pressure elevation from the installed grid, especially as future compressor/storage infrastructure is added.

### Flow scarcity

The route's current bottleneck `PlannedMolesPerTick` contributes:

```text
FlowScarcityWeight / BottleneckMolesPerTick
```

A high-throughput path receives a smaller penalty. A low-throughput path can therefore lose to a slightly longer path when the longer path has substantially greater useful throughput or much lower pressure lift.

## Why the score is dimensionless

The current physical-link abstraction supports standard and Turbo Volume Pumps through their common `Setting`/`Maximum` interface. The framework does not yet have a trustworthy device-independent model for complete electrical work, compressor work, heat rejection, or energy recovered from a particular route.

Converting the current inputs into a number labeled watts or joules would therefore imply precision the model does not possess.

A dimensionless weighted score keeps the decision policy explicit and tunable while leaving room for a later real energy/cost model.

## Bounded candidate search

IC10 should not attempt an unbounded graph optimization over a dense 64-link topology.

The Route Selector therefore evaluates at most `CandidateBudget` complete routes for one selection. The default is 32 and the profile clamps the effective budget to the supported range 1..64.

The Path Enumerator maintains DFS state across request/response calls. The Route Selector asks for another complete path, passes it to the Ranker, and repeats until either:

- the Enumerator reports no more routes; or
- the candidate budget is reached.

The lowest-cost candidate examined is returned to Path Allocator.

This means selection is **bounded cost-aware search**, not a proof of the globally minimum-cost route in every possible 64-link graph. That limitation is deliberate and visible.

## Relationship to reservation safety

Cost never overrides reservation constraints.

A low-cost route still must:

- match the active medium;
- start at LOW and terminate at HIGH;
- use only currently valid Transfer candidates;
- obey the 2/3-hop bound;
- reserve every source export and sink import endpoint;
- normalize every hop to a common admitted mol/tick rate;
- remain inert until Planner commit.

Route Ranker ABI2 subtracts reservations already made in the current build before scoring, so exhausted routes are normally removed before selection. A last-moment resource/topology change between ranking and exact COMMIT can still make the selected route fail safely. The current Plan Builder does not immediately retry the next-ranked route in that same routed step; it continues to fallback planning. This is visible under-utilization, not unsafe admission.

## Search and staging interaction

Each Route Selector request creates a new search identity. This resets Enumerator traversal but preserves the Planner/build epoch.

Transfers already staged for the same Planner/build epoch are ignored by the Enumerator. Consequently, after one selected route is admitted, the next selection searches the remaining usable edge set.

This preserves the existing edge-disjoint routed-path behavior within a plan.

## Worked example

Suppose two routes connect one Pollutant LOW domain to one HIGH domain.

Route A:

```text
LOW -> STORAGE A -> HIGH
HopCount          = 2
StorageCount      = 1
Positive lift     = 20,000 kPa
Bottleneck rate   = 1 mol/tick
```

Default cost:

```text
2*100 + 1*25 + 20,000*0.01 + 100/1
= 525
```

Route B:

```text
LOW -> STORAGE B -> STORAGE C -> HIGH
HopCount          = 3
StorageCount      = 2
Positive lift     = 0 kPa
Bottleneck rate   = 10 mol/tick
```

Default cost:

```text
3*100 + 2*25 + 0 + 100/10
= 360
```

Despite the extra physical hop, Route B wins because Route A has severe lift and throughput penalties.

If pressure and throughput were equal, the 2-hop path would win because of its lower hop/storage cost.

## Cost Profile ABI v1

`ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` publishes:

```text
S0  magic = 31415945
S1  ABI = 1
S2  HopWeight
S3  StorageWeight
S4  LiftWeightPerKPa
S5  FlowScarcityWeight
S6  CandidateBudget
```

The initial profile is intentionally tiny. A human can clone it to create alternate operating policies such as:

- minimum-device-count routing;
- storage-averse routing;
- pressure-lift-averse routing;
- throughput-first routing.

Do not make weights negative. The Ranker rejects negative configured weights.

## Route Ranker ABI v2

Inputs:

```text
S2  SearchId
S3  PathLength
S4  BottleneckMolesPerTick
S5  Link0 ReferenceId
S6  Link1 ReferenceId
S7  Link2 ReferenceId when present
S8  RequestToken
```

Outputs/state:

```text
S9   status: 1 accepted, -1 invalid
S10  ResponseToken
S16..18 best link ReferenceIds
S19  BestPathLength
S20  BestBottleneckMolesPerTick
S21  BestCost
S22  ActiveSearchId
S23  CandidatesEvaluated
S24  CandidateBudget
```

A new `SearchId` clears the retained best route before scoring the first candidate.

## Route Selector ABI v2

Inputs retain the old path-request context:

```text
S2 Planner ReferenceId
S3 BuildEpoch
S4 MediumType
S5 LeaseTicks
S6 RequestToken
```

Outputs:

```text
S7  selected PathLength
S8  selected BottleneckMolesPerTick
S9  status: 1 route, 0 none, -1 fault
S10 ResponseToken
S11 selected Cost
S16..18 selected link ReferenceIds
```

This deliberately matches the fields Path Allocator already needs, with `S11` added for commissioning visibility.

## Commissioning

Before allowing a cost-selected plan to actuate pumps:

1. run with the normal grid actuation disabled or with pumps physically disabled;
2. verify Enumerator returns expected physical paths;
3. inspect Ranker `S19..S24` while several competing paths exist;
4. verify Selector `S11` changes when weights are changed;
5. set a very large HopWeight and confirm shorter routes dominate;
6. set a very large LiftWeight and confirm lower-lift routes dominate;
7. set a very large FlowScarcityWeight and confirm higher-throughput routes dominate;
8. restore the intended production profile;
9. verify Path Allocator still normalizes and reserves all selected hops before Planner commit.

## Current limitations and next step

The current score does not model:

- exact pump electrical energy for every pump type;
- compressor efficiency/work;
- latent heat moved by the working medium;
- heat-exchanger/source/sink thermal availability;
- wear or device duty-cycle balancing;
- arbitrary-length graph optimization;
- globally optimal min-cost flow across several simultaneous routes.

The next high-value improvement is therefore **energy/thermal-aware link metadata**, not simply increasing route depth. Once trustworthy per-link energy and thermal-capacity signals exist, the ranking profile can incorporate them without changing reservation safety.
