"""Which program a network write can reach, from where its reference came from.

A network write (`putd` through a ReferenceId) lands on whatever housing the
register names. For a device port the rule is settled: a declared consumer
edge rests on a literal `S0` identity check, and every access on every path is
covered by one (`framework.identity_coverage`). For a network write there was
no rule, and nothing attributed the write to a target program (issue #174):
the contract recorded the cells written and whatever constraint the writer
checked on the target, and for most references that was nothing, because the
reference had come out of a directory record the program had already checked
at the record level, or out of a request cell a trusted peer filled. That
provenance was in the reviewer's head, not in the contract, so the contract
layer could not say which program's `S20` a `putd r2 20 r10` reaches, and the
register-seeding validator had to accept such writes as residue when it
verified a private state cell.

The rule here is the port rule carried one transport over. At every `putd`, on
every path from the entry, the reference register must hold one of two things:

- **a reference the path has identity-checked**: a `getd rX rR <base>` followed
  by an equality branch against a header magic some program publishes at that
  base, with `rR` unchanged since. The check establishes the identity of what
  `rR` names for the rest of the path; a `move` carries it along with the value
  (the Loader Router checks a Store in `r2` and writes through `ra`), and a
  check that fails takes it back. A reference loaded off a declared consumer
  port is established the same way, since `framework.identity_coverage` has
  already proven that load sits on a checked path.
- **a reference loaded from a declared origin**: a cell of an established
  peer (`cell`), one of the program's own cells (`own`), a cell of another
  reference (`ref`), or a cell of an unidentified port (`port`). Where the
  value came from is what the walk knows; what a ReferenceId *in that cell*
  names is a fact about the peer's layout, which the reviewer declares once in
  `data/script_contract_overrides.json` (`network_provenance`) with the target
  contracts and the reason, fingerprinted with the rest of the file's reviewed
  claims. The walk holds the declaration to the source: an origin no write
  site loads from is stale, and a load the declarations do not cover is an
  unattributed write.

The walk is `framework.register_seeding.BootPaths`, the same one the register
and identity rules use, so the paths explored are the feasible ones and a
reference latched in one tick is still established in the next. Widening is
partitioned by where each reference register came from, so a loop head reached
by the entry with nothing loaded and by an armed state with the reference
loaded never merges the two. Over a reflash guard's same-image edge a register
holds what some fresh-housing path of this same program could have left in it,
the carry `framework.register_seeding` allows for the same reason; a register
no fresh path loads is carried as untracked.

What comes out is recorded in each contract's `network_dependencies` entry
(`origins`, `targets`, `unattributed`, `provenance`) and counted in
`contracts/index.json`; `validation/validators/validate_network_provenance.py`
fails an unattributed write and holds an own-cell declaration to who actually
fills the cell.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from framework.ic10_source import game_hash
from framework.identity_coverage import declared_identities
from framework.register_seeding import (
    PRIVATE_STATE_CELLS,
    REGISTERS,
    BootPaths,
    Environment,
)
from framework.script_contracts.control_flow import CallState
from framework.script_contracts.provenance_declarations import validate_provenance  # noqa: F401 - re-exported
from framework.script_contracts.parsing import (
    RegisterPorts,
    collect_aliases,
    parse_rows,
    resolve_integer,
    resolve_literal,
    resolve_ports,
)

# Origin tokens. `A` is a cell address, or `*` when the walk cannot resolve it.
CHECKED = "checked"      # checked:<base>:<magic>  identity of what the register names, established on the path
CELL = "cell"            # cell:<magic>:<A>        cell A of a housing with that established identity
OWN = "own"              # own:<A>                 the program's own cell A
REF = "ref"              # ref:<rN>:<A>            cell A of whatever unidentified register rN names
PORT = "port"            # port:<dX>:<A>           cell A of an unidentified port
DEVICE = "device"        # device:<dX>             the device on an unidentified port
INDEX = "index"          # index:<N>:<A>           cell A of device index N (`db:N`)
SELF = "self"            # the program's own housing
UNTRACKED = "untracked"  # nothing on the path loaded the register

_ORIGIN = "origin:"
_HEADER = "header:"
# A literal a `move` put in a register, kept whole: the walk's ranges drop a
# bound beyond `VALUE_CAP`, and a magic held in a register for an `rrN`
# comparison (the Mapping Editor's service loop) is exactly such a value.
_LITERAL = "literal:"


def _reference_operand(row: list[str] | None) -> str | None:
    """The register a row accesses a peer through: `putd ref cell value` or `getd dest ref cell`.

    A write site is what the validator holds; a read site is recorded so a reader
    can be attributed as a peer of what it reads (the stack field map, issue #190).
    """
    if not row or len(row) < 4:
        return None
    if row[0] == "putd":
        return row[1]
    if row[0] == "getd":
        return row[2]
    return None


def _register_aliases(rows: list[list[str]]) -> dict[str, str]:
    return {row[1]: row[2] for row in rows if len(row) == 3 and row[0] == "alias" and row[2] in REGISTERS}


class ReferenceOrigins:
    """The paths from a program's entry, walked with where each reference register came from.

    `identities` maps a declared consumer port to the `(header_base, magic)`
    pairs it accepts; a reference loaded off such a port, or the port's own
    ReferenceId, is established as one of them. `register_ports` resolves
    `dr<n>` operands to pins as the contract does.
    """

    def __init__(
        self, source: str, identities: dict[str, set[tuple[int, Any]]] | None = None,
        private_cells: frozenset[int] = frozenset(), register_ports: RegisterPorts | None = None,
        known: set[tuple[int, Any]] | None = None,
    ) -> None:
        self.paths = BootPaths(source, private_cells)
        rows = parse_rows(source)
        self.port_aliases, _ = collect_aliases(rows)
        self.register_aliases = _register_aliases(rows)
        self.identities = identities or {}
        self.register_ports = register_ports
        # The `(header_base, magic)` pairs some program publishes. An equality
        # check against anything else is a payload check, not an identity, so
        # it establishes nothing; None accepts every literal compared.
        self.known = known
        # putd index -> the origin sets the reference register held on arrival
        self.sites: dict[int, set[frozenset[str]]] = defaultdict(set)
        # register -> every origin a fresh-housing path can leave in it, which
        # is what a register carried over the reflash guard's same-image edge
        # can hold: the previous image was this program.
        self.carried: dict[str, frozenset[str]] = {}
        # The registers the program writes through, the only ones the walk
        # partitions its widening by. Read sites are recorded too (`run`), but a
        # read register shares the join of the arrivals it is reached with: the
        # question the validator asks is about writes, and partitioning by every
        # read register multiplied the states past the generator's time budget.
        self.references = {
            self.register_aliases.get(entry["row"][1], entry["row"][1])
            for entry in self.paths.program
            if entry["row"] and entry["row"][0] == "putd" and len(entry["row"]) >= 4
        }

    # -- operands ------------------------------------------------------------

    def _register(self, token: str, env: Environment) -> str | None:
        """The register a `rN`, `rrN`, `sp`, or `ra` operand names under `env`."""
        if token in REGISTERS:
            return token
        index = self.paths._index_register(token)
        return self.paths._named_register(index, env) if index else None

    def _address(self, token: str, env: Environment) -> str:
        """A literal cell address, or `*` for an address held in a register.

        A register-indexed read is a scan, and one token for the scan is what
        the question needs; resolving each exact index the walk happens to know
        would give a table read as many origins as it has rows.
        """
        literal = resolve_literal(token, self.paths.integers)
        return "*" if literal is None else str(int(literal))

    def _magic(self, token: str, env: Environment) -> Any:
        literal = resolve_literal(token, self.paths.integers)
        if literal is not None:
            return literal
        register = self._register(token, env)
        if register is None:
            return None
        if _LITERAL + register in env:
            return env[_LITERAL + register]
        return self.paths.value(register, env).exact

    def _port_tokens(self, token: str, cell: str | None) -> frozenset[str]:
        """What a port operand's device (`cell` None) or one of its cells is."""
        pins = resolve_ports(token, self.port_aliases, self.register_ports)
        if not pins:
            return frozenset({f"{PORT}:{token}:{cell}" if cell is not None else f"{DEVICE}:{token}"})
        found: set[str] = set()
        for pin in pins:
            for base, magic in self.identities.get(pin, ()):
                found.add(f"{CELL}:{magic}:{cell}" if cell is not None else f"{CHECKED}:{base}:{magic}")
            if pin not in self.identities:
                found.add(f"{PORT}:{pin}:{cell}" if cell is not None else f"{DEVICE}:{pin}")
        return frozenset(found)

    def _loaded(self, row: list[str], env: Environment) -> frozenset[str] | None:
        """The origin the row's first operand receives, or None when it receives none."""
        op = row[0]
        if op == "move" and len(row) == 3:
            source = self._register(row[2], env)
            return env.get(_ORIGIN + source) if source else None
        if op == "get" and len(row) == 4:
            cell = self._address(row[3], env)
            if row[2] == "db":
                return frozenset({f"{OWN}:{cell}"})
            if row[2].startswith("db:"):
                return frozenset({f"{INDEX}:{row[2][3:]}:{cell}"})
            return self._port_tokens(row[2], cell)
        if op == "getd" and len(row) == 4:
            cell = self._address(row[3], env)
            base = self._register(row[2], env)
            held = env.get(_ORIGIN + base, frozenset()) if base else frozenset()
            checked = sorted(token for token in held if token.startswith(CHECKED + ":"))
            if checked:
                return frozenset(f"{CELL}:{token.split(':')[2]}:{cell}" for token in checked)
            if SELF in held:
                return frozenset({f"{OWN}:{cell}"})
            return frozenset({f"{REF}:{base or row[2]}:{cell}"})
        if op in {"l", "ld"} and len(row) == 4 and row[3] == "ReferenceId":
            if row[2] == "db":
                return frozenset({SELF})
            if op == "ld":
                source = self._register(row[2], env)
                return env.get(_ORIGIN + source) if source else None
            return self._port_tokens(row[2], None)
        return None

    # -- the walk ------------------------------------------------------------

    def _skip_edge(self, state: CallState, taken: bool | None) -> bool:
        """Whether this edge is the reflash guard's same-image edge."""
        skip = self.paths.skip_edge
        if skip is None or state != skip[0] or taken is None:
            return False
        row = self.paths.program[state[0]]["row"]
        return taken == (self.paths.labels.get(row[-1]) == skip[1][0])

    def _mark(self, state: CallState, taken: bool | None, env: Environment) -> Environment:
        env = dict(env)
        untracked = frozenset({UNTRACKED})
        if state == (0, None):
            # Nothing has loaded any register yet.
            for register in REGISTERS:
                env.setdefault(_ORIGIN + register, untracked)
        if self._skip_edge(state, taken):
            for register in REGISTERS:
                if env.get(_ORIGIN + register, untracked) == untracked:
                    env[_ORIGIN + register] = self.carried.get(register, untracked)
        row = self.paths.program[state[0]]["row"]
        if not row:
            return env
        op = row[0]
        # An equality branch on a register holding a header cell: the equal
        # edge establishes the identity of what the header's register names.
        if op in {"beq", "bne"} and len(row) == 4 and taken is not None:
            held = env.get(_HEADER + row[1]) if row[1] in REGISTERS else None
            magic = self._magic(row[2], env) if held else None
            if held and magic is not None:
                register, base = held
                token = f"{CHECKED}:{base}:{magic}"
                if (op == "bne") == (taken is False):
                    if self.known is None or (base, magic) in self.known:
                        env[_ORIGIN + register] = env.get(_ORIGIN + register, frozenset()) | {token}
                else:
                    # The path has just seen the header not hold this magic.
                    env[_ORIGIN + register] = env.get(_ORIGIN + register, frozenset()) - {token}
        loaded = self._loaded(row, env)
        header = None
        if op == "getd" and len(row) == 4:
            base = self._register(row[2], env)
            cell = self._address(row[3], env)
            if base and cell != "*":
                header = (base, int(cell))
        elif op == "move" and len(row) == 3:
            source = self._register(row[2], env)
            header = env.get(_HEADER + source) if source else None
        # This row's writes forget what the written registers held.
        if self.paths._writes_first(row) and self.paths._index_register(row[1]) and not self._register(row[1], env):
            for key in [key for key in env if key.startswith((_HEADER, _LITERAL))]:
                del env[key]
            for register in REGISTERS:
                env[_ORIGIN + register] = untracked
            return env
        written = self.paths.writes(row, env)
        if written:
            headers = [(key, value[0]) for key, value in env.items() if key.startswith(_HEADER)]
        for register in written:
            env[_ORIGIN + register] = untracked
            env.pop(_HEADER + register, None)
            env.pop(_LITERAL + register, None)
            # A header held in this register is forgotten with it.
            for key, holder in headers:
                if holder == register:
                    env.pop(key, None)
        destination = self._register(row[1], env) if len(row) >= 2 and self.paths._writes_first(row) else None
        if destination and destination in written:
            if loaded is not None:
                env[_ORIGIN + destination] = loaded
            if header is not None:
                env[_HEADER + destination] = header
            if op == "move" and len(row) == 3:
                literal = resolve_literal(row[2], self.paths.integers)
                if literal is not None:
                    env[_LITERAL + destination] = literal
        return env

    def _established(self, env: Environment) -> frozenset[tuple[str, frozenset[str]]]:
        """What the walk widens by: where each reference register came from.

        Widening joins the arrivals at one instruction, and an origin set is a
        may-fact that joins by union; joined across arrivals that differ in
        what a register holds, a loop head reached by the entry (nothing loaded
        yet) and by every armed state (the reference loaded) would report the
        reference as possibly untracked at every write. Partitioned by the
        origins of the registers written through, only the ranges widen, and
        each arrival keeps what it loaded; the other registers are left to the
        join, since nothing is asked of them.
        """
        return frozenset(
            (register, env.get(_ORIGIN + register, frozenset({UNTRACKED}))) for register in self.references
        )

    def run(self) -> dict[int, set[frozenset[str]]]:
        """Every `putd`, with the origin sets its reference register arrives holding.

        Over a reflash guard's same-image edge the housing keeps its registers,
        and the previous image was this program, so a register nothing on the
        skip path has loaded holds what some fresh-housing path could have left
        in it. That is what the first pass over the fresh paths collects and the
        second pass carries in; a program with no guard needs one pass. A
        register no fresh path loads at all is carried as untracked.
        """
        self.sites = defaultdict(set)
        self.carried = {}
        if self.paths.skip_edge is not None:
            carried: dict[str, set[str]] = defaultdict(set)
            for _index, _row, env in self.paths.walk(
                blocked=self.paths.skip_edge, mark=self._mark, partition=self._established,
            ):
                for register in REGISTERS:
                    carried[register] |= env.get(_ORIGIN + register, frozenset({UNTRACKED}))
            # A register some fresh path loads is carried as those loads. That it
            # may also be a leftover nothing loaded is register seeding's
            # same-image finding for the register, reported there.
            self.carried = {
                register: frozenset(tokens - {UNTRACKED} if tokens - {UNTRACKED} else tokens)
                for register, tokens in carried.items()
            }
        for index, row, env in self.paths.walk(mark=self._mark, partition=self._established):
            operand = _reference_operand(row)
            if operand is not None:
                register = self._register(operand, env)
                self.sites[index].add(env.get(_ORIGIN + register, frozenset({UNTRACKED})) if register else frozenset())
        # Every site is kept for `reference_sites`; the walk's own answer is still the writes.
        return {
            index: sets for index, sets in self.sites.items()
            if self.paths.program[index]["row"][0] == "putd"
        }

    def reference_sites(self, reference: str, ops: frozenset[str] = frozenset({"putd", "getd"})) -> dict[int, set[frozenset[str]]]:
        """The sites whose reference operand is `reference` (a register or its alias), of the given ops.

        A write's attribution is held to its write sites alone: a read that probes the
        peer's S0 before the identity check arrives with the register unchecked, and
        that is the check working, not an unattributed write.
        """
        register = self.register_aliases.get(reference, reference)
        return {
            index: sets for index, sets in self.sites.items()
            for row in [self.paths.program[index]["row"]]
            for operand in [_reference_operand(row)]
            if operand is not None and row[0] in ops and self.register_aliases.get(operand, operand) == register
        }


# -- declarations -----------------------------------------------------------------


def origin_matches(token: str, origin: dict[str, Any], aliases: dict[str, str]) -> bool:
    """Whether a walk token is one of the loads a declared origin describes."""
    if token in {UNTRACKED, SELF}:
        return False
    kind = origin["kind"]
    parts = token.split(":")
    if kind == "port-device":
        return token == f"{DEVICE}:{origin['port']}"
    cells = origin.get("cells", "any")
    if cells != "any" and (parts[-1] == "*" or int(parts[-1]) not in cells):
        return False
    if kind == "peer-cell":
        identity = origin["identity"]
        # A block header away from S0 has a numeric magic and no contract name.
        expected = identity if isinstance(identity, int) else game_hash(identity)
        return parts[0] == CELL and int(parts[1]) == expected
    if kind == "own-cell":
        return parts[0] == OWN
    if kind == "reference-cell":
        return parts[0] == REF and parts[1] == aliases.get(origin["via"], origin["via"])
    if kind == "port-cell":
        return parts[0] == PORT and parts[1] == origin["port"]
    if kind == "index-cell":
        return parts[0] == INDEX and parts[1] == str(origin["index"])
    return False


def filled_by_errors(contract: dict[str, Any], declaration: dict[str, Any], peer_written: frozenset[int]) -> list[str]:
    """Hold an own-cell declaration's `filled_by` to the contracts.

    A `peer` cell is one some wired peer's contract writes (`peer_written`, from
    `framework.register_seeding.peer_written_cells`); a `self` cell is one the
    program writes and no peer does; an `operator` cell is one nothing in the
    tree writes. A declaration over any cell is only a table the program fills.
    """
    origin = declaration["origin"]
    if origin["kind"] != "own-cell":
        return []
    own = contract["own_stack"]
    self_written = {field["address"] for field in own["fields"] if "self-write" in field["access"]}
    for item in own["dynamic_write_ranges"]:
        self_written |= set(range(item["start"], item["end"] + 1))
    filled_by = origin["filled_by"]
    cells = origin["cells"]
    errors = []
    if cells == "any":
        if filled_by != "self" or not own["dynamic_write"]:
            errors.append(f"{declaration['reference']}: an own-cell origin over any cell is only a table this program fills itself")
        return errors
    for cell in cells:
        by_peer = cell in peer_written
        by_self = cell in self_written
        if filled_by == "peer" and not by_peer:
            errors.append(f"{declaration['reference']}: S{cell} is declared filled by a peer, but no wired peer's contract writes it")
        elif filled_by == "self" and (by_peer or not by_self):
            errors.append(f"{declaration['reference']}: S{cell} is declared filled by this program, but "
                          + ("a wired peer's contract writes it" if by_peer else "the program never writes it"))
        elif filled_by == "operator" and (by_peer or by_self):
            errors.append(f"{declaration['reference']}: S{cell} is declared operator-configured, but "
                          + ("a wired peer's contract writes it" if by_peer else "the program itself writes it"))
    return errors


# -- attribution over the tree -----------------------------------------------------


def provider_index(contracts: dict[str, dict[str, Any]]) -> dict[tuple[int, Any], set[str]]:
    """`(header_base, magic)` -> the contract names published there."""
    providers: dict[tuple[int, Any], set[str]] = defaultdict(set)
    for contract in contracts.values():
        for provided in contract["contracts"]["provides"]:
            providers[(provided["base"], provided["magic"])].add(provided.get("contract") or provided["protocol_id"])
    return providers


def writing(dependency: dict[str, Any]) -> bool:
    return bool(dependency["literal_writes"]) or bool(dependency["dynamic_write"])


def accessing(dependency: dict[str, Any]) -> bool:
    """A dependency that reads or writes through its reference; a bare identity probe is neither."""
    return writing(dependency) or bool(dependency["literal_reads"]) or bool(dependency["dynamic_read"])


def attribute_network_writes(contracts: dict[str, dict[str, Any]], root: Path) -> None:
    """Record, on every accessing network dependency, what its reads and writes can reach.

    Adds `origins` (every token an access site's reference arrived holding),
    `targets` (contract names the accesses are attributed to), `devices`
    (declared non-program targets), and `unattributed` (tokens no identity
    check and no declaration covers; `untracked` when nothing on the path
    loaded the register). Raises for a declaration no site loads from.

    Only a write has to be attributed (`validate_network_provenance.py`); a
    read is attributed when the same walk can, so the stack field map counts
    the reader as a peer of the target's protocol (issue #190).
    """
    providers = provider_index(contracts)
    for contract in contracts.values():
        dependencies = [item for item in contract["network_dependencies"] if accessing(item)]
        if not dependencies:
            continue
        own = next((item.get("contract") for item in contract["contracts"]["provides"] if item["base"] == 0), None)
        source = (root / contract["source"]).read_text(encoding="utf-8")
        pins = {token: tuple(item["pins"]) for token, item in contract.get("register_ports", {}).items()}
        origins = ReferenceOrigins(
            source, declared_identities(contract),
            frozenset(PRIVATE_STATE_CELLS.get(contract["source"], {})), pins, set(providers),
        )
        origins.run()
        for dependency in dependencies:
            declarations = dependency.get("provenance", [])
            used = [False] * len(declarations)
            seen: set[str] = set()
            targets: set[str] = set()
            devices: set[str] = set()
            unattributed: set[str] = set()
            # cell operand of each site -> the targets its arrivals establish; a register
            # re-pointed from one peer to a record's target reaches different cells under
            # each, and the stack field map needs them apart (issue #190).
            site_targets: dict[int | str, set[str]] = {}
            # `targets`, `origins`, and `unattributed` answer for the writes when the
            # dependency writes (what the validator holds) and for the reads otherwise;
            # `site_targets` covers every site, so a reader is a peer at each cell it reads.
            held_ops = frozenset({"putd"}) if writing(dependency) else frozenset({"getd"})
            for index, arrivals in origins.reference_sites(dependency["reference"]).items():
                row = origins.paths.program[index]["row"]
                counts = row[0] in held_ops
                cell_token = row[2] if row[0] == "putd" else row[3]
                cell_literal = resolve_integer(cell_token, origins.paths.integers)
                site_cell: int | str = cell_literal if cell_literal is not None else "*"
                site_targets.setdefault(site_cell, set())
                for held in arrivals:
                    if counts:
                        seen |= held
                    checked = {
                        name for token in held if token.startswith(CHECKED + ":")
                        for name in providers.get((int(token.split(":")[1]), _magic_value(token.split(":")[2])), ())
                    }
                    if SELF in held and own:
                        checked.add(own)
                    if checked:
                        if counts:
                            targets |= checked
                        site_targets[site_cell] |= checked
                        continue
                    loads = {token for token in held if not token.startswith(CHECKED + ":")} or {UNTRACKED}
                    for token in loads:
                        matched = [
                            number for number, declaration in enumerate(declarations)
                            if origin_matches(token, declaration["origin"], origins.register_aliases)
                        ]
                        if not matched:
                            if counts:
                                unattributed.add(token)
                            continue
                        for number in matched:
                            used[number] = True
                            site_targets[site_cell] |= set(declarations[number]["targets"])
                            if counts:
                                targets |= set(declarations[number]["targets"])
                                if declarations[number].get("device"):
                                    devices.add(declarations[number]["device"])
            for number, declaration in enumerate(declarations):
                if not used[number]:
                    raise ValueError(
                        f"{contract['source']}: network provenance declaration matches no write site load"
                        f" (origins seen: {sorted(seen)}): {declaration}"
                    )
            dependency["origins"] = sorted(seen)
            dependency["targets"] = sorted(targets)
            dependency["site_targets"] = [
                {"cell": cell, "targets": sorted(names)}
                for cell, names in sorted(site_targets.items(), key=lambda item: (isinstance(item[0], str), str(item[0])))
                if names
            ]
            if devices:
                dependency["devices"] = sorted(devices)
            dependency["unattributed"] = sorted(unattributed)


def _magic_value(text: str) -> Any:
    try:
        return int(text)
    except ValueError:
        return float(text)


def attributed_network_writes(contracts: dict[str, dict[str, Any]]) -> dict[Any, set[int]]:
    """Cells written through a reference, by the `S0` magic of every program the write can reach.

    A dynamic write counts as every cell. This is what lets a program's private
    state cell be held against the network: a cell some attributed write reaches
    is not the program's alone.
    """
    identity: dict[str, Any] = {}
    for contract in contracts.values():
        for provided in contract["contracts"]["provides"]:
            if provided["base"] == 0 and provided.get("contract"):
                identity[provided["contract"]] = provided["magic"]
    reached: dict[Any, set[int]] = defaultdict(set)
    for contract in contracts.values():
        for dependency in contract["network_dependencies"]:
            if not writing(dependency):
                continue
            cells = set(range(512)) if dependency["dynamic_write"] else set(dependency["literal_writes"])
            for name in dependency.get("targets", ()):
                if name in identity:
                    reached[identity[name]] |= cells
    return dict(reached)
