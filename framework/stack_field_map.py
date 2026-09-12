"""Reviewed field map: a name and a role for every payload cell a peer reads or writes.

The contracts record which cells a program touches; this module records what those
cells mean, per stack protocol, from the reviewed ``layout`` lists in
``data/script_contract_protocol_definitions.json`` (issue #190). A layout entry names
one cell or one contiguous range and gives it a role from a small vocabulary, so a
report can put every service's RequestToken side by side. The generator copies the
layout into each provider's contract fields and into the protocol document; the
validator holds every entry to the provider's surface, every peer-touched payload
cell to an entry, and every attributable layout block in ``docs/ABI_REFERENCE.md``
to the map.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any


DEFINITIONS_FILE = "data/script_contract_protocol_definitions.json"
DEFINITIONS_FORMAT = "IC10_PROTOCOL_DEFINITIONS_V1"
FIELD_MAP_DOC = "docs/STACK_FIELD_MAP.md"
ABI_REFERENCE_DOC = "docs/ABI_REFERENCE.md"
LAYOUT_SEMANTIC_SOURCE = "protocol-layout"
COMMON_HEADER_LENGTH = 8
BLOCK_HEADER_LENGTH = 2

# One role per kind of cell the four cross-cutting standards and the directory and
# catalog ABIs share. A role says what a peer does with the cell, not what the value
# is, so two services that keep their RequestToken at different offsets still compare.
ROLES: dict[str, str] = {
    "metadata": "static published configuration or capability: width, capacity, unit, class, limit",
    "schema": "schema identity, version, or signature published outside the common header",
    "request": "request payload a caller writes before its token",
    "request_token": "request identity a caller writes last",
    "current_token": "LIVE_CURRENT accepted-request identity the service publishes",
    "response_token": "TERMINAL_RESPONSE handled-request identity the service publishes last",
    "state": "status, state, or mode of the service or of the current request",
    "error": "error or fault detail kept apart from the state cell",
    "result": "response payload the service publishes before its token",
    "generation": "publication generation, odd/even sequence, or revision that fences observation",
    "epoch": "epoch, lease, or ownership value that authorizes mutation",
    "bank": "A/B bank select and the per-bank generation, count, and overflow cells",
    "topology": "ReferenceId of a peer service or device, or a chain link between peers",
    "table": "record array, slot table, image, heap, or descriptor pool",
    "telemetry": "observational channel for operators and monitors",
    "reserved": "held cell that nothing interprets",
}
TOKEN_ROLES = frozenset({"request_token", "current_token", "response_token"})
CELLS_RE = re.compile(r"^S(\d{1,3})(?:\.\.S(\d{1,3}))?$")
NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
VALUE_TYPES = frozenset({"number", "integer", "enum", "hash", "reference-id", "boolean"})
ENTRY_KEYS = frozenset({"cells", "name", "role", "description", "value_type"})
_DOC_MAGIC_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*)\.v(\d+)\b")
_DOC_CELL_RE = re.compile(r"^S(\d{1,3})(?:(\.\.|/)S?(\d{1,3}))?(?:\.\.)?(?=\s|$)")
_DOC_TABLE_ROW_RE = re.compile(r"^\s*\|\s*(S\d{1,3}(?:(?:\.\.|/)S?\d{1,3})?(?:\.\.)?)\s*\|(.*)$")
DOC_GLOB = "docs/*.md"


@dataclass(frozen=True)
class LayoutEntry:
    start: int
    end: int
    name: str
    role: str
    description: str | None = None
    value_type: str | None = None

    @property
    def cells(self) -> str:
        return format_cells(self.start, self.end)

    def covers(self, cell: int) -> bool:
        return self.start <= cell <= self.end

    @property
    def is_range(self) -> bool:
        return self.end > self.start

    def field_name(self, cell: int) -> str:
        """The contract field name at one cell: the entry's name, indexed inside a range."""
        return f"{self.name}[{cell - self.start}]" if self.is_range else self.name

    def document(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "cells": self.cells, "start": self.start, "end": self.end,
            "name": self.name, "role": self.role,
        }
        if self.description:
            item["description"] = self.description
        if self.value_type:
            item["value_type"] = self.value_type
        return item


@dataclass(frozen=True)
class DocLayoutBlock:
    """One layout block in a document that names its protocol on an S0 line."""

    protocol_id: str
    line: int
    cells: tuple[tuple[int, int, int], ...]  # (start, end, line)


def parse_cells(spec: Any) -> tuple[int, int]:
    """``S10`` names one cell, ``S32..S415`` an inclusive range."""
    if not isinstance(spec, str):
        raise ValueError(f"cells must be a string like S10 or S32..S415: {spec!r}")
    match = CELLS_RE.fullmatch(spec)
    if match is None:
        raise ValueError(f"cells must be written S<n> or S<n>..S<m>: {spec!r}")
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) is not None else start
    if not 0 <= start <= end <= 511:
        raise ValueError(f"cells must lie in S0..S511 with start <= end: {spec!r}")
    return start, end


def format_cells(start: int, end: int) -> str:
    return f"S{start}" if start == end else f"S{start}..S{end}"


def normalize_layout(pid: str, value: Any) -> tuple[list[LayoutEntry], list[str]]:
    """Check one protocol's layout list for shape and return its entries."""
    errors: list[str] = []
    entries: list[LayoutEntry] = []
    if not isinstance(value, list):
        return [], [f"{pid}: layout must be a list of entries"]
    for index, item in enumerate(value):
        where = f"{pid} layout[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: entry must be an object")
            continue
        unknown = sorted(set(item) - ENTRY_KEYS)
        if unknown:
            errors.append(f"{where}: unknown keys {unknown}")
        try:
            start, end = parse_cells(item.get("cells"))
        except ValueError as error:
            errors.append(f"{where}: {error}")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            errors.append(f"{where}: name must be CamelCase starting with a capital: {name!r}")
            continue
        role = item.get("role")
        if role not in ROLES:
            errors.append(f"{where}: role {role!r} is not one of {sorted(ROLES)}")
            continue
        description = item.get("description")
        if description is not None and (not isinstance(description, str) or not description.strip()):
            errors.append(f"{where}: description must be a non-empty string when present")
            continue
        declared_type = item.get("value_type")
        if declared_type is not None and declared_type not in VALUE_TYPES:
            errors.append(f"{where}: value_type {declared_type!r} is not one of {sorted(VALUE_TYPES)}")
            continue
        entries.append(LayoutEntry(start, end, name, role, description, declared_type))
    # Entries must not overlap and names must be unique within the protocol, so a cell
    # answers to one name and a name answers to one cell or range.
    ordered = sorted(entries, key=lambda entry: entry.start)
    for previous, current in zip(ordered, ordered[1:]):
        if current.start <= previous.end:
            errors.append(f"{pid}: {previous.name} {previous.cells} overlaps {current.name} {current.cells}")
    seen: dict[str, LayoutEntry] = {}
    for entry in entries:
        if entry.name in seen:
            errors.append(f"{pid}: name {entry.name} is used at {seen[entry.name].cells} and {entry.cells}")
        seen.setdefault(entry.name, entry)
    return ordered, errors


def load_definitions(root: Path) -> dict[str, Any]:
    data = json.loads((Path(root) / DEFINITIONS_FILE).read_text())
    if data.get("format") != DEFINITIONS_FORMAT:
        raise ValueError("unsupported script contract protocol definition format")
    return data


def layouts_from_definitions(protocols: dict[str, Any]) -> tuple[dict[str, list[LayoutEntry]], list[str]]:
    layouts: dict[str, list[LayoutEntry]] = {}
    errors: list[str] = []
    for pid, definition in protocols.items():
        if not isinstance(definition, dict) or "layout" not in definition:
            continue
        entries, shape_errors = normalize_layout(pid, definition["layout"])
        errors.extend(shape_errors)
        layouts[pid] = entries
    return layouts, errors


def load_layouts(root: Path) -> dict[str, list[LayoutEntry]]:
    """The reviewed layouts, or a ValueError naming every shape problem."""
    layouts, errors = layouts_from_definitions(load_definitions(root).get("protocols", {}))
    if errors:
        raise ValueError("; ".join(errors))
    return layouts


def layout_documents(entries: list[LayoutEntry]) -> list[dict[str, Any]]:
    return [entry.document() for entry in entries]


def entry_for(entries: list[LayoutEntry], cell: int) -> LayoutEntry | None:
    for entry in entries:
        if entry.covers(cell):
            return entry
    return None


def header_cells(base: int) -> set[int]:
    """The header window a layout never names: the common S0..S7, or a block's magic and version."""
    if base == 0:
        return set(range(0, COMMON_HEADER_LENGTH))
    return set(range(base, base + BLOCK_HEADER_LENGTH))


def _range_cells(ranges: list[dict[str, int]]) -> set[int]:
    cells: set[int] = set()
    for item in ranges:
        cells.update(range(item["start"], item["end"] + 1))
    return cells


WIRING_FILE = "data/script_wiring.json"
DERIVED_RANGE_SOURCES = ("source-derived", "source-fingerprinted-exception")


def _access_cells(access: dict[str, Any]) -> set[int]:
    """Literal cells plus dynamic ranges whose provenance is a derivation or a reviewed exception.

    A conservative whole-stack fallback names nothing a layout should answer for.
    """
    cells = set(access["literal_reads"]) | set(access["literal_writes"])
    for direction in ("read", "write"):
        if access[f"dynamic_{direction}_range_source"] in DERIVED_RANGE_SOURCES:
            cells |= _range_cells(access[f"dynamic_{direction}_ranges"])
    return cells


def peer_touched_cells(
    definition: dict[str, Any], extra: dict[str, dict[int, set[str]]] | None = None,
) -> dict[int, set[str]]:
    """Payload cells the protocol's peers read or write, with the peers that touch each.

    The contract's consumer interfaces are the first source; ``extra`` carries the cells
    the wiring map's declared peers reach (``wiring_touched_cells``), for a port that
    names its peer in the wiring without a consumer edge the contracts can prove.
    """
    touched: dict[int, set[str]] = {}
    for interface in definition.get("consumer_interfaces", []):
        excluded = header_cells(interface["header_base"])
        for cell in _access_cells(interface) - excluded:
            touched.setdefault(cell, set()).add(interface["source"])
    for cell, sources in (extra or {}).get(definition.get("protocol_id", ""), {}).items():
        touched.setdefault(cell, set()).update(sources)
    return touched


def declared_peer_cells(root: Path, contracts_by_source: dict[str, dict[str, Any]]) -> dict[str, dict[int, set[str]]]:
    """Payload cells peers reach without a contract consumer edge: wired ports and attributed network accesses.

    ``data/script_wiring.json`` names every port's canonical peer program. A port whose
    peer is a script reaches that script's protocols with whatever it reads or writes, even
    when the contracts record no consumer edge for the port (no literal S0 check on that
    path). A ``putd`` through a ReferenceId is attributed by the network provenance walk to
    the contract it targets (issue #174), so its cells reach that contract's protocol the
    same way. Both belong in the map and in the report's peer count.
    """
    from framework.script_contracts.naming import protocol_id
    wiring = json.loads((Path(root) / WIRING_FILE).read_text())
    provided: dict[str, list[tuple[str, int]]] = {}
    providers_of: dict[str, set[str]] = {}
    for source, contract in contracts_by_source.items():
        provided[source] = sorted((
            (protocol_id(header["magic"], header["abi"], header.get("contract")), header["base"])
            for header in contract["own_stack"]["headers"]
        ), key=lambda item: item[1])
        for header in contract["own_stack"]["headers"]:
            if header.get("contract"):
                providers_of.setdefault(header["contract"], set()).add(source)
    touched: dict[str, dict[int, set[str]]] = {}

    def attribute(cells: set[int], provider: str, peer: str) -> None:
        # A program publishing a service header at S0 and a telemetry block at S96 owns
        # two protocols; a cell belongs to the one whose header sits at or below it.
        headers = provided.get(provider, [])
        for cell in cells:
            pid, base = next((item for item in reversed(headers) if item[1] <= cell), headers[0])
            if cell not in header_cells(base):
                touched.setdefault(pid, {}).setdefault(cell, set()).add(peer)

    # A target is a contract name for a base-0 header, or the protocol id itself for a
    # numeric block header (the Generic Telemetry block has no contract name).
    for source, headers in provided.items():
        for pid, _base in headers:
            providers_of.setdefault(pid, set()).add(source)
    for source, contract in contracts_by_source.items():
        for dependency in contract["network_dependencies"]:
            # Each access site names the cell it reaches and the targets its reference was
            # established as at that site; a site whose cell is computed reaches no literal
            # cell the map could name.
            if "site_targets" in dependency:
                for site in dependency["site_targets"]:
                    if isinstance(site["cell"], int):
                        for target in site["targets"]:
                            for provider in providers_of.get(target, ()):
                                attribute({site["cell"]}, provider, source)
                continue
            cells = set(dependency.get("literal_reads", [])) | set(dependency.get("literal_writes", []))
            for target in dependency.get("targets", []):
                for provider in providers_of.get(target, ()):
                    attribute(cells, provider, source)
    for source, ports in wiring.get("ports", {}).items():
        contract = contracts_by_source.get(source)
        if contract is None:
            continue
        access_by_port = {port["port"]: port["stack"] for port in contract["device_ports"]}
        for port, peer in ports.items():
            if peer.get("kind") != "script" or port not in access_by_port:
                continue
            cells = _access_cells(access_by_port[port])
            for provider in peer.get("providers", []):
                if provided.get(provider):
                    attribute(cells, provider, source)
    return touched


# The earlier name; the function now also collects attributed network accesses.
wiring_touched_cells = declared_peer_cells


def provider_surface(contract: dict[str, Any]) -> set[int]:
    """Every cell the provider touches, declares dynamic, or declares externally reachable."""
    own = contract["own_stack"]
    return (
        set(own["literal_reads"]) | set(own["literal_writes"])
        | {field["address"] for field in own["fields"]}
        | _range_cells(own["dynamic_read_ranges"]) | _range_cells(own["dynamic_write_ranges"])
        | _range_cells(own["external_readable_ranges"]) | _range_cells(own["external_writable_ranges"])
    )


def documented_cells(text: str) -> dict[str, set[int]]:
    """Cells each attributable layout block in a document cites, by protocol."""
    cited: dict[str, set[int]] = {}
    for block in doc_layout_blocks(text):
        for start, end, _ in block.cells:
            cited.setdefault(block.protocol_id, set()).update(range(start, end + 1))
    return cited


def layout_documents_in(root: Path) -> dict[str, str]:
    """Every markdown document under docs/ that may hold a layout block, by relative path.

    The generated field map is excluded: it is rendered from the layouts, so holding the
    layouts to it would prove nothing.
    """
    from framework.scan_coverage import require_nonempty_glob
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): path.read_text()
        for path in require_nonempty_glob(root / "docs", "*.md")
        if path.relative_to(root).as_posix() != FIELD_MAP_DOC
    }


def all_documented_cells(documents: dict[str, str]) -> dict[str, set[int]]:
    merged: dict[str, set[int]] = {}
    for text in documents.values():
        for pid, cells in documented_cells(text).items():
            merged.setdefault(pid, set()).update(cells)
    return merged


def all_doc_layout_errors(documents: dict[str, str], layouts: dict[str, list[LayoutEntry]]) -> list[str]:
    errors: list[str] = []
    for name in sorted(documents):
        errors.extend(doc_layout_errors(documents[name], layouts, name))
    return errors


def layout_errors(
    protocol_definitions: dict[str, dict[str, Any]],
    contracts_by_source: dict[str, dict[str, Any]],
    layouts: dict[str, list[LayoutEntry]],
    extra_touched: dict[str, dict[int, set[str]]] | None = None,
    documented: dict[str, set[int]] | None = None,
) -> list[str]:
    """Hold the map to the tree: entries inside the surface, peer cells named, overrides agreed.

    With ``documented`` (``all_documented_cells`` of the documents under docs/), every entry
    must also cover a cell a peer touches or a documented layout cites. The map describes
    the peer-visible surface; a cell only its provider reads and writes has nothing outside
    the program to hold its name to, so it is not mapped. A provider's own external range
    does not ground a name: it says peers may reach the cells, not what any of them means.
    """
    errors: list[str] = []
    definitions_by_pid = {definition["protocol_id"]: definition for definition in protocol_definitions.values()}
    for pid in sorted(layouts):
        if pid not in definitions_by_pid:
            errors.append(f"{pid}: layout declared for a protocol nothing provides or consumes")
    for pid, definition in sorted(definitions_by_pid.items()):
        entries = layouts.get(pid)
        touched = peer_touched_cells(definition, extra_touched)
        if entries is None:
            if touched:
                cells = format_cell_set(set(touched))
                errors.append(
                    f"{pid}: peers read or write {cells} but the protocol has no layout in "
                    f"{DEFINITIONS_FILE}")
            continue
        providers = [contracts_by_source[item["source"]] for item in definition["provider_interfaces"]
                     if item["source"] in contracts_by_source]
        surface: set[int] = set(touched)
        for provider in providers:
            surface |= provider_surface(provider)
        bases = {item["header_base"] for item in definition["provider_interfaces"]} or {0}
        header = set()
        for base in bases:
            header |= header_cells(base)
        for entry in entries:
            named = set(range(entry.start, entry.end + 1))
            inside_header = sorted(named & header)
            if inside_header:
                errors.append(
                    f"{pid}: {entry.name} {entry.cells} names header cell(s) "
                    f"{format_cell_set(set(inside_header))}; the header is declared, not mapped")
            outside = named - surface
            if outside:
                errors.append(
                    f"{pid}: {entry.name} {entry.cells} names {format_cell_set(outside)}, which no "
                    "provider touches or declares and no peer reaches")
        if documented is not None:
            visible = set(touched) | documented.get(pid, set())
            for entry in entries:
                if not any(entry.covers(cell) for cell in visible):
                    errors.append(
                        f"{pid}: {entry.name} {entry.cells} names only cells the provider keeps to itself; "
                        "the map covers cells a peer reads or writes or a documented layout cites")
        uncovered = {cell for cell in touched if entry_for(entries, cell) is None}
        if uncovered:
            by_cell = ", ".join(
                f"S{cell} ({', '.join(sorted(Path(source).stem for source in touched[cell]))})"
                for cell in sorted(uncovered))
            errors.append(f"{pid}: peer-touched payload cell(s) have no layout entry: {by_cell}")
        for provider in providers:
            for field in provider["own_stack"]["fields"]:
                if field.get("semantic_source") != "override":
                    continue
                entry = entry_for(entries, field["address"])
                if entry is None:
                    continue
                if entry.is_range:
                    errors.append(
                        f"{pid}: {provider['source']} override names S{field['address']} {field['name']} "
                        f"inside the range entry {entry.name} {entry.cells}; split the range so the cell "
                        "has its own entry")
                elif entry.name != field["name"]:
                    errors.append(
                        f"{pid}: {provider['source']} override names S{field['address']} "
                        f"{field['name']} but the layout names it {entry.name}")
    return errors


def format_cell_set(cells: set[int]) -> str:
    """Name a cell set as S<n> and S<n>..S<m> runs."""
    ordered = sorted(cells)
    runs: list[str] = []
    index = 0
    while index < len(ordered):
        start = end = ordered[index]
        while index + 1 < len(ordered) and ordered[index + 1] == end + 1:
            index += 1
            end = ordered[index]
        runs.append(format_cells(start, end))
        index += 1
    return ", ".join(runs)


def apply_layout(own_stack: dict[str, Any], layouts: dict[str, list[LayoutEntry]]) -> None:
    """Name the provider's own fields from the layouts of the protocols its headers publish.

    A source comment or an unresolved field yields to the reviewed layout; a reviewed
    per-program override keeps its name and gains the role, and the validator reports
    the two when they disagree. Header fields are the header's own.
    """
    # Imported here: this module is a dependency of the contract package, so a
    # module-level import of that package would be circular.
    from framework.script_contracts.naming import protocol_id
    from framework.script_contracts.publication import value_type
    for header in own_stack["headers"]:
        entries = layouts.get(protocol_id(header["magic"], header["abi"], header.get("contract")))
        if not entries:
            continue
        for field in own_stack["fields"]:
            entry = entry_for(entries, field["address"])
            if entry is None or field["semantic_source"] == "protocol-header":
                continue
            if field["semantic_source"] == "override":
                field["role"] = entry.role
                continue
            field["name"] = entry.field_name(field["address"])
            field["role"] = entry.role
            field["semantic_source"] = LAYOUT_SEMANTIC_SOURCE
            if entry.description and "description" not in field:
                field["description"] = entry.description
            field["value_type"] = entry.value_type or value_type(entry.name, field.get("description", ""))


def payload_fields(contract: dict[str, Any], layouts: dict[str, list[LayoutEntry]]) -> list[dict[str, Any]]:
    """The inventory's view of one service: every layout entry of every protocol it provides."""
    from framework.script_contracts.naming import protocol_id
    items: list[dict[str, Any]] = []
    for header in contract["own_stack"]["headers"]:
        pid = protocol_id(header["magic"], header["abi"], header.get("contract"))
        for entry in layouts.get(pid, []):
            items.append({"protocol_id": pid, "cells": entry.cells, "name": entry.name, "role": entry.role})
    return items


def _kebab(contract: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", contract).lower()


def _layout_line(line: str, inside_fence: bool) -> re.Match[str] | None:
    """A cell line: ``S<n> ...`` inside a fence, or a ``| S<n> | ... |`` markdown table row anywhere."""
    if inside_fence:
        return _DOC_CELL_RE.match(line)
    row = _DOC_TABLE_ROW_RE.match(line)
    if row is None:
        return None
    return _DOC_CELL_RE.match(f"{row.group(1)} {row.group(2)}")


def doc_layout_blocks(text: str) -> list[DocLayoutBlock]:
    """Layout blocks whose S0 line names the contract, with every cell line each cites.

    A layout line is ``S<n> ...`` inside a fenced block or a ``| S<n> | ... |`` table row.
    A pipe line indented four or more spaces is an indented code block, not the start of
    a table; inside a running table it is a row, since a code block cannot interrupt one.
    An ``S0`` line carrying ``<Contract>.v<abi>`` opens a block that runs to the next such
    line, the end of the fence, or the end of the table, so one fence holding two
    services attributes each cell line to its own service. Cell lines before the first
    S0 line, and blocks whose S0 line names no contract (the numeric telemetry block),
    are not held.
    """
    blocks: list[DocLayoutBlock] = []
    inside = False
    in_table = False
    current: DocLayoutBlock | None = None
    cited: list[tuple[int, int, int]] = []

    def close() -> None:
        nonlocal current, cited
        if current is not None and cited:
            blocks.append(DocLayoutBlock(current.protocol_id, current.line, tuple(cited)))
        current = None
        cited = []

    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            close()
            inside = not inside
            continue
        if not inside:
            stripped = line.lstrip(" \t")
            is_row = stripped.startswith("|") and (in_table or len(line) - len(stripped) < 4)
            if in_table and not is_row:
                close()
            in_table = is_row
            if not is_row:
                continue
        match = _layout_line(line, inside)
        if match is None:
            continue
        start = int(match.group(1))
        end = int(match.group(3)) if match.group(3) is not None else start
        if start == 0:
            magic = _DOC_MAGIC_RE.search(line)
            if magic is not None:
                close()
                current = DocLayoutBlock(f"ic10.stack.{_kebab(magic.group(1))}.v{magic.group(2)}", number, ())
        if current is None:
            continue
        if match.group(2) == "/":
            # ``S25/S26`` names two cells, not a range.
            cited.append((start, start, number))
            cited.append((end, end, number))
        else:
            cited.append((start, max(start, end), number))
    close()
    return blocks


def doc_layout_errors(text: str, layouts: dict[str, list[LayoutEntry]], document: str = ABI_REFERENCE_DOC) -> list[str]:
    """Every cell an attributable doc block cites must be a header cell or covered by the map."""
    errors: list[str] = []
    for block in doc_layout_blocks(text):
        entries = layouts.get(block.protocol_id)
        if entries is None:
            errors.append(
                f"{document}:{block.line}: layout block for {block.protocol_id} but the protocol has no "
                f"layout in {DEFINITIONS_FILE}")
            continue
        header = header_cells(0)
        for start, end, line in block.cells:
            missing = {cell for cell in range(start, end + 1) if cell not in header and entry_for(entries, cell) is None}
            if missing:
                errors.append(
                    f"{document}:{line}: {block.protocol_id} cites {format_cells(start, end)} but the layout "
                    f"does not name {format_cell_set(missing)}")
    return errors


def grounding(entry: LayoutEntry, touched: dict[int, set[str]], documented: set[int]) -> str:
    """What holds the entry's name: a peer, a document, both, or (when unchecked) nothing."""
    cells = range(entry.start, entry.end + 1)
    by_peer = any(cell in touched for cell in cells)
    by_document = any(cell in documented for cell in cells)
    if by_peer and by_document:
        return "peer, document"
    if by_peer:
        return "peer"
    if by_document:
        return "document"
    return "none"


def fields_by_role(
    layouts: dict[str, list[LayoutEntry]], protocol_definitions: dict[str, dict[str, Any]],
    extra_touched: dict[str, dict[int, set[str]]] | None = None,
    documented: dict[str, set[int]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """The alignment review's input: for each role, every protocol's cells and its fan-in.

    ``consumers`` counts programs with a contract consumer edge; ``peers_touching`` counts
    every program that reads or writes the entry's cells, declared peers included;
    ``grounding`` says whether a peer, a document, or both hold the entry's name.
    """
    definitions_by_pid = {definition["protocol_id"]: definition for definition in protocol_definitions.values()}
    report: dict[str, list[dict[str, Any]]] = {role: [] for role in ROLES}
    for pid in sorted(layouts):
        definition = definitions_by_pid.get(pid, {})
        touched = peer_touched_cells(definition, extra_touched) if definition else {}
        consumers = {item["source"] for item in definition.get("consumer_interfaces", [])}
        providers = [item["source"] for item in definition.get("provider_interfaces", [])]
        for entry in layouts[pid]:
            readers_writers = set()
            for cell in range(entry.start, entry.end + 1):
                readers_writers |= touched.get(cell, set())
            report[entry.role].append({
                "protocol_id": pid,
                "cells": entry.cells,
                "start": entry.start,
                "name": entry.name,
                "providers": providers,
                "consumers": len(consumers),
                "peers_touching": len(readers_writers),
                "grounding": grounding(entry, touched, (documented or {}).get(pid, set())),
            })
    return report


def load_generated(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Generated protocol definitions by relative path and contracts by source path."""
    from framework.scan_coverage import require_nonempty_glob
    root = Path(root)
    definitions = {
        path.relative_to(root).as_posix(): json.loads(path.read_text())
        for path in require_nonempty_glob(root / "contracts" / "protocols", "*.protocol.json")
    }
    contracts: dict[str, dict[str, Any]] = {}
    for path in require_nonempty_glob(root / "contracts", "*.contract.json", recursive=True):
        contract = json.loads(path.read_text())
        contracts[contract["source"]] = contract
    return definitions, contracts


def field_map_document(root: Path) -> str:
    """Render docs/STACK_FIELD_MAP.md from the reviewed layouts and the generated tree."""
    from framework.ic10_line_budget import CEILING_LINES, production_line_counts
    root = Path(root)
    definitions, contracts = load_generated(root)
    return render_field_map(
        load_layouts(root), definitions, production_line_counts(root), CEILING_LINES,
        declared_peer_cells(root, contracts), all_documented_cells(layout_documents_in(root)),
    )


def render_field_map(
    layouts: dict[str, list[LayoutEntry]],
    protocol_definitions: dict[str, dict[str, Any]],
    line_counts: dict[str, int],
    ceiling: int,
    extra_touched: dict[str, dict[int, set[str]]] | None = None,
    documented: dict[str, set[int]] | None = None,
) -> str:
    """docs/STACK_FIELD_MAP.md: the role vocabulary, every role's spread, and every protocol's map."""
    definitions_by_pid = {definition["protocol_id"]: definition for definition in protocol_definitions.values()}
    by_role = fields_by_role(layouts, protocol_definitions, extra_touched, documented)
    mapped_cells = sum(entry.end - entry.start + 1 for entries in layouts.values() for entry in entries)
    lines = [
        "# Stack Field Map",
        "",
        "Generated by tools/generate/generate_stack_field_map.py from the reviewed `layout` lists in",
        "data/script_contract_protocol_definitions.json and the generated protocol definitions under",
        "contracts/protocols/. Do not edit by hand. The header cells S0..S7 are described in",
        "docs/STACK_ABI_ENVELOPE.md and are not repeated here; a block header away from S0 keeps its",
        "magic and version cells out of the map the same way. The map covers the peer-visible surface:",
        "every entry names a cell a peer reads or writes (through a contract consumer edge, a",
        "wiring-declared port, or an attributed network access) or one a layout block or table under",
        "docs/ cites beside the contract's S0 line. A cell only its provider touches is not mapped,",
        "because nothing outside the program could hold its name.",
        "",
        f"Protocols with a layout: {len(layouts)}. Layout entries: "
        f"{sum(len(entries) for entries in layouts.values())}. Cells named: {mapped_cells}.",
        "",
        "## Roles",
        "",
        "| Role | Meaning | Entries |",
        "|---|---|---:|",
    ]
    for role, meaning in ROLES.items():
        lines.append(f"| {role} | {meaning} | {len(by_role[role])} |")
    lines += [
        "",
        "## By role",
        "",
        "One row per layout entry, grouped by role and ordered by cell, so the offsets services",
        "use for the same role sit together. Peers is the number of programs that read or write",
        "the entry's cells, counting contract consumer edges, the peers the wiring map declares for a",
        "port without one, and attributed network accesses; consumers counts contract consumer edges",
        "only. Grounding says what holds the name: a peer, a document, or both. Headroom is the",
        f"smallest line headroom under the {ceiling}-line ceiling among the protocol's providers, the",
        "room a move would have to fit in.",
        "",
    ]
    for role in ROLES:
        rows = sorted(by_role[role], key=lambda item: (item["start"], item["protocol_id"]))
        lines += [f"### {role}", ""]
        if not rows:
            lines += ["No entry carries this role.", ""]
            continue
        offsets = sorted({row["start"] for row in rows})
        lines += [
            f"{len(rows)} entries at {len(offsets)} distinct starting cells: "
            + ", ".join(f"S{cell}" for cell in offsets) + ".",
            "",
            "| Cells | Name | Protocol | Peers | Consumers | Grounding | Headroom |",
            "|---|---|---|---:|---:|---|---:|",
        ]
        for row in rows:
            headroom = min((ceiling - line_counts[source] for source in row["providers"] if source in line_counts), default=None)
            lines.append(
                f"| {row['cells']} | {row['name']} | {row['protocol_id']} | {row['peers_touching']} | "
                f"{row['consumers']} | {row['grounding']} | {'' if headroom is None else headroom} |")
        lines.append("")
    lines += ["## By protocol", ""]
    for pid in sorted(layouts):
        definition = definitions_by_pid.get(pid, {})
        providers = [item["source"] for item in definition.get("provider_interfaces", [])]
        consumers = sorted({item["source"] for item in definition.get("consumer_interfaces", [])})
        touched = peer_touched_cells(definition, extra_touched) if definition else {}
        lines += [
            f"### {pid}",
            "",
            f"Providers: {', '.join(providers) if providers else 'none'}.",
            "",
            f"Consumers: {len(consumers)}.",
            "",
            "| Cells | Name | Role | Peers | Grounding | Description |",
            "|---|---|---|---:|---|---|",
        ]
        for entry in layouts[pid]:
            peers = set()
            for cell in range(entry.start, entry.end + 1):
                peers |= touched.get(cell, set())
            description = (entry.description or "").replace("|", "\\|")
            held = grounding(entry, touched, (documented or {}).get(pid, set()))
            lines.append(f"| {entry.cells} | {entry.name} | {entry.role} | {len(peers)} | {held} | {description} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
