# Pressure-Grid Reservation, Parallel Scheduling, and Commit Model

The grid reserves **moles** before it allows physical pump work. This document describes the mutable reservation ledgers, multi-hop quote/commit protocol, topology-bound grants, and the Planner's final commit barrier.

## Resource layers

```text
PressureDomain Inventory ABI2
        |
        v
PressureInventory Reservation ABI1
        |
        v
Pressure Reservation Allocator ABI3
   QUOTE or COMMIT
       / \
      /   \
Single-Hop   Path Allocator
 Builder      quote all hops
              exact-commit common rate
      \       /
       Plan Builder
            |
Grid Reservation Planner ABI2
        S14 commit LAST
            |
Transfer staged grant
            |
Transfer Grant Guard
            |
physical pump
```

## Endpoint invariant

For every Reservation ledger touched by one Planner/build epoch:

```text
ReservedExportMoles <= ExportableMoles
ReservedImportMoles <= ImportCapacityMoles
```

The Reservation Allocator is the intended sole writer of `ReservedExportMoles` and `ReservedImportMoles`.

## PressureInventory Reservation ABI1

`ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` wraps one Inventory ABI2 service.

```text
S0   magic = PressureInventoryReservation.v1
S1   ABI = 1
S2   capability mask = 0
S8   MolesPerKPa
S9   MolesPerLiter
S10  Inventory status
S11  mirror publication generation
S12  ReservedExportMoles       # Allocator-owned
S13  ReservedImportMoles       # Allocator-owned
S14  build epoch               # Allocator-owned
S15  owning Planner RefId      # Allocator-owned
S16  Inventory ReferenceId
S17  PressureDomain ReferenceId
S18  role: 1 LOW, 2 HIGH, 3 STORAGE
S19  MediumType
S20  ExportableMoles
S21  ImportCapacityMoles
```

When a new build epoch first touches an endpoint, Allocator resets the stale counters, records the new owner, and records the epoch. Abandoned-build counters therefore cannot silently carry into a later epoch.

## Allocator ABI3

`ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` is screwless and serializes mutations for one medium-specific scheduling stack.

Request:

```text
S10  admission mode: 1 fallback, 2 direct, 3 path hop
S11  maximum requested mol/tick
S13  Planner RefId
S14  build epoch
S15  MediumType
S16  operation: 1 QUOTE, 0 COMMIT
S17  PressureTransfer RefId
S18  request generation; LAST
```

Response:

```text
S8   1 admissible/granted, 0 no grant, -1 rejected
S9   response generation; LAST
S12  admissible/committed mol/tick
S19  committed lease moles; 0 for QUOTE
```

### QUOTE

QUOTE calculates:

```text
RemainingSource = ExportableMoles - ReservedExportMoles
RemainingSink   = ImportCapacityMoles - ReservedImportMoles

AdmissibleRate = min(
    Transfer.PlannedMolesPerTick,
    RequestedMaximumRate,
    RemainingSource / LeaseTicks,
    RemainingSink / LeaseTicks
)
```

It does **not** modify endpoint counters and does not stage a Transfer grant.

### COMMIT

COMMIT reserves exactly the accepted rate for the full lease and stages the Transfer grant. The allocator writes endpoint counters and grant identity payload before writing the staged epoch.

## Exact multi-hop reservation

For a candidate path:

```text
hop 1 quote = 8 mol/tick
hop 2 quote = 5 mol/tick
hop 3 quote = 7 mol/tick
```

Path Allocator chooses:

```text
PathRate = 5 mol/tick
```

and then COMMITs each hop at exactly 5 mol/tick.

This replaces the old reserve-first/normalize-later strategy. The reservation ledgers now reflect the same common rate the path is staged to execute, so later routes can use capacity that would previously have been stranded by conservative over-reservation.

## Staged topology identity

Allocator COMMIT writes:

```text
S108 GrantMolesPerTick
S110 Planner RefId
S111 LeaseTicks
S117 source Reservation RefId
S118 sink Reservation RefId
S119 MediumType
S120 RouteKind
S109 staged epoch LAST
```

Those identities are part of the reservation, not descriptive telemetry.

## Grant Guard

`ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` is the only component that converts a staged grant into an active lease signal for the Transfer runtime.

It requires:

```text
current source Reservation == staged source Reservation
current sink Reservation   == staged sink Reservation
current MediumType         == staged MediumType
current RouteKind          == staged RouteKind
staged Planner RefId       == actual Planner RefId
staged epoch               == Planner committed S14
```

The current Transfer topology is read through telemetry ABI2 generation checks. If a screw is repointed or configuration changes between reservation and commit, the grant stays OFF.

Grant Guard publishes:

```text
S0  magic = PressureTransferGrantGuard.v1
S1  ABI = 1
S2  capability mask = 0
S8  active GrantMolesPerTick
S14 remaining lease ticks
S15 status: 1 active, 0 off, -1 fault
S16 active committed epoch
S17 Transfer RefId
S18 publication generation LAST
```

The physical Transfer rechecks Guard generation and locally caps the granted rate by current physical capacity every tick.

## Planner commit barrier

Builders may stage work, but only `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` can make the new build executable.

```text
S13 build epoch counter
S14 committed epoch
```

On successful Plan Builder completion the Planner publishes summary payload and writes `S14` last. A failed build leaves the previous `S14` untouched.

Therefore:

```text
quote
 -> reserve exact endpoints
 -> stage grants + topology
 -> complete plan
 -> Planner S14 commit LAST
 -> Grant Guards may activate
```

A partial path, fully staged uncommitted path, or abandoned build cannot turn on a pump.

## Parallel scheduling

Several links may execute concurrently. When links share an endpoint, their combined reservation counters bound aggregate consumption. Direct `LOW -> HIGH` reuse is built before routed reuse and storage fallback, so direct reuse gets first claim on shared inventory.

## Reservation-aware route ranking

Route Ranker ABI2 subtracts reservations already made in the current build before determining a route's bottleneck. For each hop it includes:

```text
(ExportableMoles - ReservedExportMoles) / LeaseTicks
(ImportCapacityMoles - ReservedImportMoles) / LeaseTicks
```

A path whose endpoints have already been exhausted is removed before allocation rather than being ranked using stale raw link throughput.

## Failure and interruption behavior

- **Interrupted during QUOTE:** no mutation exists.
- **All quotes complete, no commit yet:** no mutation exists.
- **Interrupted during hop COMMIT:** some reservations/staged grants may exist, but Planner `S14` is old, so no new pump lease activates.
- **Unexpected later-hop COMMIT failure:** Path Allocator invalidates already-staged grant epochs; Planner does not commit the build.
- **Planner restart:** next build uses a fresh persistent build epoch; touched endpoint ledgers lazily reset old counters.
- **Topology change after staging:** Grant Guard refuses activation even if the build epoch later commits.
- **Runtime capacity falls during active lease:** Transfer reduces or stops the physical pump; a reservation is an upper bound, never an instruction to violate current evidence.

## STORAGE rules

Ordinary fallback retains the anti-circulation rule. `STORAGE -> STORAGE` and simultaneous storage transit are admitted only as part of a complete routed LOW-to-HIGH path, where the path reservation gives the movement a defined demand-serving purpose.

See `docs/PRESSURE_MULTI_HOP_ROUTING.md` for route topology and `docs/CORRECTNESS_HARDENING.md` for the rationale behind the hardening changes.
