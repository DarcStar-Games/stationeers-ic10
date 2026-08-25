# Diagnostic Input Path

Diagnostics uses the same Scanner/Resolver implementation as configuration. The diagnostic layer defines seven logical controls, but it does not reimplement Dial/Switch/Memory handling.

```text
Field Dial / Value Dial / Memory / Switch
                |
        Generic Input Scanner
                |
        Generic Input Resolver
                ^
                |
Input Profile Catalog Store
                |
Input Profile View: DiagnosticMapping/1
                |
        Diagnostic Input Bridge
                |
        Diagnostic Selector Bridge
           /                 \
Controller Selector      Console Selector
           \                 /
           Diagnostic Mapping Editor
                    |
             Diagnostic Renderer
```

## Why there are two bridges

The responsibilities are intentionally split:

- **Diagnostic Input Bridge** converts Resolver snapshots into persistent diagnostic UI state and decides when a user change should increment a request generation.
- **Diagnostic Selector Bridge** transports desired controller/console state into the generic selectors using their atomic request protocols.

Keeping selectors screwless means controller/console discovery and resolution can be reused by configuration or other future UI front ends.

The diagnostic profile is selected through `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`: connect View `d0` to the shared Input Profile Catalog Store, set `S2=HASH("DiagnosticMapping")` and `S3=1`, then attach the View to the Scanner. The catalog Store/loaders are shared with controller configuration profiles; diagnostics does not need a dedicated metadata store.

## Seven logical controls

The Diagnostic Profile exposes:

| Ordinal | Control | Input |
|---:|---|---|
| 1 | Controller Type ordinal | Integer Dial 1..16 |
| 2 | Controller Member ordinal | Integer Dial 1..16 |
| 3 | Console ordinal | Integer Dial 1..64 |
| 4 | Telemetry channel | Integer Dial 1..16 |
| 5 | LED Mode | Integer Dial 0..14 |
| 6 | LED Color | Integer Dial 0..11 |
| 7 | Commit + Next | Switch 0/1 |

Controller/member/console ranges are bounded by framework maximums. Selectors clamp requested ordinals to the currently discovered population, so transient discovery changes do not require the generic Profile to mutate.

## Diagnostic Input Bridge state

Bridge retains the current logical UI values at `S16..S25` (see `docs/ABI_REFERENCE.md`). It does not blindly increment generations every tick.

- Controller Type/Member changes increment one shared Controller Selector request generation.
- Console changes increment a separate desired-console generation.
- Commit is converted from Switch state into a rising-edge generation.

The rising-edge rule means leaving Commit Switch ON does **not** repeatedly create mappings.

## Selector transactions

Diagnostic Selector Bridge writes Controller Type and Member first, then publishes Controller Selector request generation. It writes desired Console first, then publishes Console desired-request generation.

Controller Selector publishes its complete selection/status before `S13` handled generation. Console Selector likewise publishes the complete console/status before its `S14` desired-response token and `S11` advance-response token.

Console Selector keeps desired-selection generation independent from its automatic advance generation. Before Mapping Editor consumes selector status or ReferenceIds it requires all relevant `ASYNC_REQUEST_V1 / TERMINAL_RESPONSE` identities to match: Diagnostic Input `S24 == Controller Selector S13`, Diagnostic Input `S25 == Console Selector S14`, and Console Selector `S10 == S11` so no previous automatic advance remains pending. This enables Mapping Editor to:

1. commit only a generation-qualified controller/console mapping;
2. increment Console Selector advance generation;
3. mark the diagnostic Commit generation handled.

The previous desired Console value is not re-applied unless the user actually changes Console control and Diagnostic Input Bridge produces a new desired generation. A Commit pressed immediately after changing a selector remains pending rather than consuming the prior selector result.

## Example mapping session

Suppose three consoles and two PI controllers are discovered.

1. Choose **Controller Type** and set the PI type ordinal.
2. Choose **Controller Member** and set member 1.
3. Choose **Console** and set console 1.
4. Choose **Telemetry Channel** and set channel 1 (PI process value).
5. Choose **LED Mode** and **LED Color** as desired.
6. Choose **Commit** and toggle the Switch OFF->ON.
7. Mapping Editor snapshots the *resolved* controller and console ReferenceIds and commits the renderer record.
8. Console Selector advances to console 2.
9. Change only telemetry channel/color as needed, then commit again to configure console 2.

This workflow is why stale desired Console state must not override the post-commit advance.

## Screw ownership

Only Generic Input Scanner owns physical commissioning screws. Resolver reads Scanner ReferenceIds. Diagnostic Input Bridge, Selector Bridge, selectors, Mapping Editor, and Renderer are all logical/network services.

If a future diagnostic feature needs a new physical control type, add it to the generic input abstraction when appropriate rather than wiring the physical device directly into Mapping Editor.

## Failure behavior

- If Value Dial disappears while a numeric control is active, Resolver may use Memory fallback when available.
- If the selected control cannot be resolved, Diagnostic Input Bridge should not turn invalid data into a new selector request.
- If discovery changes while a selector is resolving identity, the selector retries rather than publish a torn identity.
- If a newer Controller/Console request exists but its selector still exposes an older success, Mapping Editor ignores that stale success until the matching handled token is published.
- If Console automatic advance is pending, Mapping Editor refuses the next Commit until the advance response token catches up.
- If Commit occurs while selectors are temporarily unavailable, Mapping Editor retains the unhandled generation and can complete after dependencies recover.
- Renderer lag affects refresh timing, not mapping transaction correctness.

## Console circuitboard mirrors

Hash Display and Graph Display are **circuitboards installed in a Console**, not display devices. They
read a value from a linked device rather than accepting one written to them, so the render path
reaches them indirectly through a mirror sink.

```text
Controller telemetry -> Diagnostic Renderer -> Logic Memory (mirror sink)
                                                     ^
                                     Console + Hash/Graph circuitboard reads it
```

A mirror sink is any device carrying a readable and writable `Setting` without `Mode`/`Color`, tagged
with the Console Registry enrollment NameHash. Console Registry v1.1 classifies rather than gates on
capability: a device exposing `Setting`, `Mode`, `Color` and `On` enrols as an LED display, and one
exposing only `Setting` enrols as a mirror sink. Both land in the same sorted registry, and because
records sort by `PrefabHash` first, the two classes cluster naturally without a second directory.

The Renderer needs no mirror-specific logic. It already probes each presentation property with
`bdnvs` before writing, so it writes `Setting` to a mirror and skips `Mode`/`Color` without faulting.
Mapping Editor is likewise unchanged; its committed `Mode`/`Color` fields are simply unused for a
mirror record.

The Console-to-circuitboard link is player-owned and established once during commissioning. It is not
settable from logic, which is the reason the mirror exists rather than the framework addressing the
Console directly.

**Gas Display is deliberately excluded.** It reads pressure and temperature from a gas-containing
device, which a Logic Memory cannot present. Link it to a PressureGrid-managed tank or pipe directly;
no framework program participates.

### Circuitboard Mode

`ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10` sets Hash Display `Mode` — `HashType.Prefab`
or `HashType.GasLiquid` — through the logic slot instructions, the mechanism the 2025-03-17 update
added for exactly this. It reads the slot back with `ls` before writing with `ss`, publishes writes
issued at `S3`, and counts unreadable records at `S4` instead of faulting. This is the framework's
only use of `ss`.

Two facts here are **not sourced from game data**: the circuitboard's slot index, and that `Mode` is
the slot logic type accepted by `ls`/`ss`. They need one live observation, which is why this lives in
a separate optional program rather than inside Renderer or Mapping Editor — if either assumption is
wrong, only this program is affected and the mirror path above still works. Case `LG-DIAG-HASHMODE`
records the observation; `LG-DIAG-MIRROR` covers the mirror render path.

See `docs/FRAMEWORK_HARDENING_TESTS.md` for the corresponding live-game cases.
