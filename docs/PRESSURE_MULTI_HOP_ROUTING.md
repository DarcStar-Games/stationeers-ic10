# Pressure-Grid Multi-Hop Routing

This document describes the first automatic multi-hop routing layer in the pressure grid. It extends the existing molar-inventory/reservation system without changing the device-level phase controller or the local PressureDomain abstraction.

The purpose of the routing layer is simple:

> If a LOW domain and a HIGH domain cannot exchange working medium through one physical pump edge, find a short path through one or two STORAGE domains, reserve the complete path coherently, and activate all of its pumps under one committed plan epoch.

The current implementation supports up to **three physical transfer links** in one routed path:

```text
LOW -> STORAGE -> HIGH

LOW -> STORAGE A -> STORAGE B -> HIGH
```

Direct `LOW -> HIGH` remains the preferred fast path and is scheduled before multi-hop discovery.

## Why STORAGE -> STORAGE is now a valid edge

The earlier single-hop grid rejected `STORAGE -> STORAGE` because there was no route context: a pump between two storage networks could otherwise move medium without proving that the movement helped satisfy a phase-cycle demand.

Multi-hop routing supplies that missing context. A storage-to-storage link is now legal **only as a member of a complete LOW-to-HIGH routed path**. Ordinary fallback scheduling still admits only:

```text
LOW -> STORAGE
STORAGE -> HIGH
```

and explicitly skips opposing storage-direction fallback reservations.

This preserves the anti-circulation behavior of the old scheduler while allowing storage buses to become real graph vertices.

## Scheduling order

One medium-specific plan is built in three stages:

```text
1. DIRECT REUSE
   LOW -> HIGH

2. MULTI-HOP REUSE
   LOW -> STORAGE -> HIGH
   LOW -> STORAGE -> STORAGE -> HIGH

3. FALLBACK
   LOW -> STORAGE
   STORAGE -> HIGH
```

Direct phase-cycle reuse therefore gets first claim on export/import inventory. Multi-hop paths use the capacity left after direct reuse. Storage buffering/restoration receives whatever capacity remains after both reuse stages.

The top-level Planner commits the whole staged plan only after all three stages finish.

## Service decomposition

Multi-hop routing is intentionally split across small ICs because IC10 has a 128-line hard limit and the framework retains a 120-line maintainability ceiling.

### Grid Link Directory

`ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10`

Wiring:

```text
d1 -> Generic Snapshot Controller Directory (`DirectorySchema.Controller`)
```

The system-wide Controller directory still discovers all controller families through the generic Snapshot Host. The Pressure Grid Link adapter derives a transfer-only topology candidate set from that schema-qualified snapshot, and the generic bridge commits it into another Snapshot Host.

Published Generic Snapshot Directory contract:

```text
S0/S1   31415981 / ABI1
S9/S10  HASH("DirectorySchema.PressureGridLink") / 1
S11/S12 entry width 3 / capacity 64
S2      active bank
S3/S4   generation A/B
S5/S6   count A/B
S7/S8   overflow A/B

bank A = S32..223
bank B = S224..415
```

Each record is:

```text
[PressureTransfer ReferenceId,
 Source Reservation ReferenceId,
 Sink Reservation ReferenceId]
```

There are up to 64 records per bank.

The generic bridge commits a new bank only when the transfer topology actually changes. An unchanged rebuild leaves the active generation alone. This gives the pathfinder a comparatively stable graph view instead of treating unrelated controller-directory refreshes as topology changes.

## Path Enumerator and cost-aware selection

`ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` is now a resumable candidate enumerator rather than a first-match Pathfinder. It keeps bounded-depth DFS state across request/response calls and yields one currently usable LOW-to-HIGH route at a time.

Enumerator wiring:

```text
d0 -> Grid Link Directory
```

Enumerator request surface:

```text
S2  Planner ReferenceId
S3  reservation build epoch
S4  MediumType
S5  SearchId
S6  request generation; written last
```

Response surface:

```text
S7   path length: 2 or 3; 0 when enumeration is exhausted
S8   bottleneck candidate mol/tick
S9   status: 1 candidate, 0 none, -1 dependency/topology fault
S10  response generation; written last
S16  hop 1 PressureTransfer ReferenceId
S17  hop 2 PressureTransfer ReferenceId
S18  hop 3 PressureTransfer ReferenceId when length=3
```

`ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` drives the Enumerator, passes each complete candidate to `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10`, and returns the lowest-cost candidate examined. `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` supplies the weights and candidate budget.

The default score is:

```text
Cost = 100 * HopCount
     + 25 * IntermediateStorageCount
     + 0.01 * SumPositivePressureLiftKPa
     + 100 / BottleneckMolesPerTick
```

The default search budget is 32 complete candidate paths. Search stops when the Enumerator is exhausted or that budget is reached. This is bounded cost-aware selection, not an unbounded proof of global minimum cost in every possible 64-link graph.

See `docs/PRESSURE_ROUTE_COST_MODEL.md` for the scoring ABI, rationale, tuning, and commissioning procedure.

## Path Allocator

`ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10`

Wiring:

```text
d0 -> Route Selector
d1 -> Pressure Reservation Allocator ABI3
```

The Path Allocator asks the Route Selector for one ranked route, then uses the shared endpoint Reservation Allocator ABI3 in two phases.

First it **QUOTEs** every hop. QUOTE observes current remaining endpoint reservations but mutates neither endpoint counters nor Transfer staged-grant state. The allocator returns the mol/tick that each hop could admit now.

The path then chooses:

```text
PathRate = min(all quoted hop rates)
```

Only after every hop has a positive quote does Path Allocator **COMMIT** every hop at exactly `PathRate`. Endpoint ledgers and staged grants therefore agree with the final common route rate; there is no intentional reserve-first/normalize-later leakage.

### Partial-path failure

A failed QUOTE consumes no endpoint capacity and stages no grant. If an unexpected COMMIT-stage failure occurs after earlier hops have committed, Path Allocator invalidates those already-staged grant epochs and the top-level Planner leaves its previous committed epoch unchanged. The partial new build therefore cannot actuate pumps; a later fresh build epoch resets stale endpoint counters when those ledgers are touched.

## Single-Hop Builder

`ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10`

Wiring:

```text
d0 -> Grid Link Directory
d1 -> Pressure Reservation Allocator ABI3
```

The same service performs either direct or fallback sweeps depending on its request mode.

Modes:

```text
2 = direct LOW -> HIGH only
1 = fallback LOW -> STORAGE / STORAGE -> HIGH only
```

Mode 1 preserves storage anti-circulation behavior. A LOW-to-STORAGE fallback is skipped when that STORAGE already has reserved export in the build; a STORAGE-to-HIGH fallback is skipped when that STORAGE already has reserved import.

`STORAGE -> STORAGE` is never admitted by the Single-Hop Builder.

## Plan Builder

`ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10`

Wiring:

```text
d0 -> Single-Hop Builder
d1 -> Path Allocator
```

The Plan Builder orchestrates one complete staged plan:

```text
direct sweep
    -> path allocation until no more route exists
        -> fallback sweep
            -> return staged-plan summary
```

It is not the activation authority. It cannot make pumps execute merely by finishing.

## Reservation Planner ABI2

`ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10`

Wiring:

```text
d0 -> Grid Link Directory
d1 -> matching PHASE_MEDIUM Resource Profile View
d2 -> Grid Plan Builder
```

The Planner is now deliberately small because its responsibility is transaction ownership rather than route search.

Planner ABI:

```text
S0   magic = 31415937
S1   ABI = 2
S7   LeaseTicks = max(64, 4 * linkCount + 16)
S8   number of staged physical links in the committed plan
S9   summary reserved end-to-end moles
S10  plan status: 1 grants exist, 0 none, negative dependency/build fault
S12  MediumType
S13  persistent build epoch counter
S14  committed plan epoch; WRITTEN LAST
S15  persistent Plan-Builder request generation
```

A failed build **does not write S14**. This is a stronger rule than the earlier scheduler implementation: dependency or construction failures can leave staged data in services, but without the commit token none of it can become an active lease.

## PressureTransfer v2.0 and Grant Guard

`ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` publishes transactional telemetry ABI2 and owns exactly one real pump. Transfer topology contains four route classes:

```text
1  LOW -> HIGH
2  LOW -> STORAGE
3  STORAGE -> HIGH
4  STORAGE -> STORAGE
```

Route 4 is only admitted by path-mode reservation.

Allocator ABI3 stages grant payload and topology identity on the Transfer:

```text
S108 staged GrantMolesPerTick
S109 staged epoch; written after staged payload
S110 staged Planner ReferenceId
S111 staged LeaseTicks
S117 staged source Reservation RefId
S118 staged sink Reservation RefId
S119 staged MediumType
S120 staged RouteKind
```

`ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` owns activation/lease lifecycle. It validates a coherent current Transfer telemetry snapshot, requires the staged topology to match current source/sink/medium/route, requires Planner commit, and consumes each committed epoch at most once. It publishes active grant rate and remaining ticks to the Transfer runtime. The Transfer still recomputes current physical capacity every tick, so a lease is an upper bound rather than permission to ignore newer endpoint conditions.

## Atomicity model

A multi-hop route is not activated hop-by-hop.

The ordering is:

```text
1. QUOTE hop 1 without mutation
2. QUOTE hop 2 without mutation
3. optionally QUOTE hop 3 without mutation
4. choose PathRate = minimum quoted rate
5. exact-COMMIT every hop at PathRate; stage topology + epoch
6. continue building other paths/fallback work
7. Plan Builder reports complete
8. Planner publishes summary
9. Planner writes S14 commit epoch LAST
10. matching Grant Guards activate the new epoch at most once
```

Only the Planner commit in step 9 makes staged grants eligible; the Grant Guard then performs the topology/identity check before exposing an active lease to the Transfer runtime.

If power loss/reflash interrupts steps 1-9, the new path remains inert. A restarted Planner increments the persistent build epoch before beginning again, so old endpoint reservations are lazily discarded when the new epoch touches those ledgers.

## Example: two-hop recirculation

Topology:

```text
Pollutant LOW
   |
   | Transfer A
   v
Pollutant STORAGE
   |
   | Transfer B
   v
Pollutant HIGH
```

Assume current candidate rates are:

```text
A = 7 mol/tick
B = 4 mol/tick
```

The path proposal is 4 mol/tick. If endpoint reservation accounting grants A=4 and B=4, both are staged at 4 mol/tick and activate together after Planner commit.

The storage node receives a reserved import and a reserved export in the same route epoch. That is intentional transit behavior, not fallback circulation.

## Example: three-hop world-grid segment

```text
LOW district
   |
   v
STORAGE A
   |
   v
STORAGE B
   |
   v
HIGH district
```

Physical route classes are:

```text
LOW -> STORAGE       route 2
STORAGE -> STORAGE   route 4
STORAGE -> HIGH      route 3
```

If the three current candidates are 8, 6, and 7 mol/tick, the maximum route rate is initially 6 mol/tick. Endpoint reservations can reduce it further. Once admitted, all three staged pumps use the same final route rate.

## Current limits

This is intentionally the first multi-hop slice, not a general network optimizer.

Current limits are:

- maximum routed reuse path: **3 links / 2 intermediate STORAGE domains**;
- automatic multi-hop routing currently starts at LOW and ends at HIGH;
- STORAGE-root multi-hop restoration is not yet implemented; one-hop `STORAGE -> HIGH` remains fallback behavior;
- LOW-to-remote-STORAGE multi-hop buffering is not implemented; buffering stops at the first usable storage edge;
- route discovery is availability-sensitive rather than a persistent all-pairs route table;
- path allocation uses non-mutating whole-path QUOTE followed by exact common-rate COMMIT, eliminating the previous normalization over-reservation;
- route cost is a dimensionless heuristic rather than exact electrical/thermodynamic work;
- cost-aware selection is bounded to the configured candidate budget (default 32);
- no temperature/latent-energy throughput optimization is included;
- no arbitrary-length path or global min-cost-flow optimization yet.

These limits are deliberate. The framework now proves that topology discovery, path staging, path-level rate normalization, and commit atomicity work under IC10 constraints before adding a substantially more expensive graph optimizer.

## Recommended next extension

The next high-value improvement is **energy/thermal-aware link metadata**, not simply longer paths. The safe reservation and bounded route-ranking layers now exist; the missing information is trustworthy per-link cost data such as compressor electrical work, thermal-source/sink availability, and recoverable latent energy.

Once those signals exist, they can be added to the Cost Profile/Ranker without changing the reservation or commit invariants.
