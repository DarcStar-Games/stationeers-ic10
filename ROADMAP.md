# Framework Roadmap

This roadmap tracks the remaining major milestones after completion of the generic catalog/storage/discovery substrate, manufacturing scheduler, physical ITEM inventory/storage layer, bounded dependency planner, and power-management generalization. Detailed records for completed Items 1–11 live in `docs/COMPLETED_MILESTONES.md`.

Items 1–11 are implemented and automatically validated. Item 12 is the active field-validation milestone: it closes the remaining gap between deterministic/model evidence and real Stationeers device, network, timing, and reflash behavior without changing the authority model merely to make commissioning easier. Item 13 is in progress behind it: stock-target ingress is implemented inert-by-default, while live activation and later ingress layers remain gated.

## Cross-cutting invariants

- **Logical catalog items are atomic.** A logical catalog item is never split across Loader ICs, Store nodes, migrations, or compaction operations.
- **Directories separate discovery from authority.** Directory membership identifies candidates; reservations/epochs/ownership tokens authorize mutation.
- **Publication is coherent.** Readers fence generation/token identity before consuming request-specific or snapshot-specific state.
- **Quotes precede mutation.** Planning gathers and revalidates all required resources before any transactional ownership change.
- **Physical execution revalidates committed identity.** A reservation does not authorize acting on a different Endpoint generation, processor, slot, or topology.
- **Failure is fail-closed.** Missing capacity, stale generations, duplicate identities, unsupported capabilities, and incomplete reservations prevent execution rather than degrading silently.
- **Precision is explicit.** Exact quantities and conservative lower bounds are different facts and planners must preserve that distinction.

## 8. Simple dependency planning — COMPLETE

Bounded dependency planning is implemented and validated. It reuses Generic Jobs, Item-7 inventory/reservation discovery, transform/recipe catalogs, and the existing scheduler rather than creating a parallel queue or warehouse model. The current bound is root -> child -> grandchild, with active future-output sharing, aggregate claim accounting, exact parent-generation guards, coherent inventory confirmation after child completion, and fail-closed cycle/overflow handling.

See `docs/DEPENDENCY_PLANNING.md` and `docs/COMPLETED_MILESTONES.md`.

## 9. Power-management reuse — COMPLETE

Power management now reuses Resource Profiles, Generic Resource Endpoints/Reservations/Links, Generic Snapshot Directories, coherent planning/allocator epochs, and Generic Jobs. It covers producer supply, managed consumer demand, bidirectional battery reserve/target policy, transformer topology/overhead, critical-first load shedding, surplus charging, break-before-make actuation, and finite `JobType.POWER` policy transactions.

See `docs/POWER_MANAGEMENT.md` and `docs/COMPLETED_MILESTONES.md`.

## 10. Broad interruption and fault-injection suite — COMPLETE

The reusable interruption campaign now injects restarts at transaction boundaries across Store/migration, directory snapshots, processor identity, ITEM quote/commit/action, LArRE held-item recovery, dependency cancellation/catalog validity, Gateway replay, POWER plan replacement/allocator authority, and Generic Job cancellation. It also executes real IC10 Power Plan Store COMMIT at dozens of instruction cut points.

Item 10 and its post-completion review found and fixed three POWER restart/interleaving defects: `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` invalidates torn odd plan publication on boot; `ic10/power-grid/power_reservation_allocator_v1_0.ic10` revokes and then revalidates the unchanged current plan after reflash; and the load/link executors re-fence allocator ACTIVE/PlanGeneration/Epoch at the final physical write boundary. The campaign also verifies scheduler fairness and POWER-job WAIT/FAULT termination. See `docs/INTERRUPTION_FAULT_INJECTION.md`.

## 11. Cross-domain process & utility orchestration — COMPLETE

Complementary systems now compose through a generic `ProcessCondition` demand contract instead of special-case furnace or generator planners. Transform pressure/temperature bounds can drive PressureGrid-backed chamber conditioning; prepared two-component gas mixtures live in the existing FLUID Resource Profile catalog; Advanced Furnace embedded pumps project as ordinary PressureTransfer participants; and POWER shortage can request, prepare, route, and verify H2/O2 fuel before a Gas Fuel Generator is enabled.

The milestone preserves domain ownership: `ProcessCondition` never reserves or moves resources, PressureGrid remains gas-movement authority, Transform Admission remains final furnace P/T authority, and PowerPlan remains electrical shortage authority. The first bounded reference demonstrations and current exclusions are documented in `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## 12. Live-game commissioning and evidence closure — ACTIVE

Turn the existing human hardening plan into release-bound, machine-readable field evidence. Item 12 does **not** claim that automated simulation is equivalent to Stationeers. It adds a read-only commissioning snapshot probe, a versioned live-suite catalog, and fingerprint-bound PASS/FAIL/BLOCKED sessions so physical observations cannot be silently reused after the framework or acceptance criteria change. It also adds `USER_DEPLOYMENT_GUIDE.md`, whose generated program inventories are bound to `data/source_manifest.json` so every production IC10 program has one operator-facing deployment family/class and a consistent install/health/reflash/reclaim procedure.

Acceptance requires:

- all automated validators/tests green for the same framework input fingerprint;
- all required suites in `data/live_commissioning_cases.json` have current live `PASS` evidence;
- real pressure, material/chute, job/manufacturing, storage/LArRE, POWER, and Item-11 cross-domain paths are exercised;
- device/property/slot/timing discrepancies are fixed or removed from the supported production contract, then rerun;
- live evidence remains separate from deterministic `validation/evidence/`;
- no model/harness result is relabeled as a live-game PASS.

See `docs/LIVE_COMMISSIONING.md` and `docs/FRAMEWORK_HARDENING_TESTS.md`.

## 13. Manufacturing demand and job ingress — IN PROGRESS

Nothing in the framework decides that a job is needed. `docs/MANUFACTURING_SCHEDULER.md` records the boundary: "The scheduler does not submit jobs. Job ingress may be manual or provided by a later UI/control service." Exactly one program issues Job Store `PUBLISH_NEW` today — `ic10/dependency-planning/dependency_child_creator_v2_0.ic10` on Gateway lane C — and it only creates children of a job that already exists. Item 8 answers "given that X is needed, what else must be made"; no component answers "X is needed".

Root job intent therefore has to be staged into a free Job Store slot by hand. The three layers below close that gap in increasing order of cost, and each is independently deliverable.

Item 13 adds no second job lifecycle, queue, or reservation ledger. Ingress publishes ordinary `GENERIC_JOB_ABI_V1` intent through the existing Gateway/Command Executor serialization, and `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` continues to own every lifecycle edge after publication.

**Sequencing.** Live activation starts only after Item 12 closes. Item 13.1 is implemented inert-by-default so its contracts and optional field case can be reviewed without publishing into an execution path that still lacks complete Item-12 evidence.

### 13.1 Stock-target ingress — IMPLEMENTED, LIVE ACCEPTANCE PENDING

Maintain declared on-hand quantities: keep 50 steel sheets available. Reads coherent ITEM inventory from Generic Resource Endpoints, subtracts active future-output claims through `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` so one shortfall is not ordered twice, and publishes a single root job when the deficit exceeds a configured hysteresis band. Coherent requirement quoting already exists in `ic10/dependency-planning/job_inventory_preflight_v1_0.ic10`.

This is the cheapest layer and the one with the most operational value: a reader over surfaces that are already published, plus one lane-style writer. Targets are ordinary Config Policy schema, so the existing Host/Editor/Policy pipeline configures them without new UI.

The implementation is under `ic10/manufacturing-ingress/` and is documented in `docs/STOCK_TARGET_INGRESS.md`. Four disabled-by-default persistent targets share coherent exact inventory, active unclaimed output, and sequence-fenced Gateway ABI5 lane-E root publication. Automated coverage is complete; optional live case `LG-STOCK-TARGET-INGRESS` remains pending and activation stays gated on Item 12.

### 13.2 Operator order ingress — IMPLEMENTED, LIVE ACCEPTANCE PENDING

Explicit one-shot requests: make ten of this now, at this priority. Selects a RecipeHash through the existing Recipe Catalog Lookup, sets quantity and priority, and publishes one root job. Commissioning-class, and a shared-input panel problem rather than a scheduling problem — the Generic Input Scanner/Resolver/Editor pipeline already solves that shape.

Kept distinct from 13.1 because an operator order is satisfied once and then forgotten, while a stock target is continuously re-evaluated. The two must not share one requirement record.

The implementation stages four shared-input values, resolves and revalidates the selected RecipeHash, and publishes one ordinary PRINT root through dedicated Gateway ABI5 lane F. It is documented in `docs/OPERATOR_ORDER_INGRESS.md`; automated coverage is complete and optional live case `LG-OPERATOR-ORDER-INGRESS` remains pending behind Item 12.

### 13.3 Consumption-rate demand

Infer needs from observed drawdown so steady consumers do not need hand-tuned targets. This requires consumption history the framework deliberately does not keep, a sampling window that survives reflash, and a rule separating genuine demand from transient movement.

Materially harder than the other two and the least certain to be worth building. It should not start until 13.1 has run in a live base long enough to show that static targets are genuinely insufficient.

## Current milestone status

Items **1–11 are implemented and automatically validated**; detailed completion records are preserved in `docs/COMPLETED_MILESTONES.md`. Item **12 is ACTIVE** and is intentionally not complete until the required live-game evidence is recorded against the current release fingerprint. Item **13 is IN PROGRESS**: 13.1 and 13.2 are implemented and await Item-12 closure plus their own live acceptance; 13.3 remains planned.

## Transaction substrate note

Generic Job Store and Generic Persistent Config Host share `BANKED_TRANSACTION_V1` old-or-new/replay semantics (`SELECTOR_BANK` and `REVISION_BANK` respectively) while retaining separate runtime ICs and physical layouts. `ASYNC_REQUEST_V1` remains request-observation fencing, while storage/job/material/power reservation epochs and ownership identities remain separate mutation authorities. `ProcessCondition` adds cross-domain demand/verification only and is never a mutation authority.
