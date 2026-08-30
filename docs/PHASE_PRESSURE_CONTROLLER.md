# ControllerPhasePressure

`ControllerPhasePressure` is a pressure-requirement controller for phase-change systems. It is intentionally **not** defined as a heater, cooler, condenser, or evaporator controller. Its job is narrower:

> Given a working medium, its current temperature, and a desired phase operation, determine the pressure regime required to place that medium on the desired side of its liquid/gas phase boundary.

This makes the controller useful with the dedicated Stationeers Phase Change devices today while preserving an interface that now feeds the framework's local PressureDomain layer and feeds the framework's inventory/reservation pressure-grid layer.

## Why pressure is the controlled requirement

Stationeers phase behavior depends on both temperature and pressure. The current phase-change devices are pressure-setpoint devices: the Condensation Chamber draws gas toward its pressure setting, while the Evaporation Chamber removes gas above its pressure setting. The controller therefore treats **temperature as an input to the phase-boundary calculation** and **pressure as the requested operating condition**.

Inside the normal liquid window, the current published phase curve uses:

```text
Pboundary = A * Temperature^B
```

where temperature is Kelvin and pressure is kPa. The result is clamped to the medium profile's minimum/triple pressure and maximum/critical pressure.

The controller then deliberately moves to one side of that boundary:

```text
EVAPORATE: RequestedPressure = Pboundary * EvaporationFactor
CONDENSE:  RequestedPressure = Pboundary * CondensationFactor
HOLD:      RequestedPressure = StandbyPressure
```

Typical factors are below 1 for evaporation and above 1 for condensation. The family defaults are `0.95` and `1.05`, giving a 5% pressure margin on either side of the phase boundary.

## Architecture

```text
                   Resource Profile View
                    A, B, limits, identity
                           |
                           v
Phase device ------> ControllerPhasePressure ------> RequestedPressure telemetry
 Pressure                  |                              |
 Temperature               |                              +--> PressureDomain / pressure grid
                           |
                           +--> optional direct Setting/PressureSetting write
```

The medium profile owns thermodynamic identity and curve parameters. The controller owns the phase-operation policy and pressure requirement. The pressure infrastructure is deliberately outside both.

This is a useful separation for the eventual grid architecture:

```text
DEVICE LEVEL
ControllerPhasePressure
"I require 11.4 kPa to evaporate this medium here."
        |
        v
LOCAL PRESSURE DOMAIN (implemented)
"I aggregate compatible requests and maintain one safe pressure bus."
        |
        v
WORLD PHASE GRID (future)
"Route pressure/working-medium capacity among producers, consumers, and storage."
```

## Runtime file and wiring

Runtime: `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10`

| Screw | Connect to | Purpose |
|---|---|---|
| `d0` | phase-change device or compatible enclosed process device | Reads `Pressure` and `Temperature`; optionally writes configured pressure setpoint LogicType. |
| `d1` | Resource Profile View | Selects one `PHASE_MEDIUM` record from the unified catalog. |
| `d2` | paired Generic Persistent Config Host | Supplies coherent accepted controller configuration. |

Policy: `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10`, with Policy `d0` connected to the same Host.

Optional commissioning Profile View: `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`, connected to the shared Input Profile Catalog Store with `S8=HASH("ControllerPhasePressure")`, `S9=1`.

The bundled `data/resource_profiles.json` contains Water, Pollutant, Silanol, Nitrous Oxide, Nitrogen, Methane, Carbon Dioxide, Oxygen, and Hydrogen phase-medium records. Select one with a Resource Profile View (`S26=1`, `S27=HASH(<medium>)`) instead of loading a different IC10 program per medium.

## Configuration schema

Schema 1 uses nine active fields. Physical slots are stable and contiguous in the initial schema, but they remain physical schema addresses rather than promises that future schemas will always be packed.

| Active ordinal | Physical slot | Field | Meaning | Default |
|---:|---:|---|---|---:|
| 1 | 0 | `Enabled` | 0 disables active phase targeting; 1 enables it. | 1 |
| 2 | 1 | `Mode` | `0=HOLD`, `1=EVAPORATE`, `2=CONDENSE`. | 0 |
| 3 | 2 | `EvaporationFactor` | Multiplier applied below the boundary. Must be `>0` and `<=1`. | 0.95 |
| 4 | 3 | `CondensationFactor` | Multiplier applied above the boundary. Must be `>=1` and `<=10`. | 1.05 |
| 5 | 4 | `MinimumPressure` | Lower clamp for requested pressure, kPa. | 0 |
| 6 | 5 | `MaximumPressure` | Upper clamp for requested pressure, kPa. | 6000 |
| 7 | 6 | `StandbyPressure` | Request used in HOLD and as operational fault fallback, kPa. | 100 |
| 8 | 7 | `OutputLogicType` | Writable pressure setpoint property. Profile offers `Setting` and `PressureSetting`. | `Setting` |
| 9 | 8 | `DirectWrite` | 1 writes the requirement to `d0`; 0 publishes requirement only. | 1 |

Host geometry:

```text
blockCount = 2
mask0      = 255
mask1      = 1
signature  = CFG1|ControllerPhasePressure|1|2|255|1|0|0
```

## Modes

### HOLD (`Mode=0`)

The controller does not derive a phase boundary target. It publishes `StandbyPressure`. If direct writing is enabled, it writes that standby pressure to the configured device property.

HOLD is useful when a chamber should remain at a known neutral pressure between phase operations.

### EVAPORATE (`Mode=1`)

Within the medium's supported normal liquid temperature window:

```text
boundary = clamp(A * T^B, TriplePressure, CriticalPressure)
request  = clamp(boundary * EvaporationFactor,
                 MinimumPressure,
                 MaximumPressure)
```

The default factor of `0.95` asks for a pressure 5% below the modeled liquid/gas boundary.

### CONDENSE (`Mode=2`)

Within the same supported window:

```text
boundary = clamp(A * T^B, TriplePressure, CriticalPressure)
request  = clamp(boundary * CondensationFactor,
                 MinimumPressure,
                 MaximumPressure)
```

The default `1.05` factor asks for a pressure 5% above the modeled phase boundary.

## Direct-write versus grid-request mode

`DirectWrite` is intentionally part of the family because it lets the same runtime support two deployment stages.

### `DirectWrite=1`: local autonomous device

The controller writes `RequestedPressure` directly to `d0` using `OutputLogicType`. This is appropriate for today's Condensation/Evaporation Chambers or another compatible pressure-setting device.

### `DirectWrite=0`: requirement producer

The runtime does **not** write a pressure property. It still publishes the requested pressure, mode, actual chamber pressure, temperature, medium identity, and status through generic telemetry.

This is the preferred mode when `ControllerPressureDomain` or another explicit infrastructure owner owns the pressure-setting surface. A consumer should honor the request only while the controller status is valid and should decide how the pressure differential is actually supplied.

## Resource Profile View ABI

The runtime expects `d1` to be `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` resolving a `PHASE_MEDIUM` record:

```text
S0   magic = 31415963
S29  positive coherent publication generation
S9   MediumType hash
S11  ProfileKind = 1 PHASE_MEDIUM
S13  A coefficient
S14  B coefficient
S15  triple/minimum liquid pressure, kPa
S16  critical/maximum liquid pressure, kPa
S17  freezing/minimum liquid temperature, K
S18  critical/maximum liquid temperature, K
```

The runtime captures `S29`, reads the required payload, then requires the same positive `S29` afterward. It also requires the Resource Profile View magic and `ProfileKind=PHASE_MEDIUM`, so an ITEM record cannot be interpreted as thermodynamic coefficients. The View itself validates catalog completeness and clears `S29` whenever its selected record is unavailable.

See `docs/RESOURCE_PROFILES.md` for the complete View/catalog ABI and `docs/PHASE_MEDIUM_PROFILE.md` for the phase-specific parameter model and selection guidance.

## Telemetry

Generic telemetry header remains the framework ABI:

```text
S96  27182818
S97  2
S98  254
S99  HASH("ControllerPhasePressure")
S116 paired Host ReferenceId
```

Channels:

| Channel | Stack cell | Meaning |
|---:|---:|---|
| 1 | S100 | Actual device pressure, kPa. |
| 2 | S101 | Actual device temperature, K. |
| 3 | S102 | Computed phase-boundary pressure, kPa. Last valid derived boundary. |
| 4 | S103 | Requested operating pressure, kPa. |
| 5 | S104 | Requested phase mode (`0/1/2`). |
| 6 | S105 | Runtime status. |
| 7 | S106 | MediumType hash read from the Resource Profile View. |

The PhasePressure Request Arbiter consumes the request/status/medium fields needed to reduce compatible device requirements into a LOW or HIGH PressureDomain target. Level-3 grid services consume the resulting PressureDomain Inventory rather than reading PhasePressure telemetry directly.

## Runtime status

| Status | Meaning |
|---:|---|
| 0 | HOLD/disabled standby state. |
| 1 | Valid EVAPORATE request. |
| 2 | Valid CONDENSE request. |
| -1 | Required process input property/device unavailable. |
| -2 | Configured direct-write output property unavailable. |
| -4 | Config Host/type/schema/signature invalid. |
| -5 | Pressure/temperature input became NaN. |
| -6 | Resource Profile View unavailable/invalid, or phase calculation produced NaN. |
| -7 | Temperature is outside the Profile's supported normal liquid window. |

For operational faults (`-1`, `-5`, `-6`, `-7`), the runtime publishes `StandbyPressure` and, when `DirectWrite=1` and the configured output exists, best-effort writes that standby value. A Host/config fault does not trust stale configuration enough to perform a fallback write.

## Policy validation results

The family Policy uses the framework's normal success result `5` and malformed-candidate result `-5` plus these semantic rejects:

| Result | Meaning |
|---:|---|
| -81 | Invalid phase margin factor (`EvaporationFactor` or `CondensationFactor`). |
| -82 | Invalid pressure bounds or StandbyPressure outside the configured bounds. |
| -83 | Invalid discrete field (`Mode` or `OutputLogicType`). |

`Enabled` and `DirectWrite` are canonicalized to 0/1.

## Example: Water at 20 °C

Using the current Water reference coefficients in this bundle:

```text
T = 293.15 K
A = 3.8782059839e-19
B = 7.90030107708

Pboundary ~= 12.006 kPa
```

With default factors:

```text
EVAPORATE request ~= 11.405 kPa
CONDENSE  request ~= 12.606 kPa
```

These are pressure *requirements*, not guarantees of phase-change throughput. Actual transition rate also depends on available liquid/gas quantity, heat/latent-energy flow, device throughput, connected pipe conditions, and how quickly the pressure infrastructure can satisfy the request.

## Why v1 rejects temperatures outside the normal liquid window

Stationeers has additional behavior for supercooled/frozen and supercritical conditions. In particular, evaporation behavior below the normal liquid window is not simply the same `A*T^B` control problem, and above the maximum liquid temperature condensation is not achievable by pressure alone.

Rather than silently extrapolate a misleading target, v1 reports `-7` and falls back to standby. A later profile schema can explicitly model frozen/supercooled behavior if the world-grid design needs it.

## Safety and engineering limits

The family deliberately distinguishes **thermodynamic boundary** from **plant safety**.

- `CriticalPressure` in the medium profile describes the phase curve, not the maximum safe pressure of every pipe/device.
- `MinimumPressure`/`MaximumPressure` are deployment-specific operational clamps and should reflect the connected infrastructure.
- A pressure request does not prove the grid can satisfy the request safely.
- Grid-level routing must account for gas-pipe/liquid-pipe limits, working-medium contamination, backflow, and storage capacity.
- A phase change itself exchanges latent heat. Pressure targeting alone does not provide an unlimited heat source/sink.

## Intended evolution toward a world phase grid

The current runtime establishes a stable per-device contract before adding centralized routing complexity.

Current/evolution layers:

1. **Phase-pressure device controller** — implemented. Publishes desired medium/mode/pressure and local state.
2. **Pressure-domain controller + request Arbiter** — implemented. Maintains the safe target for one same-medium LOW or HIGH pressure bus from multiple device requests.
3. **Inventory-aware transfer/grid scheduler** — implemented as PressureDomain Inventory + `ControllerPressureTransfer` + `Grid Reservation Planner`. It measures export/import capacity in moles, matches real pump-connected domain edges, and uses STORAGE fallback without requiring phase devices to understand world topology.
4. **Reservation/routing model** — implemented through parallel molar reservations and bounded multi-hop LOW-to-HIGH routing. The remaining work is compressor/work cost, route quality, latent-energy demand, and thermal-source/sink availability.

The important invariant is that `ControllerPhasePressure` should continue to say **what pressure regime is required**, not become the component that knows every pump, tank, valve, and route in the world.

## Current limitations

- One medium profile is wired per controller instance.
- The supplied reference profile is Water; additional medium profiles are data additions, not new controller families.
- Automatic phase targeting is restricted to the profile's normal liquid temperature window.
- v1 computes pressure requirement but does not estimate phase-change rate or heat transfer capacity.
- v1 does not itself arbitrate shared pressure infrastructure. Its telemetry request channel is consumed by `ControllerPressureDomain` + the PhasePressure Request Arbiter regardless of `DirectWrite`; `DirectWrite=0` is reserved for publish-only commissioning or another explicit owner of the phase-device setpoint.
- The runtime assumes the controlled device exposes readable `Pressure` and `Temperature` properties.
- A medium profile is treated as immutable during normal operation; swap/reflash it only as a commissioning action and recheck telemetry before enabling a phase operation.
