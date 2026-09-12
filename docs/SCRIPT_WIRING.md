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
exactly — but only 139 of 311 ports do. The wiring map names the rest.

A literal check names the peer only on the paths that pass it. Two consumers
reached a port's stack around a check that sat on their main path — a boot
fast-path into a resume block, a sibling branch at the top of a loop — and
acted on whatever was wired (issue #109).
`validation/validators/validate_identity_coverage.py` walks every path from
the entry and refuses an access to a declared consumer port on a path that
never passed the port's check. A state register or private state cell armed
after the check gates the accesses of later ticks, so the ordinary cross-tick
state machine proves; a read taken before the check is fine while nothing acts
on it; a check the previous image passed over a reflash guard counts for
nothing, because the pin is wiring and a reflash preserves none of it.

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
  `S0` magic check that names the peer mechanically. A note that names cells
  (`S<n>`, or a range `S<a>..S<b>`) names only the cells the consumer reads or
  writes on that port; the peer's own layout lives in `contracts/` and
  `docs/STACK_FIELD_MAP.md`, and a note restating it is a second copy that
  drifts.
- `header_reads` optionally declares reviewed, deliberate reads of a migrated
  peer's `S2..S7` header cells (for example reading `S3` as SchemaId). Anything
  not declared there is treated as a stranded payload read and fails validation.

### Register-indexed ports

A port operand can be a register: `put dr9 14 r2` writes whichever pin `r9`
names when the instruction runs. The map keys on `d0..d5`, so the contract
resolves every `dr<n>` to the pins its register can hold before the map is
checked, and each of those pins is an ordinary port entry here with the
accesses made through the register attributed to it. The pins come from the
same branch-bounds derivation that bounds a computed stack address: a scanner
walking `move r7 0 .. blt r7 6 Pins` proves `d0..d5` on its own, while a
register the program reads back from its own stack proves nothing at that
access and needs a reviewed `register_ports` entry in
`data/script_contract_overrides.json` (`{"dr9": ["d1", "d2"]}`), fingerprinted
to the source and required to contain every pin the branches did prove. A
`dr<n>` with neither does not build, so a program cannot reach a pin the map
never names. The POWER Scheduler is why: it wrote Prepare's and Finalize's job
fields through `dr9` at the peers' header cells for the life of the header
migration, and nothing compared the write against anything until the port
existed (issue #163).

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
- a magic-checking port's `note` never names the identity it pins. A port that
  checks `S0` has better evidence than the cell-shape correspondence most notes
  were written against, and a note left alone keeps citing the weaker story for
  an edge the source now names outright;
- a `physical-device` declaration sits on a port whose `S0` check names a
  registered script header, or overrides a stack-shaped contract target without
  a `note` saying why the peer is not a script;
- a port reads a migrated provider's `S2..S7` — literally or through a declared
  dynamic range — without a `header_reads` declaration, or writes anywhere in
  that provider's `S0..S7` envelope at all: only the owner publishes envelope
  cells;
- a `header_reads` declaration names a cell outside `S2..S7` or one the port
  never reaches;
- a script edge's `note` names a cell (`S<n>`, or a range written `S<a>..S<b>`
  or `S<a>-S<b>`) the port never reads or writes, literally or through a
  declared dynamic range. The notes carried the mailbox numbering from before
  the mailboxes moved above the envelope long after the source left it, since
  nothing compared the prose with the tree (issue #196). `S0` is exempt — a
  note names it for the identity check, which the rule above already holds the
  note to — and a bare number is not a citation, since notes also quote line
  numbers and status codes;
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
contracts, through the one pair of functions (`published_cells` and
`accepted_cells` in `framework/script_contracts/checks.py`) that every check
comparing a peer's access against a program's own stack uses (issue #155):

- a program **publishes** the cells it writes — literally or through its
  effective dynamic write range — plus any `external_readable_ranges`;
- a program **accepts** the cells it reads, on the same terms, plus any
  `external_writable_ranges`.

Effective, not proven: a reviewed range and a fail-closed fallback both stand
for cells the program may touch, and a consumer comparing against the proven
subset alone would reject an access the provider is entitled to make. Both
surfaces are upper bounds for the same reason — neither can tell a mailbox cell
from a counter the owner writes and reads back — so the check catches a consumer
reaching outside what its peer touches at all, not a consumer reaching the wrong
field inside it.

A port passes on the first declared provider that publishes everything it reads
and accepts everything it writes; a port matching none reports each. Because
both sides are derived, a padded envelope on one end cannot make the comparison
vacuous the way two rounded-up declarations could: the pressure-grid route stack
declared a 16-cell hop window on both sides of a three-cell array, and the
comparison that was already enforced there passed anyway.

One vacuity does survive, and the validator counts it rather than hiding it: a
provider whose published surface is all 512 cells cannot fail a read, and because
providers are any-of, one such peer absorbs the whole edge however narrow the
others are. That used to be mostly boot clears — a `clr db` writes every cell, so
every program with one offered the whole stack — and taking the entry clear out of
the derived write range dropped it from 26 of the 113 declared providers to 9.
The rest were providers whose computed writes the bounds analysis could not
follow, where the whole-stack surface was a gap in the proof rather than a fact
about the source. Each of those now carries a reviewed, source-fingerprinted
`dynamic_write_ranges` window in `data/script_contract_overrides.json`, and
`validation/validators/validate_script_contracts.py` refuses a deployable program
whose own-stack write range falls back to the whole stack, so the gap cannot
reopen silently: a new computed write is proved by the branches around it or
reviewed into a window before the program builds. What still absorbs an edge is a
reviewed `external_readable_ranges` naming the whole stack — the Generic Catalog
Store declares its heap that way — which leaves 230 of 236 edges able to fail.
The first edge the narrowing exposed was a real one: the Manufacturing Scheduler
waits on Gateway `S8`, and Gateway ABI5 had moved lane A's reply one cell high.

The accepted surface had the mirror-image gap. A provider's own computed *reads*
are the cells a peer may write into it, so a program whose read range fell back
to the whole stack accepted every cell, and every port writing into it — ten of
them, mostly request mailboxes — passed whatever it posted. Each of those ten
programs now carries a reviewed `dynamic_read_ranges` window beside the write
window, held from below by the same proof, and the validator refuses the read
fallback exactly as it refuses the write one. A read window is a claim about what
the owner reads: for a record scan it is the record block, and for a request
mailbox it is the request cells the owner names in its own
`external_writable_ranges`, so the two declarations describe one layout. No
deployable program accepts all 512 cells, and every one of the 119 writing ports
can fail.

A window counts on the same terms as a literal access, and for every check.
Since #137 and #138 no deployable program's range is the fallback, so a window is
a proven or reviewed claim about the cells the owner touches — exactly what a
literal is — and the declared-consumer-edge check in
`framework/script_contracts/checks.py`, the network-target check that holds an
attributed network write to its target, and the commissioning stack-coverage
obligations all compare against the same two surfaces. Until #155 the contract
check left the effective ranges out, so a read window counted for the wiring map
and not for a declared edge: seven wired write edges — the request lanes into
the Job Command Gateway from the Child Creator, the Existing Plan Controller,
the Scheduler, and the Lifecycle Client, the Planner's request into the plan
store, the Gate's into the Planner, and the Sink Flow Builder's into the
dispatch plan store — landed only in their provider's read window, and seven
read edges only in a write window, and each would have failed the day it was
declared, until an envelope duplicating the window silenced the check.

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

## Network writes

A `putd` lands on whatever housing its reference register names, and the map
has no port to key it on. The rule that attributes it is the port rule carried
one transport over (issue #174): at every write, on every path from the entry,
the reference must be one the path has identity-checked -- a `getd rX rR 0`
followed by an equality branch against a magic some program publishes, with
`rR` unchanged since; a `move` carries the check with the value, and a check
that fails takes it back -- or one loaded from a place whose meaning a reviewer
has declared. `framework/network_provenance.py` walks the paths with the same
machinery as the register and identity rules and records, on each contract's
`network_dependencies` entry, where the reference came from (`origins`), the
contracts the accesses reach (`targets`), and anything neither covers
(`unattributed`); `contracts/index.json` counts the unattributed writes and
`validation/validators/validate_network_provenance.py` fails on any. A read
through a reference is attributed the same way, held to its own read sites, so
`docs/STACK_FIELD_MAP.md` counts the reader as a peer of what it reads.

Where the reference came from is what the walk knows: a cell of an identified
peer (`cell`), one of the program's own cells (`own`), a cell of another
reference (`ref`), a cell of a port with no declared identity (`port`). What a
ReferenceId *in that place* names is a fact about the peer's layout, declared
once per accessing reference in `data/script_contract_overrides.json`:

```json
"network_provenance": [
  {
    "reference": "r7",
    "origin": {"kind": "peer-cell", "identity": "PowerDispatchPlanStore.v1", "cells": "any"},
    "targets": ["ResourceReservation"],
    "reason": "a plan flow record holds the source POWER Reservation ReferenceId at +1; ..."
  }
]
```

Origins are `peer-cell` (identity, cells), `own-cell` (cells, and who fills
them: `self`, `peer`, or `operator`, each held to the contracts), `reference-cell`
(via another reference register, cells), `port-cell`, `port-device`, and
`index-cell`; `cells` is a list of addresses or `any`. A declaration no write
site loads from fails the build, a target no program provides or one that
accepts none of the cells written fails compatibility, and a write to a device
that is not a program names the device instead of a target. The same
attribution is what lets `validation/validators/validate_register_seeding.py` hold a private state
cell against the network: a cell some attributed write reaches is not the
program's alone.

## Mailbox arbitration

The map also says who *writes* each program. A port that writes a peer's cells
posts a request, and a request/response mailbox on one instance holds one
request. `ASYNC_REQUEST_V1` fences what a caller may read of the response; it
does not order who may post. Two programs posting to one instance with nothing
ordering them displace each other before the callee latches the request: the
callee answers whichever token it finds when it polls, and the other caller
waits forever for a response that was never served. A post that straddles a
tick can also hand the callee a payload assembled from both. The Job Command
Gateway exists so that six producers never do this to the Job Store; the same
question has to be answered for every other mailbox.

`framework/script_wiring.writer_edges` derives the writers of every program
from the map and the contracts, and `data/mailbox_arbitration.json` carries a
reviewed answer for every mailbox whose writers overlap on a cell:

- `serial` -- the writers are one call tree: a named root posts and waits at
  every hop, so no two of them are ever mid-request at once. The map proves
  the shape (each writer sits downstream of the root through declared mailbox
  writes) and the review vouches for the blocking. A root that drives a peer
  through a register-indexed port (the POWER Scheduler's `dr9`) reaches it
  through a declared `d<n>` like any other, because the contract resolves the
  register to its pins (see *Register-indexed ports* above).
- `dedicated` -- the writers are independent loops, and each gets its own
  instance of the program. An instance brings every request mailbox it reaches
  downstream, or the sharing moves one hop, so each instance cites the
  document that must name the whole closure by path.
- `alternatives` -- the writers are alternative peers for one role (a Config
  Host and its Policy, an adapter and its Bridge or Registry Host); a
  deployment wires one of them per instance.
- `operator` -- on-demand tools an operator runs one at a time; at most one
  writer may be resident.
- `reselect` -- not a token mailbox but a selected snapshot whose consumers
  read nothing until the selection echoes back, and re-check the generation
  when their reads span a tick, so competing selections cost a retry. A
  `reselect` surface also stops a dedicated closure.

Writers whose write cells never overlap are *laned* -- the Gateway, the
Dependency Planner's plan and cleanup lanes, the stock-target Producer View --
and need no entry. The validator refuses an entry for a laned or single-writer
mailbox as stale, as it refuses one whose writer list no longer matches the
map. `validation/validators/validate_mailbox_arbitration.py` runs all of it;
`tests/test_mailbox_arbitration.py` exercises the checks on a synthetic map and
then shows the race on the production programs: one Claim View shared by the
stock-target Future View and the Plan Builder strands one of them, and one per
caller answers both. Thirty mailboxes carry an entry. The deployment
consequences are in `docs/STOCK_TARGET_INGRESS.md` (seven dedicated instances)
and `docs/DEPENDENCY_PLANNING.md` (the Cancellation Guard's own Job Monitor).

## Maintenance

When adding a program (see `docs/ADDING_CONTROLLERS.md`), add a wiring entry for
each of its device ports, and extend the `providers` list of any generic service
whose peer class the new program joins. When a port's magic check names its peer,
say so in the `note`; otherwise cite the deployment documentation that fixes the
edge. When retiring a program, validation fails until its entry and every edge
naming it are removed. When a new program writes a mailbox another program
already writes, `validation/validators/validate_mailbox_arbitration.py` fails
until `data/mailbox_arbitration.json` says what keeps the two apart.
