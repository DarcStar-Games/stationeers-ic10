# Config Policy Contract

A Config Policy contains the **controller-family-specific configuration semantics**. Generic Host owns storage/transactions; Policy owns what the fields mean and whether a candidate is acceptable.

This separation is a central framework rule: adding a new controller schema should require a new/updated Policy, not a fork of the Generic Persistent Config Host.

## Policy responsibilities

A Policy owns:

- ControllerType and schema identity;
- block count and validity masks;
- persistence schema signature;
- complete padded defaults;
- field-level validation;
- cross-field validation;
- enum/integer validation;
- normalization/canonicalization.

A Policy does **not** own:

- Generic Config Host public transaction semantics;
- Editor/Loader/Committer behavior;
- A/B persistence or recovery;
- physical commissioning input handling;
- diagnostics;
- controller selection.

## Wiring

Policy `d0` is the Generic Persistent Config Host instance it configures.

One Host instance is paired with the Policy for that controller instance. The same Policy script can be programmed into multiple ICs, each pointing at a different Host of the same family.

## Initialization/publication

Policy publishes schema metadata and defaults to Host before incrementing Policy generation `S13` last. Consumers can therefore treat `S13` as the “metadata/default set is coherent” marker.

The important metadata is summarized in `docs/PERSISTENCE_STANDARD.md` and `docs/ABI_REFERENCE.md`.

## Request protocol

Generic Committer writes candidate values and then Host `S52`. Policy observes `S52 != S20`.

Policy then:

1. captures the new request generation;
2. loads candidate values from `Host S128..S159`;
3. rejects malformed values such as NaN;
4. applies controller semantic and cross-field validation;
5. normalizes accepted values in place in `Host S128..S159`;
6. zeroes padding/reserved slots as required by the family schema;
7. writes Host `S21 = result`;
8. writes Host `S20 = requestGeneration` **LAST**.

A positive accepted result is `5` in the current families. Negative values are controller-family error codes.

Writing `S20` last is what turns all prior candidate/result writes into one coherent Policy response.

## Validation vs normalization

Policies may do both:

- **Validation** answers “is this candidate allowed?”
- **Normalization** answers “what exact canonical representation should be stored?”

Examples of normalization include forcing boolean values to `0/1`, forcing a direction to `-1/+1`, rounding values that must be integral, or zeroing padding. A runtime should therefore read the Host **effective** image after commit rather than assume the user's staged candidate was stored bit-for-bit unchanged.

## Cross-field validation

Cross-field rules belong in Policy because generic code cannot know their meaning. For PI, examples include ensuring output minimum does not exceed output maximum and integral minimum does not exceed integral maximum.

A good error code should identify the rule class rather than the physical UI mechanism. For example, “invalid output range” is useful whether the value came from a Dial, Memory device, or future input adapter.

## Current policies

- PI uses `ic10/controller-pi/pi_config_policy_v1_0.ic10`.
- ControllerTest is test-only and uses `tests/ic10/framework_test_config_policy_v1_0.ic10`.
- ControllerSequencer uses `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10`.
- ControllerPhasePressure uses `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10`.
- ControllerPressureDomain uses `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10`.
- ControllerPressureTransfer uses `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10`.

ControllerTest proves the mechanics with a deliberately synthetic schema. ControllerSequencer proves the same boundary works for a production state machine. ControllerPhasePressure adds cross-field pressure/factor constraints while keeping medium thermodynamic data outside the Host in a separate PHASE_MEDIUM Resource Profile View. ControllerPressureDomain adds directional domain-role and plant-pressure limits while consuming the same medium identity externally. ControllerPressureTransfer adds per-link deadband/gain/flow limits while topology itself remains screw-defined rather than stored in the Host.


### ControllerPhasePressure Policy rules

Schema 1 contains nine fields over masks `[255,1,0,0]`. The Policy enforces:

- `0 < EvaporationFactor <= 1`;
- `1 <= CondensationFactor <= 10`;
- non-negative `MinimumPressure`;
- `MinimumPressure <= MaximumPressure`;
- `StandbyPressure` inside the configured pressure bounds;
- integral Mode in `0..2`;
- integral output LogicType;
- boolean canonicalization for Enabled and DirectWrite.

The Policy intentionally does **not** validate medium-specific phase limits. Those belong to the PHASE_MEDIUM Resource Profile record. This means the same durable controller schema works with Water, Pollutant, Nitrogen, or future media without changing the controller family.

### ControllerPressureDomain Policy rules

Schema 1 contains eight fields in one block with mask `[255,0,0,0]`. The Policy enforces:

- integral `Role` in `1..2` (`LOW/EVAP` or `HIGH/CONDENSE`);
- non-negative `MinimumPressure`;
- `MinimumPressure <= MaximumPressure`;
- `StandbyPressure` inside the configured bounds;
- boolean canonicalization for `Enabled` and `DirectWrite`.

`PressurizeLogicType` and `DepressurizeLogicType` remain operator-selected numeric LogicType values. The runtime uses property-validity guards before either physical write, so an unsupported property produces runtime status `-2` rather than a half-applied pair.

The Policy does not encode a medium hash. Medium identity comes from the wired Resource Profile View so the same durable schema can be reused for separate Water, Pollutant, Nitrogen, or other pressure domains.

## Adding or changing a Policy

Keep these invariants:

1. Publish complete schema/default metadata before Policy generation.
2. Use masks as authoritative geometry.
3. Validate every active field that requires semantic constraints.
4. Do not assign meaning to padding/reserved slots.
5. Canonicalize accepted candidate data before acknowledging it.
6. Publish result before response generation.
7. Keep persistence signature synchronized with type/schema/block/mask geometry.
8. Update Runtime and Profile expectations together when schema meaning changes.

Run `validation/validators/validate_config_contracts.py` after every Policy/schema change.
