# Dependency Planning

Roadmap Item 8 adds bounded manufacturing dependency planning above the existing Generic Job, Item Storage, Catalog, Directory, and Manufacturing Scheduler substrates. It does **not** add a second job queue, a second physical reservation ledger, or an arbitrary graph engine.

## Scope and deliberate bounds

The planner currently handles `TRANSFORM` and `PRINT` jobs whose requirements resolve to ITEM resources. It supports a dependency depth of at most two edges:

```text
root job -> child -> grandchild
```

A third dependency edge is rejected. Self-dependencies and immediate ancestor cycles such as `A -> B -> A` are rejected before child publication.

Planning uses coherent Item-7 inventory **quotes**, not long-lived planner-owned physical reservations. The execution layer remains the sole physical reservation authority. This avoids a reservation handoff in which planning would otherwise reserve stock that execution must reserve again. Any inventory/topology change causes re-evaluation before execution.

## End-to-end control flow

```text
171 Generic Job Store
        ^
        | only 213 writes its command mailbox
        |
213 Generic Job Store Command Executor
        ^
        |
199 Job Command Gateway ABI4
   | Scheduler lane A
   | Planner-cancel lane B
   ` Child-create lane C
        ^
        |
183 Manufacturing Scheduler
        |
        +--> 181 Job Selector
        |
        `--> 210 Dependency Gate ABI2
                  |
                  +--> 208 Dependency Planner
                  |      |
                  |      +--> 217 Existing-plan controller
                  |      `--> 218 New-plan controller
                  |
                  `--> 182 Driver Router only when dependency-ready
```

`ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` remains the manufacturing **lifecycle-policy owner**: it decides legal state transitions and wait/fault results. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` is the only Item-8 service that physically writes the Job Store command mailbox. This separates lifecycle policy from mailbox serialization and prevents Scheduler, Planner, and Child Creator from racing on the Store request cells.

## Normalized requirement view

`ic10/dependency-planning/job_requirement_view_v1_0.ic10` normalizes TRANSFORM and PRINT metadata into one bounded ITEM view. Transform requirements come from Transform Profile ABI4. Print requirements come from Recipe execution metadata and `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10`, which maps `ManufacturingReagentHash` aliases back to canonical ITEM `ResourceType` values derived from the Resource Profile catalog.

The normalized view exposes both requirements and promised output semantics so dependency validation can prove that a proposed child still produces the resource the parent expects.

## Producer resolution

`ic10/dependency-planning/item_producer_resolver_v1_0.ic10` is generated from `data/resource_transforms.json`. Known transform outputs resolve to `ProducerKind=TRANSFORM` plus exact `TransformType`. Unknown ITEM outputs fall back to PRINT with the requested ResourceType as the print-side producer identity.

The generator rejects duplicate transform producers for the same ITEM ResourceType rather than silently choosing one.

## Inventory preflight

`ic10/dependency-planning/job_inventory_preflight_v1_0.ic10` quotes Item-7 `DirectorySchema.ResourceReservation` through the existing six-leg selector. It preserves Item-7 precision semantics:

- exact stock can prove both satisfaction and a real deficit;
- conservative lower-bound stock can prove that at least that quantity exists, but cannot prove that no additional stock exists;
- more than six eligible reservation sources is explicit overflow, never an ordinary deficit.

Planning therefore never manufactures a dependency merely because an eligible seventh storage source was outside the bounded quote.

For liveness after a child completes, Preflight computes two ordered rolling fingerprints over the selected Reservation references and semantic generations. These fingerprints are **not reservation authority**. They only distinguish an unchanged short inventory publication from a materially changed quote that requires replanning.

## Dependency Plan Store

`ic10/dependency-planning/dependency_plan_store_v2_0.ic10` owns 32 fixed-width eight-cell records:

```text
[ParentJobId,
 ChildJobId,
 ResourceType,
 RequiredTotal,
 BaselineKnown,
 FutureQty,
 QuoteFingerprintA,
 QuoteFingerprintB]
```

Physical records start at `S128`, width 8. `S40` is the global odd/even Plan Store sequence.

`ParentJobId` is the per-record commit marker. Mutation protocol is:

1. make the global sequence odd;
2. clear `ParentJobId` in the target record;
3. write the remaining seven cells;
4. publish `ParentJobId` last;
5. make the global sequence even.

On same-stack restart, an interrupted odd global sequence is normalized; a record with `ParentJobId=0` remains invalid rather than exposing a torn plan.

The Plan Store supports only three operations: lookup parent, upsert, and clear. Resource-level sharing is intentionally outside the persistent store API.

## Future-output sharing

`ic10/dependency-planning/dependency_claim_view_v1_0.ic10` is the read-only sharing authority over committed plans. Only **active** child jobs count as future work. A COMPLETE child is historical inventory, not future capacity, and is never reused for a newly arriving parent.

Each parent claim is:

```text
claim = max(0, RequiredTotal - BaselineKnown)
```

For a shared child, Claim View sums claims from all other parents and only advertises unclaimed surplus:

```text
availableFuture = FutureQty - aggregateClaims
```

`ic10/dependency-planning/dependency_plan_builder_v2_0.ic10` reuses the child only when `availableFuture >= newDeficit`; otherwise it creates another child. This prevents several parents from each treating the child's full promised output as independently available.

## Child creation and atomic Job Store publication

`ic10/dependency-planning/dependency_child_creator_v2_0.ic10` validates producer identity, ancestry/depth, current output semantics, and bounded quantity, then submits child intent through Gateway lane C.

Free-slot selection is **not** performed in Child Creator. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` selects a free slot atomically while also checking the exact parent:

- ParentJobId still matches the expected parent slot;
- parent JobGeneration is unchanged;
- parent is still `PLANNING`;
- selected child slot is still free.

Only after those checks does it stage child immutable intent and issue the Job Store `PUBLISH_NEW` request. This removes the earlier scan-then-publish race.

While an internal Job Store request is outstanding, Executor stays in `StoreWait` on every loop and does not reissue the external command. Same-stack restart also resumes that pending Store request from its preserved pending cells.

## Child validity and catalog changes

`ic10/dependency-planning/dependency_child_validity_v1_0.ic10` combines exact Job monitoring with the normalized Requirement View. A stored ChildJobId is never treated as sufficient proof by itself. The child must still exist, have coherent state/generation, and still promise the ResourceType stored in the plan under current catalog metadata.

This means a transform/recipe catalog change can invalidate a plan even when the child JobId itself remains valid.

## Parent release after child completion

Child `COMPLETE` is necessary but not sufficient. `ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10` runs a fresh parent inventory preflight.

Decision rules are:

```text
inventory now satisfies requirement -> parent dependency READY
lower-bound ambiguity              -> keep probing / WAIT_RESOURCE
child active                         -> wait
child terminal failure               -> dependency failure
child COMPLETE + still short:
    quote fingerprints unchanged     -> wait for inventory publication catch-up
    quote fingerprints changed       -> replan
```

This closes the race where output becomes visible and is consumed by another job before a shared parent evaluates. A changed-but-still-short quote cannot strand the parent indefinitely waiting for output that is no longer available.

## Cancellation and cleanup

`ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10` decides whether a child can be cancelled when one parent releases its plan. Cancellation is reference-aware:

- if another committed plan still references that active child, do not cancel it;
- if no other plan references it and it is active, Planner may request cancellation through Gateway lane B;
- COMPLETE children are not cancelled as future work.

`ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10` scans committed plans for parents that became terminal or disappeared and requests cleanup through the Planner. It never writes Job Store or Plan Store directly.

## Single-writer boundaries

The important authorities are intentionally separate:

- `ic10/generic-jobs/generic_job_store_v1_0.ic10` owns durable JobId/state storage mechanics;
- `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` owns manufacturing lifecycle-edge **policy**;
- `ic10/generic-jobs/generic_job_command_gateway_v4_0.ic10` arbitrates independent command producers, including Item-13.1 root ingress on lane E;
- `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` alone writes the Job Store command mailbox for Item-8 production paths;
- `ic10/dependency-planning/dependency_plan_store_v2_0.ic10` owns persistent dependency plan records;
- `ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10` alone mutates Plan Store through its request interface;
- `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` is read-only future-output sharing/claim accounting;
- Item-7 execution allocators remain the physical resource-reservation authorities;
- `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` gates access to the unchanged Transform/Print Driver Router.

Async request tokens fence observation. They do not replace JobGeneration, Plan Store sequence, Resource Reservation generation, ownership epochs, or catalog generations.

## Failure behavior

Dependency planning fails closed on:

- stale parent JobGeneration;
- missing/changed child JobId;
- child output no longer matching the required ResourceType;
- depth greater than two;
- self/ancestor cycle;
- six-leg quote overflow;
- unsupported/ambiguous producer metadata;
- stale async responses;
- Plan Store incoherence;
- lower-bound inventory when absence cannot be proven.

There is no arbitrary planning timeout. Progress is tied to exact request identities, generations, job state, inventory publications, and plan records.

## Validation

`validation/validators/validate_dependency_planning_contracts.py` checks the static production contract. `tests/test_dependency_planning.py` executes the Plan Store and Gateway/Executor/Job Store paths and models shared claims, depth/cycles, completed-child inventory liveness, and cancellation semantics.

The full release suite also re-runs the pre-existing manufacturing, storage, Job ABI, catalog, directory, and 780-recipe stress tests so Item 8 cannot silently weaken earlier milestones.
