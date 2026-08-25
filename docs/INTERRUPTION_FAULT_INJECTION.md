# Interruption and Fault-Injection Campaign

Roadmap Item 10 applies one deterministic interruption philosophy across the complete dynamic framework. The campaign does not create a new runtime transaction protocol. It reuses each subsystem's existing publication generation, bank selector, reservation owner/epoch, topology identity, and request token as the authority boundary, then crashes the modeled operation after every meaningful mutation boundary.

## Reusable campaign helper

`framework/fault_injection.py` provides `inject_every_boundary()`. A test supplies an initial state, ordered mutation steps, subsystem-specific recovery, and a safety invariant. The helper deep-copies the initial state and injects a restart after every prefix, including before the first mutation and after the complete transaction.

The common rule is:

```text
observe/quote -> stage -> commit authority LAST -> execute only from committed identity
```

Recovery may preserve the old complete state, expose the new complete state, or deliberately invalidate the operation. It may not expose a torn state as authoritative.

## Automated campaign matrix

`tests/test_fault_injection.py` covers these interruption classes:

| Area | Injected boundary | Required invariant |
|---|---|---|
| Catalog migration | payload copy / destination publication / source removal | at least one authoritative whole item always remains |
| Directory mutation / Store loss | snapshot sequence and generation change during read | torn/odd/stale discovery is observation only and is rejected |
| Manufacturing processor replacement | device ReferenceId/generation changes after planning | stale reservation cannot actuate a replacement processor |
| ITEM storage | inventory quote / reservation commit / movement | semantic-generation change invalidates the stale ownership/action |
| LArRE | pickup followed by destination obstruction/restart | held item retains a persisted physical origin and recovers fail-closed |
| Dependency planning | parent cancellation / shared child / catalog-output mutation | shared work is reference-aware; stale child meaning never releases a parent |
| Job Gateway | reflash before/after Store mutation | deterministic external-token + lane identity prevents duplicate mutation |
| Generic Job lifecycle | cancellation from every nonterminal state | cancellation is legal; terminal records never reopen |
| POWER replacement | new reservation commit / old release / authority publication | staged reservations alone never authorize electrical actuation |
| POWER Plan Store | reflash during real IC10 plan COMMIT | odd/torn plan is invalidated before sequence becomes readable |
| POWER Allocator | reflash with an active/staged epoch | startup revokes authority, preserves old epoch for cleanup, revalidates the unchanged current plan, and republishes only a fresh committed epoch |
| POWER Executors | allocator ACTIVE/PlanGeneration/Epoch changes after initial validation but before final write | managed load/transformer re-fence authority at the physical write boundary and remain OFF on mismatch |

`validation/validators/validate_fault_injection_contracts.py` additionally checks source-level ordering for the transaction-critical implementations so a later refactor cannot silently move an authority marker ahead of its payload.

## Item-10 defects found and fixed

The campaign found that `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` previously left an interrupted COMMIT sequence odd across a reflash. A subsequent request could start from that odd value and temporarily make the sequence even while copying a new plan. Boot recovery now detects an odd sequence, invalidates PlanGeneration/flow-count/status headers, advances the sequence to even, and only then accepts new work. This deliberately sacrifices continuity after a torn plan to preserve the stronger fail-closed execution invariant.

The real IC10 harness injects interruption at dozens of instruction boundaries inside Plan Store COMMIT and requires every odd cut to recover to an even, non-authoritative plan. A later adversarial review added direct interleaving tests for allocator reflash liveness and for authority withdrawal after the POWER load/link executors have validated a plan but before they write physical `On`/`Setting`. Those tests exposed and fixed two more defects: `ic10/power-grid/power_reservation_allocator_v1_0.ic10` could remain safely inactive forever when PlanGeneration was unchanged after reflash, and the load/link executors could otherwise act on authority that had been revoked during their scan. The campaign now requires both fail-closed safety and eventual reacquisition of a still-valid current plan.

## Relationship to live-game tests

This automated campaign covers deterministic protocol and source-order failures. `docs/FRAMEWORK_HARDENING_TESTS.md` remains the physical Stationeers verification plan for device disappearance, power loss, network timing, Cargo LArRE behavior, and game-specific LogicType/slot semantics that cannot be fully reproduced by the Python harness.

A live-game failure does not weaken the transaction rule: physical execution remains fail-closed until exact current identity, generation, owner, epoch, and topology evidence agree.


## Item 11 cross-domain authority cuts

`tests/test_process_utility.py` extends the same stale-authority philosophy to complementary systems. Direct IC10 execution mutates external authority after initial observation but before final writes and proves:

- `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` does not actuate an Advanced Furnace embedded pump after GrantGuard generation/active authority is withdrawn;
- `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` does not turn on the composition Gas Mixer after ProcessCondition generation changes;
- `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` does not turn on the thermal Gas Mixer after ProcessCondition generation changes;
- `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` does not start a Gas Fuel Generator after the PowerPlan sequence is replaced/shortage cleared before its final write;
- current profile/request generations are re-fenced at actuation boundaries rather than trusted from the start of a scan.

These tests are intentionally separate from `ProcessCondition` correctness: the condition contract is not authority, so stale-condition rejection must ultimately collapse to the existing physical domain authority or safe-off behavior.
