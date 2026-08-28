# Common Stack Header v1

Every deployable IC10 service identifies itself in the same five cells, `S0..S4`.
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

So the header costs nothing to adopt at `S0/S1`. What it costs is `S2..S4`,
which 139, 137, and 131 programs respectively use for family payload today.
Those programs are the migration backlog, and each is listed individually in
`contracts/stack_envelope_inventory.json` with the cells it must move.

A fixed window high in the stack — the shape first proposed for this design — avoids
that renumbering, but only by duplicating the ABI and schema cells the majority
already publish at `S1..S3` and by spending eight cells and eight lines on every
program to say what four of its own cells already said.

## Fixed v1 cells

| Cell | Name | Rule |
| ---: | --- | --- |
| `S0` | `ServiceMagic` | the service's registered nonzero magic; identity |
| `S1` | `ServiceABI` | positive exact ABI of this service contract |
| `S2` | `SchemaId` | canonical schema hash, or `0` when the service has no schema |
| `S3` | `SchemaVersion` | positive when `SchemaId` is nonzero; otherwise `0` |
| `S4` | `ExtensionBase` | integer base of a v1 extension, or `0` when absent |

The magic is the on-stack identity. It is registered in `docs/ABI_REFERENCE.md`,
stable across implementation revisions, and unrelated to a filename — moving a
source file or bumping a `_v<major>_<minor>` suffix changes neither the magic nor
the service contract. The semantic `ic10.script.*` contract id remains the
registry-side identity in `contracts/`; it is not published on the stack.

v1 validates the **shape** of a header, not membership in a registry: a reader
proves the five cells are well formed and self-consistent, then resolves the
magic through the generated contract index. There is no common marker cell,
because a common marker at `S0` would displace the identity that 154 programs
already publish there.

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
5. The extension begins at `S5` or later, so it cannot overlap the header.
6. Any common flag-implied cell is inside the declared length.

Failure rejects the header; it never falls back to interpreting extension cells
as a family payload. Mutable status, request tokens, publication generations,
bank selectors, and transaction state stay in the service payload from `S5` up.

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

- a program migrates when it publishes `S0..S4` exactly, on the straight-line
  entry path, before its first `yield`;
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
| Header per program | 5 | 5 | 2 of them already published by 154 programs |
| Monitor (migrated pilot) | 5 | 100 | was 117 with a high fixed window and its 8-cell reader |
| Backlog | — | — | 172 programs, 156 of which use `S0..S4` today |

## Machine-readable authority

The generated artifacts keep the `stack_envelope` name: the five-cell header
plus the extension it points at is the envelope a generic reader opens first.

`data/stack_envelope_declarations.json` is the reviewed migration/exemption
source. `tools/generate/generate_script_contracts.py` combines it with all 173
per-script contracts and writes `contracts/stack_envelope_inventory.json`.

Each generated row records current identity/header cells, every directly
published schema hash, whether a primary stack protocol was declared, payload
bases, existing consumer checks, literal/dynamic stack pressure, line headroom,
which of `S0..S4` the program occupies today, and either the v1 header or its
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

Connect the Stack Cell Monitor to a target housing and set its address Logic
Memory to `-1`. Status `3` means a valid header was read; the monitor publishes
the discovered magic in its `S7` and mirrors it to the optional output Memory.
Because the payload always begins at `S0`, an operator reads the rest of the
header by setting the address Memory to `1`, `2`, `3`, or `4`.

Status `-5` means `S0` holds no usable magic. Status `-6` means the magic was
present but the ABI, schema pairing, or extension bounds were invalid. See
`docs/STACK_CELL_MONITOR_GETTING_STARTED.md` for the physical setup.
