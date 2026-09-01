# Canonical Device-Port Wiring

`data/script_wiring.json` records, for every device port (`d0..d5`) of every
deployable program, which program the port is intended to point at — or that the
port faces a physical game device. It is the machine-checkable form of the
wiring that previously lived only in `docs/DEPLOYMENT.md` prose and the
`USER_DEPLOYMENT_GUIDE.md` family chapters.

## Why it exists

The contract layer models each port structurally (`interface_id`, cells,
constraints) with `provider_resolution: deployment-supplied`; it deliberately
cannot say *which* program a player wires to a screw terminal
(`docs/SCRIPT_CONTRACTS.md`). That gap made header migrations dangerous:
relocating a payload cell strands every consumer still reading the old address,
and a migrated peer *does* publish something at `S2`, so a stale read looks like
a satisfied read of the CapabilityMask. Six such edges survived the Common Stack
Header migration; two left a program completely non-functional (GitHub issue #42).

A consumer that compares a peer's `S0` against a literal names that peer
exactly — but only 97 of 264 ports do. The wiring map names the rest.

## What it declares, and what it does not

The map names **identity only**. It is not a fifth protocol authority: async
tokens still fence observation, banked revisions still establish durability,
reservation epochs still authorize mutation, and `ProcessCondition` still
expresses demand. Nothing reads the wiring map at runtime; it exists so the
validators and migration tooling can check edges instead of inferring them.

Each port entry is one of:

```json
{"kind": "script", "providers": ["ic10/<family>/<file>.ic10"], "note": "<evidence>"}
{"kind": "physical-device", "role": "<pin role>", "note": "<properties>"}
```

- `providers` is an any-of list. A generic service that faces a class of peers
  (a snapshot host accepting any directory adapter, a reservation service
  accepting any endpoint) lists every program in that class. The list is the
  program's *possible* peers; a deployment picks one per instance.
- `note` is required for script edges and cites the evidence for the edge —
  the `docs/DEPLOYMENT.md` wiring line, the deployment-guide chapter, or the
  `S0` magic check that names the peer mechanically.
- `header_reads` optionally declares reviewed, deliberate reads of a migrated
  peer's `S2..S7` header cells (for example reading `S3` as SchemaId). Anything
  not declared there is treated as a stranded payload read and fails validation.

## Enforcement

`validation/validators/validate_script_wiring.py` (model:
`framework/script_wiring.py`, exercised by `tests/test_script_wiring.py`) fails
when:

- any device port of any deployable program lacks a declared peer, or an entry
  names a program or port that does not exist;
- a port whose contract target is a physical device declares a script peer
  (the reverse is legitimate: a stack-shaped port may face a game device with a
  native stack, or an IC housing hosting an arbitrary program);
- a port checks an `S0` identity that a declared provider does not publish at
  `S0` — the mechanical edges and the declared edges must agree. The identity is
  the whole check: the ABI is folded into it, so no port pins a peer's `S1`, and
  `validation/validators/validate_service_identity.py` rejects one that tries;
- a magic-checking port's `providers` list omits a registered publisher of that
  magic, so the any-of lists cannot drift as new publishers appear;
- a `physical-device` declaration sits on a port whose `S0` check names a
  registered script header, or overrides a stack-shaped contract target without
  a `note` saying why the peer is not a script;
- a port reads a migrated provider's `S2..S7` — literally or through a declared
  dynamic range — without a `header_reads` declaration, or writes anywhere in
  that provider's `S0..S7` envelope at all: only the owner publishes envelope
  cells;
- a `header_reads` declaration names a cell outside `S2..S7` or one the port
  never reaches;
- a port reads a cell no declared provider publishes, or writes a cell no
  declared provider accepts. See below.

## Every declared range is compared against something

A port's declared dynamic range used to be compared against a provider only
where `data/script_protocol_headers.json` declared a consumer edge — 29 of the
57 ports that carry one. Everywhere else the range was carried into `contracts/`,
into the interface identity, and into the commissioning plan's provider
obligations without ever meeting a provider (GitHub issue #92). The wiring map
names a peer for **every** port, so the comparison can be total, and
`framework/script_wiring.stack_surfaces` derives the two sides of it from the
contracts:

- a program **publishes** the cells it writes — literally or through its own
  proven dynamic write range — plus any `external_readable_ranges`;
- a program **accepts** the cells it reads, plus any `external_writable_ranges`.

A port passes on the first declared provider that publishes everything it reads
and accepts everything it writes; a port matching none reports each. Because
both sides are derived, a padded envelope on one end cannot make the comparison
vacuous the way two rounded-up declarations could: the pressure-grid route stack
declared a 16-cell hop window on both sides of a three-cell array, and the
comparison that was already enforced there passed anyway.

One vacuity does survive, and the validator counts it rather than hiding it: a
program that runs `clr db` writes the whole stack, so its published surface is
all 512 cells and no read of it can fail. 27 of the 108 declared providers are
in that position, and because providers are any-of, one such peer absorbs the
whole edge however narrow the others are. That leaves 152 of the 208 edges able
to fail at all. Narrowing the rest means deriving the publish surface from what
a provider writes *after* initialization rather than from its full dynamic write
range.

The reviewed envelope stays the escape hatch, for the one thing derivation
cannot see: a mailbox that one peer posts and a *different* peer consumes, which
the host itself never touches. `catalog_coordinator_core_v3_0` hosts exactly that
at `S40..S42` for the migration Planner and Worker. Declaring an envelope is a
statement that the owner accepts the access — including a request field the
owner publishes but does not currently consume — so a declaration that exists
only to silence the check is a review finding, not a fix.

The declared consumer edge still matters, for the other half of the problem: it
is the *runtime* guarantee, because
`framework/script_contracts.verify_declared_consumers` refuses a declaration the
source does not back with a literal `S0` check, so an edge exists only where the
program itself fails closed against a mis-wired peer. That is why the two are
kept separate — the static comparison runs off the wiring map for every port,
while `UNENFORCED_RANGES` in
`validation/validators/validate_script_contracts.py` holds the ports that declare
a range and still trust whatever is wired to them. Six remain, each with a
reviewed reason: the Print Material Resolver's two ports pin a schema and a
status cell instead, and at 120 lines it has no room for a check; the Multi
Reservation Stager and Allocator accept either lane's resolver, so no single
`S0` equality expresses the edge; and the two live-commissioning diagnostics read
whatever housing they are pointed at by design.

`validation/validators/validate_stack_envelopes.py` keeps its independent,
source-scan-based guard for magic-checking consumers and reference-register
reads; its reviewed-read allowlist for device ports is drawn from the wiring
map's `header_reads` declarations, so there is one list to maintain.

`tools/plan_header_migration.py` uses the map to print a family's exact inbound
edges — every consumer port wired at a family member, with the cells it touches
and which of them the header window displaces — instead of asking the operator
to confirm every unattributed low-cell access by hand. Reference-register
accesses (`getd`/`putd` through a resolved ReferenceId) have no port for the map
to key on, so the planner still scans the family and its magic-namers and lists
those separately for manual confirmation.

## Maintenance

When adding a program (see `docs/ADDING_CONTROLLERS.md`), add a wiring entry for
each of its device ports, and extend the `providers` list of any generic service
whose peer class the new program joins. When a port's magic check names its peer,
say so in the `note`; otherwise cite the deployment documentation that fixes the
edge. When retiring a program, validation fails until its entry and every edge
naming it are removed.
