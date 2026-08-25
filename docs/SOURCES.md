# Sources

Current IC10 semantics were rechecked against the Stationeers Community Wiki IC10 and IC10/instructions pages during the shared-input refactor. The implementation relies on documented direct ReferenceId access (`ld`, `sd`, `getd`, `putd`), `rrN`/`drN` indirection, `jal`/`j ra`, `select`, `round`, `lerp`, NaN tests, and device-property validity branches.

Dial behavior was also checked against the current Logic Switch / Kit (Switch) pages: Dial `Mode` controls its maximum Setting, `Setting` is integral, and `Ratio` exposes the normalized position used by the Resolver for linear scaling.


The ControllerSequencer family was also checked against the current IC10 guidance describing state machines as the appropriate structure for ordered multi-step processes. The reference example contrasts continuous filtration logic with a phase-change purification cycle that pressurizes, waits, drains, transfers, and repeats. This is the design rationale for using a state-machine family as the framework's first non-feedback production controller.

Relevant references:

- Stationeers Community Wiki, `IC10`: https://stationeers-wiki.com/IC10
  - current Stack Memory documentation specifies 512 values (`S0..S511`), used to validate the expanded 64-controller Directory/Catalog bank layouts.
- Stationeers Community Wiki, `IC10/instructions`: https://www.stationeers-wiki.com/IC10/instructions
- Stationeers Community Wiki, `Filtration`: https://stationeers-wiki.com/Filtration

The current Integrated Circuit reference also documents that IC10 registers and stack values are retained across reflashing and power events. New runtimes therefore explicitly initialize every persistent register whose starting value matters instead of assuming zeroed registers.

- Stationeers Community Wiki, `Integrated Circuit (IC10)`: https://www.stationeers-wiki.com/Integrated_Circuit_%28IC10%29

## Instruction set provenance

The authoritative mnemonic/signature list is vendored as `ic10_instruction_set.json` and enforced by
`validation/validators/validate_ic10_opcodes.py`. It is extracted from Stationeers **game data**
(Stationpedia command definitions) by the WikiExtractorMod BepInEx mod, not transcribed from wiki
prose, and carries the source commit and extraction date. Refresh it by re-exporting against the
running game or re-pulling the recorded source path, then rerun that validator.

**Do not use the community wiki's instruction list to conclude that an instruction does not exist.**
That page is lossy: it omits `ld`, `sd`, `sne` and `snez`, all four of which are present in game data
with current signatures (`ld r? id(r?|id) logicType`, `sd id(r?|id) logicType r?`). The wiki remains
useful for prose semantics; game data is authoritative for existence and operand counts.

The framework's minimum compatible game build is **2026-07-02**. `clamp` was introduced by that
update alongside `ror`, `rol` and `sgn`; `bdnvl`, `bdnvs` and `lerp` require the 2025-09-15 update.
Earlier builds cannot run this framework. The current target is **0.2.6428.27798**, the hotfix
published 2026-08-13.

Target the 2026-08-13 hotfix rather than the 2026-08-12 Power Line Update it patches. That hotfix
fixes saves failing to load in some cases. Item 12 exercises A/B bank recovery, reflash behaviour and
interruption handling, all of which route through save/load, so a save-load defect in the base build
would be indistinguishable from a framework persistence bug. Nothing warns about this: commissioning
sessions are fingerprint-bound to framework source, not to a game version.

No instruction changed after 2026-07-02. The Power Line Update's only IC10 entries correct
Stationpedia text for `bapal`, `acos` and `bnaal`, none of which this framework uses. Its substantive
changes sit under the framework rather than in it: cable networks now unify across Power Pylons, so a
pylon link merges two device populations into one network and can push a Controller Directory into
its 64-entry overflow path; `StructureNetwork` was reparented onto a new `ReferenceableNetwork` base
class; and multiplayer now sends pipe/chute/cable values only when they change, so client-observed
values may lag differently from server-side IC execution during live verification.

Indirect addressing deserves live scrutiny rather than trust: the 2025-09-15 notes state that `dr`
use "is not fully supported yet", 2025-09-23 fixed indirect addressing, and 2026-07-02 fixed
indirect register resolution in `l`/`s` specifically. The framework uses 35 `drN` and 35 `rrN`
operands, and no deterministic model can confirm that behaviour.

## Phase-pressure references

The PhasePressure family was checked against current phase-change documentation in August 2026. The relevant game-model points are:

- all phase-changing media have pressure/temperature-dependent liquid/gas boundaries;
- the dedicated Condensation and Evaporation Chambers are pressure-setpoint devices;
- the normal liquid-region pressure curve is represented by medium-specific `A` and `B` coefficients;
- current Water Stationpedia data lists a normal-liquid window of 273.15 K through 643 K with 6.3 kPa minimum condensation pressure and 6000 kPa maximum liquid pressure;
- phase transition rate depends on more than the boundary pressure, including quantity and available latent-energy transfer.

Relevant references:

- Stationeers Community Wiki, `Phase Change Mechanics`: https://stationeers-wiki.com/Phase_Change_Mechanics
- Stationeers Community Wiki, `Condensation Chamber`: https://stationeers-wiki.com/Condensation_Chamber
- Stationeers Community Wiki, `Module:Gas/data`: https://stationeers-wiki.com/Module:Gas/data
- Stationeers Community Wiki, `Module:Gas/doc`: https://stationeers-wiki.com/Module:Gas/doc
- Stationeers Community Wiki, `Water`: https://stationeers-wiki.com/Water
- Stationeers Community Wiki, `Phase Change guide`: https://stationeers-wiki.com/Phase_Change_guide

The Community Wiki warns that phase-change details can change with patches. Treat medium constants as versioned game data and revalidate profiles after major atmospherics/phase-change updates.

## Phase-medium library references

The initial working-medium library was expanded in August 2026 using the current Community Wiki `Module:Gas/data` coefficients and current medium/Stationpedia phase-window values. The current generated practical set is Water, Pollutant, Silanol, Nitrous Oxide, Nitrogen, Methane, Carbon Dioxide, Oxygen, and Hydrogen.

Selection rationale was also checked against the current `Coolant` page. It describes Silanol as a premium broad-range phase-change medium, Pollutant as common and broadly useful despite its high pressure requirement, and the cryogenic fluids as having substantially lower liquid temperature windows. The Nitrogen page and historical phase-change patch notes specifically call out Nitrogen's usefulness in creating and maintaining other cryogenic liquids.

Relevant references:

- `Module:Gas/data`: https://stationeers-wiki.com/Module:Gas/data
- `Module:Gas/doc`: https://stationeers-wiki.com/Module:Gas/doc
- `Coolant`: https://stationeers-wiki.com/Coolant
- `Pollutant`: https://stationeers-wiki.com/Pollutant
- `Silanol`: https://stationeers-wiki.com/Silanol
- `Nitrous Oxide`: https://stationeers-wiki.com/Nitrous_Oxide
- `Nitrogen`: https://stationeers-wiki.com/Nitrogen
- `Methane`: https://stationeers-wiki.com/Methane
- deprecated `Volatiles` redirect: https://stationeers-wiki.com/Volatiles
- `Carbon Dioxide`: https://stationeers-wiki.com/Carbon_Dioxide
- `Oxygen`: https://stationeers-wiki.com/Oxygen
- `Hydrogen`: https://stationeers-wiki.com/Hydrogen

The profile files intentionally use the **current gas identity names** (`Methane`, not deprecated `Volatiles`) and game-model values rather than real-world constants.


## Pressure-domain references

The PressureDomain layer was checked against current Stationeers pressure-device and phase-device behavior in August 2026. The control assumptions used by the reference topology are:

- a Pressure Regulator transfers gas from its input network until its **output** reaches the configured Setting;
- a Back Pressure Regulator transfers gas away when its **input** exceeds the configured Setting;
- both expose writable `Setting` and `On`;
- current gas-pipe pressure limits are about 60.795 MPa / 60795 kPa, but framework defaults remain deliberately lower and deployment-specific;
- an Evaporation Chamber sends gas to its output when chamber pressure exceeds its setpoint;
- a Condensation Chamber pulls gas from its input toward its pressure setpoint.

These semantics support the reference local-domain pair: Pressure Regulator from a higher-pressure source **into** the domain and Back Pressure Regulator from the domain **out** to a lower-pressure sink. The pair maintains a target only when suitable source/sink pressure already exists; it is not a compressor.

Relevant references:

- `Pressure Regulator`: https://stationeers-wiki.com/Pressure_Regulator
- `Back Pressure Regulator`: https://stationeers-wiki.com/Back_Pressure_Regulator
- `Kit (Pressure Regulator)`: https://stationeers-wiki.com/Kit_%28Pressure_Regulator%29
- `Pipes`: https://www.stationeers-wiki.com/Pipes
- `Pipe Analyzer`: https://www.stationeers-wiki.com/Pipe_Analyzer
- `Evaporation Chamber`: https://stationeers-wiki.com/Evaporation_Chamber
- `Condensation Chamber`: https://www.stationeers-wiki.com/Condensation_Chamber
- `Phase Change Mechanics`: https://stationeers-wiki.com/Phase_Change_Mechanics

The Back Pressure Regulator documentation notes relatively low flow versus active vents/turbo pumps for emergency dumping. PressureDomain therefore treats target pressure as a requirement and does not claim source/sink capacity or convergence. The new Level-3 PressureTransfer layer now owns active capacity-aware cross-domain transfer; PressureDomain itself still does not claim transfer capacity.


## Pressure-transfer/grid mechanics checked August 2026

The Level-3 grid design was checked against current Stationeers documentation before implementation:

- IC10 has 16 internal CPU registers (`r0..r15`) plus `ra` and `sp`; `db` addresses the IC housing. The framework validator now rejects direct references to nonexistent CPU/device registers.
- IC10 programs have a 128-line / 90-character-per-line / 4096-byte limit, and execution automatically yields after 128 executed lines. This supports the coordinator's one-provider-per-tick incremental scan.
- Registers and stack persist across reflashing/power events, so grid scripts explicitly initialize scan/control state rather than assuming zeroed memory.
- Turbo Volume Pump (Gas) exposes `Setting`, `Maximum`, `On`, and `Mode`, with a current adjustable range up to 100 L/tick and power scaling with Setting. PressureTransfer reads `Maximum`, writes only `Setting`/`On`, and treats direction/Mode as physical commissioning state.
- Standard gas Volume Pump uses the same volume-per-tick concept at lower capacity. The transfer Runtime therefore caps planned flow to both configured maximum and device `Maximum` rather than hard-coding 100 L/tick.
- Fixed Small/Large Tanks are integrated into their connected pipe network and currently provide roughly 6000 L / 50000 L capacity. They have no data port, so a Pipe Analyzer on the same network is the practical observation device for a STORAGE PressureDomain.
- Gas pipes/tanks operate under the current roughly 60.795 MPa pipe-network pressure ceiling; deployment-specific PressureDomain min/max values must remain conservative plant policy rather than blindly using the absolute structural limit.

These sources justified the original pressure-proxy grid abstraction. The current inventory-aware revision now uses the Pipe Analyzer's documented `Pressure`, `Temperature`, `Volume`, `TotalMoles`, and `VolumeOfLiquid` outputs and the documented gas-transfer relationship `n = P*V/(R*T)` with `R=8.3144` to express LOW/HIGH/STORAGE capacity in moles. PressureTransfer still commands a volume pump in L/tick, but converts the capped Setting back into planned mol/tick using current source gas density before the coordinator ranks links.

Additional current references used for the inventory revision:

- `Pipe Analyzer`: https://www.stationeers-wiki.com/Pipe_Analyzer
- `Pipe Volume Pump`: https://stationeers-wiki.com/Pipe_Volume_Pump
- `Tank`: https://www.stationeers-wiki.com/Tank

The current Tank reference lists 6000 L for the Small Tank and 50000 L for the Large Tank and notes that fixed tanks are part of the connected pipe network. Those volumes illustrate why equal kPa margins do not imply equal inventory.

## Pressure-grid route-cost references

- Stationeers Community Wiki — **Pipe Volume Pump**: current documentation states the standard gas Volume Pump uses `Setting * 20 W`, operates in liters per tick, and gives `n = P*V/(R*T)` for moles transferred. This is why the current route score is explicitly dimensionless rather than claiming that positive pressure lift maps directly to pump electrical work.
- Stationeers Community Wiki — **Turbo Volume Pump (Gas)**: current data-network documentation exposes `Setting`, `Maximum`, `Ratio`, `On`, and `RequiredPower`; the framework continues to use the common `Setting`/`Maximum` interface and does not assume an undocumented pressure-dependent energy model.

## Generic Resource / MaterialGrid references

The first Resource Core and MaterialGrid slice was checked against current Stationeers data-network and slot behavior in August 2026.

Relevant references:

- `IC10/instructions`: https://www.stationeers-wiki.com/IC10/instructions
  - documents `ls` slot reads, `Quantity`, `OccupantHash`, and dynamic device access concepts used by the material inventory implementation.
- `Vending Machine Refrigerated`: https://www.stationeers-wiki.com/Kit_%28Vending_Machine_Refrigerated%29
  - documents 100 internal storage slots at indices `2..101`, plus `Occupied`, `OccupantHash`, `Quantity`, and the device `ImportCount`/`ExportCount` counters.
- `Logic Sorter`: https://www.stationeers-wiki.com/Logic_Sorter
  - documents prefab-hash filtering, Mode behavior, accept/reject outputs, import/export counters, and slot identity/quantity fields used by the active Material Feeder.
- `IC10`: https://stationeers-wiki.com/IC10
  - includes the current bit-shift/or example for constructing `FilterPrefabHashEquals`, matching the filter encoding used by the Material Feeder.
- `Stacker`: https://stationeers-wiki.com/Stacker
  - documents Mode 1 hold behavior, `Setting`, `Output`, and ImportCount/ExportCount; this is the exact-quantity boundary used to split an oversized Vending-emitted stack before committed delivery.
- `Vending Machine`: https://stationeers-wiki.com/Vending_Machine
  - documents `RequestHash` immediate output plus internal storage slots 2..101; the source warehouse and active Feeder both depend on this behavior.
- `Kit (Arc Furnace)`: https://stationeers-wiki.com/Special%3AMyLanguage/Kit_%28Arc_Furnace%29
  - current page exposes `Activate`, `Power`, `Error`, `ImportCount`, `ExportCount`, `PrefabHash`, `Reagents`, and `RecipeHash`. Its data-network section warns that some details are outdated, so the first Transform runtime uses only the small subset verified by live-game hardening/tests and does not claim complex recipe-condition automation.
- `Autolathe`: https://stationeers-wiki.com/Autolathe
  - documents `RecipeHash`, `Reagents`, `CompletionRatio`, `ImportCount`, `ExportCount`, and `RequiredPower`, which are the observability/execution surface used by the implemented printer manufacturing path.
- `Ore (Iron)`: https://www.stationeers-wiki.com/Ore_%28Iron%29
- `Ore (Copper)`: https://www.stationeers-wiki.com/Ore_%28Copper%29
- `Ore (Gold)`: https://www.stationeers-wiki.com/Ore_%28Gold%29
- `Ingot (Iron)`: https://stationeers-wiki.com/Ingot_%28Iron%29
- `Ingot (Copper)`: https://stationeers-wiki.com/Ingot_%28Copper%29
- `Ingot (Gold)`: https://stationeers-wiki.com/Ingot_%28Gold%29
  - these pages provide the starter ItemHash and stack-size metadata used by the ITEM_STACK records in `resource_profiles.json`.

The current material profiles are intentionally generated from local versioned data rather than being hand-maintained independently of tests and documentation. Material transport and capability-based furnace transform behavior are covered by direct IC10 execution tests, but `docs/FRAMEWORK_HARDENING_TESTS.md` still requires in-game verification of chute timing, Stacker split behavior, sorter routing, jams, and Arc Furnace output timing.

## Cargo LArRE storage access

The Item Storage subsystem relies on the Stationeers LArRE behavior documented by current community/official update material: Cargo LArRE is intended for slot-based tasks such as pulling items from lockers; `TargetSlotIndex` selects the target slot; proxy slot 255 exposes the selected target slot to logic; `Setting` selects a rail station; `Idle` reports movement/action completion; and `Activate` operates the claw.

References:

- Stationeers Community Wiki, LArRE: https://stationeers-wiki.com/LARrE
- Stationeers update v0.2.5195.23625 / LArRE Reloaded: https://stationeers-wiki.com/Update_v0.2.5195.23625
- Developer-tracker mirror of LArRE Reloaded notes: https://devtrackers.gg/stationeers/p/89965d2d-larre-reloaded

## Item storage / SDB references

Item 7 was checked against current Stationeers storage-device behavior in August 2026.

- `Kit (SDB Silo)`: https://stationeers-wiki.com/Kit_%28SDB_Silo%29
  - documents capacity up to 600 stacks, import/export/internal slots, `Quantity` as **number of occupied slots/stacks**, `ImportCount`, `ExportCount`, `Lock`, and writable `Open`; the current page notes `Open` returns to its default after action. This is why `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` publishes conservative lower-bound quantities and `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` fences one FIFO export action by Stacker ImportCount rather than treating SDB `Quantity` as exact total items.
- `LArRE`: https://stationeers-wiki.com/LARrE
- `Update v0.2.5195.23625 / LArRE Reloaded`: https://stationeers-wiki.com/Update_v0.2.5195.23625
  - Cargo LArRE uses station `Setting`, `TargetSlotIndex`, proxy slot 255, `Idle`, and `Activate`; the framework revalidates proxy ItemHash and exact Quantity immediately before pickup.
- `Powered Chute Import Bin` / powered chute devices: https://stationeers-wiki.com/Chutes
  - chute handoff devices are treated as transport boundaries, not as the warehouse inventory authority.
- `Stacker`: https://stationeers-wiki.com/Stacker
  - exact output `Setting` remains the quantity-metering boundary after Vending or SDB source stacks enter the active material path.


## Item 11 process-utility mechanics

Current public Stationeers references used for the bounded Item-11 physical model:

- Stationeers Community Wiki, **Advanced Furnace** — integrated inlet/output pump behavior and exposed pressure/temperature/settings: https://stationeers-wiki.com/Advanced_Furnace
- **Advanced Furnace/AllRecipes** — current alloy pressure/temperature windows used to cross-check generated transform data: https://stationeers-wiki.com/Advanced_Furnace/AllRecipes
- **Furnace temperature and pressure math** — gas/fuel/diluent and thermal relationships: https://stationeers-wiki.com/Furnace_temperature_and_pressure_math
- **Pipe Gas Mixer** — temperature-corrected mole-ratio and hot/cold mixing formulas: https://stationeers-wiki.com/Pipe_Gas_Mixer
- **Gas Fuel Generator** — current mole/feed behavior and ambient operating envelope: https://stationeers-wiki.com/Kit_%28Gas_Fuel_Generator%29
- **Electrolyzer** — 2:1 Volatiles/Oxygen output composition: https://stationeers-wiki.com/Kit_%28Atmospherics%29_Electrolyzer
- **IC10 instructions** — `bdnvl`/`bdnvs` mean branch when a LogicType is not valid to load/store: https://stationeers-wiki.com/IC10/instructions

These references guide the physical specialization only. Live-game commissioning remains authoritative for exact device availability, property writability, timing, and numerical behavior on the target game build.

## Item-12 commissioning probe reference

The live commissioning snapshot probe was rechecked against the current Stationeers Community Wiki IC10 instruction reference in August 2026. The current documentation permits register-addressed `get` stack reads, device indirection through `drN`, and dynamically selected LogicType values for `l`/`s`. The probe uses those mechanisms only for read-only observation and never writes an observed device.

- `IC10`: https://stationeers-wiki.com/IC10
- `IC10/instructions`: https://stationeers-wiki.com/IC10/instructions
