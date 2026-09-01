# Machine-Readable Script Contracts

Every deployable program under `ic10/` has one generated JSON contract under
`contracts/<deployment-family>/`. These files make the framework inventory and
the statically provable portion of component wiring available to validators and
external tools without scraping Markdown ABI tables.

Current documents use `IC10_SCRIPT_CONTRACT_V2` and extraction mode `static-v2`.
V2 replaces the aggregate V1 `dynamic_range_source` field with independent
read/write provenance and exact source-proven range subsets. The original V1
schema remains at `schemas/script_contract.schema.json`; V2 documents use the
distinct `schemas/script_contract_v2.schema.json` identity.

## Authority

The generated contract files are not edited directly. Contract facts have this
authority order:

1. IC10 source owns instructions, literal stack accesses, device-property
   accesses, inline field/publication semantics, and literal dependency checks.
2. `data/source_manifest.json` owns deployment family/class, layer, and purpose.
3. Generated files under `contracts/protocols/` are the common canonical
   protocol definitions. Existing specialized JSON documents remain canonical
   for their extra domain semantics and are linked as supplemental references.
4. `data/script_contract_overrides.json` owns semantics that cannot be bounded
   from one program in isolation, including public provider ranges, complex
   consumer or own-stack dynamic-address ranges, paired-sequence or explicitly declared
   seqlocks, and
   allocator-owned cells in another
   housing. Every such override is bound to the source SHA-256 so source
   arithmetic cannot change without an explicit re-review. An address is derived
   directly where the branches around it bound every value it can hold and say
   so; the same derivation serves wired-device and own-stack accesses. Every
   override must contain every cell that derivation proves, whether or not it
   proved the whole set. An override wider than a whole derivation is a reviewer
   being deliberately conservative and is kept as the published range; only an
   undeclared surface publishes the derivation itself as source-derived.
5. `data/script_contract_protocol_definitions.json` gives shared protocol IDs a
   name and links them to supplemental domain definitions.
6. `contracts/` is deterministic generated output from those inputs.

An override must not restate an ordinary literal access merely to give the
generator a preferred answer. Dynamic ranges must describe the narrowest stable
interface justified by the target ABI. Every override is rejected if its source
path becomes stale.

## Contract contents

Each generated per-script contract document is validated by
`schemas/script_contract_v2.schema.json` and records:

- stable versionless `service_id`, implementation revision, deployment family,
  deployment class, layer, and purpose;
- the exact source path and SHA-256, making stale output detectable;
- used `d0..d5` ports, source aliases, required/optional status, device-property
  reads/writes, bounded external stack reads/writes, and literal constraints;
- an explicit target classification for every port: literal-header-verified
  stack protocol, access-only stack interface, or physical-device assumptions.
  Each access-only interface has a content-derived identity shared by equivalent
  access requirements and resolves to its canonical definition in
  `contracts/index.json`;
- ordinary and slot-scoped device properties, including literal versus dynamic
  slot selection;
- `getd`/`putd` ReferenceId dependencies and `db:n` device-index discovery,
  including literal stack cells and accepted network-discovered protocols;
- literal and dynamic access to the housing's own 512-cell stack. An access the
  branch bounds derive whole emits an exact source-derived range, including the
  disjoint singletons a non-unit address stride reaches. A reviewed bound stands
  where the derivation was left open anywhere, and also where a reviewer named a
  window wider than the derivation on purpose; either way it is a
  source-fingerprinted exception that has to contain every proven cell. Every
  remaining unresolved access fails closed to `S0..S511`. Exact proven subsets
  are retained even when another access forces the aggregate range to fall back,
  so analysis never loses known occupancy;
- source-comment-backed field names, descriptions, semantic value types,
  explicit defaults, enums, reserved markers, explicit cross-program ownership,
  and literal protocol headers at any base address. Unnamed cells are labeled
  `unresolved` rather than presented as source-derived semantics;
- restart mode distinguished as unconditional clear, conditional reset, or
  preservation; source-order-verified commit-last publication rules;
  source-fingerprinted seqlocks classified as structurally paired sequences or
  explicit declarations for non-linear publication protocols;
  and executable header cell-equality invariants emitted only when the matching
  literal initialization is guaranteed before every observable yield,
  termination, or loop backedge and dynamic writes do not overlap either header
  cell. Local calls are followed through `ra`, and a return is not a loop
  backedge; a return that reads an address no call left there fails closed;
- provided stack protocols and consumed literal magic/ABI requirements.

`contracts/index.json` is the complete source-to-contract report and canonical
registry of access-only stack interfaces and their consumers. Its
`own_stack_range_inventory` reports every dynamic script, exact source-proven
subsets, effective ranges and provenance, and a count of unresolved full-stack
fallback surfaces for stack-envelope and migration planning.
`contracts/protocol_registry.json` groups stable protocol identities, provider
locations, consumer locations, and one generated definition path per protocol.
Each document under `contracts/protocols/` carries typed provider fields,
published/writable ranges, consumer reads/writes, dynamic ranges, constraints,
and supplemental domain references. A base-0 protocol is identified by its
contract name, which already carries the ABI, so its document is named
`contracts/protocols/ic10.stack.*.protocol.json`; the Generic Telemetry block at
`S96` keeps the numeric `ic10.stack.<magic>.abi<n>` form because its consumers
accept a version range. Header base is tracked separately either way, so the
`S96` header is never mistaken for an `S0` header.

## Compatibility checks

`validation/validators/validate_script_contracts.py` fails when:

- a deployable source is missing a contract or an orphaned contract remains;
- a document does not satisfy the common JSON Schema;
- source, manifest metadata, inferred access, overrides, or generated output
  drift apart;
- stable service IDs, device ports, or stack-field addresses collide inside
  their required scope;
- a consumed magic/ABI/header-base combination has no provider;
- a literal schema ID, schema version, width, controller-type discriminator, or
  other checked stack value conflicts with every matching provider;
- a consumer reads a cell no matching provider publishes, or writes a cell no
  matching provider accepts;
- a canonical generated definition is missing, stale, or schema-invalid;
- a supplemental JSON definition reference is missing or has a bad pointer;
- a dynamic wired access lacks an explicit range;
- a declared dynamic range omits a cell the branches around the access prove it
  reaches, whether or not the derivation was whole;
- an own-stack proven subset falls outside its effective range, a claimed
  source-derived range exceeds its proof, or a conservative fallback is not
  exactly `S0..S511`;
- stack ranges overlap within one access class;
- a required publication rule is absent from every compatible provider;
- a commit-last consumer neither checks nor double-reads its publication cell;
- a seqlock consumer does not reject odd snapshots and compare a preserved first
  sequence read with a distinct second read;
- a machine-readable invariant evaluates false;
- a semantic override's source fingerprint no longer matches;
- a port declares a dynamic range but no consumer edge, and carries no reviewed
  `UNENFORCED_RANGES` entry saying what it pins instead and what blocks the `S0`
  check — or carries an entry that no longer applies.

Access-only interface identities are hashes of their stack and device-assumption
contracts. Equivalent requirements therefore resolve to one canonical entry in
`contracts/index.json`; incompatible requirements cannot silently reuse that
identity. Each definition includes the exact stack/property obligations and
required stack equality values an in-world provider must satisfy, and marks
verification as `commissioning-required`.
These ports intentionally remain `deployment-supplied`: source contracts cannot
identify the object a player wires to a screw terminal. Literal-header protocols
additionally resolve and statically compare concrete script providers.

Dynamic wired addresses fail closed: they contribute their entire declared
range to compatibility, and a provider must publish or accept every requested
cell. That comparison happens here only where a consumer edge is declared;
`data/script_wiring.json` names a peer for every port, and
`validation/validators/validate_script_wiring.py` makes the same comparison total
against what each declared provider's own contract writes and reads
(`docs/SCRIPT_WIRING.md`).
Range provenance distinguishes source-derived bounds from explicit,
source-fingerprinted exceptions. Network discovery is represented separately from wired ports. Consumed
wired protocols come from authoritative consumer declarations verified against
literal equality checks; publication requirements additionally require an
observable marker check or coherent double-read. Network protocols that use ABI
ranges are declared explicitly and verified against their source checks.
Access-only stack targets remain explicitly labeled as such and are not
presented as ABI-verified wiring.

Dynamic own-stack addresses use the same proof, and there is one proof: the
branch bounds below both derive the cells an address reaches and say whether
those are all of them. A range is source-derived exactly where nothing along the
way was left open -- no write the analysis could not evaluate, no register
arriving from a reflash rather than a write, no loop nothing counts out, no
limit read off a bound that was never shown whole. An address that fails any of
those is an explicit `conservative-full-stack` fallback unless a
source-fingerprinted override supplies a reviewed range. `clr db` is a
source-derived full-stack write rather than an unresolved fallback.

A reviewed override still has to describe the code it stands for, and the
branches are what say which cells that is. A branch that gates an access says
what the registers reaching it may hold, so `blt r3 0 Bad` with `bgt r3 8 Bad`
accepts a count of eight however the peer fills it in; a branch that decides
whether a loop runs again bounds its trip count, whether it is written at the
top against the counter or at the bottom against a different one. Between them
the whole `S32..S95` plan window falls out of a validator that only ever names
`8` and `32`, and the generator rejects any declared range that omits a cell
they reach -- a window anchored in the wrong place, and one anchored right and
cut short.

What that derives is the surface the program *permits*, not what one execution
performs: a declaration has to cover every cell a legal peer can steer the loop
to. It is always a floor a declaration must contain, and where the derivation
was whole it is the ceiling as well, which is what lets an undeclared surface
publish it as the range rather than as a bound on one. An address bounded by
nothing the branches state -- a record pointer, a count the consumer never
validates -- is held only to the cell its first pass reaches and remains a review
obligation. Widen such a range to the record window the provider actually
publishes rather than to the first plausible span. A reviewer may also name a
window wider than a whole derivation on purpose, and that stands: the proof is
its floor and the source fingerprint holds it to the revision it was reviewed
against.

Because a derived cell is a cell a declaration is held to, the arithmetic
between a seed and an access is enumerated rather than approximated: widening a
sum to the interval between its ends would claim the gaps between two sparse
operands and reject a declaration that was right. Enumerating reaches far enough
because the values that carry a bank index are small -- a set-instruction
answers one of two things, and `select` holds one arm or the other, never the
span between them. That is what lets a service which reads its record width from
a peer be bounded at all: `generic_snapshot_directory_host_v1_0` names no
address literally, but guards its width to three, its capacity to 64 and their
product to 192, which places both snapshot banks at `S32..S415`.

Reading a branch as a bound needs the whole control-flow graph, and one walk
produces it for every proof here. Its states pair a program index with the return
address `ra` holds, because `ra` is one register rather than a stack: `jal`
overwrites it, so a subroutine is walked once per call site with the edge that
site really returns along, a second call replaces the first return address
instead of nesting under it, and a subroutine leaving through a shared error path
needs no special case. A record loop is exactly the thing a program writes as a
subroutine, so this is what lets the loop's own exit test be read at all --
`resource_transform_profile_view_v8_0` clears `S8..S67` behind `blt r9 68 Clear`,
and it is a `jal` elsewhere in the program that used to hide it. What still
stands the bounds down is a transfer nothing can name: a return whose `ra` the
program computed itself, and a branch that links.

The dominance and ordering proofs read those states projected onto plain
indices, which joins each caller's entry to every caller's return. That only
weakens them -- a guard surviving the merge really does gate every call -- so the
projection is where they belong. The exception is asking which write is still in
a register when an access runs: on the projection a path stitched from two
callers would carry a write no execution does, so that question is asked of the
states, where a return goes back to the site that made it.

That question is a reaching-definition fixpoint over the states rather than a
backward scan for the nearest earlier write, because a register holds what the
last write on the path that got here left in it and different paths get here
from different writes. Every write that arrives is joined: one that nothing can
evaluate costs the derivation its closure and not the terms beside it, and a
path that arrives with no write at all costs the closure too, since a reflash
leaves a register holding something no branch bounds. `generic_persistent_config_host_v1_1`
copies an image whose base is a persisted bank at boot and the normalized
candidate at commit, and the nearest write names only the second of those.

`data/script_protocol_headers.json` is the authoritative provider and consumer
header catalog. The generator verifies every declaration against literal source
writes/checks and never guesses headers from adjacent numeric payload values.

## Maintenance

After changing an IC10 program, source metadata, a canonical schema, or contract
override, regenerate and validate:

```bash
python3 tools/generate/generate_script_contracts.py
python3 validation/validators/validate_script_contracts.py
python3 tests/test_script_contracts.py
```

The full validation runner performs both checks. Release construction also
regenerates contracts after other source generators and before validation.

Implementation-only edits keep `service_id` stable and update the source
revision or fingerprint. Change ABI when compatibility rules or an existing
wire layout change. Change schema version when the ABI remains compatible but
the interpreted payload schema changes. Never derive protocol identity from the
versioned filename.

## Adding a program

1. Add the versioned source under `ic10/` and cover it in
   `data/source_manifest.json`.
2. Add every provided and consumed header to
   `data/script_protocol_headers.json`; generation rejects entries that are not
   literal writes/checks in the source.
3. Check a wired dependency with one literal `S0` identity comparison — the ABI is
   folded into it, so do not also check the peer's `S1`. Declare an explicit network
   ABI range when discovery accepts more than one ABI at a block header away from `S0`.
4. Add narrow public/dynamic ranges or externally owned fields to
   `data/script_contract_overrides.json` when source inspection cannot prove
   the cross-program bound, then record the reviewed source SHA-256.
5. Declare each device port's canonical peer in `data/script_wiring.json`
   (`docs/SCRIPT_WIRING.md`).
6. Regenerate contracts and run the full validation suite.

This inventory is also the measured input for the common stack-envelope design
in GitHub issue #29: it identifies existing header locations, occupied cells,
dynamic surfaces, and consumers before any migration is proposed.
