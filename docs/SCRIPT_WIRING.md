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
  never reaches.

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
