# Shared Input System

## Goal

Configuration and diagnostics use the same physical-input machinery. Device classification, Dial scaling, integer quantization, Switch mapping, enum lookup, Memory fallback, and snapshot coherence live in one generic Scanner/Resolver pair.

The result is a small input “driver layer”: higher-level components ask for logical control N and receive a resolved value without caring which screw has a Dial or whether the value came from a fallback Memory device.

## Physical panel

The Scanner loops all six screws. Roles are capability-driven:

- first writable-Mode/readable-Ratio Dial => **Field Dial**;
- second Dial => **Value Dial**;
- readable-Open device => **Switch**;
- other readable-Setting device => **Memory fallback**;
- IC housing with stack identity `HASH("InputProfileView.v1")` and ABI 1 => **Input Profile**.

The first/second Dial distinction is deterministic screw order. Other device roles may occupy any remaining screws.

### Why capability-driven classification

The Scanner does not depend on one hard-coded prefab for every input role. It asks “can this device provide the properties this role needs?” This makes the physical panel more reusable while still publishing exact ReferenceIds after classification.

A device is classified once per Scanner hardware snapshot. Higher layers consume the resulting identity/capability record rather than probing screws independently.

## Field Dial vs Value Dial

The two dials have different jobs:

- **Field Dial** selects *which logical control* is being edited.
- **Value Dial** supplies a value for descriptor kinds that use a Dial.

Resolver tells Scanner how many logical controls are active. Scanner then sets Field Dial Mode to `count - 1` and publishes a 1-based ordinal.

This means a controller Profile can have 14 fields while Diagnostic Profile has 7, using the same physical panel.

## Scanner -> Resolver

Scanner publishes exact ReferenceIds and a generation-stamped hardware snapshot. Resolver writes the logical control count to Scanner `S9`. Scanner configures Field Dial and publishes selected ordinal at `S10`.

Resolver receives:

```text
S8  Scanner RefId
S9  logical control count
S10 Profile RefId or 0
```

and publishes:

```text
S11 ready/fault status
S12 snapshot generation LAST
S13 logical ordinal
S14 resolved value
S15 input kind
```

One Scanner/Resolver pair should serve one active commissioning context at a time because Resolver owns Scanner requested control count and the active Profile context.

## Catalog-backed profile selection

The Scanner still recognizes the stable Generic Input Profile ABI (`HASH("InputProfileView.v1")`), but current profile definitions no longer each require a dedicated IC stack. All six production/diagnostic definitions fit one runtime-placed Coordinator-managed Store today. The physical node runs `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` and is claimed from the UNCLAIMED pool. Three one-shot sparse Loader ABI5 candidates publish whole-profile data on their own zero-initialized stacks; the Router assigns them and the Store pulls/imports them. `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` selects one `[ContextType, schema]` entry and materializes its descriptors/enum cells into the stable Generic Input Profile ABI.

Typical View requests are:

```text
HASH("ControllerPI"), 1
HASH("ControllerSequencer"), 1
HASH("ControllerPhasePressure"), 1
HASH("ControllerPressureDomain"), 1
HASH("ControllerPressureTransfer"), 1
HASH("DiagnosticMapping"), 1
```

The production Input Profile Catalog contains only production/diagnostic contexts. ControllerTest uses the standalone fixture under `tests/ic10/`; multiple production Views may share the one Store when configuration and diagnostics need simultaneous profile surfaces.

## Input Profile descriptors

A Profile descriptor tells Resolver how logical field N should be interpreted. Descriptor N starts at:

```text
S32 + 4 * (N - 1)
```

with:

```text
+0 InputKind
+1 minimum / OFF value / enum table base
+2 maximum / ON value / enum count
+3 Dial step count / auxiliary value
```

The Profile is metadata, not stored configuration. Reflashing/changing a Profile can change the commissioning UX without directly rewriting a controller's durable config.

## Input kinds

### 0 — Logic Memory

Reads `Setting` directly. This is the universal fallback when a preferred input is missing or the context has no Profile.

Use it for arbitrary numeric values where Dial range/quantization would be inconvenient.

### 1 — Linear Dial

Resolver sets Value Dial Mode from descriptor `aux`, reads `Ratio`, and evaluates:

```text
lerp(min, max, Ratio)
```

No rounding occurs. Use this for continuous/scaled values such as PI gains.

### 2 — Integer Dial

Uses the same linear mapping, followed by intentional `round` of the resolved value.

Use this for bounded integer choices where the numeric value itself is meaningful.

### 3 — Switch

`Setting > 0` selects descriptor maximum; otherwise descriptor minimum.

This supports both normal booleans (`0/1`) and two-state semantic mappings such as PI direction (`-1/+1`).

### 4 — Enum Dial

Value Dial `Setting` is an ordinal. Resolver uses it to index the Profile's numeric enum table. No rounding is needed because Dial Setting is already integral.

Use Enum Dial when the allowed values are sparse or non-linear — for example a curated list of writable LogicTypes.

## Preferred-device fallback

A descriptor expresses the preferred input style. If that device is unavailable, Resolver can fall back to the Scanner's Memory-like device. This keeps a configuration field editable even if the user has only a Logic Memory available.

The fallback is deliberately centralized in Resolver. Domain bridges should never duplicate “if Dial missing, try Memory” logic.

## Coherence

Resolver captures Scanner generation before resolving and rechecks it before publishing. If a Profile is present, its generation is captured and rechecked as well. Any change causes the partial result to be discarded and retried.

The final Resolver snapshot generation is written last so bridges never need to consume a torn `(ordinal, value, kind)` tuple.

### Example of a torn read that is prevented

Without generation checks:

1. Resolver reads Field Dial ordinal 2.
2. Scanner rescans because a device is removed.
3. Resolver reads a Value Dial ReferenceId from the new snapshot.
4. Resolver accidentally publishes a value combining two hardware states.

With the generation capture/recheck, step 3/4 causes a retry instead of publication.

## One active context per pair

Configuration and diagnostics can share the same *implementation* but should not simultaneously drive one Resolver/Scanner instance because each context wants a different logical control count/Profile.

Safe options are:

- separate Scanner/Resolver pairs for simultaneously active panels; or
- one physical panel with only one active domain bridge/context at a time.

This is an intentional ownership constraint, not a missing arbitration feature.

## Extending the input system

Before adding a new InputKind, ask whether the requirement can be represented using existing Memory, Linear, Integer, Switch, or Enum semantics. A new kind changes the generic Resolver ABI/behavior and should be reserved for genuinely different resolution semantics.

When adding one, update together:

- Resolver implementation;
- Profile ABI documentation;
- input-contract validator/tests;
- any Profiles that use it;
- `docs/ABI_REFERENCE.md` and this document.
