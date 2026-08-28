# Stack Cell Monitor Getting Started

The Stack Cell Monitor is an on-demand commissioning tool for discovering a
common header of a service or reading one stack cell from another IC housing
without modifying that target. A Logic Memory selects discovery mode or an
address, and the monitor mirrors the result to its own housing `Setting` and,
optionally, to a second Logic Memory.

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

## 4. Identify a target

1. Set `Stack Address.Setting` to `-1`.
2. Wait for monitor status `3` in its own `S8`.
3. Read the target's `ServiceMagic` from monitor `S10` (and the optional
   `Stack Value` Memory), then look it up in the registry table in
   `docs/ABI_REFERENCE.md`.
4. Set `Stack Address.Setting` to `1` through `7` to read the rest of the header:
   ABI, CapabilityMask, SchemaId, ExtensionBase, State, TelemetryBase, and
   Generation. The mask at `S2` says which of those the target maintains.

Discovery reads only `S0..S7`. It validates a usable magic, a positive ABI, a
mask with no reserved bit set, and then only the fields that mask declares.
Because the header is the payload header, there is no separate payload address
to chase. See `docs/STACK_ABI_ENVELOPE.md` for the complete contract and the
migration backlog.

## 5. Read a stack cell

1. Set `Stack Address.Setting` to the integer stack address, from `0` through
   `511`.
2. Look directly at the monitor housing to read its `Setting` value.
3. If `d2` is connected, the same value appears in `Stack Value.Setting`.
4. Change the selector value to inspect another cell. No reflash is required.

For example, setting `Stack Address` to `6` reads `S6` from the housing connected
to `d0`. A captured NaN is displayed as NaN rather than being replaced with a
plausible number.

Legacy-exempt targets still require their ABI documentation. For migrated
targets, discovery reports whether the primary payload is at `S0`, `S96`, or
another address. Controller runtimes commonly use Generic Telemetry at `S96`.

The monitor publishes this diagnostic state in its own stack:

| Cell | Meaning |
| ---: | --- |
| `S8` | Status |
| `S9` | Selected stack address |
| `S10` | Sampled value for status `1`/`2`; otherwise `0` |
| `S11` | Target housing ReferenceId |
| `S7` | Sample generation, published last (the common header cell) |

For status `3`, `S10` is the discovered `ServiceMagic`. For status `1`/`2` it is
the sampled value. `S9` always holds the selected address, so a failed discovery
reports `-1` there rather than an address the monitor probed on its own.

Status values are:

| Status | Meaning |
| ---: | --- |
| `1` | Finite value captured |
| `2` | NaN captured from the target cell |
| `3` | Valid common header discovered |
| `-1` | Target missing |
| `-2` | Target is not a standard or compact IC housing |
| `-3` | Address selector missing or does not expose `Setting` |
| `-4` | Address is NaN, fractional, negative, or greater than `511` |
| `-5` | `S0` holds no usable magic |
| `-6` | Header fields or extension bounds are invalid |

## 6. Safety and limitations

The monitor never writes to `d0` or `d1`. Its only external write is the optional
`Setting` mirror on `d2`. It samples one cell at a time and does not claim that
several separately viewed cells came from one coherent generation. For a
generation-fenced multi-value capture, use
`ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` instead.
