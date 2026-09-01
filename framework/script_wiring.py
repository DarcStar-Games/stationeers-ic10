"""Validate the canonical device-port wiring map against the script contracts.

`data/script_wiring.json` declares, for every device port of every deployable
program, which program(s) the port is intended to point at — or that the port
faces a physical game device. The map names *identity* only: it does not
authorize movement, establish durability, or fence observation. Its purpose is
to make the wiring checkable, so that relocating a peer's payload cells cannot
silently strand a consumer that still reads the old address.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

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
    The reviewed `external_readable_ranges`/`external_writable_ranges` cover what
    derivation cannot see: a mailbox one peer posts and a *different* peer
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
