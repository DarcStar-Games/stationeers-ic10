# Live-Game Commissioning & Field Evidence

Roadmap Item 12 closes the gap between automated protocol proof and actual Stationeers device/network behavior. Items 1–11 remain implemented and automatically validated; Item 12 is **ACTIVE** until every required live suite in `data/live_commissioning_cases.json` has current PASS evidence from the target game build.

Automated/model evidence is never promoted to live evidence. A safe modeled result can still differ from real device timing, writable LogicTypes, slot layouts, atmosphere behavior, chute timing, or machine-specific semantics.

## 1. Evidence authority

Three identities are deliberately separate:

1. `validation/evidence/` proves deterministic source/model/harness checks for a release input fingerprint.
2. `data/live_commissioning_cases.json` defines the required field suites and acceptance summaries.
3. A live session records human-observed physical results and is bound to the exact framework input fingerprint plus commissioning-catalog SHA-256.

Changing framework inputs or the case catalog makes an older field session **STALE**. Re-run affected live suites rather than copying their old PASS state forward.

Do not hand-edit automated evidence to represent game observations.

Contract-aware wiring checks use the same field session and fingerprint. See `docs/CONTRACT_COMMISSIONING.md` for validating explicit `d0..d5` mappings and recording per-port runtime obligations.

## 2. Field session CLI

Create a session outside the framework tree or under an ignored local evidence directory:

```text
python3 tools/live_commission.py init --session ../field_evidence/base_a.json --label "Base A commissioning"
```

List or inspect the required suites:

```text
python3 tools/live_commission.py list
python3 tools/live_commission.py show LG-XDOMAIN-FURNACE
```

Record an observation:

```text
python3 tools/live_commission.py record \
  --session ../field_evidence/base_a.json \
  --case LG-XDOMAIN-FURNACE \
  --status PASS \
  --precondition "Transform=Inconel; plan epoch=12; ProcessCondition generation=41" \
  --action "Route conditioned fuel buffer into Advanced Furnace" \
  --observed "161 stayed WAIT until live P/T entered recipe window, then admitted" \
  --refs "furnace:12345,condition:23456,planner:34567"
```

`PASS`, `FAIL`, and `BLOCKED` observations are append-only within a case; the latest run is the current case status. A failed case can therefore be rerun after a fix without deleting the failure history.

Verify closure and generate a report:

```text
python3 tools/live_commission.py verify --session ../field_evidence/base_a.json
python3 tools/live_commission.py report --session ../field_evidence/base_a.json --output ../field_evidence/base_a.md
```

Item 12 closes only when `verify` reports every required suite PASS on a non-stale session.

## 3. Live Commission Snapshot Probe ABI1

`ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` is a read-only on-demand diagnostic. It observes up to six devices/services connected on `d0..d5`. It never writes any observed device and therefore cannot become a commissioning bypass around normal reservations, epochs, locks, or actuator authority.

Magic `31416051`, ABI 1.

```text
S0  magic
S1  ABI
S2  RequestToken                caller publishes LAST
S3  ResponseToken               probe publishes LAST
S4  Status: 1 complete, -1 bad config generation,
            -2 one or more observations failed, -3 descriptor changed during capture
S5  successful observation count
S6  DescriptorGeneration        caller increments after descriptor edits
S7  captured DescriptorGeneration
S9  first failing observation ordinal, -1 if none
```

Six descriptors live at `S32..S49`, three cells each:

```text
[Mode, FieldOrStackCell, FenceStackCell]
```

Modes:

- `0` disabled;
- `1` LogicType read from the matching screw; `FieldOrStackCell` is the numeric LogicType enum and `FenceStackCell` is ignored;
- `2` stack-cell read; `FieldOrStackCell` is the value cell and `FenceStackCell >= 0` requests positive before/after generation fencing. Use `-1` only for a stack value whose source contract does not define a generation.

Results live at `S64..S93`, five cells per observation:

```text
[ReferenceId, Mode, ObservationStatus, Value, FenceGeneration]
```

Observation status:

```text
 1 captured
 0 disabled
-1 source screw missing
-2 unsupported LogicType / invalid mode
-3 nonpositive or changed stack fence
-4 NaN value
```

A stack-mode source is expected to be a stack-capable device/service. The probe does not invent a way to query whether an arbitrary game object implements stack memory.

IC10 currently supports register-addressed stack reads and device/LogicType indirection; those are the only dynamic mechanisms the probe relies on. See `docs/SOURCES.md`.

### Human-visible stack inspection

`ic10/live-commissioning/stack_cell_monitor_v1_0.ic10` is the smaller tool for
interactive commissioning. It reads one selected `S0..S511` cell from a standard
or compact IC housing and mirrors the result to its own housing `Setting` and an
optional Logic Memory. Selector value `-1` instead reads and validates only the
common `S320..S327` Stack Envelope v1, publishing semantic ServiceId and primary
payload base without prior family knowledge. It never writes the target or
selector. Separate samples are not a coherent multi-cell snapshot. Use the
Snapshot Probe above when generation fencing matters. See
`docs/STACK_CELL_MONITOR_GETTING_STARTED.md` for the in-world setup and
`docs/STACK_ABI_ENVELOPE.md` for the fixed contract.

## 4. Required live suites

`data/live_commissioning_cases.json` is canonical. The current required suites cover:

- PressureGrid inventory, purity, reservation, routing, interruption, scale, and overflow;
- persistent configuration and banked transactions;
- shared input/diagnostics;
- Sequencer, PhasePressure, and PressureDomain controllers;
- multi-hop and cost-aware pressure routing;
- MaterialGrid, chute/Stacker behavior, and real furnace execution;
- Generic Job Store and Manufacturing Scheduler behavior;
- ITEM storage, LArRE recovery, and SDB exact-delivery boundaries;
- PowerGrid batteries, transformers, shedding, allocator recovery, and final authority fences;
- Item-11 furnace utility orchestration;
- Item-11 Gas Fuel Generator utility behavior and measured fuel-to-power characterization;
- cross-domain reflash and authority-mutation cuts.

The Electrolyzer energy-storage cycle remains optional because it has not yet been implemented as a production policy.

## 5. Minimum POWER live checks

The POWER suite must include at least:

1. compare a Cable Analyzer-backed producer Endpoint with real aggregate `PowerPotential` while generators are added/removed;
2. verify managed load demand remains visible while the executor sheds the physical load Off;
3. verify a Station Battery never advertises discharge below reserve or charge above target and reacquires the unchanged current plan after allocator reflash;
4. verify `RespectPhysicalOn=1` is a real external lockout while the default does not self-lock a framework-controlled battery;
5. verify transformer `Maximum`, configured safe ceiling, and source-side `RequiredPower` overhead constrain real delivery;
6. revoke allocator ACTIVE/PlanGeneration/Epoch immediately before load/transformer writes and confirm break-before-make safe-off;
7. replace the coherent PowerPlan while executors are scanning and confirm stale flows never actuate;
8. measure plan behavior at actual network update cadence rather than assuming the deterministic harness timing is identical to the game.

## 6. Item-11 commissioning split

The Item-11 twelve-step hardening list is recorded as four suites:

- `LG-XDOMAIN-FURNACE` — steps 1–7;
- `LG-XDOMAIN-GFG` — steps 8–9;
- `LG-XDOMAIN-RESTART` — steps 10–11;
- `LG-ELECTROLYZER-CYCLE` — step 12, optional until the storage policy exists.

This keeps a GFG characterization failure from hiding behind a broader furnace PASS and preserves the distinction between implemented orchestration and future energy-storage policy.

## 7. Closing Item 12

Item 12 acceptance requires all of the following:

- the automated release suite is green for the same framework fingerprint;
- every required live suite has a latest `PASS` observation;
- the session is not stale;
- every discovered live-game mismatch is either fixed and rerun or explicitly removed from the supported production contract;
- game-build/version notes are recorded in the session label or observations;
- no live PASS is inferred solely from a Python model or `framework/ic10_harness.py` result.

Until then, a release may be described as **commissioning-ready**, not **field-verified**.
