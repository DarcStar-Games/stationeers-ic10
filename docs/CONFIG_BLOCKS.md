# Generic Config Block Images

Config ABI v1 stores controller configuration as a **fixed physical image** divided into eight-slot blocks. Generic infrastructure understands geometry (which slots exist) but not field meaning.

## Geometry

- block width: **8 slots**;
- `Host S10`: block count, `1..4`;
- maximum physical image: **32 slots**;
- `Host S16..S19`: one low-eight-bit validity mask per block;
- effective image: `Host S96..S127`;
- candidate image: `Host S128..S159`.

A mask bit of `1` means that physical slot is part of the active schema. A `0` bit is padding/reserved and must not be treated as a user-editable field.

For block `b` and bit `i`, the physical slot is:

```text
slot = b * 8 + i
```

## Why physical slots and UI ordinals are different

A controller schema may contain reserved holes. Humans should still see a compact list of editable fields, so Loader derives:

```text
active ordinal 1..N  ->  stable physical slot 0..31
```

Example mask:

```text
block 0 mask = 0b00101101
```

Active physical slots are `0, 2, 3, 5`. The UI mapping is therefore:

| Active ordinal | Physical slot |
|---:|---:|
| 1 | 0 |
| 2 | 2 |
| 3 | 3 |
| 4 | 5 |

The user edits field 4; generic input resolves ordinal 4; Config Input Bridge maps it to physical slot 5; Editor stages slot 5. Generic code never needs to know the semantic field name.

## Persistence behavior

Generic Loader and Committer operate only on set mask bits. Generic Persistent Config Host persists the complete `blockCount * 8` physical image so bank offsets remain fixed and padding stays deterministic. Controller Policies zero padding while canonicalizing defaults/candidates.

Persisting the fixed-width image instead of packing only active fields has several advantages:

- bank offsets do not change when a schema contains holes;
- stable slots remain stable across revisions;
- recovery is a simple fixed-offset copy;
- schema compatibility is captured by the persistence signature rather than by reinterpreting packed records.

## Stable slot rule

Once a controller family assigns semantic meaning to a physical slot, later schemas **must not reuse that slot for a different meaning**. A removed/deprecated field becomes a reserved hole.

For example:

```text
schema 1: slot 4 = OutputMaximum
schema 2: OutputMaximum removed
schema 2: slot 4 = RESERVED   # correct
schema 2: slot 4 = NewSensorMode  # incorrect
```

Reusing a slot would make an old stored value look valid under a new meaning. The persistence signature protects incompatible geometry, but stable slot discipline also keeps tooling, documentation, and future migration logic intelligible.

## Adding fields safely

Preferred order:

1. Keep all existing field->slot assignments unchanged.
2. Fill an unused/reserved slot only if it has **never** carried another meaning.
3. Extend block count only when required.
4. Update masks, Policy defaults/validation, Profile descriptors, runtime slot constants, and documentation together.
5. Change controller schema/signature when compatibility rules require it.
6. Run `validation/validators/validate_config_contracts.py` and the persistence model tests.

See `docs/ADDING_CONTROLLERS.md` for the complete family checklist.
