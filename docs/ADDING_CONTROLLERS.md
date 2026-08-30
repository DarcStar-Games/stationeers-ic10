# Adding a Controller Family

A normal controller family requires only the pieces that contain **family-specific meaning**:

1. **Runtime** — controller algorithm + generic telemetry.
2. **Config Policy** — type/schema/block masks/defaults/validation/normalization.
3. **Input Profile catalog entry** — optional commissioning UX metadata stored in `data/input_profiles.json` and materialized through the shared Profile View.

Reuse `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`, Generic Input Scanner, Generic Input Resolver, Config Input Bridge, Editor, Loader, Committer, discovery, selectors, and diagnostics unchanged.

If adding a family appears to require editing those generic services, first check whether family semantics are leaking across the intended boundary.

## Step 1: choose identity and stable schema geometry

Choose a unique `ControllerType` hash and controller config schema number. Then assign every field a stable physical slot in one to four eight-slot blocks.

Each new program also needs its own `S0` service identity, which you do not
allocate: pick an UpperCamelCase contract name, declare it in
`data/script_protocol_headers.json`, and publish `poke 0 HASH("<Contract>.v<ABI>")`.
The ABI belongs inside the name — bumping it later mints a different value, which
is exactly what makes every consumer's single `S0` check ABI-exact. That check is
the whole admission test: do not follow it with a check of the peer's `S1`, which
can never fail and costs two lines.
`validation/validators/validate_service_identity.py` enforces this; see
`docs/ABI_REFERENCE.md`.

Write down the mapping before coding:

| Physical slot | Meaning | Type/constraints | Default | Preferred input |
|---:|---|---|---:|---|
| 0 | example field A | finite number | 0 | Memory |
| 1 | example field B | 0..10 | 1 | Linear Dial |

Do not plan to repack slots later. Deprecated fields become reserved holes rather than being reused for a new meaning.

## Step 2: implement the Config Policy

### Policy checklist

- choose stable physical slots in 8-slot blocks;
- publish block count and masks;
- zero unused mask entries;
- create persistence signature `CFG1|Type|schema|blocks|m0|m1|m2|m3`;
- publish complete padded default image at Host `S32..S63`;
- publish Policy generation `S13` last;
- validate every active candidate field that has semantic constraints;
- validate cross-field invariants;
- canonicalize accepted candidate values in Host `S128..S159`;
- zero padding/reserved slots;
- publish Policy result `S21`, then response `S20` last.

Prefer small, stable error-code classes. Document every negative result in `docs/ABI_REFERENCE.md` or a family-specific section.

## Step 3: implement the Runtime

The Runtime should:

- advertise generic telemetry magic/ABI;
- publish the family `ControllerType` at telemetry `S99`;
- publish the paired Generic Config Host ReferenceId where the telemetry ABI expects it;
- consume only the Host **effective** image, not candidate/staging state;
- react to effective generation/revision changes;
- expose useful runtime/diagnostic telemetry channels;
- avoid persistence/editor/physical-input logic.

Keep physical-slot constants synchronized with the Policy. The config contract validator should catch geometry mismatches, but semantic names still deserve human review.

## Step 4: optionally add an Input Profile catalog entry

A Profile controls commissioning UX, not the durable schema. It can therefore be omitted when Logic Memory editing is sufficient. New families normally **do not add another Input Profile IC**. Add one record to `data/input_profiles.json`, regenerate the shared catalog/loaders, and select the family through `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`.

### Input Profile checklist

- choose `profile_type = ControllerType` and the exact controller schema;
- set `field_count` to the active logical field count;
- add one four-value descriptor per active field in **active ordinal order**;
- Dial descriptors provide explicit step count in descriptor `+3`;
- enum tables remain numeric/symbolic source entries that the generator compiles into sparse numeric target/value pairs;
- run `tools/generate/generate_input_profiles.py`;
- verify all generated loaders still fit the 120-line soft target and the one catalog store remains below 512 cells;
- configure View `S2=ControllerType`, `S3=schema` and verify it republishes Generic Input Profile identity `HASH("InputProfileView.v1")`, with positive generation `S5`.

The Profile's field order must match the active ordinal order derived from Policy masks, not raw physical slot count including holes. If the Input Profile catalog eventually exceeds one stack, split storage because of **512-cell capacity**, not because a Loader program becomes too large; source-size pressure is handled by additional sparse whole-profile Loader candidates.

## Step 5: add telemetry documentation

Define channel numbers and units/meaning. Diagnostics maps a numeric channel, so stable channel documentation is essential for humans.

Useful telemetry usually includes:

- primary process/input measurement;
- controller output;
- important internal state;
- saturation/fault/status indicators;
- current setpoint/mode;
- values that make tuning/debugging possible.

Avoid changing an existing channel's meaning without a deliberate compatibility decision.

## Step 6: validate the family

At minimum:

1. Run `validation/validators/validate_ic10.py`.
2. Run `validation/validators/validate_abi_contracts.py`.
3. Extend/run `validation/validators/validate_config_contracts.py` so Policy/catalog-profile/Runtime geometry agrees.
4. Run shared input and persistence model tests.
5. Exercise live-game edit/apply/recovery cases.
6. Verify diagnostics can discover the runtime and render documented telemetry channels.
7. Declare each new program's device-port peers in `data/script_wiring.json` and run
   `validation/validators/validate_script_wiring.py` — see `docs/SCRIPT_WIRING.md`.

## Example: why a new family should not need generic changes

Suppose a new pressure controller needs fields for setpoint, hysteresis, output LogicType, and inverted direction. Those differences can all be represented by:

- Policy slot meanings/defaults/validation;
- Profile descriptors using Memory/Linear/Enum/Switch kinds;
- Runtime logic reading those slots;
- telemetry channel definitions.

Scanner still only discovers devices. Resolver still only interprets descriptors. Editor still stages slots. Host still persists the image. That is the desired extension path.

No controller-family change should be required in Scanner, Resolver, Config Bridge, diagnostics, Editor, Loader, Committer, or Generic Host.


## Existing families as reference implementations

Use the current families for different kinds of examples:

- **ControllerPI** — continuous numeric control, bounds, normalization, and richer numeric telemetry.
- **ControllerTest (test-only)** — smallest framework-contract exerciser and fault-injection target under `tests/ic10/`.
- **ControllerSequencer** — discrete state machine with timers, transitions, two action outputs, and terminal states.
- **ControllerPhasePressure** — pressure-requirement controller that consumes a separate domain-data Profile and can either actuate locally or publish a request for a higher-level coordinator.
- **ControllerPressureDomain** — infrastructure controller consuming many same-medium PhasePressure producers through an incremental request Arbiter, applying local plant limits, and exposing passive STORAGE bounds.
- **ControllerPressureTransfer** — topology-edge controller that composes two reserved PressureDomain endpoints plus a physical pump, publishes a molar rate ceiling, and executes only a committed bounded-rate lease.
- **Grid Reservation Planner + Pressure Reservation Allocator** — infrastructure services, not controller families: together they reserve shared endpoint inventory, stage grants, and atomically activate a parallel plan.

When adding another family, pick whichever existing family is closest in *semantic shape*, not simply the one with the most fields. A state-oriented controller should usually start from the Sequencer family; another continuous controller should usually start from PI.

## When controller semantics need external domain data

Do not force slowly changing domain constants into either the Generic Host or the Runtime when they are conceptually independent of controller configuration. `ControllerPhasePressure` is the reference pattern: its Config Policy stores operating choices/margins, while the PHASE_MEDIUM Resource Profile View supplies the working-medium curve.

Use this pattern when all of the following are true:

- multiple controller instances can share the same *kind* of domain model;
- changing the domain identity should not create a new controller family;
- the data is mostly static compared with operator configuration;
- the Runtime can validate a small explicit ABI before consuming it.

Avoid turning every lookup table into a service. The unified Resource Profile layer is justified because resource identity/metadata are a separate axis from controller behavior and are reused by both pressure and material grids.


## When a controller needs a bounded aggregation service

Do not force multi-provider scanning into a Runtime merely to reduce script count. `ControllerPressureDomain` is the reference counterexample. Its first combined implementation exceeded the IC10 line budget because Host/config handling, medium validation, Controller Directory scanning, request filtering, coherent aggregation, telemetry, and physical actuation were separate responsibilities competing for one 128-line program.

The accepted split is:

```text
many telemetry producers -> PhasePressure Request Arbiter -> one PressureDomain Runtime

PressureDomain Inventory -> PressureInventory Reservation
         |                         |
         +---- real pump edge ----+ -> PressureTransfer candidate
                                      -> Reservation Allocator
                                      -> Grid Reservation Planner commit
```

Use a separate service when all of these are true:

- the service owns a reusable publication/transaction boundary;
- its work can be validated independently;
- keeping it inside the Runtime would violate IC10 size/maintainability constraints;
- the split reduces rather than duplicates domain logic;
- ownership is explicit (one Arbiter context belongs to one active PressureDomain in v1).

Do not split merely because a Runtime is aesthetically large. The extra IC must represent a real boundary.


## When a new controller needs Telemetry ABI2

Use Generic Telemetry ABI2 when another service must combine two or more live telemetry fields as one invariant-bearing snapshot. Clear `S115` before mutating the payload and publish a new positive generation at `S115` last. Consumers must capture/recheck it. A controller whose telemetry is only independently displayed can remain ABI1 unless a transactional consumer is introduced.


## Adding a Resource Grid specialization

Do not turn a physical-domain controller into a generic controller merely because its state can be normalized. The Resource Core generalizes **contracts and transaction semantics**, while the native implementation remains responsible for domain physics and device behavior.

Use these normalized surfaces where they fit:

```text
Generic Resource Endpoint   typed supply / demand / storage capacity
Generic Resource Reservation mutable planning ledger for one Endpoint
Generic Resource Link       real directed topology + transferable rate
Resource Transform Profile  typed input -> typed output metadata
```

A new specialization should prove at least two things before sharing more scheduler code with PressureGrid:

1. it can publish a coherent Generic Resource Endpoint without losing domain-specific safety information;
2. its physical transport mechanism can publish a topology-bound Generic Resource Link whose capacity has an unambiguous unit.

For material systems, `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` is the warehouse Endpoint reference implementation. It scans one vending slot per tick, invalidates the snapshot on `ImportCount`/`ExportCount` churn, and publishes exact ItemHash quantity/capacity. `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` is the conservative processor-sink reference.

There are now two Link reference implementations. `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` projects a hardened PressureTransfer into Generic Resource Link ABI1 while verifying the generalized Reservations resolve to the same native pressure inventories. `ic10/material-grid/material_resource_link_v1_0.ic10` publishes the same Link ABI for a Vending/Stacker/Logic-Sorter path; its Generic Link S2/S3 are Reservation ReferenceIds, while native Vending/Stacker/Sorter/sink identities live in material extension cells.

When creating a **discrete** resource specialization, do not assume pressure-style rate leases are appropriate. MaterialGrid v1 instead uses an exact quantity transaction split across Allocator, Grant Guard, Feeder, and Executor. This proved several discrete-specific requirements: a preparation buffer can contain more than the committed batch, destination completion can race the executor if its counter is captured too late, and physical item topology may not be fully discoverable from the data network.

Do **not** model a printer, furnace, or centrifuge as a strange Resource Link. Movement preserves resource identity; processing changes it. Use a Resource Transform Profile for typed accounting and keep machine Admission/Execution as a separate service boundary. The `ic10/material-transform/` pipeline is the reference: Admission validates processor conditions and output capacity, Link Resolver resolves input routes, Multi Reservation Stager prepares all reservations, Material Allocator ABI2 commits one shared epoch, and Generic Transform Runtime executes only after every input delivery is confirmed.

Before promoting a specialization-specific allocator into the Generic Resource Core, require at least two stable implementations with demonstrably identical transaction semantics. Pressure continuous-flow reservations and Material exact-batch reservations are intentionally still separate.

Resource services have their own 64-entry Endpoint and Link directories and therefore do not need to consume Controller Directory slots just to be routable.

## IC10 implementation guidance

Keep rounding only where conversion is semantically required: scaled integer-dial values and validation/canonicalization of arbitrary discrete candidate floats. Already-integral authored metadata does not need redundant rounding.

Use bitmasks for capabilities, valid-slot geometry, and fault/status flags. Keep ReferenceIds, request/snapshot generations, schema values, telemetry payloads, and numeric ranges in separate cells unless a documented ABI explicitly packs them. Request identity follows `docs/ASYNC_REQUEST_STANDARD.md`; durable commit authority follows `docs/BANKED_TRANSACTION_STANDARD.md`.

## Step 7: assign deployment ownership and operator instructions

Every new production-capable `.ic10` program must have exactly one operator-facing deployment home before it can pass release validation.

For a hand-maintained program, add these fields to its exact semantic-path entry in `data/source_manifest.json`:

```json
{
  "deployment_family": "controller-example",
  "deployment_class": "resident"
}
```

If the program belongs to an existing family, reuse that family slug. If it represents a genuinely new installable subsystem, add one `deployment_families` definition and one matching `<!-- DEPLOYMENT_FAMILY:... -->` section in `USER_DEPLOYMENT_GUIDE.md`. Generated loader/store families should use `generated_deployment_rules` rather than one metadata entry per generated file.

Allowed deployment classes are `resident`, `conditional-resident`, `commissioning`, `one-shot`, and `on-demand`.

Then run:

```text
python3 tools/generate/update_user_deployment_inventory.py
python3 tools/generate/generate_source_catalog.py
python validation/validators/validate_source_catalog.py
python validation/validators/validate_user_deployment_guide.py
```

The generated program block in `USER_DEPLOYMENT_GUIDE.md` must not be edited by hand. The surrounding family chapter is human-owned and must document prerequisites, operator-significant wiring/configuration, deployment order, healthy state, commissioning proof, common failures, reflash/replacement behavior, and what can be reclaimed after commissioning.

A new program with no deployment family is an incomplete feature even if its IC10 and protocol tests pass.
