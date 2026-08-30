# Phase-Medium Profiles in the Unified Resource Catalog

Phase-medium data is now one `ProfileKind` inside the shared Resource Profile system rather than one IC10 program per working medium. `ControllerPhasePressure`, `ControllerPressureDomain`, the grid planner, and the Purity Guard consume `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10`.

The canonical source is `data/resource_profiles.json`. `tools/generate/generate_resource_profiles.py` emits ResourceClass-partitioned relocatable Loader candidates. Runtime placement currently puts the nine FLUID phase media in one Store and the 27 ITEM material profiles across two Stores (26+1). Loaders self-clear only their own candidate stacks, keep each 16-cell profile whole, write only non-zero cells, publish Ready last, and terminate; the Loader Router assigns them and each Generic Store pulls its assigned candidates. See `docs/RESOURCE_PROFILES.md` for the Store/View ABIs, loader mechanics, publication checks, and extension rules.

## Phase-medium record layout

The View publishes a phase record as:

```text
S0   magic = 31415963
S1   View ABI = 1
S28  status = 1 while valid
S29  publication generation; positive only while the record is valid
S8   ResourceClass = 1 FLUID
S9   MediumType hash
S10  Unit = 1 MOLE
S11  ProfileKind = 1 PHASE_MEDIUM
S12  ProfileSchema = 2
S13  phase coefficient A
S14  phase exponent B
S15  triple/minimum liquid pressure, kPa
S16  critical/maximum liquid pressure, kPa
S17  freezing/minimum liquid temperature, K
S18  critical/maximum liquid temperature, K
S19  Pipe Analyzer gas-ratio LogicType
S20  minimum accepted gas purity ratio
S21  latent heat, J/mol
S22  CatalogId
```

Consumers capture a positive `S29`, read the payload, and require the same `S29` afterward. If the selected identity disappears, the catalog is incomplete, or the View cannot resolve a coherent record, it clears `S29` to zero before publishing the error status.

The default purity threshold for the included phase records is `0.995`. It is a deployment safety policy, not part of the phase equation. The Purity Guard dynamically reads `S19` from the View and requires the observed ratio to meet `S20` whenever the bus contains gas.

## Included phase-medium records

| Medium | ResourceType | Ratio LogicType | Liquid window (K) | Pressure window (kPa) | Latent heat (J/mol) | Operational note |
|---|---|---|---:|---:|---:|---|
| Water | `HASH("Water")` | `RatioSteam` | 273.15–643 | 6.3–6000 | 8000 | High latent heat; useful above freezing when water resource use is acceptable. |
| Pollutant | `HASH("Pollutant")` | `RatioPollutant` | 173.32–425 | 1800–6000 | 2000 | Practical broad-range working fluid; common and otherwise low-value, but requires relatively high pressure. |
| Silanol | `HASH("Silanol")` | `RatioSilanol` | 143.359–822.729 | 516–6000 | 10000 | Very broad temperature span and high latent heat; excellent premium medium when supply permits. |
| Nitrous Oxide | `HASH("NitrousOxide")` | `RatioNitrousOxide` | 252.1–430.6 | 800–2000 | 4000 | Strong medium-temperature performance; valuable/reactive oxidizer, so use deliberately. |
| Nitrogen | `HASH("Nitrogen")` | `RatioNitrogen` | 40.01–190 | 6.3–6000 | 500 | Inert cryogenic/cascade medium. |
| Methane | `HASH("Methane")` | `RatioMethane` | 81.6–195 | 6.3–6000 | 1000 | Cryogenic medium overlapping Nitrogen; combustible. |
| Carbon Dioxide | `HASH("CarbonDioxide")` | `RatioCarbonDioxide` | 217.82–265 | 517–6000 | 600 | Abundant but comparatively narrow liquid window. |
| Oxygen | `HASH("Oxygen")` | `RatioOxygen` | 56.416–162.2 | 6.3–6000 | 800 | Deep-cryogenic option; oxidizer and often strategically valuable. |
| Hydrogen | `HASH("Hydrogen")` | `RatioHydrogen` | 15.1767–70.0552 | 6.3–6000 | 200 | Very-low-temperature cascade medium; extends the library below Oxygen/Nitrogen, with low latent heat. |

## Selection guidance

Choose a working medium by the temperature region the phase-change device must span, available pressure infrastructure, inventory/sourcing, safety/resource value, and the ability to keep the pressure domain sufficiently pure. There is no single universally best medium.

- **Pollutant** remains the practical default for many moderate-temperature experiments when the high pressure range is acceptable.
- **Water** has excellent latent heat and is attractive above its freezing boundary.
- **Silanol** is the broad-range premium option.
- **Nitrous Oxide** is thermodynamically useful but also valuable/reactive.
- **Nitrogen and Methane** cover cryogenic cascade work.
- **Oxygen** reaches deeper cryogenic temperatures but is an oxidizer.
- **Hydrogen** extends the phase library to very-low-temperature cascade stages; its low latent heat means it should be selected for temperature reach rather than bulk heat transport.
- **Carbon Dioxide** is useful when abundant and its narrow liquid window matches the job.

## Phase-boundary calculation

Within the supported normal-liquid window the runtime uses:

```text
Pboundary = A * Temperature^B
Pboundary = clamp(Pboundary, TriplePressure, CriticalPressure)
```

The profile deliberately does not claim validity for every frozen, supercooled, supercritical, or chemically asymmetric state. `ControllerPhasePressure` reports a range fault outside `S17..S18` rather than extrapolating the simple model.

## Constants by medium

### Water

```text
MediumType           HASH("Water")
GasRatioLogicType    RatioSteam
MinimumPurity        0.995
A                    3.8782059839e-19
B                    7.90030107708
TriplePressure       6.3 kPa
CriticalPressure     6000 kPa
FreezingTemperature  273.15 K
CriticalTemperature  643 K
LatentHeat           8000 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Pollutant

```text
MediumType           HASH("Pollutant")
GasRatioLogicType    RatioPollutant
MinimumPurity        0.995
A                    2.079033884
B                    1.31202194555
TriplePressure       1800 kPa
CriticalPressure     6000 kPa
FreezingTemperature  173.32 K
CriticalTemperature  425 K
LatentHeat           2000 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Silanol

```text
MediumType           HASH("Silanol")
GasRatioLogicType    RatioSilanol
MinimumPurity        0.995
A                    0.48388429552357676
B                    1.4041336082044964
TriplePressure       516 kPa
CriticalPressure     6000 kPa
FreezingTemperature  143.35886137639 K
CriticalTemperature  822.72854867724 K
LatentHeat           10000 J/mol   # documentation/planning metadata, not stored in ABI2
```

### NitrousOxide

```text
MediumType           HASH("NitrousOxide")
GasRatioLogicType    RatioNitrousOxide
MinimumPurity        0.995
A                    0.065353501531
B                    1.70297431874
TriplePressure       800 kPa
CriticalPressure     2000 kPa
FreezingTemperature  252.1 K
CriticalTemperature  430.6 K
LatentHeat           4000 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Nitrogen

```text
MediumType           HASH("Nitrogen")
GasRatioLogicType    RatioNitrogen
MinimumPurity        0.995
A                    5.5757107833e-07
B                    4.40221368946
TriplePressure       6.3 kPa
CriticalPressure     6000 kPa
FreezingTemperature  40.01 K
CriticalTemperature  190 K
LatentHeat           500 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Methane

```text
MediumType           HASH("Methane")
GasRatioLogicType    RatioMethane
MinimumPurity        0.995
A                    5.863496734e-15
B                    7.8643601035
TriplePressure       6.3 kPa
CriticalPressure     6000 kPa
FreezingTemperature  81.6 K
CriticalTemperature  195 K
LatentHeat           1000 J/mol   # documentation/planning metadata, not stored in ABI2
```

### CarbonDioxide

```text
MediumType           HASH("CarbonDioxide")
GasRatioLogicType    RatioCarbonDioxide
MinimumPurity        0.995
A                    1.579573e-26
B                    12.195837931
TriplePressure       517 kPa
CriticalPressure     6000 kPa
FreezingTemperature  217.82 K
CriticalTemperature  265 K
LatentHeat           600 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Oxygen

```text
MediumType           HASH("Oxygen")
GasRatioLogicType    RatioOxygen
MinimumPurity        0.995
A                    2.6854996004e-11
B                    6.49214937325
TriplePressure       6.3 kPa
CriticalPressure     6000 kPa
FreezingTemperature  56.416 K
CriticalTemperature  162.2 K
LatentHeat           800 J/mol   # documentation/planning metadata, not stored in ABI2
```

### Hydrogen

```text
MediumType           HASH("Hydrogen")
GasRatioLogicType    RatioHydrogen
MinimumPurity        0.995
A                    3.18041e-05
B                    4.4843872973
TriplePressure       6.3 kPa
CriticalPressure     6000 kPa
FreezingTemperature  15.1767057463 K
CriticalTemperature  70.0551551908 K
LatentHeat           200 J/mol   # documentation/planning metadata, not stored in ABI2
```

## Purity and intended-medium identity

The PhasePressure controller still receives a profile intentionally; it does not auto-discover which thermodynamic model to use. The grid, however, no longer trusts that label by itself. `Pressure Medium Purity Guard` checks the actual Pipe Analyzer composition using the profile-selected ratio property before Inventory can advertise moles.

This separation is deliberate:

```text
Profile -> what medium this domain is intended to model
Analyzer ratio -> what gas is actually present
Purity Guard -> whether those two facts are compatible
```

Changing a profile while a domain contains another medium therefore results in zero schedulable inventory once purity enforcement is wired correctly.

## Adding or changing a medium

1. Update the phase-medium record in `data/resource_profiles.json`; do not hand-edit the generated Catalog Store/loaders.
2. Provide the medium ResourceType, gas-ratio LogicType, A/B coefficients, triple/critical pressures, liquid temperature window, and purity policy.
3. Keep `ResourceClass=FLUID`, `Unit=MOLE`, `ProfileKind=PHASE_MEDIUM`, and schema 2 unless the parameter contract itself changes.
4. Run `tools/generate/generate_resource_profiles.py`.
5. Run `tests/test_phase_pressure_protocol.py`, `tests/test_ic10_execution.py`, and the full validation suite.
6. Commission the selected View against a real Pipe Analyzer before unattended grid operation.

## Deferred media and asymmetric fluids

Ozone, Hydrazine, Hydrochloric Acid, Alcohol, Sodium Chloride, and other fluids are not prohibited by the architecture. They are deferred until a real use case justifies profile data and any special semantics. Fluids whose liquid and gas identities differ should not be forced into the current single-`MediumType` model without explicitly extending the profile schema. Helium does not belong in this phase-change library when it has no applicable reversible phase model in the current game data.

## Source provenance and patch drift

Phase constants and available gas-ratio LogicTypes can change with Stationeers updates. `docs/SOURCES.md` records the references used for this baseline. Treat those values as game-model data, not real-world chemistry, and re-verify them after major game updates. Generated profiles reduce copy drift inside this repository; they do not eliminate upstream game-data drift.
