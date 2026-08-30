# Pressure Domain Controller

`ControllerPressureDomain` is the first infrastructure controller above `ControllerPhasePressure`. A phase-pressure controller answers **what pressure does this phase-change device require?** A pressure-domain controller answers **what pressure should this shared local bus maintain to service the compatible requests attached to it?**

It deliberately does not calculate phase-change heat capacity or perform cross-domain transfer scheduling. Runtime revision 1.1 adds a passive `STORAGE` role so the Level-3 grid can treat a tank/pipe network as a source or sink within configured pressure bounds, while actual transfer/routing remains the responsibility of `ControllerPressureTransfer` and `Grid Reservation Planner`.

## Architectural position

```text
PHASE_MEDIUM Resource Profile View
        |
        +------------------------------+
        |                              |
PhasePressure device A          PhasePressure device B
DirectWrite=1 normally          DirectWrite=1 normally
        |                              |
        +------ generic telemetry -----+
                       |
             Controller Directory
                       |
                       v
          PhasePressure Request Arbiter
                       |
                       v
             PressureDomain Controller
              /                   \
     pressurize source        depressurize sink
              \                   /
                 pressure domain
                       |
                 Pipe Analyzer
```

The split between the Arbiter and the controller is intentional. Multi-controller discovery and request reduction require enough IC10 code that combining them with Host/config validation and physical actuation would exceed the framework's IC10 size limits. The Arbiter therefore owns **request-set interpretation**; the controller owns **one physical domain**.

## Files

- `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10` — scans `ControllerDirectory` incrementally and reduces matching phase-pressure requests.
- `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` — consumes the reduced request, applies domain safety limits, publishes telemetry, and optionally writes the domain setpoint.
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` — select `S8=HASH("ControllerPressureDomain")`, `S9=1` from the shared Input Profile Catalog for the eight commissioning controls.
- `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10` — defaults, normalization, and semantic validation.

The family uses the existing Generic Persistent Config Host and all existing configuration/discovery/diagnostic infrastructure without generic-service changes.

## Domain roles

A pressure domain has one fixed role. Runtime revision 1.1 supports LOW, HIGH, and STORAGE.

### LOW / evaporation service (`Role=1`)

The domain services `ControllerPhasePressure` requests whose mode and valid runtime status are both `EVAPORATE` (`1`) and whose `MediumType` matches the domain's PHASE_MEDIUM Resource Profile View.

An evaporation chamber removes gas from itself when its internal pressure rises above its configured setpoint. Its output therefore benefits from a sink below that setpoint. When several compatible evaporators share a low-pressure domain, the lowest requested pressure is the most demanding request:

```text
request A = 1900 kPa
request B = 1700 kPa
request C = 2100 kPa

LOW-domain raw target = min(...) = 1700 kPa
```

A bus at or below 1700 kPa is pressure-compatible with all three requests. This is why LOW arbitration is a minimum reduction rather than an average.

### HIGH / condensation service (`Role=2`)

The domain services matching `CONDENSE` (`2`) requests.

A condensation chamber pulls gas from its input until its internal pressure reaches its setpoint. Its supply bus therefore needs to be at or above the requested chamber pressure. The highest request is the most demanding:

```text
request A = 2800 kPa
request B = 3100 kPa
request C = 2600 kPa

HIGH-domain raw target = max(...) = 3100 kPa
```

A bus at or above 3100 kPa is pressure-compatible with all three.

### STORAGE / flexible reservoir (`Role=3`)

A STORAGE domain does not consume PhasePressure requests. Instead it exposes one medium-specific storage network to the transfer grid. `MinimumPressure` is the reserve floor below which export must stop, and `MaximumPressure` is the import ceiling above which additional storage must stop.

For STORAGE only, telemetry cells have role-specific meanings:

```text
S100 actual storage pressure
S101 MinimumPressure / export reserve floor
S102 MaximumPressure / import ceiling
S103 role = 3
S104 MediumType
S105 status = 3 when enabled/profile-valid
```

`d0` observation is therefore required for useful grid scheduling even though LOW/HIGH local setpoint operation can tolerate missing observation. STORAGE bypasses the PhasePressure Request Arbiter and does not write `d3/d4`; those screws may remain unassigned. See `docs/PRESSURE_GRID_CONTROLLER.md` for source/sink margin calculations.

## Medium isolation

Every PressureDomain runtime is wired to one PHASE_MEDIUM Resource Profile View on `d1`. Only PhasePressure telemetry publishing the same `MediumType` hash can participate in its arbitration set.

This is a control-plane filter, not a physical contamination detector. The pipe network must still be engineered so incompatible media cannot enter the domain. The Level-3 pressure-grid layer now adds physical transfer-link ownership and scheduling without changing the PressureDomain family contract; mixture verification remains a future extension.

## Request Arbiter

### Why it exists

Controller Directory ABI 2 can contain up to **64 telemetry controllers**. The Arbiter walks that directory one provider per game tick, considering only valid `ControllerPhasePressure` producers that match the configured role and medium.

This makes scan cost bounded and avoids a large synchronous loop inside the physical controller.

A complete pass takes approximately:

```text
1 tick  pass setup
N ticks one provider per tick, N <= 64
1 tick  coherent commit
```

So the worst-case refresh latency is about **66 ticks** at a full 64-controller directory, excluding concurrent directory changes that force a restart. Smaller deployments scale linearly with actual provider count. Phase-pressure requirements generally change slowly enough for this first infrastructure layer; fast flow control belongs lower in the actuator path.

### Request validity

A provider contributes only when all of the following are true:

- Directory record type is `ControllerPhasePressure`.
- The provider still publishes that ControllerType.
- `MediumType` matches the domain context.
- runtime `Status` equals the requested domain role (`1` EVAPORATE or `2` CONDENSE).
- telemetry `Mode` equals the same role.
- `RequestedPressure` is finite.

Faulted, HOLD, wrong-medium, wrong-role, NaN, and unrelated controllers are ignored.

### Coherence

The PressureDomain runtime publishes Arbiter context as payload first:

```text
Enabled
Role
MediumType
Host effective generation
```

The Arbiter captures that context together with one Controller Directory bank/generation. During its incremental scan it restarts if the context, active bank, or directory generation changes. On completion it publishes result payload and writes its result generation last.

The PressureDomain runtime accepts a result only if:

- the Arbiter result generation is complete and stable across the read;
- the echoed Host generation matches the Runtime's loaded Host generation;
- the echoed MediumType matches the currently wired profile.

This prevents a target calculated under an old controller configuration or old medium identity from leaking into actuation.

## PhasePressure Request Arbiter ABI v1

Magic: `HASH("PhasePressureRequestArbiter.v1")`, ABI: `1`.

The Arbiter is **not** generic telemetry and is not discovered as a controller. It is an internal pressure-grid service.

```text
S0   magic = PhasePressureRequestArbiter.v1
S1   ABI = 1
S2   capability mask = 0

# Context written by one paired PressureDomain runtime
S15  Enabled
S16  Role: 1 LOW/EVAP, 2 HIGH/CONDENSE
S17  MediumType hash
S18  paired Host effective generation

# Result published by Arbiter
S8   raw aggregate requested pressure
S9   number of contributing PhasePressure controllers
S10  result status: 0 no request, 1 LOW request, 2 HIGH request,
                   -3 Directory unavailable/invalid, -9 invalid context
S11  Controller Directory source generation
S12  result generation; written last
S13  handled Host effective generation
S14  handled MediumType hash
```

One Arbiter instance belongs to one active PressureDomain context. Do not point multiple PressureDomain runtimes at one Arbiter in v1; they would overwrite each other's context exactly like competing consumers of one shared commissioning Resolver.

## Runtime wiring

`ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` uses:

| Screw | Device | Purpose |
|---|---|---|
| `d0` | Pipe Analyzer or another readable `Pressure` device | Optional observation of actual domain pressure. Missing/invalid property publishes `NaN`; it does not prevent setpoint control. |
| `d1` | PHASE_MEDIUM Resource Profile View | Establishes the domain's `MediumType`. |
| `d2` | PhasePressure Request Arbiter | Supplies the coherent aggregate requirement. |
| `d3` | Pressurizing setpoint device | Adds gas/pressure from an available higher-pressure source toward the target. |
| `d4` | Depressurizing setpoint device | Removes gas/pressure into an available lower-pressure sink toward the target. |
| `d5` | Generic Persistent Config Host | Supplies the accepted PressureDomain configuration. |

The Arbiter's own `d0` points to the shared `Controller Directory`.

### Recommended first physical implementation

For a gas-domain prototype:

- `d3`: **Pressure Regulator**, oriented from a higher-pressure source/storage network into the controlled domain.
- `d4`: **Back Pressure Regulator**, oriented from the controlled domain into a lower-pressure sink/storage network.
- configure both writable output properties as `LogicType.Setting`.
- power the regulators, set `On=1`, and orient their input/output networks correctly.

The runtime writes the same domain target to both devices. Their built-in opposite regulation semantics bracket the bus: the standard regulator supplies its output until the target is reached, while the back-pressure regulator relieves its input when it exceeds the target.

This arrangement **does not create a pressure differential**. The source for `d3` must already be capable of supplying gas above the target, and the sink for `d4` must be capable of accepting gas below the target. Compression/active transfer and storage scheduling are intentionally owned by the Level-3 transfer grid, not by LOW/HIGH local setpoint control.

## Configuration schema 1

The schema uses one physical config block with mask `255`.

| Active ordinal | Physical slot | Field | Meaning | Default |
|---:|---:|---|---|---:|
| 1 | 0 | `Enabled` | 1 allows request arbitration; 0 holds StandbyPressure. | 1 |
| 2 | 1 | `Role` | `1=LOW/EVAP`, `2=HIGH/CONDENSE`, `3=STORAGE`. | 1 |
| 3 | 2 | `MinimumPressure` | Lowest plant pressure this domain may command. | 0 kPa |
| 4 | 3 | `MaximumPressure` | Highest plant pressure this domain may command. | 6000 kPa |
| 5 | 4 | `StandbyPressure` | Target when disabled, waiting, or no valid request exists. | 100 kPa |
| 6 | 5 | `PressurizeLogicType` | Writable pressure-setpoint property on `d3`. | `Setting` |
| 7 | 6 | `DepressurizeLogicType` | Writable pressure-setpoint property on `d4`. | `Setting` |
| 8 | 7 | `DirectWrite` | 1 writes target to both actuators; 0 publishes arbitration only. | 1 |

Persistence signature:

```text
CFG1|ControllerPressureDomain|1|1|255|0|0|0
```

## Safety-limit semantics

The aggregate request is a **requirement**; domain bounds are **plant limits**. The controller never violates its configured pressure bounds.

For a LOW domain:

```text
raw request < MinimumPressure
    -> command MinimumPressure
    -> Status = -8 (request cannot be fully satisfied safely)
```

For a HIGH domain:

```text
raw request > MaximumPressure
    -> command MaximumPressure
    -> Status = -8
```

The opposite clamp direction can remain pressure-compatible with the request:

- a LOW bus below a higher evaporation request still provides a lower-pressure sink;
- a HIGH bus above a lower condensation request still provides a higher-pressure source.

The controller therefore clamps but only reports `-8` when the safety boundary prevents it from reaching the **demanding direction**.

## Runtime telemetry

Generic telemetry header:

```text
S96  27182818
S97  2
S98  126
S99  HASH("ControllerPressureDomain")
S116 paired Host ReferenceId
```

Channels:

| Channel | Cell | Meaning |
|---:|---:|---|
| 1 | S100 | Actual domain pressure from `d0`, or NaN when unavailable. |
| 2 | S101 | Safe commanded/standby pressure. |
| 3 | S102 | Number of matching PhasePressure requests in the last accepted Arbiter pass. |
| 4 | S103 | Domain role (`1=LOW`, `2=HIGH`, `3=STORAGE`). |
| 5 | S104 | MediumType hash. |
| 6 | S105 | Runtime status. |

Status values:

| Status | Meaning |
|---:|---|
| 0 | Standby: disabled, Arbiter result not yet current, or no matching request. |
| 1 | Valid LOW/EVAP aggregate request. |
| 2 | Valid HIGH/CONDENSE aggregate request. |
| -2 | One or both configured output properties are unavailable; neither actuator is written that tick. |
| -3 | Arbiter reports Controller Directory unavailable/invalid. |
| -4 | paired Generic Config Host is unavailable, not ready, wrong ABI/magic/signature, or effective image is invalid. |
| -6 | PHASE_MEDIUM Resource Profile View unavailable/invalid. |
| -7 | Arbiter service unavailable/invalid. |
| -8 | Most demanding request exceeds the domain's safe capability in the required direction; command is clamped to the safe boundary. |
| -9 | Arbiter context invalid. |

The runtime intentionally checks both actuator properties before either write, preventing a half-applied target caused by one missing/wrong output property.

## `DirectWrite=0`

Like PhasePressure, PressureDomain can run as a requirement-processing stage without owning physical actuation.

With `DirectWrite=0` it still:

- publishes role and medium context to the Arbiter;
- reduces all matching requests;
- applies safety bounds;
- reports request count and status;
- publishes the resulting safe target.

This is useful for commissioning and for the implemented Level-3 grid layer, where the transfer scheduler may own how medium is moved to satisfy the domain target.

## End-to-end example: Pollutant cooling loop

Assume three Pollutant evaporators publish valid requests:

```text
E1: 1900 kPa
E2: 1700 kPa
E3: 2100 kPa
```

The Pollutant LOW domain receives:

```text
Role       = LOW
MediumType = Pollutant
Min        = 1200 kPa
Max        = 3000 kPa
```

The Arbiter chooses `1700 kPa`. The runtime commands its pressurizing and depressurizing devices to 1700 kPa and publishes `Status=1`, `RequestCount=3`.

Elsewhere, Pollutant condensers request:

```text
C1: 3200 kPa
C2: 3500 kPa
```

A separate Pollutant HIGH domain chooses 3500 kPa. If its configured maximum were only 3300 kPa, it would command 3300 kPa and publish `Status=-8` so the higher grid layer knows demand exceeds safe local capability.

The LOW and HIGH domains are separate physical pressure networks. The Level-3 Inventory + PressureTransfer layer can now measure available gas inventory and move working medium between them directly or through a STORAGE domain.

## What v1 does not do

The controller is deliberately a first local-domain layer. It does **not** yet:

- estimate mol/s demand or actual throughput;
- publish source/sink capacity;
- detect whether a regulator is starved despite having a valid Setting property;
- control compressor power or volume-pump displacement;
- reserve storage volume;
- route valves between multiple pressure domains;
- detect physical gas contamination;
- prioritize consumers when capacity is insufficient;
- account for latent-energy availability;
- keep the shared 64-controller Directory as the authoritative controller registry; the Level-3 grid now derives its own 64-link Grid Link Directory so route-search churn is isolated without splitting diagnostics/config discovery.

These omissions are intentional. A target-pressure domain must be correct before adding capacity scheduling and routing.

## Implemented next grid layer

The transfer layer described by the original design now exists. One `PressureDomain Inventory` service can be paired with each domain to convert its target/bounds plus Pipe Analyzer `Pressure`, `Temperature`, `Volume`, and `TotalMoles` into exportable/importable moles. `ControllerPressureTransfer` represents one real pump-connected source->sink edge, and `Grid Reservation Planner` selects among those links for one working medium. It supports direct `LOW -> HIGH` recirculation plus STORAGE buffering (`LOW -> STORAGE`, `STORAGE -> HIGH`).

PressureDomain therefore remains intentionally local. It publishes target/role/medium/status and does not learn which pump, storage route, or transfer link services it. See `docs/PRESSURE_INVENTORY_MODEL.md` for the capacity layer and `docs/PRESSURE_GRID_CONTROLLER.md` for Level-3 topology, transfer tuning, reservation policy, parallel lease execution, and remaining world-grid limitations.


## Transactional telemetry and overflow behavior

PressureDomain runtime v1.2 publishes Generic Telemetry ABI2 with `S115` written last. Inventory consumes role, MediumType, status, and bounds from one coherent generation. PhasePressure Request Arbiter v1.2 requires coherent PhasePressure ABI2 snapshots and refuses an overflowed 64-entry Controller Directory rather than treating truncation as complete discovery.
