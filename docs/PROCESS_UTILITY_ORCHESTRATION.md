# Cross-Domain Process & Utility Orchestration

Roadmap Item 11 composes the existing ResourceGrid specializations across domain boundaries without creating a second pressure planner, a furnace-specific scheduler, or a power-specific gas ledger. The first bounded proof covers two complementary industrial systems:

1. a Furnace/Advanced Furnace material transform whose declared pressure and temperature window is actively prepared through gas utilities and then enforced again by the existing Transform Admission authority; and
2. a Gas Fuel Generator whose POWER shortage creates a fuel-gas demand that can drive H2/O2 mixture preparation and ordinary PressureGrid delivery before generation is enabled.

The design rule remains:

> **A process may request conditions; only the existing domain reservation/actuation authority may satisfy them physically.**

`ProcessCondition` is therefore a demand/verification contract, not a reservation and not permission to move gas, switch a generator, or activate a furnace.

## 1. ProcessCondition ABI1

Magic `31416048`, ABI 1.

```text
S0   magic = 31416048
S1   ABI = 1
S2   Target ReferenceId
S3   semantic FLUID ResourceType / prepared-medium hash
S4   MinimumPressure kPa
S5   MaximumPressure kPa; <=0 means no upper bound represented
S6   MinimumTemperature K
S7   MaximumTemperature K; <=0 means no upper bound represented
S8   unmet-condition bitmask: bit0 pressure, bit1 temperature
S9   process identity / strategy-specific identity
S10  Active: 1 demand is live, 0 inactive
S11  PublicationGeneration; payload first, generation LAST
S12  Status: 1 valid, <0 invalid
S13  Strategy code
S14  pressure target hint
S15  temperature target hint
```

A consumer captures positive `S11`, reads the payload, and requires unchanged `S11` before accepting the request. Signed Stationeers hashes are valid identities; only explicit zero/missing identity is treated as absent where a field requires an identity.

The ABI intentionally does not carry reservation owner/epoch fields. Pressure movement remains authorized by PressureGrid reservations, the committed Planner epoch, and `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10`.

## 2. Furnace condition request

`ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` converts the selected Resource Transform Profile ABI4 into a live ProcessCondition for one Furnace or Advanced Furnace.

The transform catalog remains the single source of truth for:

- `MinPressure` / `MaxPressure`;
- `MinTemperature` / `MaxTemperature`;
- transform identity and processor capability.

`ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` compares those bounds with the live processor `Pressure` and `Temperature`, publishes the unmet mask, and carries a commissioned semantic medium/strategy. It does not write Furnace `Activate`, inlet/output settings, or any pressure reservation.

This is intentionally complementary to `ic10/material-transform/material_transform_admission_v1_0.ic10`. Active preparation may make the processor ready, but `ic10/material-transform/material_transform_admission_v1_0.ic10` still independently revalidates the exact pressure/temperature bounds immediately before manufacturing proceeds. A stale or failed utility plan therefore cannot bypass material admission.

## 3. Reusing PressureGrid unchanged

### Process chamber as PressureDomain

`ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` projects a valid active ProcessCondition target into the existing `ControllerPressureDomain` telemetry ABI2:

```text
ProcessCondition TargetPressure window
        |
        v
248 Process PressureDomain
        |
        v
46 Pressure Inventory / 47 Reservation
        |
        +--> ordinary PressureGrid discovery, quote, route and commit
```

The projected process chamber uses role `STORAGE` so its current pressure can expose both import and export correction capacity within the requested window. Its semantic medium is exactly ProcessCondition `S3`.

### Advanced Furnace embedded pumps as PressureTransfer

`ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` projects one Advanced Furnace embedded pump direction as the standard `ControllerPressureTransfer` ABI2. A commissioned instance selects:

- inlet pump -> `SettingInput`; or
- outlet pump -> `SettingOutput`.

It consumes the same PressureInventory Reservation ABI1 endpoints as an ordinary PressureTransfer and accepts physical actuation only when `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` authorizes the exact committed route/epoch. Safe-off writes the selected embedded pump setting to zero.

This preserves the pressure ownership chain:

```text
PressureGrid planner
   -> pressure reservation epoch
   -> Grant Guard
   -> 249 embedded transfer
   -> Advanced Furnace SettingInput/SettingOutput
```

No manufacturing service writes the embedded pumps.

## 4. Prepared gas mixtures as FLUID resources

A prepared mixture is a semantic resource, not a pressure link. Mixing changes ResourceType, so a Gas Mixer must never be represented as an ordinary type-preserving Generic Resource Link.

Resource Profile kind `5`, schema `1`, describes the first two-component prepared mixture:

```text
Fuel.H2O2
ResourceClass = FLUID
Unit = MOLE
Component1LogicType = RatioVolatiles
Component1Fraction  = 2/3
Component2LogicType = RatioOxygen
Component2Fraction  = 1/3
RatioTolerance      = 0.005
```

The profile is stored in the existing Resource Profile catalog alongside pure gases. This raises the current catalog to 39 profiles: FLUID 10, ITEM 27, POWER 1, ENERGY 1, still fitting the existing five-Store minimum commissioning geometry.

`ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` consumes Resource Profile kind 5 and publishes the existing PurityGuard ABI1 (`31415947`). The ordinary Pressure Inventory service can therefore purity-gate a prepared mixture exactly as it does a pure phase medium without learning two-component chemistry.

Empty storage is considered admissible for import; once nonempty, both component ratios and temperature must satisfy the profile.

## 5. Demand-driven composition mixing

`ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` controls one Gas Mixer from:

```text
d0  component-1 source analyzer
d1  component-2 source analyzer
d2  prepared-mixture output analyzer/buffer
d3  Gas Mixer
d4  prepared-mixture Resource Profile kind 5
d5  ProcessCondition demand
```

It verifies that the demand medium matches the prepared-mixture profile and that both source streams are sufficiently pure. For unequal source temperatures it converts the requested mole fraction into the temperature-corrected mixer setting:

```text
settingFraction = (targetFraction * T1)
                / ((1 - targetFraction) * T2 + targetFraction * T1)
```

The mixer continues running until the output simultaneously has:

- nonzero inventory;
- pressure at least `ProcessCondition.MinPressure`; and
- both component ratios inside the profile tolerance.

It re-fences both profile generation and ProcessCondition generation before the physical mixer write. An inactive or malformed request safe-offs the mixer.

This gives a GFG fuel request a real producer path rather than assuming prepared fuel already exists:

```text
POWER shortage
   |
253 GFG utility -> ProcessCondition(Fuel.H2O2)
   |                         |
   |                         +--> 251 composition mixer
   |                                  ^       ^
   |                                  |       |
   |                              Volatiles  Oxygen
   |                                  \       /
   |                                  fuel buffer
   |                                      |
   +--------------------------------------+
                    PressureGrid delivery
```

Pure-gas source pressure and prepared-mixture transport remain PressureGrid concerns. The mixer owns only the physical type-changing composition step.

## 6. Thermal gas preparation

`ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` prepares one medium from hot and cold source streams. It consumes ProcessCondition directly and chooses the midpoint of a finite requested temperature window, or the minimum temperature for an open-ended upper window.

For same-medium streams it uses the temperature-corrected Gas Mixer relation:

```text
Setting% = 100 / (Tcold - Thot)
         * ((Thot * Tcold / Ttarget) - Thot)
```

The controller keeps the mixer active until the output buffer simultaneously satisfies:

- the ProcessCondition temperature window; and
- at least `ProcessCondition.MinPressure`.

PressureGrid can then route that conditioned buffer into the furnace through the normal reservation/transfer path. Thermal preparation does not authorize chamber pressure movement.

## 7. Furnace reference topology

A bounded Advanced Furnace deployment can be wired as:

```text
Transform Profile ABI4
        |
        v
247 Furnace ProcessCondition
        |                         hot medium ----+
        |                                        |
        |                         cold medium ---+--> 252 Thermal Mixer
        |                                                  |
        |                                          conditioned buffer
        |                                                  |
        +--> 248 process PressureDomain                    |
                     ^                                    |
                     |                                    v
               Advanced Furnace <--- 249 inlet --- PressureGrid
                     |
                 249 outlet
                     |
                  exhaust
```

If a prepared chemical mixture is also required, `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` may maintain a mixture buffer before thermal conditioning or as a separate commissioned supply strategy. The first milestone deliberately keeps strategy selection commissioned/bounded; it does not attempt arbitrary thermochemical search.

Execution sequence:

1. Manufacturing selects a transform and publishes its Transform View.
2. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` publishes the current P/T demand.
3. `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` exposes the processor as a PressureDomain.
4. Gas utility controllers prepare the commissioned medium/buffer.
5. PressureGrid reserves and routes gas through ordinary pressure authorities; `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` is only the physical embedded-pump specialization.
6. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` eventually reports no unmet P/T bits.
7. Existing manufacturing retries.
8. `ic10/material-transform/material_transform_admission_v1_0.ic10` independently verifies the processor conditions again before committing material execution.

A utility success is therefore never sufficient by itself to authorize a transform.

## 8. Gas Fuel Generator utility loop

`ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` observes the coherent Power Dispatch Plan Store but never mutates it. A shortage exists when either:

- shed watts exceed the configured trigger; or
- the plan reports a critical shortage.

During shortage it publishes ProcessCondition ABI1 for the commissioned fuel medium and fuel-pressure window. It enables the GFG only after all of the following are current:

- the GFG is the expected Gas Fuel Generator prefab;
- the mixture PurityGuard reports valid prepared fuel;
- GFG fuel-side pressure is inside the commissioned window;
- surrounding atmosphere is at least 20 kPa;
- surrounding temperature is 278..328 K;
- GFG `Error == 0`;
- PowerPlan sequence and mixture-guard generation remain unchanged at the final write boundary.

When the shortage disappears, it safe-offs the GFG and withdraws the ProcessCondition request.

The controller intentionally requests **fuel pressure as a commissioned operating envelope**, not “watts converted to pressure.” Current GFG behavior is mole/feed dependent, so a universal pressure-to-watt conversion would be false unless input volume, temperature, fuel pair, and generator behavior are all represented.

## 9. Electrolyzer and cycle safety

The current prepared `Fuel.H2O2` mixture is compatible with the 2:1 Volatiles/Oxygen output of an Electrolyzer, which makes an Electrolyzer a natural future alternative producer for the same semantic FLUID resource.

Item 11 deliberately does **not** turn on an Electrolyzer as an immediate dependency of a GFG shortage. That would create the dependency cycle:

```text
POWER -> Electrolyzer -> Fuel.H2O2 -> GFG -> POWER
```

Such a cycle is useful only across time when surplus external power is converted into stored chemical energy and consumed later. It therefore belongs to a storage/energy-arbitrage policy with explicit reserve and surplus conditions, not recursive deficit expansion.

A future policy may safely implement:

```text
surplus POWER -> Electrolyzer -> stored Fuel.H2O2
low POWER reserve -> stored Fuel.H2O2 -> GFG -> POWER
```

provided the charge and discharge phases cannot mutually justify each other in the same planning epoch.

## 10. Ownership boundaries

Item 11 preserves these authorities:

| Concern | Authority |
|---|---|
| Transform recipe P/T truth | Resource Transform catalog / View |
| Process condition demand | ProcessCondition publisher |
| Gas inventory/capacity | PressureDomain Inventory |
| Pressure reservation | Pressure Reservation/Allocator |
| Route activation | Pressure Planner epoch + Grant Guard |
| Advanced Furnace embedded pump write | `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10`, only under GrantGuard |
| Gas composition write | `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` |
| Thermal mixer write | `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` |
| Final transform admission | `ic10/material-transform/material_transform_admission_v1_0.ic10` |
| Power shortage truth | Power Dispatch Plan Store |
| GFG On/Off | `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10`, after fuel/ambient verification |
| Job lifecycle | Generic Job Store through Gateway |

Discovery never becomes mutation authority, and ProcessCondition never becomes a hidden reservation protocol.

## 11. Restart and stale-state rules

- ProcessCondition payload is published before S11 generation.
- `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10`, `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10`, `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10`, and `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` reject torn/stale request generations.
- `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` inherits the existing PressureTransfer/GrantGuard committed-epoch boundary.
- utility controllers safe-off physical actuators on malformed/inactive demand where the target write is supported;
- manufacturing still rechecks the final physical furnace P/T state rather than trusting persisted utility state;
- GFG startup re-fences PowerPlan and mixture-guard generations immediately before `On=1`.

These rules make a restart cause temporary loss of readiness rather than unauthorized continued actuation.

## 12. Current bounded scope

Implemented now:

- transform-derived furnace P/T ProcessCondition;
- process-target PressureDomain projection;
- Advanced Furnace embedded inlet/outlet PressureTransfer projection;
- two-component prepared-mixture Resource Profiles and purity validation;
- temperature-corrected demand-driven Gas Mixer composition;
- hot/cold thermal blending driven by process P/T demand;
- GFG fuel demand derived from coherent PowerPlan shortage;
- GFG ambient/fuel verification and safe start/stop;
- direct IC10 harness proofs of both reference paths.

Not claimed yet:

- arbitrary chemistry/combustion optimization;
- automatic selection among multiple furnace heating strategies;
- multi-client utility-demand aggregation into one shared preparation plant;
- exact GFG watt-to-mole dispatch optimization;
- Electrolyzer surplus-energy storage policy;
- heat/exhaust recovery as a first-class THERMAL resource class;
- live-game commissioning evidence for all mixer/furnace/GFG timing and device properties.

Those are extensions above the now-proven cross-domain contract, not reasons to duplicate PressureGrid or manufacturing ownership.
