# Ore Processing Transforms

The Resource Transform catalog models the complete current furnace material set used by this framework: seven one-input basic smelts, five two-input base alloys, and five three-input advanced alloys/superalloys.

There is one execution architecture for all of them. Basic smelts, including Arc Furnace work, use the same generic Admission -> Link Resolver -> Reservation Stager -> Allocator ABI2 -> Runtime path as Furnace and Advanced Furnace jobs.

## 1. Architectural role

Ore processing is modeled as a **resource transform**, not as a special transport edge:

```text
Resource Transform Catalog
        |
        v
Transform Profile View ABI4
        |
        v
161 Material Transform Admission
        |
        v
162 Material Transform Link Resolver
        |
        v
163 Multi Reservation Stager
        |
        v
164 Multi Material Reservation Allocator ABI2
        |
        v
165 Generic Material Transform Runtime
        |
        +--> processor
        +--> Material Links / Grant Guards / Executors
        `--> output Resource Reservation
```

The catalog states declarative requirements. Runtime services validate live processor state, locate compatible input routes, reserve every required input atomically, wait for delivery, activate the processor, and confirm output growth.

## 2. Catalog schema

Each transform is one self-contained, 4-cell-aligned Store ABI6 item. Its logical content is:

```text
12-cell header:
  TransformType
  RequiredCapabilityMask
  InputCount
  OutputCount
  MinPressure
  MaxPressure
  MinTemperature
  MaxTemperature
  Flags
  reserved x3

InputCount x 4-cell descriptors:
  ResourceClass
  ResourceType
  Unit
  Quantity

OutputCount x 4-cell descriptors:
  ResourceClass
  ResourceType
  Unit
  Quantity

zero padding to 4-cell alignment
```

The generator may split immutable Loader source only **between complete transforms**. Runtime Store placement may put complete transform items in any compatible Store with sufficient capacity.

## 3. Processor capability hierarchy

The transform catalog expresses the minimum capability required by each recipe:

```text
SMELT_BASIC     = 1
FURNACE_ALLOY   = 2
ADVANCED_ALLOY  = 4
```

Processors advertise cumulative capability masks:

```text
Arc Furnace       = 1
Furnace           = 3
Advanced Furnace  = 7
```

Admission uses:

```text
(ActualCapabilities & RequiredCapabilityMask) == RequiredCapabilityMask
```

Therefore:

- one-input basic smelts may execute on Arc Furnace, Furnace, or Advanced Furnace;
- two-input base alloys require Furnace or Advanced Furnace;
- three-input advanced alloys require Advanced Furnace.

This hierarchy avoids maintaining separate transform catalogs for each processor class.

## 4. Transform Profile View ABI4

`ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` (generated) resolves a TransformType from the dynamic catalog and republishes a bounded runtime view. Identity lives in the common `S0`/`S1` header cells (magic = ResourceTransformProfileView.v4, ABI = 4); the resolved-request mailbox and payload sit above the descriptor pools:

```text
S8..S31   up to six input descriptors, four cells each
S32..S63  up to eight output descriptors, four cells each
S64..S67  pressure/temperature condition bounds
S68  request echo
S69  resolve status (1 = resolved)
S70  TransformType request cell, written by the consumer
S71  RequiredCapabilityMask; -2/-3 publish resolution errors
S72  InputCount
S73  OutputCount
S74  coherent publication generation
S75  condition flags
```

Input 0 begins at S8 and output 0 at S32. A consumer writes the TransformType to
S70, waits for its echo at S68 with status 1, snapshots S74, reads the fields and
descriptors, then re-checks S74 unchanged. The stable offsets are part of the
current ABI, not compatibility scaffolding for an older runtime.

## 5. Generic admission

`ic10/material-transform/material_transform_admission_v1_0.ic10` consumes:

- `d0` Transform Profile View ABI4;
- `d1` live processor;
- `d2` output Generic Resource Reservation.

It accepts `InputCount=1..3` and exactly one output. It validates:

- stable Transform Profile generation;
- processor prefab and capability mask;
- processor Power/Error state;
- required pressure and temperature bounds for every processor class whenever the profile declares a nonzero bound;
- input/output descriptor units and positive quantities;
- output Reservation resource identity, role, health, and capacity.

Admission publishes the exact processor identity and transform requirements used by downstream services. A basic Arc Furnace smelt is simply the `InputCount=1`, `RequiredCapabilityMask=1` case.

## 6. Link resolution

`ic10/material-transform/material_transform_link_resolver_v1_0.ic10` consumes:

- Admission;
- Transform Profile View;
- a Generic Snapshot Directory with `DirectorySchema.ResourceLink`.

It validates the generic directory magic/ABI plus schema ID/version before reading the active bank, and holds the admitted input count to at most the three the Admission accepts -- the count sizes a record window on the resolver's own stack, so a peer publishing a fourth would be written past the three records it owns. The floor is the Admission's to enforce; what the resolver has to hold is the end of its own window. For each required input descriptor it chooses a healthy Material Link whose:

- resource type matches;
- source Reservation has enough available quantity;
- native sink is the exact admitted processor;
- Link/Reservation publications are coherent.

The resolver publishes up to three records:

```text
[LinkRef, QuantityPerJob, ResourceType, ResourceClass]
```

No domain-specific Resource Link Directory magic is supported.

## 7. Atomic multi-input reservation

A transform must never deliver only a subset of its required ingredients.

`ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` prepares every input first. It holds the resolved count to at most three for the same reason the resolver holds the admitted one. For each resolved Material Link it provisionally stages:

- exact source quantity;
- exact sink quantity;
- common candidate epoch;
- Grant Guard transaction identity.

If any input cannot be staged, the Stager cleans up every partial reservation and reports failure.

The staged count at S8 is published after each record rather than once at the end, so a Stager interrupted mid-staging restarts holding the number of records it actually wrote, and a later clean undoes exactly those. That only holds while the stack is its own: S8 survives a reflash, but so does whatever a previous occupant of the housing left there. Boot therefore admits an inherited count only behind the `MultiMaterialReservationStager.v1` identity it publishes at S0, and zeroes it on any stack that identity does not claim — a housing that last ran something else cleans nothing rather than releasing reservations it never staged.

`ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` is the sole current material commit authority. Only after all inputs stage successfully does it publish the common active epoch at **S14 last**.

That commit-last rule means a Grant Guard cannot activate from merely provisional state.

`ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` accepts **Allocator ABI2 only**.

## 8. Runtime execution

`ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` consumes:

- `d0` processor;
- `d1` Admission;
- `d2` Link Resolver;
- `d3` Allocator ABI2;
- `d4` output Resource Reservation.

A requested batch proceeds through these logical stages:

```text
validate admission/resolution
        |
        v
request atomic input allocation
        |
        v
wait for common committed epoch
        |
        v
wait until every input Link completes that epoch
        |
        v
snapshot output Reservation
        |
        v
Activate processor
        |
        v
wait for newer coherent output snapshot
        |
        v
verify expected quantity increase
        |
        v
deactivate + complete
```

The runtime never treats processor activation alone as evidence of success.

## 9. Output completion evidence

Before activation, Runtime snapshots the output Resource Reservation quantity and generation. Completion requires:

1. a newer coherent Reservation generation; and
2. quantity growth of at least the declared transform output for the requested batch.

This makes completion evidence resource-centric and keeps the Runtime independent of machine-specific UI state beyond activation and admission checks.

## 10. Reflash and interruption behavior

The generic runtime preserves active job state across same-service reflash. Re-execution does not create a second material allocation for the same active request.

The safety model is deliberately asymmetric:

- before Allocator S14 commit, failure may discard all staged work;
- after S14 commit, Grant Guards recognize one exact epoch;
- processor activation waits for completed input delivery;
- job completion waits for coherent output growth.

The broad interruption/fault-injection roadmap item will enumerate every transition systematically, but the current protocol already fails closed at the transaction boundaries above.

## 11. Current furnace coverage

The catalog currently contains:

- **7 basic smelts** — one input, one output, capability `SMELT_BASIC`;
- **5 base alloys** — two inputs, one output, capability `FURNACE_ALLOY`;
- **5 advanced alloys/superalloys** — three inputs, one output, capability `ADVANCED_ALLOY`.

The same execution services handle all 17 transforms.

All declared pressure and temperature bounds are enforced by Admission for every processor class—Arc Furnace, Furnace, and Advanced Furnace. Processor capability never bypasses catalog environmental requirements.

## 12. Commissioning checklist

For a processor that should run catalog transforms:

1. deploy Resource Profile and Resource Transform catalog infrastructure;
2. deploy Material source inventory/Reservations and processor import Reservations;
3. deploy Material Links, Feeders, Grant Guards, and Transfer Executors for each usable resource route;
4. publish those links through `DirectorySchema.ResourceLink` using the Generic Snapshot Directory;
5. deploy `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10`;
6. deploy the five semantic services under `ic10/material-transform/`;
7. wire Admission to Transform View, processor, and output Reservation;
8. wire Resolver to Admission, Transform View, and Resource Link generic directory;
9. wire Stager and Allocator ABI2 together;
10. wire Runtime to processor, Admission, Resolver, Allocator, and output Reservation;
11. for manual operation, select TransformType/request count directly; for queued operation, publish a TRANSFORM Generic Job and let Item 6 select the transform lane and drive this transaction.

## 13. Deliberate limitations

The current transform executor intentionally does not provide:

- dependency DAG expansion;
- arbitrary output cardinality;
- arbitrary transform input counts beyond three;
- resource substitution rules;
- arbitrary fuel/thermal strategy search. Item 11 provides bounded commissioned process-condition and gas-preparation strategies, not a general thermochemical optimizer.

Roadmap Item 6 now supplies the global TRANSFORM/PRINT manufacturing queue and processor selection above this executor. It reuses this 161..165 transaction unchanged. Dependency expansion is complete in Item 8; Item 11 can now actively prepare declared furnace P/T conditions while this executor retains final admission authority.


## 14. Item 11 active condition preparation

The catalog pressure/temperature fields remain declarative transform truth. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` can now convert those exact fields into a coherent ProcessCondition, allowing PressureGrid plus commissioned gas-composition/thermal utilities to prepare the selected Furnace/Advanced Furnace. This does not modify transform execution: `ic10/material-transform/material_transform_admission_v1_0.ic10` still verifies the live P/T window before the Multi Material Reservation Stager/Allocator can commit material reservations. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.
