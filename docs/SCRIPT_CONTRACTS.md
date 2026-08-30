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
   arithmetic cannot change without an explicit re-review. Literal-seeded
   linear address loops are derived directly only when address and counter seeds
   dominate a strict single-backedge loop with exactly one update to each
   register. The same proof is used for wired-device and own-stack accesses.
   Source-derived ranges must exactly match any retained override; partially
   provable exceptions must contain every cell established by the source proof.
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
- literal and dynamic access to the housing's own 512-cell stack. Literal-seeded
  strict linear loops emit exact source-derived ranges, including disjoint
  singleton ranges for non-unit address strides. Reviewed bounds that
  cannot be expressed by that proof are source-fingerprinted exceptions, and
  every remaining unresolved access fails closed to `S0..S511`. Exact proven
  subsets are retained even when another access forces the aggregate range to
  fall back, so analysis never loses known occupancy;
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
  cell. One-level local calls are followed through `ra`; nested calls, return
  address mutation, and unresolved transfers fail closed;
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
and supplemental domain references. Protocol identity is based on magic plus
ABI; header base is tracked separately, so the Generic Telemetry header at
`S96` is not mistaken for an `S0` header.

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
- a source-derived dynamic range disagrees with its literal-seeded address loop,
  or an exception omits a statically proven cell;
- an own-stack proven subset falls outside its effective range, a claimed
  source-derived range exceeds its proof, or a conservative fallback is not
  exactly `S0..S511`;
- stack ranges overlap within one access class;
- a required publication rule is absent from every compatible provider;
- a commit-last consumer neither checks nor double-reads its publication cell;
- a seqlock consumer does not reject odd snapshots and compare a preserved first
  sequence read with a distinct second read;
- a machine-readable invariant evaluates false;
- a semantic override's source fingerprint no longer matches.

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
cell. Range provenance distinguishes source-derived bounds from explicit,
source-fingerprinted exceptions. Network discovery is represented separately from wired ports. Consumed
wired protocols come from authoritative consumer declarations verified against
literal equality checks; publication requirements additionally require an
observable marker check or coherent double-read. Network protocols that use ABI
ranges are declared explicitly and verified against their source checks.
Access-only stack targets remain explicitly labeled as such and are not
presented as ABI-verified wiring.

Dynamic own-stack addresses use the same strict loop proof. Address and counter
seeds must dominate a single-backedge loop, each register must have exactly one
literal update, and the loop must have no bypass, re-entry, unmodeled transfer,
or additional mutation. Unknown, branch-dependent, multiply-mutated, and
unbounded cases remain explicit `conservative-full-stack` fallbacks unless a
source-fingerprinted override supplies a reviewed range. `clr db` is a
source-derived full-stack write rather than an unresolved fallback.

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
3. Use literal magic/ABI checks for ABI-verified wired dependencies. Declare an
   explicit network ABI range when discovery accepts more than one ABI.
4. Add narrow public/dynamic ranges or externally owned fields to
   `data/script_contract_overrides.json` when source inspection cannot prove
   the cross-program bound, then record the reviewed source SHA-256.
5. Declare each device port's canonical peer in `data/script_wiring.json`
   (`docs/SCRIPT_WIRING.md`).
6. Regenerate contracts and run the full validation suite.

This inventory is also the measured input for the common stack-envelope design
in GitHub issue #29: it identifies existing header locations, occupied cells,
dynamic surfaces, and consumers before any migration is proposed.
