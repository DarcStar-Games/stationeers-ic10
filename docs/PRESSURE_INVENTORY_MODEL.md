# Pressure-Domain Inventory and Purity Model

Pressure is the local control variable, but **moles** are the grid's resource-accounting unit. The amount a domain can export or accept depends on its volume, temperature, current gas inventory, pressure policy, and verified gas composition.

## Architecture

```text
Resource Profile View / PHASE_MEDIUM
   ratio LogicType + purity threshold
              |
              v
Pipe Analyzer ---> Pressure Medium Purity Guard
     |                        |
     | P,T,V,n,liquid         | verified medium/purity
     +------------+-----------+
                  v
        PressureDomain Inventory ABI2
                  |
          export/import moles
                  v
        PressureInventory Reservation
                  v
             grid planner
```

One Inventory/Purity pair is deployed per grid-participating pressure domain and can be shared by every physical transfer touching that domain.

## Wiring

Purity Guard:

```text
ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10
d0 -> Pipe Analyzer on the exact pressure bus
d1 -> Resource Profile View / PHASE_MEDIUM
```

Inventory:

```text
ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10
d0 -> ControllerPressureDomain telemetry ABI2
d1 -> the same Pipe Analyzer
d2 -> Pressure Medium Purity Guard
```

The analyzer must expose `Pressure`, `Temperature`, `Volume`, `TotalMoles`, `VolumeOfLiquid`, and the ratio LogicType selected by the attached profile.

## Purity is enforced

The selected PHASE_MEDIUM Resource Profile describes the **intended** medium. The analyzer ratio describes the **observed** gas composition. The Purity Guard reconciles them.

The Resource Profile View publishes:

```text
S19 GasRatioLogicType
S20 MinimumPurity
```

For a nonempty bus:

```text
ObservedRatio >= MinimumPurity
```

is required. Generated profiles default to `0.995`.

A contaminated or mismatched bus cannot advertise export/import capacity. This prevents, for example, a domain configured as Pollutant from routing every mole in a mostly-Nitrogen mixture as though it were Pollutant.

Empty buses are accepted because they contain no contaminating inventory.

## Gas-only invariant

The current inventory model intentionally refuses any positive `VolumeOfLiquid`. A two-phase network needs a separate inventory/enthalpy model; applying ideal-gas capacity math to liquid inventory would be misleading.

## Molar conversion

For a valid gas network:

```text
MolesPerKPa   = Volume / (8.3144 * Temperature)
MolesPerLiter = Pressure / (8.3144 * Temperature)
```

Role-specific capacity:

```text
LOW:
  ExportableMoles = max(TotalMoles - TargetPressure*MolesPerKPa, 0)

HIGH:
  ImportCapacityMoles = max(TargetPressure*MolesPerKPa - TotalMoles, 0)

STORAGE:
  ExportableMoles = max(TotalMoles - MinimumPressure*MolesPerKPa, 0)
  ImportCapacityMoles = max(MaximumPressure*MolesPerKPa - TotalMoles, 0)
```

Volume therefore matters correctly. At equal temperature and pressure bounds, a 50,000 L storage network has about 8.33 times the pressure-defined molar capacity of a 6,000 L network. An empty HIGH sink still has a finite calculable demand because capacity derives from volume/temperature rather than a current-pressure ratio.

## Coherent PressureDomain input

PressureDomain runtime uses telemetry ABI2. Inventory captures positive `S115`, reads role, MediumType, status and pressure bounds, then requires the same `S115`. Torn domain state is retried rather than published as inventory.

## Inventory ABI2

```text
S0   magic = 31415935
S1   ABI = 2
S2   capability mask = 0
S8   MolesPerLiter
S9   TotalMoles
S10  Pressure
S11  status
S12  publication generation LAST
S13  PressureDomain RefId
S14  role
S15  MediumType
S16  ExportableMoles
S17  ImportCapacityMoles
S18  MolesPerKPa
```

Statuses:

```text
 1 ready
-1 PressureDomain/telemetry fault
-2 analyzer property unavailable
-3 invalid numeric observation
-4 liquid/two-phase bus
-6 purity guard failure or medium mismatch
```

## Purity Guard ABI1

```text
S0  magic = 31415947
S1  ABI = 1
S2  capability mask = 0
S8  MediumType
S9  observed ratio
S10 required threshold
S11 status: 1 good, -1 profile, -2 sensor/property, -3 numeric, -4 contaminated
S12 Resource Profile View generation used
S13 publication generation LAST
```

## Commissioning

Before enabling transfers for a domain:

1. verify the correct PHASE_MEDIUM Resource Profile View is connected to Purity Guard;
2. verify the analyzer is on the exact network represented by PressureDomain;
3. confirm Purity Guard `S11=1` and inspect observed ratio versus threshold;
4. confirm Inventory role and MediumType match the domain;
5. confirm Inventory `S11=1` and `S12` advances;
6. compare reported capacity with expected network volume;
7. during commissioning, deliberately use a wrong profile or contaminated test mixture and verify Inventory drops to zero capacity.

## Current limits

The model is gas-only, single-intended-medium, and uses the game's reported gas ratio as the purity signal. It does not calculate liquid inventory, latent enthalpy, or mixture-specific thermodynamic capacity. Those should be separate model extensions rather than hidden assumptions inside the gas inventory service.
