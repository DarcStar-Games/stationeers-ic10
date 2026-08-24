# Configuration Input Path

Configuration reuses the domain-neutral `Generic Input Scanner` and `Generic Input Resolver`. Controller-specific field meaning stays in the Config Policy/Profile; physical device handling stays generic.

```text
Input Profile Loader candidates 92..94 (one-shot sparse own-stack producers)
    |  discovered/imported by
    v
Input Profile Catalog (Coordinator-managed Generic Store)
    |
Input Profile View (selected ControllerType/schema)
    |
physical inputs -> Generic Input Scanner
                    |
             Generic Input Resolver
                    |
             Config Input Bridge
    |
Generic Config Editor
```

## What each component knows

| Component | Knows | Does not know |
|---|---|---|
| Scanner | physical devices, capabilities, Field Dial ordinal | controller field meaning |
| Resolver | Profile descriptors and how to resolve each InputKind | stable config slot meaning |
| Loader | Host masks/schema and active ordinal->slot mapping | how a Dial/Switch is read |
| Config Input Bridge | Resolver ordinal/value + Editor mapping | controller semantics |
| Editor | staged physical image and save/reload/apply UI state | persistence semantics |
| Policy | controller-specific field meaning/validation/defaults | physical input hardware |

This is the main reason a new controller family does not need a new editor or scanner.

## Wiring

1. Run the global Coordinator Core/Loader Router and add one UNCLAIMED `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` with a unique positive NodeId.
2. Program the generated `ic10/input-profile-catalog/input_profile_catalog_loader_*_v4_0.ic10` candidates anywhere on the same discoverable network. They self-clear their own stacks, write only non-zero candidate data, publish readiness last, and terminate; they have no Store screw.
3. Wait until the Coordinator-claimed Store is ACTIVE and reports `S9 LocalItemCount=7` and `S9 LocalItemCount=7`.
4. Connect `ic10/input-profile-catalog/input_profile_view_v5_0.ic10 d0` to the Store. Set View `S2` to the selected controller type hash and `S3` to its config schema. Require positive View `S5`.
5. Connect Field Dial, Value Dial, optional Logic Memory, optional Switch, and the configured Input Profile **View** to the Generic Input Scanner screws.
6. Set Generic Input Resolver `S2` to the Scanner ReferenceId.
7. Set Config Input Bridge `S2` to the Generic Config Editor RefId and `S3` to the Resolver RefId.
8. Set Config Loader `S3` to the Scanner RefId so Loader can discover and validate the Generic Input Profile ABI published by the View.

All controller profiles share the runtime catalog topology. To reuse a physical panel for another family, change View `S2/S3` rather than reflashing a different profile program.

The Config Bridge reads Loader-validated Editor metadata:

```text
Editor S17 active field count
Editor S27 validated Profile RefId
Editor S29 validated Profile generation
```

and configures Resolver accordingly.

## Stable config slots

Resolver returns a contiguous active-field ordinal. Config Bridge maps that ordinal through Editor `S64..S95` to the stable physical image slot derived by Loader from Host validity masks.

It then publishes:

```text
Editor S20 physical slot
Editor S21 resolved value
Editor S22 InputKind
Editor S26 loaded Host snapshot
Editor S25 valid marker LAST
```

Editor Save therefore remains unaware of Dial/Switch/Profile mechanics.

## Human edit cycle

A typical edit is easier to understand as two separate actions: **resolve** and **stage**.

### Resolve

1. Field Dial chooses active ordinal `N`.
2. Scanner publishes the selected ordinal and discovered devices.
3. Resolver loads descriptor `N` from the validated Profile.
4. Resolver chooses the preferred physical device for that InputKind.
5. If the preferred device is absent and Memory is available, Resolver falls back to Memory where permitted.
6. Resolver publishes `(ordinal, resolved value, InputKind)` as one generation-stamped snapshot.

### Stage

1. Config Input Bridge confirms Editor/Host/Profile snapshot consistency.
2. It translates active ordinal `N` through Editor `S64..S95` to a physical slot.
3. It publishes the slot/value into Editor and marks the publication valid last.
4. Save copies that resolved value into the Editor's staged physical image.
5. Apply later sends the full valid staged image to the Host; merely turning a Dial does not modify durable config.

This distinction is important during debugging: a correct Resolver value does not imply the value has been staged, and a staged value does not imply it has been durably applied.

## Catalog-backed PI Profile

PI schema 1 exposes fourteen active fields:

| Field | Preferred input |
|---|---|
| Setpoint | Memory |
| Kp | Linear Dial 0..20 |
| Ki | Linear Dial 0..2 |
| Output min/max | Memory |
| Integral min/max | Memory |
| Bias | Memory |
| Deadband | Linear Dial 0..10 |
| Mode | Switch 0/1 |
| Manual output | Memory |
| Input LogicType | Enum Dial |
| Output LogicType | Enum Dial |
| Direction | Switch -1/+1 |

If a preferred Value Dial/Switch is missing, Resolver falls back to Memory when a Memory-like input is available.

The enum controls use numeric tables in the Profile because IC10 cannot recover a human symbolic LogicType name from a stored hash. The Profile therefore acts as the curated list of allowed choices.


## Catalog-backed PhasePressure Profile

PhasePressure schema 1 exposes nine fields:

| Field | Preferred input |
|---|---|
| Enabled | Switch |
| Mode | Enum Dial: HOLD / EVAPORATE / CONDENSE |
| EvaporationFactor | Linear Dial 0.05..1 |
| CondensationFactor | Linear Dial 1..2 |
| MinimumPressure | Linear Dial 0..6000 kPa |
| MaximumPressure | Linear Dial 0..6000 kPa |
| StandbyPressure | Linear Dial 0..6000 kPa |
| OutputLogicType | Enum Dial: Setting / PressureSetting |
| DirectWrite | Switch |

The 0..6000 kPa Dial ranges are commissioning conveniences, not hard schema maxima. A Memory-like input can stage values outside the Dial's convenience range when the Policy permits them. Deployment-specific pressure limits should be chosen from the actual connected plant, not inferred from the UI Dial range.

The working medium is deliberately **not** another config field. It is supplied through the separate Resource Profile View so thermodynamic data is not copied into each Host image.

## Catalog-backed PressureDomain Profile

`ic10/input-profile-catalog/input_profile_view_v5_0.ic10` exposes eight active controls matching the one-block PressureDomain schema:

1. Enabled — Switch.
2. Role — Enum: LOW/EVAP (`1`) or HIGH/CONDENSE (`2`).
3. MinimumPressure — Linear Dial / Memory.
4. MaximumPressure — Linear Dial / Memory.
5. StandbyPressure — Linear Dial / Memory.
6. PressurizeLogicType — Enum of writable pressure-setting properties.
7. DepressurizeLogicType — same enum.
8. DirectWrite — Switch.

The Profile intentionally does not contain MediumType. The working medium is selected by wiring a PHASE_MEDIUM Resource Profile View to the Runtime, keeping physical medium identity outside the durable operator configuration.

## Troubleshooting by layer

When an edit looks wrong, identify the first layer where state diverges:

1. **Scanner** — did it discover the expected physical device and publish the expected Field Dial ordinal?
2. **Resolver** — did it select the intended descriptor/InputKind and resolve the expected value?
3. **Bridge** — did the active ordinal map to the correct physical slot?
4. **Editor** — did Save update staging and increment staging revision?
5. **Committer/Host** — did Apply publish a request and get a response?
6. **Policy** — was the candidate rejected or normalized?
7. **Runtime** — did it observe the new Host effective generation?

This is usually faster than debugging the full path at once.
