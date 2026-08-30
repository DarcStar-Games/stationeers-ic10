# ControllerSequencer Family

`ControllerSequencer` is the first non-feedback-loop production family in the framework. It exists both as a useful controller and as an architectural test: the same discovery, selection, configuration, persistence, shared-input, and diagnostics infrastructure must work even when the runtime is a discrete state machine rather than PI math.

The family implements a simple reusable cycle:

```text
FILL -> SETTLE -> DRAIN -> repeat or COMPLETE
```

The process input decides when FILL and DRAIN finish. A configurable timeout prevents either active phase from running forever.

## Why this family matters

PI/PID-style control repeatedly calculates a numeric output from an error. A sequencer has a different shape:

- discrete states instead of a continuously varying control law;
- transition conditions instead of proportional/integral math;
- timers and timeouts;
- two mutually exclusive actuators;
- one-shot versus repeating behavior;
- terminal COMPLETE and FAULT states.

If this family required special cases in Generic Host, Loader, Committer, Scanner, Resolver, selectors, or diagnostics, that would be evidence that the supposedly generic layer still contained PI assumptions. It does not: only the Runtime, Policy, and optional Profile are family-specific.

## Files

- `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` — runtime/state machine and telemetry.
- `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` — optional commissioning metadata selected from the shared Input Profile Catalog with `S8=HASH("ControllerSequencer")`, `S9=1`.
- `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10` — config geometry, defaults, validation, normalization, and persistence signature.
- `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` — unchanged generic durable configuration Host used per sequencer instance.

## Runtime wiring

The Runtime uses four screws:

| Screw | Purpose |
|---|---|
| `d0` | Process/input device. The configured Input LogicType is read from this device. |
| `d1` | Fill actuator. Runtime writes `1` during FILL and `0` otherwise using the configured Fill LogicType. |
| `d2` | Drain actuator. Runtime writes `1` during DRAIN and `0` otherwise using the configured Drain LogicType. |
| `d3` | Paired Generic Persistent Config Host. |

The Runtime is intentionally device-agnostic. A pressure sensor plus two valves is the obvious use, but the process value can be any readable numeric LogicType and the two outputs can use any writable action LogicType accepted by the devices.

## State machine

Runtime state is published as telemetry channel 2.

| State | Name | Outputs | Transition |
|---:|---|---|---|
| `0` | FILL | Fill=1, Drain=0 | When process value reaches/exceeds `HighThreshold`, enter SETTLE. |
| `1` | SETTLE | Fill=0, Drain=0 | After `SettleTicks`, enter DRAIN. |
| `2` | DRAIN | Fill=0, Drain=1 | When process value reaches/falls below `LowThreshold`, finish the cycle. |
| `3` | COMPLETE | Fill=0, Drain=0 | Remains complete until the controller is disabled or config is reloaded. |
| `4` | TIMEOUT | Fill=0, Drain=0 | Latched while enabled; disable to acknowledge/reset. |
| `5` | NUMERIC FAULT | Fill=0, Drain=0 | Latched while enabled; disable to acknowledge/reset. |

When `Repeat=1`, successful DRAIN completion increments the cycle counter and returns directly to FILL. When `Repeat=0`, it increments the counter and enters COMPLETE.

Disabling the controller always commands both outputs off and resets state/ticks to the start of the sequence. Re-enabling starts with FILL.

## Configuration schema 1

The schema uses two eight-slot blocks. Masks are:

```text
block 0: 255 = 0b11111111
block 1:   1 = 0b00000001
```

There are nine active fields and seven reserved/padding cells in the second physical block.

| Active ordinal | Physical slot | Field | Default | Meaning |
|---:|---:|---|---:|---|
| 1 | 0 | Enabled | `0` | `0` safe/off; nonzero input is normalized to `1`. |
| 2 | 1 | Input LogicType | `Pressure` | Numeric LogicType read from `d0`. |
| 3 | 2 | LowThreshold | `100` | DRAIN completes when process `<=` this value. |
| 4 | 3 | HighThreshold | `200` | FILL completes when process `>=` this value. |
| 5 | 4 | Fill LogicType | `On` | Writable LogicType used on `d1`. |
| 6 | 5 | Drain LogicType | `On` | Writable LogicType used on `d2`. |
| 7 | 6 | SettleTicks | `10` | Controller iterations spent with both outputs off after FILL. |
| 8 | 7 | TimeoutTicks | `300` | Maximum controller iterations allowed in FILL or DRAIN. |
| 9 | 8 | Repeat | `1` | `1` repeats after DRAIN; `0` enters COMPLETE. |

### Timing units

`SettleTicks` and `TimeoutTicks` are **runtime loop iterations**, not a promise of wall-clock seconds. Each Runtime loop begins with `yield`, so tick duration is tied to Stationeers IC execution scheduling. Use live-game measurements if exact elapsed time matters.

The Input Profile exposes both timing fields through Integer Dial ranges suitable for quick commissioning (`0..999` settle, `1..999` timeout). The Policy accepts values up to `100000`, so Logic Memory fallback can enter larger values when needed.

## Policy validation and normalization

The Config Policy enforces controller semantics before Generic Host is allowed to durably apply a candidate.

Accepted candidates are normalized as follows:

- Enabled becomes exactly `0` or `1`.
- Repeat becomes exactly `0` or `1`.
- Input, Fill, and Drain LogicType values must be integral.
- SettleTicks and TimeoutTicks must be integral.
- reserved/padding cells are zeroed before acceptance.

Cross-field rules:

- `LowThreshold < HighThreshold`;
- `SettleTicks >= 0`;
- `TimeoutTicks > 0`;
- both timing values must be `<= 100000`.

Policy result codes:

| Result | Meaning |
|---:|---|
| `5` | Candidate accepted and normalized. |
| `-5` | Candidate contains NaN/malformed numeric data. |
| `-71` | Invalid threshold ordering (`LowThreshold >= HighThreshold`). |
| `-72` | A discrete field that must be integral was not integral. |
| `-73` | Invalid settle/timeout range. |

The persistence signature is:

```text
CFG1|ControllerSequencer|1|2|255|1|0|0
```

The Runtime checks exact Generic Host ABI 1 and this exact schema signature before loading the effective image.

## Input Profile behavior

The optional Profile uses the generic commissioning input kinds rather than custom sequencer UI code.

Preferred inputs:

- Enabled -> Switch.
- Input LogicType -> Enum Dial.
- LowThreshold / HighThreshold -> Logic Memory by default because useful ranges depend on the process variable.
- Fill / Drain LogicType -> Enum Dial.
- SettleTicks / TimeoutTicks -> Integer Dial.
- Repeat -> Switch.

The readable Input LogicType enum matches the broad PI read list:

```text
Setting, Pressure, Temperature, Ratio, Charge,
Power, PowerActual, PowerPotential, Volume, Quantity,
On, Open, Mode, Output, PressureSetting, TemperatureSetting
```

The writable action enum is intentionally smaller:

```text
On, Open, Activate, Setting, Mode
```

A missing preferred input can still fall back to Logic Memory through the existing Generic Input Resolver rules.

## Telemetry

The Runtime advertises channels 1..5.

| Channel | Meaning |
|---:|---|
| 1 | Current process value read from `d0`; NaN when unavailable. |
| 2 | Current sequencer state (`0..5`, table above). |
| 3 | Number of loop iterations spent in the current timed state. |
| 4 | Completed cycle count since Runtime program start/reinitialization. |
| 5 | Runtime status code. |

Status codes:

| Status | Meaning |
|---:|---|
| `0` | No currently detected runtime fault. |
| `-1` | Process/input device or configured input LogicType unavailable. |
| `-4` | Paired Config Host is unavailable/incompatible or effective config cannot be loaded coherently. |
| `-5` | Process value was NaN; Runtime enters numeric-fault state. |
| `-6` | FILL or DRAIN exceeded TimeoutTicks; Runtime enters timeout state. |

Status is deliberately separate from state. For example, COMPLETE is state `3` with status `0`. Output writes use store-validity guards so an unavailable actuator does not halt the IC; the v1 Runtime does not dedicate a separate status code to which output is unavailable. If an unavailable output prevents process progress, the active phase reaches the normal timeout fault.

## Safety and failure behavior

The Runtime explicitly initializes its state, timer, cycle counter, Host identity, and effective-generation registers at program start. This is required because IC10 registers are retained across program flashes and power changes rather than automatically zeroed.

The controller uses a conservative output policy:

- Disabled -> both outputs commanded `0`.
- SETTLE -> both outputs `0`.
- COMPLETE -> both outputs `0`.
- TIMEOUT -> both outputs `0`.
- NUMERIC FAULT -> both outputs `0`.
- missing process input -> both outputs `0` for that iteration.
- invalid/incompatible Config Host -> Runtime attempts to command both outputs `0` using the last loaded output LogicTypes.

FILL and DRAIN are mutually exclusive because actuator commands are derived directly from the state number.

This is not a substitute for physical pressure relief, back-pressure regulation, or other fail-safe hardware. IC10 failure, power loss, device behavior, and pipe mechanics still need to be considered in the actual build.

## Example: pressure cycling

A simple gas-transfer test could use:

```text
Enabled        = 1
Input LogicType= Pressure
LowThreshold   = 100
HighThreshold  = 200
Fill LogicType = On
Drain LogicType= On
SettleTicks    = 10
TimeoutTicks   = 300
Repeat         = 1
```

With `d0` reading the controlled volume pressure, `d1` driving an inlet device, and `d2` driving an outlet device:

1. FILL turns inlet on until pressure reaches 200.
2. SETTLE turns both outputs off for 10 controller iterations.
3. DRAIN turns outlet on until pressure reaches 100.
4. Cycle count increments.
5. Repeat returns to FILL.

For a one-shot transfer/test, set `Repeat=0`. The controller enters COMPLETE after the first successful DRAIN leg and stays safely off until disabled/re-enabled.

## What this controller is not

The v1 sequencer deliberately stays small enough for one IC10 runtime. It does not currently provide:

- arbitrary user-defined state tables;
- more than two action outputs;
- per-state independent timeout values;
- conditional branching to multiple next states;
- wall-clock scheduling;
- recipe-aware furnace logic;
- automatic discovery of the process/actuator devices.

Those can be considered later, but adding them should be driven by a concrete use case. The purpose of this family is to establish that discrete state-machine controllers fit the existing framework without expanding generic infrastructure.

## Architecture result

The family reuses, unchanged:

- Controller Directory / direct Controller Selector;
- Generic Persistent Config Host;
- Generic Config Editor / Loader / Committer;
- Generic Input Scanner / Resolver / Config Input Bridge;
- diagnostic mapping and rendering services.

That is the primary architectural success criterion. `ControllerSequencer` adds a genuinely different runtime model without creating a new generic service or adding family-specific branches to existing generic scripts.
