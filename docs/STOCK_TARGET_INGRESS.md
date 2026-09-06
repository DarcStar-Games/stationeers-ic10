# Stock-Target Manufacturing Ingress

Roadmap Item 13.1 adds the missing demand boundary above manufacturing: declare an ITEM quantity to keep on hand, then publish one ordinary `GENERIC_JOB_ABI_V1` root when a coherent deficit exceeds hysteresis. It does not add another queue, lifecycle, reservation ledger, or scheduler.

The implementation is inert by default. All four target records default to `ResourceType=0`, and live activation remains gated on Item 12 field-evidence closure. The optional `LG-STOCK-TARGET-INGRESS` case records Item 13.1 field evidence without making Item 12 depend on the later milestone.

## Persistent target schema

`ic10/manufacturing-ingress/stock_target_config_policy_v1_0.ic10` pairs with an ordinary Generic Persistent Config Host. Schema 1 contains four records of four cells each in effective Host `S96..S111`:

```text
record 0: S96..S99
record 1: S100..S103
record 2: S104..S107
record 3: S108..S111

[ResourceType, TargetQuantity, Hysteresis, Priority]
```

`ResourceType=0` disables and zero-normalizes that record. Enabled records require a non-zero integral ResourceType, positive TargetQuantity, `0 <= Hysteresis < TargetQuantity`, and integral Priority. Duplicate ResourceTypes are allowed deliberately: the first publication changes the Job Store sequence, so another record must re-evaluate and share the active output instead of double-ordering it.

The publish rule is:

```text
deficit = TargetQuantity - exactOnHand - unclaimedActiveOutput
publish only when deficit > Hysteresis
RequestedQuantity = ceil(deficit / OutputPerBatch)
```

Hysteresis controls when a request starts; it does not lower the refill goal.

## Coherent evaluation

The read path is split to keep every Item-13 program below the 120-line maintainability ceiling:

- `ic10/manufacturing-ingress/stock_target_inventory_view_v1_0.ic10` quotes the existing ITEM Resource Reservation Selector. A sufficient quote proves no job is needed. An insufficient quote is usable only when every returned Reservation is exact; lower-bound inventory and directory overflow suppress publication.
- `ic10/manufacturing-ingress/stock_target_producer_view_v1_0.ic10` serializes two client lanes over Item Producer Resolver and Job Requirement View. Lane A serves evaluation; lane B re-resolves the same ResourceType at the mutation boundary.
- `ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10` scans active matching jobs under one even Job Store QueueSequence and one even Dependency Plan Store sequence. A root contributes its full requested output. A dependency child contributes only `FutureQty - aggregateClaims` from Dependency Claim View.
- `ic10/manufacturing-ingress/stock_target_demand_view_v1_0.ic10` combines exact stock, unclaimed future output, and hysteresis into one bounded batch decision.
- `ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10` round-robins the four persistent records and submits at most one proven root per evaluation.
- `ic10/manufacturing-ingress/stock_target_job_ingress_v1_0.ic10` is the sole Gateway lane-E producer. It revalidates producer identity and output-per-batch, reruns exact demand, and fences the Config Host generation immediately before mutation. It also preserves an in-flight request token across same-stack reflash.

The split is by authority and replay boundary, not by domain duplication: views are read-only, the evaluator decides demand, and only the ingress writer can publish.

## Gateway lane E

`ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10` retains lanes A-D and adds lane E:

```text
S80  request token, written last
S81  response token, written last
S82  status: 1 success, <0 rejected
S83  allocated JobId
S84  allocated slot
S85  expected Job Store QueueSequence
S86  expected Dependency Plan Store sequence
S87..S93  JobType, RequiredCapability, Identity,
           InputCount, OutputCount, RequestedQuantity, Priority
```

The Gateway forwards root creation to the sole Generic Job Store Command Executor. The Executor grants root-create authority only to lane E with the exact `ParentJobId=-1` sentinel; lane C accepts non-negative child parents only. For a root, the Executor requires both expected sequences to be unchanged and even immediately before staging the chosen free slot. Since it is the only Store mailbox writer, two targets evaluated against the same snapshots cannot both commit: the first root advances QueueSequence and the second request is rejected for re-evaluation.

The resulting job is an ordinary `QUEUED/Generation=1/ErrorStatus=0` Generic Job. Manufacturing Scheduler and Dependency Planner own every later lifecycle and child-planning edge.

## Deployment wiring

The stock-target pipeline runs on its own loop, rooted at the Evaluator. The dependency planner runs on another, rooted at the Planner behind the Manufacturing Scheduler. Neither waits on the other. A request mailbox holds one request: a dependency service both loops post to answers whichever request landed last before it polled, and the other caller waits forever for a response token that was never served. `tests/test_mailbox_arbitration.py` shows exactly that on the production programs: the Future View asking a Claim View once per active job strands a Plan Builder request on the same instance, and Producer View and Child Creator posting to one Item Producer Resolver strand each other. So the stock-target family deploys its own instance of every request mailbox it reaches, and shares only what it reads:

```text
Config Host <- Stock Target Config Policy
     |
     v
Stock Target Job Evaluator
  d0 -> Config Host
  d1 -> Stock Target Producer View lane A
  d2 -> Stock Target Demand View
  d3 -> Stock Target Job Ingress

Demand View    d0 -> Inventory View
               d1 -> Future View
Inventory View d0 -> own ITEM Reservation Selector
                       d0 -> Resource Reservation Snapshot Host   (shared; read only)
Producer View  d0 -> own Item Producer Resolver
               d1 -> own Job Requirement View
                       d0 -> Transform Profile View                (shared; re-validated selection)
                       d1 -> Recipe Execution Profile View         (shared; re-validated selection)
                       d2 -> own Manufacturing Reagent Resolver
Future View    d0 -> Job Store                                     (shared; read only)
               d1 -> own Dependency Claim View
                       d0 -> Dependency Plan Store                 (shared; read only)
                       d1 -> own Dependency Child Validity
                               d0 -> own Generic Job Monitor -> Job Store (read only)
                               d1 -> the own Job Requirement View above
               d2 -> Dependency Plan Store                         (shared; read only)
Job Ingress    d0 -> Job Gateway ABI5 lane E
               d1 -> Producer View lane B
               d2 -> Demand View
               d3 -> Config Host
Store Command Executor d0 -> Job Store
                       d1 -> Dependency Plan Store
```

That is seven housings beyond the family's own programs, each running the unchanged dependency-planning or item-storage program:

- `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10`
- `ic10/dependency-planning/item_producer_resolver_v1_0.ic10`
- `ic10/dependency-planning/job_requirement_view_v1_0.ic10`
- `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10`
- `ic10/dependency-planning/dependency_claim_view_v1_0.ic10`
- `ic10/dependency-planning/dependency_child_validity_v1_0.ic10`
- `ic10/dependency-planning/generic_job_monitor_v1_0.ic10`

The rule that produces the list is declared in `data/mailbox_arbitration.json` and checked by `validation/validators/validate_mailbox_arbitration.py` (`docs/SCRIPT_WIRING.md`): an instance kept apart from another call tree brings every request mailbox it reaches downstream, or the sharing moves one hop; the walk stops at a selected snapshot whose consumers re-validate the echo and generation (the two profile views) and at anything the instance only reads (the stores and hosts). A resident dependency planner keeps its own set of the same programs.

Inside the family, Producer View's two lanes keep the Evaluator (lane A) and the Ingress (lane B) apart, and the Demand View's two writers are one call tree: the Evaluator posts its evaluation, then hands the target to the Ingress and waits on it while the Ingress posts the mutation-time request. Gateway lanes remain single-producer: A Scheduler, B dependency cancellation, C child creation, D POWER lifecycle, E stock-target ingress, F operator orders.

## Failure and restart behavior

Publication is suppressed on invalid or generation-changed config, missing/mismatched service identity, lower-bound inventory deficit, selector overflow, odd or changed Job/Plan sequences, stale Claim View results, mutation-time sufficient stock, changed producer/output-per-batch metadata, or full Job Store capacity.

An evaluator reflash before publication simply starts a new coherent evaluation. Once the ingress writer records a pending token, it keeps replaying the same lane-E token until the Gateway returns the matching response. Gateway and Executor replay markers make that retry idempotent. If the response was committed before a reflash, the active root is visible to Future View and subsequent evaluations subtract it.

## Live commissioning case

Do not enable a non-zero target until Item 12 required suites are current PASS. Then record optional case `LG-STOCK-TARGET-INGRESS` against the current release fingerprint:

1. Configure a target below exact on-hand stock and verify no JobId is allocated.
2. Lower exact stock until the deficit exceeds hysteresis; verify exactly one root with the expected producer, priority, and rounded batch quantity.
3. Configure a second record for the same ResourceType; verify it counts the active root and does not allocate another JobId.
4. Reflash Evaluator, Ingress, and Gateway at separate points before/after lane-E submission; verify the original JobId is retained and no duplicate root appears.
5. Complete the job and verify inventory reaches the target before another deficit is eligible.
6. Repeat with lower-bound-only stock, an odd/stale Plan Store view, and changed producer metadata; each condition must suppress publication.

Automated coverage lives in `tests/test_stock_target_ingress.py` and `validation/validators/validate_stock_target_ingress_contracts.py`; it is regression evidence, not a substitute for this physical case.
