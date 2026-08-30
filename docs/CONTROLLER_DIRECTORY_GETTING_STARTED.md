# Controller Directory Getting Started

This guide tests the smallest useful production Controller Directory path. It
uses an already working telemetry controller, such as the PI Runtime from
`docs/PI_CONTROLLER_GETTING_STARTED.md`, and adds the generic snapshot
publication infrastructure needed by selection, diagnostics, and controller
arbitration.

This test covers directory discovery and publication only. It does not add the
Controller Selector or configuration editor stack.

## 1. Prepare the stack monitor

Build and verify the monitor in
`docs/STACK_CELL_MONITOR_GETTING_STARTED.md` before assembling the directory.
The directory programs publish their contracts in stack cells and do not alter
their housing `Setting` values for display.

Keep exactly one telemetry controller on the test data network for the simplest
expected result. The PI Config Host and PI Config Policy do not advertise
controller telemetry and are not counted.

## 2. Export the directory programs

From the repository root, export the three production programs:

```bash
python3 tools/export_to_game.py \
  --output "<Stationeers-scripts-dir>" \
  --program controller_directory_adapter_v4_0 \
  --program generic_directory_adapter_bridge_v1_0 \
  --program generic_snapshot_directory_host_v1_0
```

Add `--overwrite` when refreshing existing exports. They appear in the in-game
script library as:

- `Directory Adapter`
- `Directory Adapter Bridge`
- `Snapshot Directory Host`

## 3. Build the directory

Add three IC housings and three blank IC10 chips. In a creative single-player
game, spawn missing components by prefab name:

```text
thing spawn ItemKitLogicCircuit
thing spawn ItemKitLogicCircuit
thing spawn ItemKitLogicCircuit
thing spawn ItemIntegratedCircuit10
thing spawn ItemIntegratedCircuit10
thing spawn ItemIntegratedCircuit10
```

Write one exported directory program to each chip. Label the housings:

- `Controller Directory Adapter`
- `Controller Directory Bridge`
- `Controller Directory Host`

Connect all three housings to the same power/data network as the running PI
Runtime. The Adapter discovers telemetry IC housings by scanning its own data
network.

## 4. Set the device screws

Use the screwdriver to make these connections:

| Program | Screw | Device |
| --- | --- | --- |
| Controller Directory Adapter | none | No device screws required |
| Generic Directory Adapter Bridge | `d0` | Controller Directory Adapter |
| Generic Directory Adapter Bridge | `d1` | Controller Directory Host |
| Generic Snapshot Directory Host | none | No device screws required |

Turn on the Directory Host and Bridge, then turn on the Adapter. Wait several
game ticks for the first scan and publication.

## 5. Inspect the Adapter

Connect the Stack Cell Monitor's `d0` screw to the Controller Directory Adapter.
Use its `Stack Address` Logic Memory to inspect:

| Address | Expected value | Meaning |
| ---: | ---: | --- |
| `0` | `HASH("DirectoryAdapter.v3")` | Generic Directory Adapter magic |
| `1` | `3` | Adapter ABI |
| `2` | `17` | Capability mask: `HAS_SCHEMA` + `HAS_GENERATION` |
| `3` | record exact value | `DirectorySchema.Controller.v1` folded schema hash |
| `10` | `2` | Two cells per controller record |
| `11` | `64` | Directory capacity |
| `12` | `1` | One telemetry controller discovered |
| `13` | even | Stable adapter sequence |
| `14` | `0` | No overflow |
| `15` | `1` | Snapshot publication mode |

If other telemetry controllers share the network, `S12` should equal that larger
known count instead of `1`.

The exported Controller Directory Adapter hardcodes
`HASH("DirectorySchema.Controller.v1")` at `S3`. Record its displayed numeric value;
the Host must publish that exact value at `S9` after the Bridge commits it.

## 6. Inspect the Snapshot Host

Move the Stack Cell Monitor's `d0` screw to the Controller Directory Host.
First verify the fixed header:

| Address | Expected value | Meaning |
| ---: | ---: | --- |
| `0` | `HASH("GenericSnapshotDirectoryHost.v1")` | Generic Snapshot Directory magic |
| `1` | `1` | Host ABI |
| `9` | same as Adapter `S3` | Controller schema identity |
| `11` | `2` | Two cells per record |
| `12` | `64` | Capacity |
| `23` | `0` | No malformed Host request observed |

Read `S24` to determine the active bank, then use the matching row:

| `S24` | Generation | Count | Overflow | First record |
| ---: | ---: | ---: | ---: | --- |
| `0` | `S25` | `S27` | `S29` | type `S32`, ReferenceId `S33` |
| `1` | `S26` | `S28` | `S30` | type `S160`, ReferenceId `S161` |

The active generation must be positive, count must be `1`, and overflow must be
`0`. Use the Authoring Tool tooltip to confirm that the first record's
ReferenceId matches the PI Runtime housing.

## 7. Test removal and recovery

1. Record the Host's active bank and generation.
2. Physically disconnect the PI Runtime housing from the directory data network.
   Merely switching the IC off may leave its previous telemetry stack reachable.
3. Wait for a new directory publication. Re-read `S24`, then the active count and
   generation. Count should become `0`, and generation should advance.
4. Reconnect the PI Runtime data cable.
5. Wait for publication again. Count should return to `1`, generation should
   advance, and the published ReferenceId should match the same runtime housing.

The test passes when discovery, removal, and recovery each produce a complete,
non-overflowed snapshot. A later guide can add Controller Selector behavior on
top of this verified directory substrate.
