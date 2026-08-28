# Common Stack Header v1

Every deployable IC10 service identifies itself in the same eight cells, `S0..S7`.
A generic tool reads those cells and learns what the program is, which ABI it
speaks, which schema it carries, and where to find any extended metadata —
without knowing the family beforehand.

The header is not a second copy of an existing layout. It **is** the payload
header, at the address 154 of 173 programs already use.

## Why the first cells

The generated inventory evaluated every one of the 173 deployable programs:

- 154 already publish their magic at `S0` and their ABI at `S1`;
- the 7 Generic Telemetry runtimes publish at `S96`, and 6 of them touch no cell
  below `S96` at all, so `S0/S1` is free in every one;
- the 12 programs with no declared header have `S0/S1` free, and 10 of them use
  no own-stack cell whatsoever.

So the header costs nothing to adopt at `S0/S1`. What it costs is `S2..S7`, which
148 programs use for family payload today. Reserving eight rather than five adds
only three programs to that backlog — nearly every program that uses `S5..S7`
already uses `S2..S4` — while adding cells later would break the same ~146
programs a second time.
Those programs are the migration backlog, and each is listed individually in
`contracts/stack_envelope_inventory.json` with the cells it must move.

A fixed window high in the stack — the shape first proposed for this design — avoids
that renumbering, but only by duplicating the ABI and schema cells the majority
already publish at `S1..S3` and by spending eight cells and eight lines on every
program to say what four of its own cells already said.

## Fixed v1 cells

| Cell | Name | Written | Rule |
| ---: | --- | --- | --- |
| `S0` | `ServiceMagic` | always | the service's registered nonzero magic; identity |
| `S1` | `ServiceABI` | always | positive exact ABI of this service contract |
| `S2` | `CapabilityMask` | always | which of `S3..S7` this service declares |
| `S3` | `SchemaId` | bit 0 | schema identity **and version**, one exact match |
| `S4` | `ExtensionBase` | bit 1 | base of a v1 extension, `S8` or later |
| `S5` | `State` | bit 2 | v1 state value; mutable |
| `S6` | `TelemetryBase` | bit 3 | base of a telemetry block outside the header |
| `S7` | `Generation` | bit 4 | publication fence; initialized to 0, advanced, published last |

Three cells are mandatory and contiguous: identity at `S0`/`S1`, which 154 of
173 programs already publish, and the mask at `S2`. A reader takes that prefix
and immediately knows which of the rest to read. Every other cell is written only when the
mask declares it, and a reader never reads an undeclared cell. That is what makes
the header safe on hardware where the stack survives reflash: a cell nobody wrote
holds whatever the previous script left, so v1 reads it only when a service that
provably writes it says to.

The magic is the on-stack identity. It is registered in `docs/ABI_REFERENCE.md`,
stable across implementation revisions, and unrelated to a filename — moving a
source file or bumping a `_v<major>_<minor>` suffix changes neither the magic nor
the service contract. It identifies a *contract*, not a program: the three
generated directory adapters share one magic because they publish one contract.
The semantic `ic10.script.*` id remains the registry-side identity in
`contracts/`; it is not published on the stack.

v1 validates the **shape** of a header, not membership in a registry: a reader
proves the cells are well formed and self-consistent, then resolves the magic
through the generated contract index.

### CapabilityMask

| Bit | Value | Meaning |
| ---: | ---: | --- |
| 0 | 1 | `HAS_SCHEMA` — `S3` carries a schema identity |
| 1 | 2 | `HAS_EXTENSION` — `S4` addresses a v1 extension |
| 2 | 4 | `HAS_STATE` — `S5` carries a v1 state value |
| 3 | 8 | `HAS_TELEMETRY` — `S6` addresses a telemetry block |
| 4 | 16 | `HAS_GENERATION` — `S7` is a publication fence |
| 5+ | — | reserved for cross-cutting protocol capabilities; must be zero |

The mask is **derived, never hand-written**: the generator computes it from the
reviewed declaration and the validator requires the source to publish exactly
that value. A bit cannot be set for a field the program does not publish, and a
field cannot be published without its bit.

Bits 5 and up are reserved for the framework's cross-cutting standards —
`ASYNC_REQUEST_V1`, `BANKED_TRANSACTION_V1`, `GENERIC_JOB_ABI_V1`, directory
provider. They stay unallocated until each has a derivable source of truth;
today those participant lists live as literals inside their validators, and a
hand-maintained capability bit is exactly the kind of metadata that rots.

### SchemaId carries its version

`S3` publishes `HASH("<schema id>.v<version>")`, not a bare schema name, and
there is no separate version cell. The framework already requires exact
matching — *magic, schema id, and schema version must all match before a
directory or catalog is consumed* — so two exact comparisons of two cells
collapse into one exact comparison of one cell with nothing lost. It is measured
work saved, not only a cell: 25 publishers each spent a cell and a line on a
separate version, and 20 consumer sites spent two lines checking it.

The reviewed declaration keeps `schema_id` and `schema_version` as separate
structured fields, so the canonical-registry binding still checks a real schema
at a real version; only the on-stack encoding folds. A consumer whose schema
moved on sees an unknown identity rather than a known one at the wrong version,
so its diagnostic is coarser — the registry maps the hash back for anyone
debugging.

`S1 ServiceABI` deliberately stays a separate numeric cell. The principle would
fold it too; the arithmetic says otherwise. Magic-plus-ABI is established across
154 programs and the whole `ABI_REFERENCE` registry, while the schema pair was
newly standardized with 25 publishers already in the backlog.

### Generation

`S7` is a publication fence: initialized to `0` before the first `yield`,
advanced by the service, and **the last cell it publishes**. A reader snapshots
it, reads what it needs, and re-checks the same positive value — the framework's
first invariant, at a fixed address for the first time.

Every publisher in the framework already implements that discipline, each at its
own address: the final `poke` lands on cell 12 in 25 programs, cell 11 in 16,
cell 8 in 15, cell 4 in 14, and so on down a long tail. Standardizing the
address is what lets a generic reader fence a service it has never seen — the
coherent multi-cell snapshot the Stack Cell Monitor documents it cannot take
today.

The validator proves the shape it can prove statically: a literal zero
initializer, at least one later write, and the generation `poke` last in source
order among all writes.

### State

`S5` holds one of six values, and it is one of the two header cells a service may
write after publication:

| Value | Meaning |
| ---: | --- |
| 0 | not reported |
| 1 | booting |
| 2 | ready |
| 3 | working |
| 4 | blocked on a dependency |
| 5 | fault — fail-closed stop |

A service that halts on a violated invariant publishes `5`, so one cell answers
"is anything red?" across every migrated program. Declaring `HAS_STATE` costs a
line per published transition, so a program with no line budget leaves the bit
clear rather than publishing a value it cannot maintain.

### TelemetryBase

`S6` points at a telemetry block that lives outside the header — for the Generic
Telemetry runtimes, the block already at `S96`. This is not a payload pointer:
the payload header *is* the common header. It exists so a family with a large
published block can advertise it without moving it, which turns those
migrations from breaking changes into additive ones.

## Extension v1

`ExtensionBase = 0` means no extension. A nonzero extension begins:

| Offset | Name | Rule |
| ---: | --- | --- |
| `E+0` | `ExtensionMagic` | `31416054` exactly |
| `E+1` | `ExtensionVersion` | `1` exactly |
| `E+2` | `ExtensionLength` | total cells including this header; integer `4..192` |
| `E+3` | `ExtensionFlags` | bit field; v1 readers reject any reserved bit set |
| `E+4` | `ImplementationId` | present when flag bit 0 is set; otherwise family fields may begin here |

Extension flag bit 0 is `HAS_IMPLEMENTATION_ID`. Other v1 flag bits are reserved
and must be written zero. Family-specific metadata may follow the common fields.
Generic tools use the length to skip it and are never required to interpret
family payload semantics.

A reader accepts an extension only when all of these are true:

1. `ExtensionBase` is an integer and can address the four-cell header.
2. Magic and version match exactly.
3. Length is an integer in `4..192`.
4. `ExtensionBase + ExtensionLength <= 512`.
5. The extension begins at `S8` or later, so it cannot overlap the header.
6. Any common flag-implied cell is inside the declared length.

Failure rejects the header; it never falls back to interpreting extension cells
as a family payload. Request tokens, publication generations, bank selectors,
and transaction state stay in the service payload from `S8` up; only the `S5`
state value and the `S7` generation are common.

## Unknown and invalid values

- `SchemaId = 0` and `SchemaVersion = 0` is the only no-schema representation.
- A nonzero schema ID requires a positive schema version. A zero schema ID with
  a nonzero version, or the reverse, is invalid rather than partially known.
- `ExtensionBase = 0` is absence. No other header field uses zero as unknown.
- A zero, fractional, or NaN magic is not a header. Unknown magics are
  structurally valid: a reader reports the number even when its local registry
  has no name for it.
- Unknown extension versions are rejected. They are not interpreted as
  v1-compatible prefixes.

## Migration contract

The rollout is per family, not per program, because renumbering a payload cell
changes every consumer that reads it by literal address:

- a program migrates when it publishes its declared header cells exactly, on the
  straight-line entry path, before its first `yield`;
- its family's consumers move in the same change, since `S2..S4` reads shift;
- every other program stays a named, generated baseline exemption until then;
- `S0`/`S1` never move for the 154 programs that already publish them there.

New deployable programs cannot inherit the baseline exemption. The declaration
file lists every pre-v1 source path explicitly and pins that sorted list by count
and a validator-owned SHA-256. Because baseline paths stay listed as they
migrate, the digest records the pre-v1 set rather than migration progress, and a
newly added source is unclassified — failing validation until it publishes the
header.

A service ABI changes only when its semantic contract changes; a schema version
only when that schema changes. A future incompatible header uses a new exact
version and is rejected by v1 readers; it may not silently repurpose a v1 cell.

## Cost and current state

| | cells | lines | notes |
| --- | ---: | ---: | --- |
| Header reservation | 8 | — | costs 3 more programs than reserving 5; deferring costs a second break of ~146 |
| Mandatory writes | 3 | 3 | `S0`/`S1` already published by 154 programs |
| Stack Header Reader | 8 | 117 | the reference reader; validates every declared field |
| Stack Cell Monitor | 8 | 45 | the probe: one cell at a chosen address |
| Generic Telemetry family | 8 | +4 each | 7 runtimes migrated; 5 spend reviewed margin, 0 consumers changed |
| Backlog | — | — | 165 programs, 148 of which use `S2..S7` today |

## Worked migration: Generic Telemetry

The seven Generic Telemetry runtimes were the first family to migrate, and they
show why `TelemetryBase` earns its cell. Each runtime added four lines —
`ServiceMagic`, `ServiceABI`, `CapabilityMask` = `HAS_TELEMETRY`, and
`TelemetryBase` = `96` — and moved nothing. The block at `S96` keeps its magic
`27182818`, its ABI, and every cell it published, so all five consumers that
read `getd r0 ref 96` were untouched.

Each runtime also gained its own registered magic, because the header identifies
a service and `27182818` identifies a telemetry block that seven different
services publish. An operator reading `S0` now learns which runtime is in the
housing, and `S7` tells the reader where its telemetry lives — the exact question
that opened this design.

Five of the seven were at or near the soft ceiling, so they carry reviewed
soft-limit exemptions in `validation/validators/validate_ic10.py`. That validator
is the single owner of the 120-line ceiling; the 128-line hard limit still binds
everywhere.

## Machine-readable authority

The generated artifacts keep the `stack_envelope` name: the five-cell header
plus the extension it points at is the envelope a generic reader opens first.

`data/stack_envelope_declarations.json` is the reviewed migration/exemption
source. `tools/generate/generate_script_contracts.py` combines it with all 173
per-script contracts and writes `contracts/stack_envelope_inventory.json`.

Each generated row records current identity/header cells, every directly
published schema hash, whether a primary stack protocol was declared, payload
bases, existing consumer checks, literal/dynamic stack pressure, line headroom,
which of `S0..S7` the program occupies today, and either the v1 header or its
explicit baseline exemption. Migrated rows also record the reviewed source
fingerprint, straight-line publication rule, immutable stack ownership outside
the header, and source-fingerprinted post-initialization dynamic-write bounds.

`validation/validators/validate_stack_envelopes.py` enforces coverage,
publication before the first yield, post-publication stability, exact source
writes, schema binding, extension-flag and bounds rules, header/ABI agreement
with the generated contract, line cost, and generated freshness. A declared
schema must be canonical in the reviewed data files or verified by the source
itself; a declaration nothing backs is rejected rather than assumed.

## Live-game discovery

Connect `ic10/live-commissioning/stack_header_reader_v1_0.ic10` to a target
housing. Status `3` in its `S8` means a valid header was read; `S9..S16` then
carry the target's magic, ABI, capability mask, and every field that mask
declares, with `0` for anything undeclared. Status `-5` means `S0` holds no
usable magic; `-6` means a declared field or an extension bound was invalid.

The Stack Cell Monitor stays the probe for reading one chosen cell at an address,
which is what an operator uses next to inspect a payload the reader identified.
Splitting them keeps each program small: the reader is 117 lines and the probe
is 45, where one combined program had reached 121 with 7 lines of hard-limit
margin left.
