# Common Stack ABI Envelope v1

Stack Envelope v1 gives every migrated IC10 service one fixed discovery window.
An operator or generic tool can identify the semantic service contract, verify its
ABI/schema, and locate its primary legacy payload without knowing whether that
payload begins at `S0`, `S96`, or a family-local address.

The rollout is additive. Existing payloads and consumers do not move.

## Decision and measured reservation

The v1 envelope is the eight cells `S320..S327`. `S320` is the first address of
the fixed window; it is not a claim that cells below it share one layout.

The generated inventory evaluated every one of the 173 deployable programs:

- `S0..S7` already had literal use in 157 programs and could not be adopted
  without broad ABI breaks;
- `S320..S327` had no literal use before the pilot;
- 61 of the 168 remaining legacy programs have conservative or source-derived
  dynamic ranges crossing the window and therefore remain explicit exemptions
  until those ranges are proved safe or their ABI receives a planned revision;
- all 168 non-pilot programs appear individually in
  `contracts/stack_envelope_inventory.json` as `legacy-exempt`.

An eight-cell reservation costs 1.5625% of a 512-cell stack. A 16-cell envelope
would cost 3.125%, 32 cells 6.25%, and 64 cells 12.5%. The eight required
literal `poke` instructions cost eight source lines. Metadata that is not needed
for first-contact discovery belongs in a bounded extension rather than a 32/64
cell universal reservation.

## Fixed v1 cells

| Cell | Name | Rule |
| ---: | --- | --- |
| `S320` | `EnvelopeMagic` | `31416053` exactly |
| `S321` | `EnvelopeVersion` | `1` exactly |
| `S322` | `ServiceId` | `HASH(canonical semantic service contract id)` |
| `S323` | `ServiceABI` | Positive exact ABI of the primary payload contract |
| `S324` | `SchemaId` | Canonical schema hash, or `0` when the service has no independent schema |
| `S325` | `SchemaVersion` | Positive when `SchemaId` is nonzero; otherwise `0` |
| `S326` | `PrimaryPayloadBase` | Integer `0..511`; points to the established magic/header cell |
| `S327` | `ExtensionBase` | Integer base of a v1 extension, or `0` when absent |

The common magic and version are present because a random nonzero service hash
is not sufficient proof that the fixed cells are an envelope. The optional
implementation identity and capability flags moved to the extension, preserving
the eight-cell budget while keeping first-contact validation unambiguous.

## Identity and hash namespace

`ServiceId` names a semantic contract. Current IDs use the canonical
`ic10.script.<semantic-name>` namespace already generated in per-script
contracts. The `_v<major>_<minor>` filename suffix is removed before that
identity is formed. Moving a source file or changing an implementation revision
does not, by itself, create a new service contract or ServiceId.

Schema hashes use their existing canonical names, such as
`DirectorySchema.ResourceLink` and `CatalogSchema.Recipe`. They are not service
identities and their versions do not need to match a service ABI.

When exact-program provenance is useful, an extension may carry
`ImplementationId`. It must be an explicitly assigned semantic build/program
identity. A validator must reject any policy that derives it from the versioned
filename.

## Extension v1

`ExtensionBase = 0` means no extension. A nonzero extension begins:

| Offset | Name | Rule |
| ---: | --- | --- |
| `E+0` | `ExtensionMagic` | `31416054` exactly |
| `E+1` | `ExtensionVersion` | `1` exactly |
| `E+2` | `ExtensionLength` | Total cells including this header; integer `4..192` |
| `E+3` | `ExtensionFlags` | Bit field; v1 readers reject any reserved bit set |
| `E+4` | `ImplementationId` | Present when flag bit 0 is set; otherwise family fields may begin here |

Extension flag bit 0 is `HAS_IMPLEMENTATION_ID`. Other v1 flag bits are
reserved and must be written zero. Family-specific metadata may follow the
common fields. Generic tools use the length to skip it and are never required to
interpret family payload semantics.

A reader accepts an extension only when all of these are true:

1. `ExtensionBase` is an integer and can address the four-cell header.
2. Magic and version match exactly.
3. Length is an integer in `4..192`.
4. `ExtensionBase + ExtensionLength <= 512`.
5. The extension range does not overlap `S320..S327`.
6. Any common flag-implied cell is inside the declared length.

Failure rejects the envelope; it never falls back to interpreting extension
cells as a family payload. Mutable status, request tokens, publication
generations, bank selectors, and transaction state stay in the primary
service-specific payload.

## Unknown and invalid values

- `SchemaId = 0` and `SchemaVersion = 0` is the only no-schema representation.
- A nonzero schema ID requires a positive schema version. A zero schema ID with
  a nonzero version, or the reverse, is invalid rather than partially known.
- `ExtensionBase = 0` is absence. No other envelope field uses zero as unknown.
- Unknown service IDs are structurally valid. A generic reader may report the
  numeric hash and payload base even when its local registry has no display name.
- Unknown envelope or extension versions are rejected. They are not interpreted
  as v1-compatible prefixes.

## Compatibility and upgrade rules

The v1 migration contract is:

- do not relocate or reinterpret an established payload;
- keep its old magic, ABI, schema checks, mutable fields, and publication order;
- publish `PrimaryPayloadBase` pointing to that unchanged header;
- add the fixed envelope only where stack and line inventory proves it safe;
- keep every other program as a named, generated legacy exemption.

Existing consumers continue reading their old addresses and require no envelope
awareness. New generic tooling reads the envelope first, then applies the named
service/schema contract at the advertised payload base.

A service ABI changes only when its semantic primary contract changes. A schema
version changes only when that schema changes. An implementation revision or
filename change changes neither automatically. A future incompatible fixed
envelope uses a new exact envelope version and is rejected by v1 readers; it may
not silently repurpose a v1 cell.

New deployable programs cannot inherit the pre-v1 exemption. The declaration
file lists every source in the immutable pre-v1 baseline explicitly and pins
that sorted list by count and a validator-owned SHA-256. Adding or renaming a
source leaves it unclassified and fails validation until the program publishes
the envelope. Baseline paths remain listed as they migrate, allowing the
validator to distinguish historical exemptions from new programs.

## Pilot matrix and cost

| Family | Pilot | Old payload | Lines before/after | Result |
| --- | --- | ---: | ---: | --- |
| Monitor | `ic10/live-commissioning/stack_cell_monitor_v1_0.ic10` | `S0`, ABI1 | 53 / 117 | Publishes v1 and adds discovery/validation mode |
| Generic Telemetry | `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` | `S96`, ABI2 | 61 / 69 | Existing Generic Telemetry layout unchanged |
| Directory | `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` | `S0`, ABI2 | 57 / 65 | Existing ResourceLink schema and candidates unchanged |
| Catalog | `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` | `S0`, ABI3 | 106 / 114 | Existing Recipe schema v3 request/response unchanged |
| Transaction | `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` | `S0`, ABI1 | 51 / 59 | Existing reservation ledger/publication unchanged |

The four service pilots each pay exactly eight lines and eight stack cells. The
monitor pays the same publication cost plus 56 lines for generic discovery,
schema checks, extension bounds checks, and distinct failure statuses. Every
pilot remains at or below the 120-line project ceiling.

## Machine-readable authority

`data/stack_envelope_declarations.json` is the reviewed migration/exemption
source. `tools/generate/generate_script_contracts.py` combines it with all 173
per-script contracts and writes `contracts/stack_envelope_inventory.json`.

Each generated row records current identity/header cells, every directly
published schema hash, whether a primary stack protocol was declared, payload
bases, existing consumer checks, literal/dynamic stack pressure, line headroom,
window collisions, and either the v1 envelope or its explicit legacy exemption.
Migrated rows also record the reviewed source fingerprint, straight-line
publication rule, immutable pre-extension stack ownership, and
source-fingerprinted post-initialization dynamic-write bounds. Extensions must
be disjoint from that established ownership. `validation/validators/validate_stack_envelopes.py` enforces coverage,
publication before the first yield, post-publication stability, exact source
writes, hash/schema and extension-flag rules, payload-header compatibility,
extension bounds, pilot-family coverage, line cost, and generated freshness. A
declared schema binds to one the source publishes in its payload header or
verifies on the stack it consumes; a declaration no source backs is rejected
rather than assumed.

## Live-game discovery

Connect the Stack Cell Monitor to a target housing and set its address Logic
Memory to `-1`. Status `3` means a valid envelope was read. The monitor publishes
the discovered `PrimaryPayloadBase` in its `S3` and the semantic `ServiceId` hash
in `S4`; the optional output Memory also shows the ServiceId hash. An operator
can then set the address Memory to the reported payload base to read the legacy
magic, without knowing the target's script family beforehand.

Status `-5` means no v1 envelope marker. Status `-6` means a marker was present
but version, ABI, schema pairing, payload address, or extension bounds were
invalid. See `docs/STACK_CELL_MONITOR_GETTING_STARTED.md` for the physical setup.
