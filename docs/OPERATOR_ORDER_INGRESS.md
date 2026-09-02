# Operator-Order Manufacturing Ingress

Roadmap Item 13.2 provides explicit one-shot manufacturing requests: select a printer recipe, choose a quantity and priority, and publish exactly one ordinary `GENERIC_JOB_ABI_V1` PRINT root. The order is forgotten after publication; Scheduler and Dependency Planner own every later lifecycle and material-planning edge.

The whole family is commissioning-class. It may be reclaimed when operators are not placing orders, and live use remains gated on the Item-12 manufacturing evidence. Optional case `LG-OPERATOR-ORDER-INGRESS` records physical acceptance without making the later roadmap item part of Item 12.

## Panel and staged values

`ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10` reuses Generic Input Scanner and Resolver. Configure Resolver without an Input Profile so the shared Logic Memory supplies each value selected by the Field Dial. The four one-based controls are:

```text
1  Recipe FamilyHash       non-zero integral Stationeers hash
2  FamilyOrdinal           zero-based non-negative integer
3  RequestedQuantity       positive integer
4  Priority                integer
```

Selecting a control stages its current coherent Resolver value. All four controls must have been staged before commit. The dedicated commit Switch connects to Editor `d2`; only a rising edge submits the complete snapshot. Holding the Switch does not publish again. Release and raise it again to submit another order, including an intentionally identical order.

Editor status is visible on its housing and at `S8`: `1` staged, `2` pending, `-1` dependency fault, `-2` invalid field value, and `-4` incomplete staging. After a response, `S8` is the ingress/Gateway status, `S12` the allocated JobId, and `S13` the slot.

## Recipe resolution

`ic10/manufacturing-ingress/operator_order_recipe_view_v1_0.ic10` owns a dedicated Recipe Catalog Lookup request mailbox. It resolves `[FamilyHash, maximum capability 255, FamilyOrdinal]`, then asks a dedicated Recipe Execution Profile View to revalidate the exact RecipeHash, family, required capability, and input count.

The capability ceiling exposes every recipe represented by the catalog; it does not assert that a compatible printer is currently online. A valid order may therefore enter `WAIT_PROCESSOR` or `WAIT_CAPACITY` later under normal Scheduler policy.

Lookup status `-3` is preserved as the distinguishable unknown/unresolvable selection result. Catalog and profile failures also remain negative, and no failed resolution reaches the Gateway.

## Root publication

`ic10/manufacturing-ingress/operator_order_job_ingress_v1_0.ic10` turns the validated view into this immutable intent:

```text
JobType             = 2 (PRINT)
RequiredCapability  = selected recipe capability
Identity            = RecipeHash
InputCount          = execution-profile input count
OutputCount         = 1
RequestedQuantity   = staged quantity
Priority            = staged priority
```

It captures even Generic Job Store and Dependency Plan Store sequences, then publishes through Gateway ABI5 lane F. Lane E remains exclusively owned by stock-target ingress. Both lanes reach the same Command Executor root command, which rechecks the two sequences immediately before staging a free Store slot. The Store still assigns JobId and publishes ordinary `QUEUED/Generation=1/ErrorStatus=0` state.

Gateway lane F uses:

```text
S96   request token, written last
S97   response token, written last
S98   status
S99   allocated JobId
S100  allocated slot
S101  expected Job Store QueueSequence
S102  expected Dependency Plan Store sequence
S103..S109  JobType, RequiredCapability, Identity,
            InputCount, OutputCount, RequestedQuantity, Priority
```

## Deployment wiring

```text
physical panel -> Generic Input Scanner -> Generic Input Resolver
                                             |
Commit Switch -------------------------------+-> Operator Order Editor
                                                   |
                                                   v
Operator Order Ingress d0 -> Job Gateway ABI5 lane F
                       d1 -> Operator Order Recipe View
                       d2 -> Generic Job Store
                       d3 -> Dependency Plan Store
Recipe View d0 -> dedicated Recipe Catalog Lookup -> any Recipe Store
            d1 -> dedicated Recipe Execution Profile View -> any Recipe Store
Gateway d0 -> Generic Job Store Command Executor
Executor d0 -> Generic Job Store
         d1 -> Dependency Plan Store
```

The two recipe services are dedicated to this panel: do not share either request mailbox with the resident print pipeline or another commissioning client. Editor is the only writer to the order-ingress mailbox, Ingress is the only lane-F writer, and Gateway/Executor remain the only physical Store command path.

## Failure and restart behavior

Editor writes every payload cell before its request token. Recipe View and Ingress write result/status before their response token. A stale response can therefore never acknowledge a new commit.

Ingress records its pending lane-F token before asking Gateway to act. A same-stack reflash resumes that exact token; Gateway and Executor replay markers prevent a second JobId. Reflashing Editor while commit remains held preserves the sampled Switch state and pending request, so the held level cannot become a new edge.

An ABI4-to-ABI5 Gateway replacement is a quiescent upgrade, not a same-ABI reflash. Suppress new work, let every producer consume its final reply and reach its documented idle state, then stop the producer ICs. Recheck that every ABI4 request equals its response (`S19=S8`, `S32=S33`, `S48=S49`, `S64=S65`, and `S80=S81`) and Gateway `S24=0`; only then load ABI5 and resume producers. ABI5 executor tokens occupy a namespace disjoint from persisted ABI4 replay tokens.

An odd Store/Plan sequence returns `-5` without publishing. Invalid wiring or malformed staged values returns `-1`; incomplete/invalid panel staging is rejected before Ingress. Release and recommit after correcting a failure.

## Live commissioning case

After the required Item-12 suites are current PASS, record optional case `LG-OPERATOR-ORDER-INGRESS` against the current release fingerprint:

1. Stage a known family/ordinal, quantity, and priority; commit once and verify exactly one PRINT root with every immutable field intact.
2. Hold commit across multiple ticks and verify no second JobId appears.
3. Release and recommit the same staged values; verify one new JobId appears.
4. Select an absent family/ordinal and verify status `-3` with no job.
5. Reflash Editor, Recipe View, Ingress, Gateway, and Executor at separate pre/post-publication points; verify each commit retains one JobId and never duplicates.

Automated regression coverage is in `tests/test_operator_order_ingress.py` and `validation/validators/validate_operator_order_ingress_contracts.py`; it does not replace the live case.
