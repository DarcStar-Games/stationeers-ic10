"""Posts a program makes that it does not wait on before posting elsewhere or replying.

A serial mailbox group in `data/mailbox_arbitration.json` claims its writers are
one call tree: a root posts and waits at every hop, so no two writers are ever
mid-request at once. `framework.script_wiring` proves the shape of that claim
from the wiring map, every writer downstream of the root through declared
mailbox writes. This module proves the blocking half, per program, from the
source: after a program writes a peer's request token, every path it can take
reads that peer's response token before it writes any other peer's request
token or its own response token (issue #146). A program that posted to two
peers and then waited on both would put its two subtrees in flight together;
one that replied to its caller with a request outstanding would let the caller
start a sibling while the callee still holds the first request. Either breaks
the claim, and neither was checked before.

Which cells are tokens comes from the reviewed protocol layouts behind the
generated contracts (`role: request_token` and `role: response_token`, issue
#190): a post is a literal write of a request-token cell on a port whose wired
peer publishes that layout, and a wait is a literal read of a response-token
cell on the same port. A register-addressed write on a port counts as a post
only when the contract's proven write range for that port reaches a request
cell; the payload copies in the tree stay below their tokens, and the token is
always written at a literal address last (`docs/ASYNC_REQUEST_STANDARD.md`).
A register-indexed port (`dr9`) is the set of pins its register can hold, as
the contract resolves it; a wait on the same set answers a post on it.

The wait usually sits a tick away. Most callers are cross-tick state machines:
the post arms a state cell (`poke 20 2`) and returns to the loop head, and the
block that reads the response is the one the head dispatches to on the next
tick when the state says so. So the question is asked as a path question over
`framework.register_seeding.BootPaths`, the same walk the identity and seeding
checks use: it carries what a path has put in its registers and its own state
cells and takes only the edges a decidable branch permits, so the re-dispatch
is followed and the accept block, which would post for a new request, is not
reached while the old one is pending. A state cell prunes only when the program
declares it private (`PRIVATE_STATE_CELLS`); a program whose dispatch the walk
cannot decide is reported, and the finding names the post and what it reached.

The wait is the match, not the read. A post is answered on the edge of the
`beq` or `bne` that compares the register the response token was read into
where equality holds; on the other edge the post stays pending, so a caller
whose mismatch edge went back to accepting requests and posted elsewhere is
reported. A read whose register is overwritten before any compare leaves the
post pending too, as does a compare against a literal, which is a poll or a
status test rather than the match. What a path knows about a read is one
register name, and two paths arriving at one instruction holding the token in
different registers lose it when the walk widens past its environment cap; the
post then stays pending on the joined path, which costs a finding to review
and never hides one.

Two things this does not read. A second post to the *same* peer before its
response is not reported: it replaces the program's own request and strands no
sibling, and one caller in the tree re-posts its token every tick while it
waits. And a post made through `putd`, to a mailbox named by ReferenceId, is
not a post here: the walk knows the token cells of what a declared pin faces,
and nothing about a device the program names at run time. No program on a
serialized tree posts that way.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from framework.ic10_source import integer_value
from framework.register_seeding import REGISTERS, BootPaths, Environment
from framework.script_contracts.control_flow import CallState
from framework.script_contracts.parsing import RegisterPorts, collect_aliases, parse_rows, resolve_ports

_PENDING = "post:"
_READ = "read:"


@dataclass(frozen=True, slots=True)
class PortTokens:
    """The token cells of whatever is wired to one pin, from its protocol layout."""

    request: frozenset[int]
    response: frozenset[int]
    # Whether a register-addressed write on the pin can reach a request cell,
    # from the contract's proven write range for the port.
    dynamic_may_post: bool = False


@dataclass(frozen=True, slots=True)
class UnblockedPost:
    """One post a path leaves unanswered when it posts elsewhere, replies, or halts."""

    port: str
    line_number: int
    code_text: str
    offence: str
    offence_line: int
    offence_text: str


def token_cells(contract: dict[str, Any]) -> tuple[frozenset[int], frozenset[int]]:
    """The request-token cells and the answering cells a program's own layout names.

    A `TERMINAL_RESPONSE` service answers at its response token; a
    `LIVE_CURRENT` producer answers at its current token, which it echoes when
    it accepts the request and which its caller fences every later read on
    (`docs/ASYNC_REQUEST_STANDARD.md`). Either is the cell a caller waits on.
    """
    request: set[int] = set()
    response: set[int] = set()
    for cell in contract["own_stack"]["fields"]:
        role = cell.get("role")
        if role == "request_token":
            request.add(cell["address"])
        elif role in {"response_token", "current_token"}:
            response.add(cell["address"])
    return frozenset(request), frozenset(response)


def own_response_cells(contract: dict[str, Any]) -> frozenset[int]:
    """The response-token cells a program writes to answer its own caller."""
    return token_cells(contract)[1]


def port_tokens(
    path: str, contract: dict[str, Any], wiring: dict[str, Any], by_source: dict[str, dict[str, Any]],
) -> dict[str, PortTokens]:
    """Per pin of `path`: the token cells of the peers its wiring names, any-of across providers."""
    by_name = {port["port"]: port for port in contract["device_ports"]}
    out: dict[str, PortTokens] = {}
    for pin, peer in wiring["ports"].get(path, {}).items():
        if peer.get("kind") != "script":
            continue
        request: set[int] = set()
        response: set[int] = set()
        for provider in peer.get("providers", ()):
            if provider in by_source:
                asked, answered = token_cells(by_source[provider])
                request |= asked
                response |= answered
        dynamic = False
        port = by_name.get(pin)
        if port is not None:
            stack = port["stack"]
            covered: set[int] = set()
            for item in stack["dynamic_write_ranges"]:
                covered |= set(range(item["start"], item["end"] + 1))
            if stack["dynamic_write"] and not stack["dynamic_write_ranges"]:
                covered = set(range(512))
            dynamic = bool(covered & request)
        out[pin] = PortTokens(frozenset(request), frozenset(response), dynamic)
    return out


class RequestBlocking:
    """The paths from a program's entry, walked with the posts each has left unanswered.

    `ports` maps each pin to the token cells of its wired peer, `own_response`
    is the program's own response-token cells, `private_cells` the own-stack
    cells the walk may read back, and `register_ports` resolves `dr<n>`
    operands to pins as the contract does.
    """

    def __init__(
        self, source: str, ports: dict[str, PortTokens], own_response: frozenset[int],
        private_cells: frozenset[int] = frozenset(), register_ports: RegisterPorts | None = None,
    ) -> None:
        self.paths = BootPaths(source, private_cells)
        port_aliases, self.integers = collect_aliases(parse_rows(source))
        self.ports = ports
        self.own_response = own_response
        # Per row: ("post", pins) | ("reply", ()) | ("halt", ()); waits are kept
        # apart with the register the response token is read into.
        self.actions: dict[int, tuple[str, frozenset[str]]] = {}
        self.waits: dict[int, tuple[frozenset[str], str]] = {}
        for index, entry in enumerate(self.paths.program):
            row = entry["row"]
            action = self._classify(row, port_aliases, register_ports)
            if action is None:
                continue
            if action[0] == "wait":
                self.waits[index] = (action[1], row[1])
            else:
                self.actions[index] = action
        self._found: set[tuple[int, int, str]] = set()

    def _classify(
        self, row: list[str], aliases: dict[str, str], register_ports: RegisterPorts | None,
    ) -> tuple[str, frozenset[str]] | None:
        if not row:
            return None
        op = row[0]
        if op == "hcf":
            return ("halt", frozenset())
        if op == "poke" and len(row) == 3 or op == "put" and len(row) == 4 and row[1] == "db":
            address = integer_value(row[-2], self.integers)
            return ("reply", frozenset()) if address in self.own_response else None
        if op == "put" and len(row) == 4:
            pins = frozenset(pin for pin in resolve_ports(row[1], aliases, register_ports) if pin in self.ports)
            if not pins:
                return None
            address = integer_value(row[2], self.integers)
            if address is None:
                return ("post", pins) if any(self.ports[pin].dynamic_may_post for pin in pins) else None
            return ("post", pins) if any(address in self.ports[pin].request for pin in pins) else None
        if op == "get" and len(row) == 4:
            pins = frozenset(pin for pin in resolve_ports(row[2], aliases, register_ports) if pin in self.ports)
            address = integer_value(row[3], self.integers)
            if pins and address is not None and any(address in self.ports[pin].response for pin in pins):
                return ("wait", pins)
        return None

    @staticmethod
    def _key(pins: frozenset[str]) -> str:
        return "/".join(sorted(pins))

    @staticmethod
    def _pins(key: str) -> set[str]:
        return set(key.split(":", 1)[1].split("/"))

    def _mark(self, state: CallState, taken: bool | None, env: Environment) -> Environment:
        """What leaving `state` does to the posts a path holds unanswered and the replies it has read."""
        index = state[0]
        row = self.paths.program[index]["row"]
        if not row:
            return env
        env = dict(env)
        reads = {key: register for key, register in env.items() if key.startswith(_READ)}
        # A compare of the register holding a response token against another
        # register, the token the caller posted, answers the post on the edge
        # where equality holds and settles the read either way. A compare against
        # a literal is a poll for "not yet" or a status test, not the match, and
        # leaves the post pending.
        if row[0] in {"beq", "bne"} and len(row) == 4 and taken is not None and row[1] in REGISTERS and row[2] in REGISTERS:
            equal = taken if row[0] == "beq" else not taken
            for key, register in reads.items():
                if register in row[1:3]:
                    del env[key]
                    if equal:
                        self._answer(env, self._pins(key))
        # A register written before its compare no longer holds the token it read.
        for written in self.paths.writes(row, env):
            for key, register in reads.items():
                if register == written:
                    env.pop(key, None)
        wait = self.waits.get(index)
        if wait is not None:
            pins, register = wait
            env[_READ + self._key(pins)] = register
            return env
        action = self.actions.get(index)
        if action is None:
            return env
        kind, pins = action
        pending = {key: posts for key, posts in env.items() if key.startswith(_PENDING)}
        if kind == "post":
            key = _PENDING + self._key(pins)
            for other, posts in pending.items():
                if other != key:
                    self._found.update((post, index, "posts to " + self._key(pins)) for post in posts)
            env[key] = env.get(key, frozenset()) | {index}
        elif kind == "reply":
            for posts in pending.values():
                self._found.update((post, index, "replies to its own caller") for post in posts)
        return env

    def _answer(self, env: Environment, pins: set[str]) -> None:
        for key in [key for key in env if key.startswith(_PENDING) and self._pins(key) <= pins]:
            del env[key]

    @staticmethod
    def _partition(env: Environment) -> frozenset[str]:
        return frozenset(key for key in env if key.startswith(_PENDING))

    @property
    def posts(self) -> int:
        return sum(1 for kind, _ in self.actions.values() if kind == "post")

    def findings(self) -> list[UnblockedPost]:
        """Every post some path leaves unanswered at a later post, reply, or halt; one entry per pair."""
        self._found = set()
        for index, _row, env in self.paths.walk(mark=self._mark, partition=self._partition):
            # A halt has no edge to leave by, so what a path holds there is read on arrival.
            if self.actions.get(index, ("",))[0] == "halt":
                for key, posts in env.items():
                    if key.startswith(_PENDING):
                        self._found.update((post, index, "halts") for post in posts)
        lines = self.paths.line_numbers
        program = self.paths.program
        results: list[UnblockedPost] = []
        for post, offence_index, offence in sorted(self._found):
            pins = self.actions[post][1]
            results.append(UnblockedPost(
                "/".join(sorted(pins)), lines[post], " ".join(program[post]["row"]),
                offence, lines[offence_index], " ".join(program[offence_index]["row"]),
            ))
        return results


def unblocked_posts(
    source: str, ports: dict[str, PortTokens], own_response: frozenset[int],
    private_cells: frozenset[int] = frozenset(), register_ports: RegisterPorts | None = None,
) -> list[UnblockedPost]:
    """The posts `source` makes that some path leaves unanswered when it posts elsewhere, replies, or halts."""
    return RequestBlocking(source, ports, own_response, private_cells, register_ports).findings()
