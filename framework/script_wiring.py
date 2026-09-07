"""Validate the canonical device-port wiring map against the script contracts.

`data/script_wiring.json` declares, for every device port of every deployable
program, which program(s) the port is intended to point at — or that the port
faces a physical game device. The map names *identity* only: it does not
authorize movement, establish durability, or fence observation. Its purpose is
to make the wiring checkable, so that relocating a peer's payload cells cannot
silently strand a consumer that still reads the old address.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
import json
import re

from framework.json_schema import validate
from framework.stack_envelope import BASE, LENGTH

FORMAT = "IC10_SCRIPT_WIRING_V1"
HEADER_CELLS = frozenset(range(BASE + 2, BASE + LENGTH))
ENVELOPE_CELLS = frozenset(range(BASE, BASE + LENGTH))
STACK_CELLS = frozenset(range(512))


def load_wiring(root: Path) -> dict[str, Any]:
    root = Path(root)
    value = json.loads((root / "data/script_wiring.json").read_text())
    schema = json.loads((root / "schemas/script_wiring.schema.json").read_text())
    validate(value, schema)
    return value


def ranged(ranges: list[tuple[int, int]], cells: frozenset[int]) -> set[int]:
    """The cells a set of dynamic ranges can reach inside `cells`."""
    hit: set[int] = set()
    for start, end in ranges:
        hit |= cells & set(range(start, end + 1))
    return hit


def port_index(contracts: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Reduce built contracts to the per-port facts the wiring checks need."""
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for contract in contracts.values():
        source = contract["source"]
        ports: dict[str, dict[str, Any]] = {}
        for port in contract["device_ports"]:
            stack = port["stack"]
            constraints = {c["address"]: c["equals"] for c in stack["constraints"] if "equals" in c}
            ports[port["port"]] = {
                "kind": port["target"]["kind"],
                "reads": set(stack["literal_reads"]),
                "writes": set(stack["literal_writes"]),
                "read_ranges": [(r["start"], r["end"]) for r in stack["dynamic_read_ranges"]],
                "write_ranges": [(r["start"], r["end"]) for r in stack["dynamic_write_ranges"]],
                "constraints": constraints,
            }
        index[source] = ports
    return index


def stack_surfaces(contracts: dict[str, dict[str, Any]]) -> dict[str, dict[str, frozenset[int]]]:
    """Per program: the cells peers may read, and the cells peers may write.

    A cell the owner writes is one a peer can read, and a cell the owner reads is
    one a peer can write, so most of both surfaces is derived rather than declared.
    Neither direction can tell a mailbox cell from private state -- a counter the
    owner writes and reads back looks exactly like a request field -- so the
    surfaces are an upper bound on what a peer may touch, never a statement that
    touching it means anything.

    The reviewed `external_readable_ranges`/`external_writable_ranges` cover what
    derivation cannot see at all: a mailbox one peer posts and a *different* peer
    consumes, which the host itself never touches.
    """
    def cells(ranges: list[dict[str, int]]) -> set[int]:
        return ranged([(item["start"], item["end"]) for item in ranges], STACK_CELLS)

    surfaces: dict[str, dict[str, frozenset[int]]] = {}
    for contract in contracts.values():
        own = contract["own_stack"]
        published = set(own["literal_writes"]) | cells(own["dynamic_write_ranges"])
        published |= cells(own["external_readable_ranges"])
        accepted = set(own["literal_reads"]) | cells(own["dynamic_read_ranges"])
        accepted |= cells(own["external_writable_ranges"])
        for field in own["fields"]:
            if "external-read" in field["access"]:
                published.add(field["address"])
            if "external-write" in field["access"]:
                accepted.add(field["address"])
        surfaces[contract["source"]] = {
            "published": frozenset(published), "accepted": frozenset(accepted),
        }
    return surfaces


def check_wiring(
    wiring: dict[str, Any],
    ports: dict[str, dict[str, dict[str, Any]]],
    publishers: dict[str, list[dict[str, Any]]],
    migrated: set[str],
    surfaces: dict[str, dict[str, frozenset[int]]],
) -> list[str]:
    """Every failure the wiring map can carry, as one message per defect.

    `ports` comes from `port_index` over the built contracts, `publishers` is the
    `scripts` section of `data/script_protocol_headers.json`, `migrated` is the
    set of sources with a Common Stack Header v1 declaration, and `surfaces`
    comes from `stack_surfaces` over the same contracts.
    """
    failures: list[str] = []
    declared = wiring["ports"]
    if set(declared) != set(ports):
        for source in sorted(set(ports) - set(declared)):
            failures.append(f"{source}: no wiring entry for this deployable program")
        for source in sorted(set(declared) - set(ports)):
            failures.append(f"{source}: wiring entry for a program with no contract")
    for source in sorted(set(declared) & set(ports)):
        contract_ports = ports[source]
        wired_ports = declared[source]
        for name in sorted(set(contract_ports) - set(wired_ports)):
            failures.append(f"{source} {name}: device port has no declared peer")
        for name in sorted(set(wired_ports) - set(contract_ports)):
            failures.append(f"{source} {name}: declared peer for a port the program does not use")
        for name in sorted(set(wired_ports) & set(contract_ports)):
            failures.extend(check_port(source, name, wired_ports[name], contract_ports[name],
                                       ports, publishers, migrated, surfaces))
    return failures


def check_port(
    source: str,
    name: str,
    peer: dict[str, Any],
    port: dict[str, Any],
    ports: dict[str, dict[str, dict[str, Any]]],
    publishers: dict[str, list[dict[str, Any]]],
    migrated: set[str],
    surfaces: dict[str, dict[str, frozenset[int]]],
) -> list[str]:
    failures: list[str] = []
    # S0 is the only identity constraint a port can carry: the ABI is folded into the
    # hashed name, so matching the magic already matches the ABI exactly. A port that
    # pins S1 as well is rejected by validate_service_identity.py, not narrowed here.
    magic = port["constraints"].get(0)
    if port["kind"] == "physical-device" and peer["kind"] != "physical-device":
        failures.append(f"{source} {name}: contract target is {port['kind']!r}"
                        f" but wiring declares {peer['kind']!r}")
        return failures
    # The reverse direction is legitimate: a stack-shaped port may face a game
    # device with a native stack, or an IC housing hosting an arbitrary program --
    # but a port that checks a registered script magic has proven a script peer,
    # and the override away from the contract's own kind must say why.
    if peer["kind"] == "physical-device":
        if isinstance(magic, int) and any(
                entry["base"] == BASE and entry["magic"] == magic
                for entries in publishers.values() for entry in entries):
            failures.append(f"{source} {name}: declared physical-device but the port checks"
                            f" S0 magic {magic}, a registered script header")
        if port["kind"] != "physical-device" and not peer.get("note"):
            failures.append(f"{source} {name}: physical-device peer on a stack-shaped port"
                            " needs a note saying why the peer is not a script")
        return failures
    declared_reads = peer.get("header_reads", {})
    invalid = sorted(cell for cell in declared_reads
                     if not cell.isdigit() or int(cell) not in HEADER_CELLS)
    if invalid:
        failures.append(f"{source} {name}: header_reads keys {invalid} are not header"
                        f" cells S{BASE + 2}..S{BASE + LENGTH - 1}")
        declared_reads = {cell: field for cell, field in declared_reads.items()
                          if cell not in invalid}
    allowed = {int(cell) for cell in declared_reads}
    reached_reads = port["reads"] | ranged(port["read_ranges"], ENVELOPE_CELLS)
    reached_writes = port["writes"] | ranged(port["write_ranges"], ENVELOPE_CELLS)
    if isinstance(magic, int):
        expected = {path for path, entries in publishers.items() for entry in entries
                    if entry["base"] == BASE and entry["magic"] == magic}
        omitted = sorted(expected - set(peer["providers"]))
        if omitted:
            failures.append(f"{source} {name}: checks S0 magic {magic} but the providers"
                            f" list omits publisher(s) {omitted}")
        # A note is the reviewed evidence for the edge, and a port that pins the peer's
        # identity has better evidence than whatever the note was written against. Left
        # alone the note keeps citing cell-shape coincidence for an edge the source now
        # names outright, and the next reader trusts the weaker story.
        identity = next((f"{entry['contract']}.v{entry['abi']}"
                         for entries in publishers.values() for entry in entries
                         if entry["base"] == BASE and entry["magic"] == magic
                         and "contract" in entry), None)
        if identity is not None and identity not in peer["note"]:
            failures.append(f"{source} {name}: pins S0 == HASH(\"{identity}\") but the note"
                            " never says so; say which identity names the peer")
    for provider in peer["providers"]:
        if provider not in ports:
            failures.append(f"{source} {name}: provider {provider} is not a deployable program")
            continue
        headers = [entry for entry in publishers.get(provider, []) if entry["base"] == BASE]
        if isinstance(magic, int) and not any(entry["magic"] == magic for entry in headers):
            failures.append(
                f"{source} {name}: checks S0 magic {magic}"
                f" but provider {provider} does not publish it at S{BASE}")
        if provider in migrated:
            read = sorted((reached_reads & HEADER_CELLS) - allowed)
            if read:
                failures.append(
                    f"{source} {name}: reads S{read} of migrated {provider}"
                    " -- those are header cells now; relocate the read or declare"
                    " a reviewed header_reads entry")
            written = sorted(reached_writes & ENVELOPE_CELLS)
            if written:
                failures.append(
                    f"{source} {name}: writes S{written} of migrated {provider}"
                    " -- only the owner may publish envelope cells")
    unused = allowed - reached_reads
    if unused:
        failures.append(f"{source} {name}: header_reads declares S{sorted(unused)}"
                        " which the port never reads")
    failures.extend(surface_failures(source, name, peer, port, surfaces))
    return failures


def surface_failures(
    source: str,
    name: str,
    peer: dict[str, Any],
    port: dict[str, Any],
    surfaces: dict[str, dict[str, frozenset[int]]],
) -> list[str]:
    """Compare what the port touches against what its declared peers offer.

    This is the check a declared dynamic range would otherwise escape: the
    protocol registry only compares a range where a consumer edge is declared,
    which is fewer than half the ports that carry one. The wiring map names a
    peer for every port, so the comparison can be total. Providers are any-of --
    a deployment wires one of them -- so a port passes on the first peer that
    offers everything it touches, and a port that matches none reports each.
    """
    wanted_reads = port["reads"] | ranged(port["read_ranges"], STACK_CELLS)
    wanted_writes = port["writes"] | ranged(port["write_ranges"], STACK_CELLS)
    unmatched: list[tuple[str, list[int], list[int]]] = []
    for provider in peer["providers"]:
        surface = surfaces.get(provider)
        if surface is None:
            continue
        unpublished = sorted(wanted_reads - surface["published"])
        unaccepted = sorted(wanted_writes - surface["accepted"])
        if not unpublished and not unaccepted:
            return []
        unmatched.append((provider, unpublished, unaccepted))
    failures: list[str] = []
    for provider, unpublished, unaccepted in unmatched:
        if unpublished:
            failures.append(
                f"{source} {name}: reads S{unpublished} of {provider} -- the provider"
                " neither writes those cells nor declares them externally readable")
        if unaccepted:
            failures.append(
                f"{source} {name}: writes S{unaccepted} of {provider} -- the provider"
                " neither reads those cells nor declares them externally writable")
    return failures


def inbound_edges(
    wiring: dict[str, Any],
    ports: dict[str, dict[str, dict[str, Any]]],
    family: set[str],
) -> list[dict[str, Any]]:
    """Every declared edge into `family`: who reads or writes a member, and where."""
    edges: list[dict[str, Any]] = []
    for source in sorted(wiring["ports"]):
        for name in sorted(wiring["ports"][source]):
            peer = wiring["ports"][source][name]
            if peer["kind"] != "script":
                continue
            targets = sorted(set(peer["providers"]) & family)
            if not targets:
                continue
            port = ports.get(source, {}).get(name, {})
            edges.append({
                "consumer": source,
                "port": name,
                "targets": targets,
                "reads": sorted(port.get("reads", ())),
                "writes": sorted(port.get("writes", ())),
                "read_ranges": sorted(port.get("read_ranges", ())),
                "write_ranges": sorted(port.get("write_ranges", ())),
                "header_reads": {int(cell): field
                                 for cell, field in peer.get("header_reads", {}).items()
                                 if cell.isdigit()},
            })
    return edges


# --- Mailbox arbitration -------------------------------------------------------
#
# A request/response mailbox on one program instance has room for one request:
# the caller writes its payload and then the token, and the callee answers the
# token it finds. Two callers posting to the same instance with no ordering
# between them can displace each other before the callee latches the request,
# which strands the displaced caller forever (it waits for a response token that
# was never served) or, when a post straddles a tick, hands the callee a payload
# assembled from both. `ASYNC_REQUEST_V1` fences observation of a response; it
# does not serialize requests. So every mailbox with more than one writer
# program needs an arbitration the tree can name, and
# `data/mailbox_arbitration.json` is where that review lives. What the map can
# derive on its own is *laned* sharing: writers whose write cells never overlap
# post into separate request lanes the callee serves one at a time, as the Job
# Command Gateway does.

ARBITRATION_FORMAT = "IC10_MAILBOX_ARBITRATION_V1"
RESIDENT_CLASSES = frozenset({"resident", "conditional-resident"})
REGISTER_PORT_RE = re.compile(r"\bdr(?:[0-9]|1[0-5])\b")


def load_arbitration(root: Path) -> dict[str, Any]:
    root = Path(root)
    value = json.loads((root / "data/mailbox_arbitration.json").read_text())
    schema = json.loads((root / "schemas/mailbox_arbitration.schema.json").read_text())
    validate(value, schema)
    return value


def writer_edges(
    wiring: dict[str, Any],
    ports: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, set[int]]]]:
    """Per provider: every program whose declared port writes it, with the cells touched.

    A port that only reads a peer consumes a publication; the mailboxes this is
    about are the cells a port *writes*. Providers are any-of, so a writer is
    recorded against every provider its port may face.
    """
    edges: dict[str, dict[str, dict[str, set[int]]]] = {}
    for source, entries in wiring["ports"].items():
        for name, peer in entries.items():
            if peer["kind"] != "script":
                continue
            port = ports.get(source, {}).get(name)
            if port is None:
                continue
            writes = set(port["writes"]) | ranged(port["write_ranges"], STACK_CELLS)
            if not writes:
                continue
            reads = set(port["reads"]) | ranged(port["read_ranges"], STACK_CELLS)
            for provider in peer["providers"]:
                slot = edges.setdefault(provider, {}).setdefault(
                    source, {"writes": set(), "reads": set()})
                slot["writes"] |= writes
                slot["reads"] |= reads
    return edges


def contended_pairs(writers: dict[str, dict[str, set[int]]]) -> list[tuple[str, str]]:
    """Writer pairs whose write cells overlap; none among several writers means laned."""
    names = sorted(writers)
    return [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
            if writers[a]["writes"] & writers[b]["writes"]]


def downstream(edges: dict[str, dict[str, dict[str, set[int]]]]) -> dict[str, set[str]]:
    """Per program: the providers whose mailboxes it writes."""
    out: dict[str, set[str]] = {}
    for provider, sources in edges.items():
        for source in sources:
            out.setdefault(source, set()).add(provider)
    return out


def reachable(edges: dict[str, dict[str, dict[str, set[int]]]], origins: Iterable[str]) -> set[str]:
    """Programs reached from `origins` by following mailbox writes downstream."""
    out = downstream(edges)
    seen = set(origins)
    todo = list(seen)
    while todo:
        current = todo.pop()
        for nxt in out.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def dedicated_closure(
    edges: dict[str, dict[str, dict[str, set[int]]]],
    declarations: dict[str, Any],
    provider: str,
) -> set[str]:
    """The mailboxes a dedicated instance of `provider` brings with it.

    An instance kept apart from another call tree must keep the request
    mailboxes it reaches downstream apart too, or the sharing moves one hop.
    The walk stops at `reselect` surfaces: a selected snapshot whose consumers
    read nothing until the selection echoes back tolerates any number of
    selectors, so it needs no instance of its own.
    """
    reselect = {p for p, d in declarations.items() if d["arbitration"] == "reselect"}
    out = downstream(edges)
    seen = {provider}
    todo = [provider]
    while todo:
        current = todo.pop()
        for nxt in out.get(current, ()):
            if nxt in reselect or nxt in seen:
                continue
            seen.add(nxt)
            todo.append(nxt)
    return seen


def _serial_failures(
    provider: str,
    label: str,
    group: list[str],
    root: str | None,
    unmapped: list[str],
    edges: dict[str, dict[str, dict[str, set[int]]]],
    wiring: dict[str, Any],
    source: Callable[[str], str],
) -> list[str]:
    """A serial group is one call tree: every writer posts only while the root waits on it.

    The map proves the shape -- each writer sits downstream of the root through
    declared mailbox writes -- and the review vouches for the blocking. A
    register-indexed port (`dr<n>`) has no `d<n>` for the map to key on, so a
    writer reached that way is listed under `unmapped`; the only check the tree
    can make of that claim is that the root does address a device by register.
    """
    failures: list[str] = []
    if root is None:
        failures.append(f"{provider}: {label} has {len(group)} writers and names no serialized_by")
        return failures
    if root not in wiring["ports"]:
        failures.append(f"{provider}: {label} serialized_by {root} is not a deployable program")
        return failures
    stray = sorted(set(unmapped) - set(group))
    if stray:
        failures.append(f"{provider}: {label} lists unmapped programs that are not writers: {stray}")
    if unmapped and not REGISTER_PORT_RE.search(source(root)):
        failures.append(
            f"{provider}: {label} claims {root} reaches {sorted(unmapped)} through a"
            " register-indexed port, but its source has no dr<n> operand")
    reached = reachable(edges, [root, *unmapped])
    missing = sorted(w for w in group if w not in reached)
    if missing:
        failures.append(
            f"{provider}: {label} serialized_by {root} does not reach {missing} through"
            " declared mailbox writes -- they post from an independent loop")
    return failures


def arbitration_failures(
    wiring: dict[str, Any],
    ports: dict[str, dict[str, dict[str, Any]]],
    declarations: dict[str, Any],
    classes: dict[str, str],
    source: Callable[[str], str],
) -> list[str]:
    """Every defect in the reviewed mailbox arbitration, one message each.

    `declarations` is the `mailboxes` section of `data/mailbox_arbitration.json`,
    `classes` maps each deployable program to its deployment class, and
    `source(path)` returns a program's or document's text.
    """
    failures: list[str] = []
    edges = writer_edges(wiring, ports)
    contended = {p for p, w in edges.items() if len(w) > 1 and contended_pairs(w)}
    for provider in sorted(contended - set(declarations)):
        writers = sorted(edges[provider])
        failures.append(
            f"{provider}: {len(writers)} programs write overlapping request cells"
            f" ({writers}) and data/mailbox_arbitration.json does not say what keeps"
            " them from posting at once")
    for provider, entry in sorted(declarations.items()):
        kind = entry["arbitration"]
        if provider not in wiring["ports"]:
            failures.append(f"{provider}: arbitration declared for a program with no wiring entry")
            continue
        writers = sorted(edges.get(provider, {}))
        if provider not in contended and kind != "reselect":
            why = "one writer" if len(writers) < 2 else "laned writers (write cells never overlap)"
            failures.append(f"{provider}: arbitration declared for a mailbox with {why}; remove it")
            continue
        declared = sorted(entry["writers"])
        if declared != writers:
            failures.append(
                f"{provider}: declared writers {declared} differ from the wiring map's {writers}")
            continue
        shape = {"serial": {"serialized_by", "unmapped"}, "dedicated": {"instances"}}.get(kind, set())
        stray = sorted({"serialized_by", "unmapped", "instances"} & set(entry) - shape)
        if stray:
            failures.append(f"{provider}: {kind} arbitration does not take {stray}")
            continue
        if kind == "dedicated" and "instances" not in entry:
            failures.append(f"{provider}: dedicated arbitration names no instances")
            continue
        if kind == "serial":
            failures.extend(_serial_failures(
                provider, "serial group", writers, entry.get("serialized_by"),
                entry.get("unmapped", []), edges, wiring, source))
        elif kind == "dedicated":
            claimed: list[str] = []
            closure = sorted(dedicated_closure(edges, declarations, provider))
            for index, instance in enumerate(entry["instances"]):
                label = f"instance {index + 1}"
                group = sorted(instance["writers"])
                repeated = sorted(set(group) & set(claimed))
                if repeated:
                    failures.append(f"{provider}: {label} repeats writers {repeated}")
                claimed.extend(group)
                if len(group) > 1:
                    failures.extend(_serial_failures(
                        provider, label, group, instance.get("serialized_by"),
                        instance.get("unmapped", []), edges, wiring, source))
                doc = instance["documented_in"]
                text = source(doc)
                unnamed = [item for item in closure if item not in text]
                if unnamed:
                    failures.append(
                        f"{provider}: {label} is documented in {doc}, which does not name"
                        f" {unnamed} -- a dedicated instance brings every request mailbox"
                        " it reaches, and the deployment text has to list them")
            left = sorted(set(writers) - set(claimed))
            if left:
                failures.append(f"{provider}: no instance claims writers {left}")
        elif kind == "operator":
            resident = sorted(w for w in writers if classes.get(w, "resident") in RESIDENT_CLASSES)
            if len(resident) > 1:
                failures.append(
                    f"{provider}: operator arbitration with {len(resident)} resident writers"
                    f" {resident}; only tools an operator runs one at a time qualify")
    return failures
