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

So the header costs nothing to adopt at `S0/S1`. What it cost was `S2..S7`, which
148 programs used for family payload before migration. Reserving eight rather than
five added only three programs to that backlog — nearly every program that used
`S5..S7` already used `S2..S4` — while adding cells later would have broken the
same ~146 programs a second time.
Those programs made up the migration backlog, now fully migrated; every program's
envelope is listed in `contracts/stack_envelope_inventory.json`.

A fixed window high in the stack — the shape first proposed for this design — avoids
that renumbering, but only by duplicating the ABI and schema cells the majority
already publish at `S1..S3` and by spending eight cells and eight lines on every
program to say what four of its own cells already said.

## Fixed v1 cells

| Cell | Name | Written | Rule |
| ---: | --- | --- | --- |
| `S0` | `ServiceMagic` | always | `HASH("<Contract>.v<ABI>")`; the derived service identity |
| `S1` | `ServiceABI` | always | the same ABI in readable form; `S0` is what pins it |
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

The magic is the on-stack identity, and it is **derived, not allocated**: a
service publishes `HASH("<Contract>.v<ABI>")`. Folding the ABI into the hashed
name is what makes one `S0` equality check exact — change the contract and the
value every consumer compares changes with it, so a stale consumer fails closed
rather than silently accepting a contract it was never written against. `S1`
still publishes the ABI for readers and diagnostics, but a consumer must not
branch on a peer's `S1`: after `S0` matches, the ABI is already proven, so the
comparison can never fail. `validation/validators/validate_service_identity.py`
rejects one. A program's check of its *own* `S1` is a torn-image guard, not an
ABI check, and stays.

The identity is registered in `docs/ABI_REFERENCE.md`, stable across
implementation revisions, and unrelated to a filename — moving a source file or
bumping a `_v<major>_<minor>` suffix changes neither the identity nor the service
contract. It identifies a *contract*, not a program: the three generated
directory adapters share one identity because they publish one contract.
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
matching — *the service identity, schema id, and schema version must all match
before a directory or catalog is consumed* — so two exact comparisons of two cells
collapse into one exact comparison of one cell with nothing lost. It is measured
work saved, not only a cell: 25 publishers each spent a cell and a line on a
separate version, and 20 consumer sites spent two lines checking it.

The reviewed declaration keeps `schema_id` and `schema_version` as separate
structured fields, so the canonical-registry binding still checks a real schema
at a real version; only the on-stack encoding folds. Every schema-bearing
contract in the framework now publishes one folded identity — adapters, hosts,
stores, loaders and their readers — so a schema and its version are a single
exact comparison anywhere they are checked. A consumer whose schema
moved on sees an unknown identity rather than a known one at the wrong version,
so its diagnostic is coarser — the registry maps the hash back for anyone
debugging.

`S1 ServiceABI` deliberately stays a separate numeric cell. The principle would
fold it too; the arithmetic says otherwise. Magic-plus-ABI is established across
154 programs and the whole `ABI_REFERENCE` registry, while the schema pair was
newly standardized with 25 publishers already in the backlog. Keeping the cell is
not the same as gating on it — it is published so a reader can name the ABI
without a reverse hash lookup, and read for that reason only.

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

`S5` is a packed word, and it is one of the two header cells a service may write
after publication. A stack cell is a double, so its exact integer width is 53
bits — the game's own `ext`/`ins` documentation caps a bit field at "53 bits in
final length", and bit 53 and above cannot survive a round trip through a cell.

```text
bits 0..3    State field: one value at a time
bits 4..7    reserved for future universal flags; must be zero
bits 8..52   service-specific, opaque to a generic reader
bit 53+      unusable
```

| Field value | Meaning |
| ---: | --- |
| 0 | not reported |
| 1 | booting |
| 2 | ready |
| 3 | working |
| 4 | blocked on a dependency |
| 5 | fault — fail-closed stop |

The low bits are a **field, not flags**. The six states are mutually exclusive:
as independent bits, `boot | ready` would be representable and meaningless, and
every generic scanner would have to invent its own priority rule. Conditions that
genuinely co-occur belong in the service-specific range, where a family can
express "config stale" or "operating degraded" alongside whatever the field says.
`ext r0 r_state 0 4` recovers the field in one instruction; `RequiredCapabilityMask`
already establishes the `(actual & required) == required` idiom for the rest.

A service declares the custom bits it may set in `custom_state_bits`, and the
validator rejects a published value that sets an undeclared bit, a reserved bit,
a state field outside 0..5, or anything beyond the 53-bit width. Writes must be
literal, so every state a program can publish is provable from its source.

What does **not** belong here is the result of observing another device. The
Stack Header Reader publishes `-5` when its target has no usable magic; that
describes the target, not the reader, and folding it into State would light up a
base-wide health scan for a perfectly healthy tool. State answers "how am I";
the service's own payload answers "what did I find". Both commissioning tools
now report `4` while their required devices are missing and `2` once the wiring
proves out, rather than hardcoding `2` forever.

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

### Peer-written mailboxes move as a block

Six of the nine manufacturing programs read their request from `S2..S7` — cells a
peer writes through a device port, not cells they own. Relocating only the cells a
program reads would leave its writer still writing `S2..S7`, which after migration
is the header: the writer would overwrite `CapabilityMask` and `SchemaId` on every
request. So the whole mailbox moves as one contiguous block, and the writer's `put`
addresses move with it in the same change.

`tools/plan_header_migration.py` lists a family's port and reference accesses to
`S2..S7` for exactly this reason. It cannot resolve which program a port points at
— that wiring lives in the deployment chapters, not in data — so each edge is
attributed by hand against `docs/DEPLOYMENT.md` and the family's own chapter before
its addresses are moved.

A reference-addressed write (`putd`/`getd` through a `ReferenceId`) is not a port
and does not appear in that list at all. Those must be found by reading the
program: a launcher that writes `putd ref 2` is writing some other service's header
once that service migrates, and nothing in the contract layer records which service
it holds a reference to. Resolving one means naming what each reference register
holds -- the manufacturing launchers reach the Transform Runtime, and through the
Runtime's published reference cells the Admission, Link Resolver, and Transform
Profile View behind it -- and then applying each migrated peer's own cell mapping.

One of those writes had no reader at all: the Transform Candidate Executor stamped
the owning JobId into a Runtime cell the Runtime never read. That was harmless
while the cell was unused and became a corrupt request the moment the migration
moved the Runtime's TransformType onto it. **A service's stack belongs to that
service.** A peer may write cells the owner declares and reads; an annotation on a
cell the owner ignores is invisible to the contract layer, survives no migration,
and belongs on the writer's own stack -- where, in this case, the JobId and the
Runtime reference were both already published.

### Sweeping for consumers a migration left behind

Renumbering a payload cell strands every consumer that still reads the old address,
and the contract layer cannot see it: a migrated peer *does* publish something at
`S2`, so a stale read of `S2` looks like a satisfied read of the CapabilityMask.
Five such edges survived earlier migrations and were found only by sweeping.

The one mechanical handle is the magic check. A consumer that reads a peer's `S0`
and compares it to a literal has named that peer exactly, and
`validation/validators/validate_stack_envelopes.py` now fails any such consumer that touches `S2..S7` of a
migrated peer. Four reviewed exceptions are declared, all of them reading header
fields on purpose: the SchemaId at `S3` and the Generation at `S7`. Ports without a
magic check stay unattributable and must be read.

Two signals said where to look. A migration commit that touched only its own family
had no chance to fix outside consumers -- comparing each commit's touched families
against the family it migrated found the diagnostics and power-jobs migrations, and
those two turned out to be internally consistent, while the broad ones were not. And
of the 69 migrated programs only 25 vacated a payload cell at all; the rest merely
added a mask and can strand nobody.

A service ABI changes only when its semantic contract changes; a schema version
only when that schema changes. A future incompatible header uses a new exact
version and is rejected by v1 readers; it may not silently repurpose a v1 cell.

## Cost and current state

| | cells | lines | notes |
| --- | ---: | ---: | --- |
| Header reservation | 8 | — | costs 3 more programs than reserving 5; deferring costs a second break of ~146 |
| Mandatory writes | 3 | 3 | `S0`/`S1` already published by 172 programs |
| Stack Header Reader | 8 | 117 | the reference reader; validates every declared field |
| Stack Cell Monitor | 8 | 45 | the probe: one cell at a chosen address |
| Generic Telemetry family | 8 | +4 each | 7 runtimes migrated; 5 spend reviewed margin, 0 consumers changed |
| Manufacturing family | 8 | +1 each | 10 migrated; seven move a whole peer-written mailbox, 1 spends reviewed margin |
| Dependency-planning family | 8 | +1 each | 18 migrated as one cluster; every peer mailbox moves as a contiguous block, 2 spend reviewed margin |
| Backlog | — | — | 0 programs, 0 of which use `S2..S7` today |

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

`tools/plan_header_migration.py` plans a family's move from those contracts. It
takes free cells from the analysed footprint rather than the literal one — a
program that clears a table through a computed address owns those cells even
though no literal write names them — refuses to guess when the contract cannot
bound a program's dynamic writes, reports where computed writes appear to be
based so a reviewer can bound them, and lists the port and reference accesses to
`S2..S7` that carry no magic for the contracts to key on. Those unattributed
port edges are the ones that break a migration: a sibling writing
`put d1 2 r5` is invisible to every automated check until a test fails.

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
