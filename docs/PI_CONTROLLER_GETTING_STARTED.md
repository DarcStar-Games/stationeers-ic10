# PI Controller Getting Started

This guide reproduces the smallest useful live-game test of the PI controller.
It uses the existing production scripts without modifying them and substitutes
two Logic Memories for a real sensor and actuator.

Passing this test establishes that the exported scripts load, the configuration
services bootstrap, and the PI runtime reads, integrates, clamps, writes, and
recovers from a missing input. It is a smoke test, not the full commissioning or
Item-12 evidence procedure.

## 1. Export the existing programs

From the repository root, export the three programs to the Stationeers saved
scripts directory:

```bash
python3 tools/export_to_game.py \
  --output "<Stationeers-scripts-dir>" \
  --program generic_persistent_config_host_v1_1 \
  --program pi_config_policy_v1_0 \
  --program controller_pi_runtime_v1_1
```

If these exporter-owned entries already exist and need to be refreshed, add
`--overwrite`. The programs appear in the in-game script library as:

- `controller-config__generic_persistent_config_host_v1_1`
- `controller-pi__pi_config_policy_v1_0`
- `controller-pi__controller_pi_runtime_v1_1`

No new test scripts or edits to these programs are required.

## 2. Spawn the test equipment

Start a creative single-player game. In the game console, use prefab names, not
prefab hashes. Skip any equipment already available in the world.

```text
thing spawn ItemAuthoringTool
thing spawn ItemRTG
thing spawn ItemCableCoil
thing spawn ItemLaptop
thing spawn MotherboardProgrammableChip
thing spawn ItemBatteryCellNuclear
thing spawn ItemScrewdriver
thing spawn ItemLabeller
thing spawn ItemKitLogicCircuit
thing spawn ItemKitLogicCircuit
thing spawn ItemKitLogicCircuit
thing spawn ItemIntegratedCircuit10
thing spawn ItemIntegratedCircuit10
thing spawn ItemIntegratedCircuit10
thing spawn ItemKitLogicMemory
thing spawn ItemKitLogicMemory
thing spawn ItemIronFrames
```

The repeated commands provide three IC housings, three blank IC10 chips, and two
Logic Memories. The iron frames are only needed when the test location needs a
build surface.

Install the nuclear battery and programmable-chip motherboard in the laptop.
Use the laptop to write one exported program to each blank IC10 chip.

## 3. Assemble and label the bench

Place the three IC housings and two Logic Memories. Connect all five devices to
the RTG with power/data cable.

Install the chips so that the housings run:

1. Generic Persistent Config Host
2. PI Config Policy
3. PI Runtime

Label one Logic Memory `PI Input` and the other `PI Output`. Set their initial
values with the Labeller:

- `PI Input`: `Setting = -1`
- `PI Output`: `Setting = 0`

## 4. Set the device screws

Use the screwdriver to make these connections:

| Program | Screw | Device |
| --- | --- | --- |
| Generic Persistent Config Host | none | No device screws are required |
| PI Config Policy | `d0` | Config Host housing |
| PI Runtime | `d0` | `PI Input` Logic Memory |
| PI Runtime | `d1` | `PI Output` Logic Memory |
| PI Runtime | `d2` | Config Host housing |

Turn on the Config Host and PI Config Policy first. Wait a few game ticks for
the policy to publish the default configuration, then turn on the PI Runtime.

For this test the existing PI policy supplies these defaults:

| Field | Default |
| --- | --- |
| Setpoint | `0` |
| Proportional gain (`Kp`) | `1` |
| Integral gain (`Ki`) | `0.1` |
| Output range | `0` through `100` |
| Input property | `Setting` |
| Output property | `Setting` |
| Direction | `1` |
| Automatic mode | enabled |

## 5. Run the first tests

1. Leave `PI Input` at `-1`. `PI Output` should become positive and rise
   gradually.
2. Change `PI Input` to `1`. `PI Output` should fall and clamp at `0`.
3. Change `PI Input` back to `-1`. `PI Output` should begin rising again.
4. Briefly disconnect the PI Runtime's `d0` screw. The runtime must not write an
   invalid numeric value while its input is unavailable. Reconnect `d0` and
   confirm that normal control resumes.

## 6. Interpret the result

Passing all four checks confirms:

- Stationeers can load the repository's exported saved-script XML.
- Config Host and PI Config Policy bootstrap and exchange the default image.
- PI Runtime consumes the cross-IC configuration.
- Error direction, proportional response, integration, and output clamping work.
- A missing process input does not produce an invalid actuator write, and the
  controller resumes after reconnection.

This bench does not test automatic controller discovery, the generic editor and
display workflow, durable A/B-bank recovery, a physical sensor or actuator, or
the formal live-evidence cases. Continue with
`docs/COMMISSIONING_QUICKSTART.md` when the complete controller stack is needed.
