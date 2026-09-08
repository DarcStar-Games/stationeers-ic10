"""Port accesses a path reaches without having passed the port's identity check.

A declared consumer edge rests on a literal `S0` equality check in the source
(`framework.script_contracts.device_ports.verify_declared_consumers`), and that
proof says the check exists and rejects. It says nothing about the port's other
accesses: an identity check is worth exactly the paths it covers, and on a path
that reaches an access without passing one the port is back to acting on
whatever is wired to it (issue #109). The two real cases found by reading had
the same shape -- a boot fast-path into a resume block and a sibling branch at
the top of a loop, each reaching the port's stack around the check that sat on
the main path.

Dominance is the wrong tool for the question. Most consumers are cross-tick
state machines: the check runs on the tick that arms a state register or a
private state cell, and the accesses sit in blocks the loop head dispatches to
on later ticks only when that state says to. No check dominates those blocks in
the graph, yet every path that reaches them passed one, because the dispatch
condition cannot hold otherwise. So the question is asked as a path question,
over the same walk `framework.register_seeding` uses for registers: is there a
path from the entry that reaches an access to the port without ever taking the
success edge of one of the port's identity checks? The walk carries what a path
has put in its registers and its own state cells and takes only the edges a
decidable branch permits, so the state-machine paths it explores are the
feasible ones. A check passed stays passed for the rest of the path, across
`yield` and across ticks: the guarantee is that the program has established
what is on the pin before acting on it, not that it re-reads `S0` every tick.
A check that then fails takes the establishment back: the program has just
seen that the pin no longer holds what it checked, so the reject block acts on
an unchecked pin like any other path.

An access is what the contract records as one -- a stack `get`/`put`, a device
property read or write, a slot read or write -- on any pin the operand can
name; a presence branch (`bdns`, `bdse`) observes existence only and is not
one, and neither is the `get` that feeds the check itself. A port with several
accepted identities is established by any one of its checks.

A write on an unchecked path is a finding outright. A read is a finding only
once its path *acts* while the read is still unsettled: a read whose every
continuation reaches the port's identity check, or the rejection that check
takes, before anything is written or the tick ends has been used for nothing
but deciding whether to go on to the check. That is the ordinary prologue --
a generation snapshot taken before `S0` is compared, a `bdnvl` that proves the
pin is populated and loads its ReferenceId in one line, a bounds guard that
rejects the way the check does -- and it is read from whatever is wired, but
nothing is done with it. What settles a pending read is the check's compare
(either edge) or arrival at the state the check's rejection leads to; what
turns it into a finding is a write to any port, the program's own stack, or a
device named by reference, or a `yield`, met first. What this does not see is
a reject block that publishes a value the prologue read: the rejection settles
the read, and the value goes out with the rejection. That is the same trust
the check's own `S0` read gets, and the tree's reject blocks publish their own
status and nothing read from the pin.

There is no same-image carry here, unlike `framework.register_seeding`. Over a
reflash guard's skip edge the housing keeps its registers and its stack, and a
register the previous image of this exact contract left is a fact about the
housing. What is on a pin is wiring, which no reflash preserves and which is
exactly what an operator changes before reflashing, so a check the previous
image passed proves nothing about the pin the new one acts on. The Executor
defect issue #109 records had that shape: a boot fast-path into its resume
block, taken only when the header matched, trusting a pin the last image had
checked.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framework.register_seeding import BootPaths, Environment
from framework.script_contracts.control_flow import (
    CallState,
    call_state_successors,
)
from framework.script_contracts.device_ports import equality_check_sites
from framework.script_contracts.parsing import (
    RegisterPorts,
    collect_aliases,
    parse_rows,
    resolve_ports,
)

# Rows that act on a port: the accesses `analyze_device_ports` records. The
# port operand's position is what the instruction-set signature gives it.
READ_OPERAND = {"get": 2, "l": 2, "lr": 2, "ls": 2, "bdnvl": 1}
WRITE_OPERAND = {"put": 1, "s": 1, "sr": 1, "ss": 1, "bdnvs": 1}
# Where a path acts: a write to a port, to the program's own stack, or to a
# device named by reference id, or the end of the tick.
BARRIERS = frozenset({
    "put", "s", "sr", "ss", "sb", "sbn", "sbs", "bdnvs", "poke", "push", "clr", "putd", "clrd", "sd",
    "yield", "sleep",
})
# What a path knows about a port: that it has established the identity, and
# the reads it has taken on the port that nothing has settled yet.
_CHECKED = "checked:"
_PENDING = "pending:"


@dataclass(frozen=True, slots=True)
class UncheckedAccess:
    """One access to a port on a path that never passed the port's identity check."""

    port: str
    line_number: int
    code_text: str
    accesses: int


class IdentityCoverage:
    """The paths from a program's entry, walked with the ports each has identity-checked.

    `identities` maps a port to the `(header_base, magic)` pairs its declared
    consumer edge accepts; a check at that cell against that magic establishes
    the port. `register_ports` resolves `dr<n>` operands to pins as the
    contract does.
    """

    def __init__(
        self, source: str, identities: dict[str, set[tuple[int, Any]]],
        private_cells: frozenset[int] = frozenset(), register_ports: RegisterPorts | None = None,
    ) -> None:
        self.paths = BootPaths(source, private_cells)
        rows = parse_rows(source)
        port_aliases, integer_aliases = collect_aliases(rows)
        self.identities = identities
        self.checks: dict[int, set[str]] = {}
        check_reads: set[int] = set()
        for site in equality_check_sites(source, rows, port_aliases, integer_aliases, register_ports):
            if site.port in identities and (site.cell, site.expected) in identities[site.port]:
                self.checks.setdefault(site.compare_node, set()).add(site.port)
                check_reads.add(site.read_node)
        # The states a check's rejection leads to, per port: a guard before the
        # check that branches to the same place settles the reads before it.
        self.rejections: dict[CallState, set[str]] = {}
        for state in self.paths.states:
            ports = self.checks.get(state[0])
            if not ports:
                continue
            outgoing, _ = call_state_successors(self.paths.program, self.paths.labels, state)
            for rejected in outgoing - {(state[0] + 1, state[1])}:
                self.rejections.setdefault(rejected, set()).update(ports)
        self.reads: dict[int, set[str]] = {}
        self.writes: dict[int, set[str]] = {}
        for index, entry in enumerate(self.paths.program):
            row = entry["row"]
            if not row or index in check_reads:
                continue
            for table, operands in ((self.reads, READ_OPERAND), (self.writes, WRITE_OPERAND)):
                operand = operands.get(row[0])
                if operand is None or len(row) <= operand:
                    continue
                ports = {port for port in resolve_ports(row[operand], port_aliases, register_ports)
                         if port in identities}
                if ports:
                    table[index] = ports
        self._found: set[tuple[int, str]] = set()

    def _mark(self, state: CallState, taken: bool | None, env: Environment) -> Environment:
        """What leaving `state` does to the ports a path has checked and the reads it holds."""
        index = state[0]
        row = self.paths.program[index]["row"]
        env = dict(env)
        for port in self.rejections.get(state, set()) | self.checks.get(index, set()):
            env.pop(_PENDING + port, None)
        if row and row[0] in BARRIERS:
            for key in [key for key in env if key.startswith(_PENDING)]:
                self._found.update((read, key[len(_PENDING):]) for read in env.pop(key))
        for port in self.writes.get(index, ()):
            if _CHECKED + port not in env:
                self._found.add((index, port))
        for port in self.reads.get(index, ()):
            if _CHECKED + port not in env:
                env[_PENDING + port] = env.get(_PENDING + port, frozenset()) | {index}
        # A check's fallthrough edge is the one its equality holds on; any
        # other edge out of it has just seen the pin not hold it.
        for port in self.checks.get(index, ()):
            if taken is False:
                env[_CHECKED + port] = 1
            else:
                env.pop(_CHECKED + port, None)
        return env

    @staticmethod
    def _established(env: Environment) -> frozenset[str]:
        return frozenset(key for key in env if key.startswith(_CHECKED))

    def unchecked(self) -> set[tuple[int, str]]:
        """`(index, port)` pairs a path from the entry acts on without having checked the port.

        The walk widens by the set of ports a path has established, so a loop
        head reached both by the entry and by every armed state never merges
        the two: the entry arrival keeps the state value that dispatches it
        back to the check, and the armed arrivals keep the ports they checked.
        """
        self._found = set()
        for _index, _row, _env in self.paths.walk(mark=self._mark, partition=self._established):
            pass
        return set(self._found)

    def findings(self) -> list[UncheckedAccess]:
        """Every access on a path that never checked its port, one entry per port."""
        pairs = self.unchecked()
        results: list[UncheckedAccess] = []
        for port in sorted(self.identities):
            indices = {index for index, found in pairs if found == port}
            if not indices:
                continue
            first = min(indices)
            results.append(UncheckedAccess(
                port, self.paths.line_numbers[first],
                " ".join(self.paths.program[first]["row"]), len(indices),
            ))
        return results


def declared_identities(contract: dict[str, Any]) -> dict[str, set[tuple[int, Any]]]:
    """The `(header_base, magic)` pairs each declared consumer port accepts, from its contract."""
    identities: dict[str, set[tuple[int, Any]]] = {}
    for requirement in contract["contracts"]["consumes"]:
        accepted = identities.setdefault(requirement["port"], set())
        for item in requirement["accepted"]:
            accepted.add((item["header_base"], item["magic"]))
    return identities


def unchecked_accesses(
    source: str, identities: dict[str, set[tuple[int, Any]]],
    private_cells: frozenset[int] = frozenset(), register_ports: RegisterPorts | None = None,
) -> list[UncheckedAccess]:
    """The accesses `source` makes to a declared port on some path that never checked it."""
    return IdentityCoverage(source, identities, private_cells, register_ports).findings()
