# Stack Cell Monitor Getting Started

The Stack Cell Monitor is an on-demand commissioning tool for reading one stack
cell from another IC housing without modifying that target. A Logic Memory
selects the address, and the monitor mirrors the sampled value to its own housing
`Setting` and, optionally, to a second Logic Memory.

Use this tool when a production service publishes useful state in its IC stack
but has no human-facing display. Remove or repurpose the monitor after testing;
it is not part of the service's runtime authority path.

## 1. Export the monitor

From the repository root, export the production monitor program:

```bash
python3 tools/export_to_game.py \
  --output "<Stationeers-scripts-dir>" \
  --program stack_cell_monitor_v1_0
```

Add `--overwrite` when refreshing an existing export. The program appears in the
Stationeers script library as:

```text
Stack Cell Monitor
```

## 2. Build the monitor

The minimum in-world setup is:

- one IC housing and one blank IC10 chip;
- one Logic Memory for the selected stack address;
- power/data cable;
- the laptop, IC Editor motherboard, battery, screwdriver, and Labeller used for
  ordinary IC commissioning.

An optional second Logic Memory can provide a larger or remotely located value
display. In a creative single-player game, spawn missing components by prefab
name:

```text
thing spawn ItemKitLogicCircuit
thing spawn ItemIntegratedCircuit10
thing spawn ItemKitLogicMemory
thing spawn ItemKitLogicMemory
```

The second `ItemKitLogicMemory` is optional. Write `Stack Cell Monitor` to the
blank chip and install it in the new housing.

Label the first Logic Memory `Stack Address`. If present, label the second one
`Stack Value`.

## 3. Wire the monitor

Use the screwdriver to make these connections:

| Monitor screw | Device |
| --- | --- |
| `d0` | Target standard or compact IC housing |
| `d1` | `Stack Address` Logic Memory |
| `d2` | Optional `Stack Value` Logic Memory |

Power the monitor and both memories. The target must be an IC housing; ordinary
devices are rejected even if they expose other logic properties.

## 4. Read a stack cell

1. Set `Stack Address.Setting` to the integer stack address, from `0` through
   `511`.
2. Look directly at the monitor housing to read its `Setting` value.
3. If `d2` is connected, the same value appears in `Stack Value.Setting`.
4. Change the selector value to inspect another cell. No reflash is required.

For example, setting `Stack Address` to `6` reads `S6` from the housing connected
to `d0`. A captured NaN is displayed as NaN rather than being replaced with a
plausible number.

Do not assume that every target publishes its ABI header at `S0`. Select
addresses from that target program's ABI documentation. Controller runtimes use
the shared Generic Telemetry region beginning at `S96`; for example, the PI
Runtime publishes telemetry magic `27182818` at `S96`, its ABI at `S97`, and its
live channels beginning at `S100`.

The monitor publishes this diagnostic state in its own stack:

| Cell | Meaning |
| ---: | --- |
| `S2` | Status |
| `S3` | Selected stack address |
| `S4` | Sampled value for status `1`/`2`; otherwise `0` |
| `S5` | Target housing ReferenceId |
| `S6` | Sample generation, published last |

Status values are:

| Status | Meaning |
| ---: | --- |
| `1` | Finite value captured |
| `2` | NaN captured from the target cell |
| `-1` | Target missing |
| `-2` | Target is not a standard or compact IC housing |
| `-3` | Address selector missing or does not expose `Setting` |
| `-4` | Address is NaN, fractional, negative, or greater than `511` |

## 5. Safety and limitations

The monitor never writes to `d0` or `d1`. Its only external write is the optional
`Setting` mirror on `d2`. It samples one cell at a time and does not claim that
several separately viewed cells came from one coherent generation. For a
generation-fenced multi-value capture, use
`ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` instead.
