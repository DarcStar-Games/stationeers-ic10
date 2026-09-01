"""Build and validate the fixed-address IC10 stack-envelope inventory."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import re
from typing import Any

from framework.ic10_source import game_hash, parse_ic10
from framework.protocol_headers import header_name, header_token
from framework.script_contracts.dynamic_ranges import dynamic_range_proofs, merge_ranges
from framework.script_contracts.parsing import (
    collect_aliases,
    parse_program,
    resolve_integer,
    resolve_literal,
)
from framework.script_contracts.publication import stable_cells

FORMAT = "IC10_STACK_ENVELOPE_INVENTORY_V1"
DECLARATION_FORMAT = "IC10_STACK_ENVELOPE_DECLARATIONS_V1"
BASE = 0
LENGTH = 8
CAPABILITY_MASK_CELL = BASE + 2
SCHEMA_ID_CELL = BASE + 3
EXTENSION_BASE_CELL = BASE + 4
STATE_CELL = BASE + 5
TELEMETRY_BASE_CELL = BASE + 6
GENERATION_CELL = BASE + 7
HAS_SCHEMA = 1
HAS_EXTENSION = 2
HAS_STATE = 4
HAS_TELEMETRY = 8
HAS_GENERATION = 16
FIELD_CAPABILITY_BITS_V1 = (
    HAS_SCHEMA | HAS_EXTENSION | HAS_STATE | HAS_TELEMETRY | HAS_GENERATION
)
HAS_ASYNC_REQUEST_V1 = 32
HAS_BANKED_TRANSACTION_V1 = 64
HAS_GENERIC_JOB_ABI_V1 = 128
STANDARD_CAPABILITY_BITS_V1 = {
    "ASYNC_REQUEST_V1": HAS_ASYNC_REQUEST_V1,
    "BANKED_TRANSACTION_V1": HAS_BANKED_TRANSACTION_V1,
    "GENERIC_JOB_ABI_V1": HAS_GENERIC_JOB_ABI_V1,
}
CAPABILITY_BITS_V1 = (
    FIELD_CAPABILITY_BITS_V1 | sum(STANDARD_CAPABILITY_BITS_V1.values())
)
STATE_VALUES = (0, 1, 2, 3, 4, 5)
STATE_FIELD_MASK = 0xF          # bits 0..3 carry the state, one value at a time
STATE_RESERVED_MASK = 0xF0      # bits 4..7 are reserved for future universal flags
CUSTOM_STATE_SHIFT = 8          # bits 8.. are service-specific and opaque to readers
VALUE_BITS = 53                 # a stack cell is a double: exact integers to 2**53


def derive_capability_mask(
    *,
    has_schema: bool = False,
    extension_base: int = 0,
    publishes_state: bool = False,
    telemetry_base: int = 0,
    publishes_generation: bool = False,
    standard_capabilities: frozenset[str] = frozenset(),
) -> int:
    """Derive every structural and semantic CapabilityMask bit in one place."""
    return (
        (HAS_SCHEMA if has_schema else 0)
        | (HAS_EXTENSION if extension_base else 0)
        | (HAS_STATE if publishes_state else 0)
        | (HAS_TELEMETRY if telemetry_base else 0)
        | (HAS_GENERATION if publishes_generation else 0)
        | sum(STANDARD_CAPABILITY_BITS_V1[name] for name in standard_capabilities)
    )


def publication_cost_lines(
    capability_mask: int, externally_assigned_fields: int = 0
) -> int:
    """Return mandatory writes plus declared optional fields this service writes."""
    locally_published = (
        capability_mask & FIELD_CAPABILITY_BITS_V1 & ~externally_assigned_fields
    )
    return 3 + locally_published.bit_count()


def state_errors(values: set[Any], custom_state_bits: int) -> list[str]:
    """A published state packs a v1 state field, zero reserved bits, and declared custom bits."""
    errors: list[str] = []
    for value in sorted(values, key=repr):
        if type(value) is not int or value < 0 or value >= 2 ** VALUE_BITS:
            errors.append(f"state {value!r} is not an integer inside the {VALUE_BITS}-bit cell width")
            continue
        if value & STATE_FIELD_MASK not in STATE_VALUES:
            errors.append(f"state {value} carries an undefined v1 state field")
        if value & STATE_RESERVED_MASK:
            errors.append(f"state {value} sets a reserved bit")
        custom = value >> CUSTOM_STATE_SHIFT
        if custom & ~custom_state_bits:
            errors.append(f"state {value} sets custom bits the service never declared")
    return errors
EXTENSION_MAGIC = 31416054
EXTENSION_VERSION = 1
EXTENSION_MIN_LENGTH = 4
EXTENSION_MAX_LENGTH = 192
PRE_V1_LEGACY_BASELINE_SHA256 = "88eacbf2e6961fe2fe3431321a31cd7a666f9ccba625acad57f81174bb811e0d"
SERVICE_ID_RE = re.compile(r"^ic10\.script\.[a-z0-9.]+$")
IMPLEMENTATION_ID_RE = re.compile(r"^ic10\.implementation\.[a-z0-9.]+$")
HASH_RE = re.compile(r'^HASH\("([^"\n]+)"\)$')
_REFERENCE_STACK_WRITES = {"clrd", "putd"}


class DeclarationError(ValueError):
    """Every reviewed-declaration failure found in one pass, kept as separate lines."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


@dataclass
class ErrorCollector:
    """Collect independent validation failures with an optional source prefix."""

    source: str | None = None
    errors: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        self.errors.append(f"{self.source}: {message}" if self.source else message)

    def extend(self, messages: list[str]) -> None:
        for message in messages:
            self.add(message)


@dataclass(frozen=True)
class StackRange:
    """A normalized inclusive stack range."""

    start: int
    end: int

    def cells(self) -> set[int]:
        return set(range(self.start, self.end + 1))

    def as_dict(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass(frozen=True)
class NormalizedDeclaration:
    """Typed values used by per-service stack-envelope validation rules."""

    source: str
    service_id: str = "ic10.script.example"
    contract: str = "Example"
    service_abi: int = 1
    schema_id: str | None = None
    schema_version: int = 0
    extension_base: int = 0
    telemetry_base: int = 0
    publishes_state: bool = False
    custom_state_bits: int = 0
    publishes_generation: bool = False
    extension_flags: int = 0
    implementation_id: str | None = None
    legacy_owned_ranges: tuple[StackRange, ...] = ()
    post_init_dynamic_write_ranges: tuple[StackRange, ...] = ()
    source_sha256: str = ""
    pilot_family: str = ""
    schema_assigned_externally: bool = False
    standard_capabilities: frozenset[str] = frozenset()

    @property
    def magic(self) -> int:
        """S0 is derived, never allocated: the ABI is folded into the hashed name."""
        return game_hash(header_name(self.contract, self.service_abi))

    @property
    def magic_token(self) -> str:
        return header_token(self.contract, self.service_abi)

    @property
    def capability_mask(self) -> int:
        return derive_capability_mask(
            has_schema=self.schema_id is not None or self.schema_assigned_externally,
            extension_base=self.extension_base,
            publishes_state=self.publishes_state,
            telemetry_base=self.telemetry_base,
            publishes_generation=self.publishes_generation,
            standard_capabilities=self.standard_capabilities,
        )

    def publication_metadata(self) -> dict[str, Any]:
        return {
            "source_sha256": self.source_sha256,
            "post_init_dynamic_write_ranges": [
                [item.start, item.end] for item in self.post_init_dynamic_write_ranges
            ],
        }


def legacy_source_digest(sources: list[str]) -> str:
    payload = "".join(f"{source}\n" for source in sorted(sources)).encode()
    return hashlib.sha256(payload).hexdigest()


def load_declarations(root: Path) -> dict[str, Any]:
    document = json.loads((Path(root) / "data" / "stack_envelope_declarations.json").read_text())
    if document.get("format") != DECLARATION_FORMAT:
        raise ValueError(f"unsupported stack envelope declaration format: {document.get('format')!r}")
    return document


def standard_participation_errors(
    migrated: dict[str, Any], participation: Any
) -> list[str]:
    """Validate the reviewed source lists that drive semantic capability bits."""
    if not isinstance(participation, dict):
        return ["standard_participation must be an object keyed by standard name"]
    errors: list[str] = []
    expected = set(STANDARD_CAPABILITY_BITS_V1)
    actual = set(participation)
    if actual != expected:
        errors.append(
            "standard_participation keys differ from the v1 capability registry: "
            f"expected {sorted(expected)}, got {sorted(actual)}"
        )
    for standard, sources in sorted(participation.items()):
        if standard not in expected:
            continue
        if not isinstance(sources, list) or any(not isinstance(source, str) for source in sources):
            errors.append(f"{standard} participants must be an explicit path list")
            continue
        if len(sources) != len(set(sources)):
            errors.append(f"{standard} participant list contains duplicates")
        unknown = sorted(set(sources) - set(migrated))
        if unknown:
            errors.append(f"{standard} participants are not migrated services: {unknown}")
        if sources != sorted(sources):
            errors.append(f"{standard} participant list must be sorted")
    return errors


def standards_by_source(
    participation: Any, migrated_sources: set[str] | None = None
) -> dict[str, frozenset[str]]:
    """Invert every usable membership entry, independent of presentation errors."""
    result: dict[str, set[str]] = {}
    if not isinstance(participation, dict):
        return {}
    for standard, sources in participation.items():
        if standard not in STANDARD_CAPABILITY_BITS_V1 or not isinstance(sources, list):
            continue
        for source in sources:
            if not isinstance(source, str):
                continue
            if migrated_sources is not None and source not in migrated_sources:
                continue
            result.setdefault(source, set()).add(standard)
    return {source: frozenset(standards) for source, standards in result.items()}


def unavailable_standard_capabilities(participation: Any) -> frozenset[str]:
    """Return standards whose membership cannot be derived from the registry shape."""
    if not isinstance(participation, dict):
        return frozenset(STANDARD_CAPABILITY_BITS_V1)
    return frozenset(
        standard
        for standard in STANDARD_CAPABILITY_BITS_V1
        if standard not in participation
        or not isinstance(participation[standard], list)
        or any(not isinstance(source, str) for source in participation[standard])
    )


def capability_mask_for_validation(
    declaration: NormalizedDeclaration,
    writes: dict[int, set[Any]],
    ignored_standard_bits: int = 0,
) -> int:
    """Retain unavailable standard bits from one unambiguous source publication."""
    expected = declaration.capability_mask
    actual = writes.get(CAPABILITY_MASK_CELL, set())
    if ignored_standard_bits and len(actual) == 1:
        published = next(iter(actual))
        if type(published) is int:
            return (expected & ~ignored_standard_bits) | (published & ignored_standard_bits)
    return expected


def declared_capability_mask(root: Path, source: str) -> int:
    """Derive one source's mask directly from the reviewed declaration data."""
    document = load_declarations(root)
    declaration = document["migrated"][source]
    standards = standards_by_source(
        document["standard_participation"], set(document["migrated"])
    ).get(source, frozenset())
    return derive_capability_mask(
        has_schema=(
            declaration["schema_id"] is not None
            or declaration.get("schema_assigned_externally", False)
        ),
        extension_base=declaration["extension_base"],
        publishes_state=declaration["publishes_state"],
        telemetry_base=declaration["telemetry_base"],
        publishes_generation=declaration["publishes_generation"],
        standard_capabilities=standards,
    )


def _parse(path: Path) -> tuple[list[list[str]], dict[str, int]]:
    source = parse_ic10(Path(path).read_text())
    rows = [list(row.tokens) for row in source.rows]
    return rows, collect_aliases(rows)[1]


def _writes(rows: list[list[str]], aliases: dict[str, int]) -> dict[int, set[Any]]:
    writes: dict[int, set[Any]] = {}
    for row in rows:
        if len(row) >= 3 and row[0] == "poke":
            address = resolve_integer(row[1], aliases)
            if address is not None:
                writes.setdefault(address, set()).add(resolve_literal(row[2], aliases))
    return writes


def _literal_writes(path: Path) -> dict[int, set[Any]]:
    return _writes(*_parse(path))


def _write_tokens(rows: list[list[str]], aliases: dict[str, int]) -> dict[int, set[str]]:
    """Raw HASH token text per cell, for the rules that need the semantic name.

    Every published identity resolves to a number, so the rules that compare
    values work numerically; only the rules that must recover *which* schema a
    cell names read the source spelling back.
    """
    tokens: dict[int, set[str]] = {}
    for row in rows:
        if len(row) >= 3 and row[0] == "poke" and HASH_RE.fullmatch(row[2]):
            address = resolve_integer(row[1], aliases)
            if address is not None:
                tokens.setdefault(address, set()).add(row[2])
    return tokens


def _literal_write_tokens(path: Path) -> dict[int, set[str]]:
    return _write_tokens(*_parse(path))


def _schema_check_pairs(rows: list[list[str]], aliases: dict[str, int]) -> set[tuple[str, int]]:
    """Recover the (SchemaId, SchemaVersion) pairs a source verifies on a published stack."""
    checked: dict[int, set[Any]] = {}
    for index, row in enumerate(rows):
        if row[0] not in {"get", "getd"} or len(row) < 4:
            continue
        register = row[1]
        address = resolve_integer(row[3], aliases)
        if address is None:
            continue
        for later in rows[index + 1:]:
            if later[0] in {"beq", "bne"} and len(later) >= 3 and later[1] == register:
                # the source spelling is what names the schema; the number it
                # resolves to cannot be read back into an identity
                value = later[2] if HASH_RE.fullmatch(later[2]) else resolve_literal(later[2], aliases)
                if value is not None:
                    checked.setdefault(address, set()).add(value)
                break
            if len(later) >= 2 and later[1] == register:
                break
    pairs = {
        (value, version)
        for address, values in checked.items()
        for value in values if isinstance(value, str)
        for version in checked.get(address + 1, set()) if isinstance(version, int)
    }
    for values in checked.values():
        for value in values:
            match = HASH_RE.fullmatch(value) if isinstance(value, str) else None
            if match is None:
                continue
            name, _, version = match.group(1).rpartition(".v")
            if name and version.isdigit():
                pairs.add(('HASH("' + name + '")', int(version)))
    return pairs


def canonical_schema_pairs(root: Path) -> set[tuple[str, int]]:
    """Every (schema id, version) the reviewed data files declare as canonical."""
    pairs: set[tuple[str, int]] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for id_key, version_key in (("schema_id", "schema_version"),
                                        ("catalog_schema_id", "catalog_schema_version")):
                name, version = node.get(id_key), node.get(version_key)
                if isinstance(name, str) and type(version) is int:
                    pairs.add((f'HASH("{name}")', version))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in sorted((Path(root) / "data").glob("*.json")):
        if path.name == "stack_envelope_declarations.json":
            continue
        walk(json.loads(path.read_text()))
    return pairs


def schema_hash_token(schema_id: str, schema_version: int) -> str:
    """The source literal a program writes to publish its schema identity."""
    return header_token(schema_id, schema_version)


def schema_hash(schema_id: str, schema_version: int) -> int:
    """The published schema identity carries its version: one cell, one exact match."""
    return game_hash(header_name(schema_id, schema_version))


def _range_cells(ranges: list[dict[str, int]]) -> set[int]:
    return {cell for item in ranges for cell in range(item["start"], item["end"] + 1)}


def _spans(cells: set[int]) -> str:
    """Name a cell set in the inclusive-range form the declarations are written in."""
    return ", ".join(
        f"S{item['start']}" if item["start"] == item["end"]
        else f"S{item['start']}..S{item['end']}"
        for item in merge_ranges([{"start": cell, "end": cell} for cell in sorted(cells)])
    )


def _schema_fields(
    contract: dict[str, Any], path: Path, writes: dict[int, set[Any]] | None = None
) -> list[dict[str, Any]]:
    fields: dict[int, dict[str, Any]] = {}
    for field in contract["own_stack"]["fields"]:
        semantic_text = " ".join((field["name"], field.get("description", ""))).lower()
        if "schema" in semantic_text:
            fields[field["address"]] = {
                key: field[key] for key in ("address", "name", "const") if key in field
            }
    writes = _literal_writes(path) if writes is None else writes
    for address, values in sorted(_literal_write_tokens(path).items()):
        for value in values:
            match = HASH_RE.fullmatch(value)
            if match is None or "schema" not in match.group(1).lower():
                continue
            schema_name = match.group(1)
            canonical_id = schema_name.startswith(("DirectorySchema.", "CatalogSchema."))
            fields[address] = {
                "address": address,
                "name": "SchemaId" if canonical_id else "SchemaIdentityHash",
                "const": value,
            }
            versions = writes.get(address + 1, set())
            if canonical_id and len(versions) == 1 and isinstance(next(iter(versions)), int):
                fields[address + 1] = {
                    "address": address + 1,
                    "name": "SchemaVersion",
                    "const": next(iter(versions)),
                }
    return [fields[address] for address in sorted(fields)]


def _declared_ranges(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, list):
        raise ValueError(f"reviewed dynamic ranges must be an explicit list: {value!r}")
    ranges = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(type(cell) is int for cell in item)
        ):
            raise ValueError(f"invalid reviewed dynamic range: {item!r}")
        start, end = item
        if not 0 <= start <= end <= 511:
            raise ValueError(f"reviewed dynamic range outside S0..S511: {item!r}")
        ranges.append({"start": start, "end": end})
    return ranges


def normalize_declaration(
    source: str, value: Any, standard_capabilities: frozenset[str] = frozenset()
) -> tuple[NormalizedDeclaration | None, list[str]]:
    """Normalize one declaration, returning only precise shape errors on failure."""
    collector = ErrorCollector(source)
    if not isinstance(value, dict):
        collector.add("declaration must be an object")
        return None, collector.errors

    def require(
        name: str,
        expected_type: type,
        default: Any = None,
        *,
        required: bool = True,
    ) -> Any:
        if name not in value:
            if required:
                collector.add(f"{name} is required")
            return default
        candidate = value.get(name, default)
        valid = type(candidate) is expected_type
        if expected_type is str:
            valid = isinstance(candidate, str)
        if not valid:
            article = "an" if expected_type is int else "a"
            collector.add(f"{name} must be {article} {expected_type.__name__}")
            return default
        return candidate

    service_id = require("service_id", str, "")
    contract = require("contract", str, "")
    service_abi = require("service_abi", int, 0)
    if contract and not re.fullmatch(r"[A-Z][A-Za-z0-9]*", contract):
        collector.add("contract must be an UpperCamelCase identity name")
    schema_id = value.get("schema_id")
    if "schema_id" not in value:
        collector.add("schema_id is required")
    elif schema_id is not None and not isinstance(schema_id, str):
        collector.add("schema_id must be null or a string")
    schema_version = require("schema_version", int, 0)
    extension_base = require("extension_base", int, 0)
    telemetry_base = require("telemetry_base", int, 0)
    publishes_state = require("publishes_state", bool, False)
    custom_state_bits = require("custom_state_bits", int, 0, required=False)
    publishes_generation = require("publishes_generation", bool, False)
    extension_flags = require("extension_flags", int, 0)
    implementation_id = value.get("implementation_id")
    if "implementation_id" not in value:
        collector.add("implementation_id is required")
    elif implementation_id is not None and not isinstance(implementation_id, str):
        collector.add("implementation_id must be null or a string")
    source_sha256 = require("source_sha256", str, "")
    pilot_family = require("pilot_family", str, "")
    schema_assigned_externally = require("schema_assigned_externally", bool, False, required=False)
    if schema_assigned_externally and (schema_id is not None or schema_version):
        collector.add("schema_assigned_externally requires a null schema_id and version 0")

    normalized_ranges: dict[str, tuple[StackRange, ...]] = {}
    for name, default in (
        ("legacy_owned_ranges", None),
        ("post_init_dynamic_write_ranges", []),
    ):
        if name not in value:
            collector.add(f"{name} is required")
            continue
        try:
            normalized_ranges[name] = tuple(
                StackRange(item["start"], item["end"])
                for item in _declared_ranges(value.get(name, default))
            )
        except ValueError as error:
            collector.add(str(error))

    if collector.errors:
        return None, collector.errors
    return NormalizedDeclaration(
        source=source,
        service_id=service_id,
        contract=contract,
        service_abi=service_abi,
        schema_id=schema_id,
        schema_version=schema_version,
        extension_base=extension_base,
        telemetry_base=telemetry_base,
        publishes_state=publishes_state,
        custom_state_bits=custom_state_bits,
        publishes_generation=publishes_generation,
        extension_flags=extension_flags,
        implementation_id=implementation_id,
        legacy_owned_ranges=normalized_ranges["legacy_owned_ranges"],
        post_init_dynamic_write_ranges=normalized_ranges["post_init_dynamic_write_ranges"],
        source_sha256=source_sha256,
        pilot_family=pilot_family,
        schema_assigned_externally=schema_assigned_externally,
        standard_capabilities=standard_capabilities,
    ), []


def extension_ownership_errors(
    legacy_owned_ranges: list[dict[str, int]], extension_base: int, extension_length: int
) -> list[str]:
    legacy_cells = _range_cells(legacy_owned_ranges)
    extension_cells = set(range(extension_base, extension_base + extension_length))
    if legacy_cells & extension_cells:
        return ["extension overlaps the established pre-envelope stack layout"]
    return []


def publication_errors(
    path: Path,
    expected: dict[int, Any],
    declaration: dict[str, Any],
    reserved_cells: set[int] | None = None,
    mutable_cells: frozenset[int] = frozenset(),
    reference_writes_own_stack: bool = True,
) -> list[str]:
    """Prove the fixed envelope is on the straight-line entry path and remains reserved."""
    path = Path(path)
    errors: list[str] = []
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if declaration.get("source_sha256") != source_sha256:
        errors.append("migration source fingerprint changed; re-review envelope publication and dynamic writes")
    rows, aliases = _parse(path)
    state: dict[int, Any] = {}
    first_yield = None
    branch_proved = False
    scan_from = None
    for index, row in enumerate(rows):
        op = row[0]
        if op == "yield":
            first_yield = index
            break
        if op in {"j", "jal", "jr"} or op.startswith("b"):
            # a reflash-marker guard branches before publishing; the contract layer proves
            # whether every expected cell still holds its value at every observation point
            stable = stable_cells(path.read_text(), aliases, expected)
            missing = sorted(set(expected) - stable)
            if missing:
                # Same-image induction: when the entry guard compares S0 against this
                # contract's magic before branching, the skip path runs only over a
                # stack the same contract published -- so a cell whose every literal
                # write in this source is the expected constant already holds it
                # there. Dynamic writes into the envelope are rejected below.
                guard_rows = rows[:index + 1]
                reads_magic = any(r[0] == "get" and len(r) >= 4 and r[2] == "db"
                                  and resolve_integer(r[3], aliases) == 0 for r in guard_rows)
                compares_magic = any(r[0].startswith("b") and any(
                    resolve_literal(token, aliases) == expected.get(0)
                    for token in r[1:-1]) for r in guard_rows)
                if reads_magic and compares_magic:
                    for address in list(missing):
                        writes = [r for r in rows if r[0] == "poke" and len(r) >= 3
                                  and resolve_integer(r[1], aliases) == address]
                        if writes and all(
                                resolve_literal(r[2], aliases) == expected[address] for r in writes):
                            missing.remove(address)
            if missing:
                errors.append("control transfer occurs before the first envelope-bearing yield")
            branch_proved = not missing
            scan_from = index
            break
        if op == "clr" and len(row) >= 2 and row[1] == "db":
            state = {address: 0 for address in expected}   # clr db zeroes every cell
        elif op in _REFERENCE_STACK_WRITES or (op == "put" and len(row) >= 2 and row[1] == "db"):
            errors.append("reference-addressed own-stack write occurs before the first envelope-bearing yield")
        elif op in {"push", "pop"}:
            errors.append("dynamic own-stack write occurs before the first envelope-bearing yield")
        elif op == "poke" and len(row) >= 3:
            address = resolve_integer(row[1], aliases)
            if address is None:
                errors.append("dynamic own-stack write occurs before the first envelope-bearing yield")
            elif address in expected:
                state[address] = resolve_literal(row[2], aliases)
    one_shot = not any(row[0] == "yield" for row in rows)
    if first_yield is None and not branch_proved and not one_shot:
        errors.append("no reachable straight-line yield follows envelope initialization")
    if not branch_proved:
        for address, value in expected.items():
            if state.get(address) != value:
                errors.append(f"entry path does not retain S{address} = {value} at the first yield")
    try:
        reviewed_ranges = _declared_ranges(declaration.get("post_init_dynamic_write_ranges", []))
    except ValueError as error:
        errors.append(str(error))
        reviewed_ranges = []
    reserved = set(expected) if reserved_cells is None else set(reserved_cells)
    if any(reserved & set(range(item["start"], item["end"] + 1)) for item in reviewed_ranges):
        errors.append("reviewed post-init dynamic write range overlaps envelope or extension cells")
    dynamic_after = False
    # After a proven-stable reflash-guard branch, everything past the branch is
    # post-publication for reserved-cell purposes; stable_cells already proved
    # every envelope cell holds its value at every observation point, including
    # across any guarded recovery clear that re-publishes the header.
    guard_proved = first_yield is None and branch_proved
    if guard_proved:
        first_yield = scan_from
    if first_yield is not None:
        for row in rows[first_yield + 1:]:
            op = row[0]
            if op == "clr" and len(row) >= 2 and row[1] == "db":
                if not guard_proved:
                    errors.append("clr db after publication can erase the fixed envelope")
            elif op == "clrd" or op == "putd" or (op == "put" and len(row) >= 2 and row[1] == "db"):
                # a reference-addressed write only touches this stack when it can name self,
                # which the generated contract resolves far more precisely than a source scan
                dynamic_after = dynamic_after or reference_writes_own_stack
            elif op == "poke" and len(row) >= 3:
                address = resolve_integer(row[1], aliases)
                if address is None:
                    dynamic_after = True
                elif address in mutable_cells:
                    continue
                elif address in expected and resolve_literal(row[2], aliases) != expected[address]:
                    errors.append(f"post-init write can change envelope S{address}")
                elif address in reserved and address not in expected:
                    errors.append(f"post-init write can change reserved S{address}")
            elif op in {"push", "pop"}:
                dynamic_after = True
    if dynamic_after and not reviewed_ranges:
        errors.append("post-init dynamic own-stack writes lack reviewed, source-fingerprinted bounds")
    if not dynamic_after and reviewed_ranges:
        errors.append("reviewed post-init dynamic write ranges exist but source has no such writes")
    return errors


def clears_before_yield(rows: list[list[str]]) -> bool:
    """A boot-time `clr db` deterministically zeroes every cell, initializers included."""
    for row in rows:
        if row[0] == "yield":
            return False
        if row[0] == "clr" and len(row) >= 2 and row[1] == "db":
            return True
    return False


def generation_errors(
    rows: list[list[str]], aliases: dict[str, int], declares_generation: bool
) -> list[str]:
    """A declared generation starts at zero, advances, and is the last cell published."""
    generation_rows = [
        index for index, row in enumerate(rows)
        if row[0] == "poke" and len(row) >= 3
        and resolve_integer(row[1], aliases) == GENERATION_CELL
    ]
    poke_rows = [index for index, row in enumerate(rows) if row[0] == "poke"]
    if not declares_generation:
        return [
            f"S{GENERATION_CELL} is reserved unless the service declares HAS_GENERATION"
        ] if generation_rows else []
    if not generation_rows:
        return [f"HAS_GENERATION requires S{GENERATION_CELL} to be published"]
    if generation_rows[-1] != poke_rows[-1]:
        return [f"the generation at S{GENERATION_CELL} must be the last cell published"]
    return []


def _consumer_checks(source: str, protocol_registry: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for protocol in protocol_registry["protocols"]:
        if not any(provider["source"] == source for provider in protocol["providers"]):
            continue
        checks.append({
            "protocol_id": protocol["protocol_id"],
            "provider_header_bases": sorted(
                provider["header_base"] for provider in protocol["providers"] if provider["source"] == source
            ),
            "consumers": protocol["consumers"],
        })
    return checks


def canonical_envelope() -> dict[str, Any]:
    """Return the immutable v1 declaration constants."""
    return {
        "base": BASE,
        "length": LENGTH,
        "capability_bits_v1": CAPABILITY_BITS_V1,
        "standard_capability_bits": STANDARD_CAPABILITY_BITS_V1,
        "state_values": list(STATE_VALUES),
        "state_field_mask": STATE_FIELD_MASK,
        "state_reserved_mask": STATE_RESERVED_MASK,
        "custom_state_shift": CUSTOM_STATE_SHIFT,
        "value_bits": VALUE_BITS,
        "extension_magic": EXTENSION_MAGIC,
        "extension_version": EXTENSION_VERSION,
        "extension_min_length": EXTENSION_MIN_LENGTH,
        "extension_max_length": EXTENSION_MAX_LENGTH,
    }


def envelope_cell_tokens(declaration: NormalizedDeclaration) -> dict[int, str]:
    """Source spelling of the hashed envelope cells, for diagnostics."""
    tokens = {BASE: declaration.magic_token}
    if declaration.capability_mask & HAS_SCHEMA and not declaration.schema_assigned_externally:
        tokens[SCHEMA_ID_CELL] = schema_hash_token(
            declaration.schema_id or "", declaration.schema_version
        )
    return tokens


def expected_envelope_cells(declaration: NormalizedDeclaration) -> dict[int, Any]:
    """Derive the fixed header cells from a normalized declaration."""
    expected: dict[int, Any] = {
        BASE: declaration.magic,
        BASE + 1: declaration.service_abi,
        CAPABILITY_MASK_CELL: declaration.capability_mask,
    }
    if declaration.capability_mask & HAS_SCHEMA and not declaration.schema_assigned_externally:
        expected[SCHEMA_ID_CELL] = schema_hash(
            declaration.schema_id or "", declaration.schema_version
        )
    if declaration.capability_mask & HAS_EXTENSION:
        expected[EXTENSION_BASE_CELL] = declaration.extension_base
    if declaration.capability_mask & HAS_TELEMETRY:
        expected[TELEMETRY_BASE_CELL] = declaration.telemetry_base
    if declaration.capability_mask & HAS_GENERATION:
        expected[GENERATION_CELL] = 0
    return expected


def identity_header_errors(
    declaration: NormalizedDeclaration, contract: dict[str, Any]
) -> list[str]:
    """Validate semantic identity and its contract-backed S0/S1 header."""
    errors: list[str] = []
    if not SERVICE_ID_RE.fullmatch(declaration.service_id):
        errors.append(f"invalid semantic service_id {declaration.service_id!r}")
    canonical_service_id = contract["identity"]["service_id"]
    if declaration.service_id != canonical_service_id:
        errors.append(
            f"service_id {declaration.service_id!r} != canonical contract identity "
            f"{canonical_service_id!r}"
        )
    if declaration.magic == 0:
        errors.append("magic must be the service's registered nonzero integer")
    if declaration.service_abi < 1:
        errors.append("service_abi must be a positive integer")
    if not any(
        header["base"] == BASE
        and header["magic"] == declaration.magic
        and header["abi"] == declaration.service_abi
        for header in contract["own_stack"]["headers"]
    ):
        errors.append("S0/S1 do not publish the declared magic and ABI as a verified header")
    return errors


def schema_capability_errors(
    declaration: NormalizedDeclaration,
    bound_schema_pairs: set[tuple[str, int]],
    writes: dict[int, set[Any]],
    ignored_standard_bits: int = 0,
) -> list[str]:
    """Validate schema bindings, capability pointers, and fixed header writes."""
    errors: list[str] = []
    if declaration.schema_id is not None and not declaration.schema_id:
        errors.append("schema_id must be null or a nonempty semantic hash name")
    if (declaration.schema_id is None) != (declaration.schema_version == 0):
        errors.append("schema_id and schema_version must both be absent/zero or both present")
    if declaration.schema_id is not None and (
        f'HASH("{declaration.schema_id}")', declaration.schema_version
    ) not in bound_schema_pairs:
        errors.append("schema/version is not canonical and is not verified by this source")
    if not 0 <= declaration.telemetry_base <= 511:
        errors.append("telemetry_base must be an integer in S0..S511")
    elif declaration.telemetry_base and declaration.telemetry_base < BASE + LENGTH:
        errors.append("telemetry_base cannot point inside the common header")

    expected = expected_envelope_cells(declaration)
    expected[CAPABILITY_MASK_CELL] = capability_mask_for_validation(
        declaration, writes, ignored_standard_bits
    )
    allowed_dynamic = {STATE_CELL, GENERATION_CELL} | (
        {SCHEMA_ID_CELL} if declaration.schema_assigned_externally else set()
    )
    for cell in range(BASE, BASE + LENGTH):
        if cell not in expected and cell not in allowed_dynamic and writes.get(cell):
            errors.append(f"S{cell} is reserved and must not be written undeclared")
    spelling = envelope_cell_tokens(declaration)
    for address, value in expected.items():
        if address != GENERATION_CELL and writes.get(address, set()) != {value}:
            errors.append(f"S{address} must be written exactly as {spelling.get(address, value)}")
    return errors


def state_generation_rule_errors(
    declaration: NormalizedDeclaration,
    rows: list[list[str]],
    aliases: dict[str, int],
    writes: dict[int, set[Any]],
) -> list[str]:
    """Validate declared state values and generation publication semantics."""
    errors = generation_errors(rows, aliases, declaration.publishes_generation)
    if declaration.publishes_generation:
        written = writes.get(GENERATION_CELL, set())
        initialized = 0 in written or clears_before_yield(rows)
        if not initialized or any(other is not None for other in written - {0}):
            errors.append(
                f"S{GENERATION_CELL} must be initialized to 0 and only advanced dynamically"
            )

    custom_bits_valid = 0 <= declaration.custom_state_bits < 2 ** (
        VALUE_BITS - CUSTOM_STATE_SHIFT
    )
    if not custom_bits_valid:
        errors.append("custom_state_bits must fit the service-specific state range")
    effective_custom_bits = declaration.custom_state_bits if custom_bits_valid else 0
    state_writes = writes.get(STATE_CELL, set())
    if declaration.publishes_state:
        if not state_writes:
            errors.append(f"HAS_STATE requires the source to publish S{STATE_CELL}")
        errors.extend(state_errors(state_writes, effective_custom_bits))
    elif custom_bits_valid and declaration.custom_state_bits:
        errors.append("custom state bits require HAS_STATE")
    elif state_writes:
        errors.append(f"S{STATE_CELL} is reserved unless the service declares HAS_STATE")
    return errors


@dataclass(frozen=True)
class ExtensionRuleResult:
    """Extension validation output needed by layout and publication rules."""

    errors: tuple[str, ...]
    published_cells: dict[int, Any]
    reserved_cells: frozenset[int]


def extension_rule_result(
    declaration: NormalizedDeclaration, writes: dict[int, set[Any]]
) -> ExtensionRuleResult:
    """Validate extension identity, bounds, ownership inputs, and literal writes."""
    errors: list[str] = []
    published: dict[int, Any] = {}
    reserved: set[int] = set()
    base = declaration.extension_base
    flags_valid = 0 <= declaration.extension_flags <= 1
    if base and not 0 <= base <= 511 - EXTENSION_MIN_LENGTH + 1:
        errors.append("extension base cannot fit the minimum extension header")
    if not flags_valid:
        errors.append("extension_flags may use only v1 HAS_IMPLEMENTATION_ID bit 0")
    if base == 0:
        if declaration.extension_flags != 0 or declaration.implementation_id is not None:
            errors.append("absent extension requires zero flags and no ImplementationId")
        return ExtensionRuleResult(tuple(errors), published, frozenset())

    has_implementation_id = flags_valid and bool(declaration.extension_flags & 1)
    implementation_valid = (
        isinstance(declaration.implementation_id, str)
        and bool(IMPLEMENTATION_ID_RE.fullmatch(declaration.implementation_id))
    )
    if has_implementation_id and not implementation_valid:
        errors.append("HAS_IMPLEMENTATION_ID requires a semantic ic10.implementation.* identity")
    elif flags_valid and not has_implementation_id and declaration.implementation_id is not None:
        errors.append("ImplementationId requires HAS_IMPLEMENTATION_ID")
    if not 0 <= base <= 511 - EXTENSION_MIN_LENGTH + 1:
        return ExtensionRuleResult(tuple(errors), published, frozenset())

    for address, value in {
        base: EXTENSION_MAGIC,
        base + 1: EXTENSION_VERSION,
        base + 3: declaration.extension_flags,
    }.items():
        if writes.get(address) != {value}:
            errors.append(f"extension S{address} must be written exactly as {value}")
    lengths = writes.get(base + 2, set())
    if len(lengths) != 1 or type(next(iter(lengths), None)) is not int:
        errors.append("extension length must be one literal integer")
        return ExtensionRuleResult(tuple(errors), published, frozenset())

    extension_length = next(iter(lengths))
    extension_end = base + extension_length
    published.update({
        base: EXTENSION_MAGIC,
        base + 1: EXTENSION_VERSION,
        base + 2: extension_length,
        base + 3: declaration.extension_flags,
    })
    if 0 <= base < extension_end <= 512:
        reserved.update(range(base, extension_end))
        errors.extend(extension_ownership_errors(
            [item.as_dict() for item in declaration.legacy_owned_ranges],
            base,
            extension_length,
        ))
    if not EXTENSION_MIN_LENGTH <= extension_length <= EXTENSION_MAX_LENGTH:
        errors.append("extension length is outside v1 bounds")
    if extension_end > 512:
        errors.append("extension exceeds the 512-cell stack")
    if base < BASE + LENGTH:
        errors.append("extension overlaps the fixed header")
    if has_implementation_id and implementation_valid:
        if extension_length < 5:
            errors.append("HAS_IMPLEMENTATION_ID extension is shorter than five cells")
        implementation_value = game_hash(declaration.implementation_id)
        published[base + 4] = implementation_value
        if writes.get(base + 4) != {implementation_value}:
            errors.append(
                "extension ImplementationId must be written exactly as "
                f'HASH("{declaration.implementation_id}")'
            )
    return ExtensionRuleResult(tuple(errors), published, frozenset(reserved))


def legacy_layout_errors(
    declaration: NormalizedDeclaration,
    contract: dict[str, Any],
    extension_cells: frozenset[int],
) -> list[str]:
    """Reconcile reviewed legacy ownership with literal and dynamic stack use."""
    actual = (
        set(contract["own_stack"]["literal_reads"])
        | set(contract["own_stack"]["literal_writes"])
    ) - set(range(BASE, BASE + LENGTH)) - set(extension_cells)
    for item in declaration.post_init_dynamic_write_ranges:
        actual.update(item.cells())
    reviewed = set().union(*(item.cells() for item in declaration.legacy_owned_ranges))
    return (["legacy_owned_ranges no longer match the pre-extension stack layout"]
            if actual != reviewed else [])


def post_init_range_errors(
    declaration: NormalizedDeclaration,
    contract: dict[str, Any],
    extension_cells: frozenset[int],
) -> list[str]:
    """A reviewed post-init dynamic write range sits inside the derived one.

    A post-init dynamic write *is* a dynamic write, so the reviewed set is a
    subset of the contract's -- narrower *in time*, because it excludes whatever
    ran before the first envelope-bearing yield, never wider in space.

    Only that direction is a contradiction. A reviewed range far tighter than the
    derived one is the ordinary case and stays unchecked: a boot `clr db` puts all
    512 cells in the derived range and none of them are post-init, which is why
    `generic_job_command_gateway_v3_0` declares nine cells against 504.

    Envelope and extension cells are left out because the reserved-overlap rule in
    `publication_errors` already rejects them, for a better reason than this one.
    A source with no dynamic write at all is left to that rule for the same reason:
    "the source has no such writes" names the whole declaration, not a span of it.

    The derived range covers computed-address own-stack writes. A reference-addressed
    write that named this stack would not be in it, so a program doing that would be
    rejected here for a claim its source does back; no migrated program is, and the
    fix would be for the contract layer to see the write, not for this rule to relax.
    """
    provenance = contract["own_stack"]["dynamic_write_range_source"]
    if provenance == "none":
        return []
    reserved = set(range(BASE, BASE + LENGTH)) | set(extension_cells)
    claimed = set().union(*(item.cells() for item in declaration.post_init_dynamic_write_ranges))
    derived = _range_cells(contract["own_stack"]["dynamic_write_ranges"])
    unreachable = claimed - reserved - derived
    if not unreachable:
        return []
    return [
        f"reviewed post-init dynamic write range claims {_spans(unreachable)}, which the "
        f"{provenance} dynamic write range {_spans(derived)} never reaches"
    ]


def proven_post_init_writes(path: Path) -> frozenset[int]:
    """Cells a computed own-stack write provably reaches after the first `yield`.

    The first plain `yield` stands in for the publication boundary that
    `publication_errors` establishes, which its guard cases can move earlier but
    never later -- so every cell returned here is post-init under either reading.
    An access the bounds analysis cannot prove contributes nothing, which is what
    keeps this a floor rather than a derivation.
    """
    text = Path(path).read_text()
    aliases = collect_aliases([list(row.tokens) for row in parse_ic10(text).rows])[1]
    entries = parse_program(text)
    first_yield = next(
        (index for index, item in enumerate(entries) if item["row"][:1] == ["yield"]), None
    )
    if first_yield is None:
        return frozenset()
    accesses = [
        (index, "write", item["row"][1]) for index, item in enumerate(entries)
        if index > first_yield and item["row"][:1] == ["poke"] and len(item["row"]) >= 3
        and resolve_integer(item["row"][1], aliases) is None
    ]
    if not accesses:
        return frozenset()
    return frozenset(_range_cells(dynamic_range_proofs(text, aliases, accesses)["write"].ranges))


def post_init_coverage_errors(
    root: Path,
    declaration: NormalizedDeclaration,
    extension_cells: frozenset[int],
) -> list[str]:
    """A reviewed post-init dynamic write range names every cell the source proves.

    This is the containment rule's other half, and it is the half ownership rests
    on. `legacy_owned_ranges` is derived from the reviewed set, and an extension
    may be placed on any cell that set does not name -- so a range that is too
    small hands a future extension a cell the program overwrites every tick, which
    is a worse outcome than one that is too large.

    Only *proven* cells are asserted. An unproved computed write is exactly what
    the reviewed range exists to bound, so demanding coverage of it would be
    demanding the review the declaration already is. The first plain `yield` also
    stands in for the publication boundary, which the guard cases in
    `publication_errors` can move earlier but never later. Both keep this a floor
    under the declaration rather than a second derivation of it.

    A proven write into the envelope or an extension is reported separately,
    because naming those cells is what the reserved-overlap rule rejects: the
    program is wrong there, not the declaration.

    An absent declaration is left to `publication_errors` for the same reason its
    sibling containment rule leaves an absent dynamic write there. "Post-init
    dynamic own-stack writes lack reviewed, source-fingerprinted bounds" fires on
    exactly the condition that reaches here with nothing claimed, and it names the
    missing declaration; a span measured against a range that does not exist reads
    as though one does.
    """
    if not declaration.post_init_dynamic_write_ranges:
        return []
    proven = proven_post_init_writes(Path(root) / declaration.source)
    reserved = set(range(BASE, BASE + LENGTH)) | set(extension_cells)
    errors: list[str] = []
    if proven & reserved:
        errors.append(
            f"post-init computed writes provably reach reserved {_spans(proven & reserved)}"
        )
    claimed = set().union(*(item.cells() for item in declaration.post_init_dynamic_write_ranges))
    unnamed = proven - reserved - claimed
    if unnamed:
        errors.append(
            f"post-init computed writes provably reach {_spans(unnamed)}, which the reviewed"
            " post-init dynamic write range does not name and so does not own"
        )
    return errors


def publication_rule_errors(
    root: Path,
    declaration: NormalizedDeclaration,
    contract: dict[str, Any],
    published_cells: dict[int, Any],
    extension_cells: frozenset[int],
    writes: dict[int, set[Any]] | None = None,
    ignored_standard_bits: int = 0,
) -> list[str]:
    """Validate entry-path publication, reserved cells, and the line hard limit."""
    expected = expected_envelope_cells(declaration) | published_cells
    if writes is not None:
        expected[CAPABILITY_MASK_CELL] = capability_mask_for_validation(
            declaration, writes, ignored_standard_bits
        )
    reserved = set(range(BASE, BASE + LENGTH)) | set(extension_cells)
    errors = publication_errors(
        Path(root) / declaration.source,
        expected,
        declaration.publication_metadata(),
        reserved,
        # A boot-only `clr db` is the entry clear the publication scan already
        # validates; it is not evidence that reference-addressed writes can name
        # this stack. Computed own pokes still flag themselves directly.
        reference_writes_own_stack=bool(
            contract["own_stack"]["dynamic_write_ranges"]
            and not (contract["own_stack"]["clears_all"]
                     and contract["own_stack"]["dynamic_write_proven_ranges"]
                     == [{"start": 0, "end": 511}])
        ),
        mutable_cells=frozenset(
            ({STATE_CELL} if declaration.publishes_state else set())
            | ({GENERATION_CELL} if declaration.publishes_generation else set())
            | ({SCHEMA_ID_CELL} if declaration.schema_assigned_externally else set())
        ),
    )
    line_count = len((Path(root) / declaration.source).read_text().splitlines())
    if line_count > 128:
        errors.append(f"migrated pilot is {line_count} lines, above the 128-line hard limit")
    return errors


def declaration_set_errors(
    by_source: dict[str, dict[str, Any]],
    migrated: dict[str, Any],
    exemption: dict[str, Any],
) -> list[str]:
    """Validate declaration coverage and the immutable pre-v1 baseline."""
    errors: list[str] = []
    unknown = sorted(set(migrated) - set(by_source))
    if unknown:
        errors.append(f"migrated declarations reference missing scripts: {unknown}")
    shape_errors: list[str] = []
    for field_name in ("id", "reason", "migration_rule"):
        value = exemption.get(field_name)
        if not isinstance(value, str) or not value:
            shape_errors.append(f"legacy exemption {field_name} must be a nonempty string")
    declared_legacy = exemption.get("sources")
    if not isinstance(declared_legacy, list) or any(
        not isinstance(source, str) for source in declared_legacy
    ):
        shape_errors.append("legacy exemption sources must be an explicit path list")
    source_count = exemption.get("source_count")
    if type(source_count) is not int:
        shape_errors.append("legacy exemption source_count must be an integer")
    source_digest = exemption.get("source_set_sha256")
    if not isinstance(source_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", source_digest):
        shape_errors.append("legacy exemption source_set_sha256 must be a lowercase SHA-256 digest")
    if shape_errors:
        return errors + shape_errors
    if len(declared_legacy) != len(set(declared_legacy)):
        errors.append("legacy exemption source list contains duplicates")
    legacy_sources = sorted(set(declared_legacy))
    unclassified = sorted(set(by_source) - set(migrated) - set(legacy_sources))
    if unclassified:
        errors.append(
            "new deployable programs must publish the header or receive explicit "
            f"exemptions: {unclassified}"
        )
    if source_count != len(legacy_sources):
        errors.append(
            f"legacy baseline count {source_count} != baseline path count "
            f"{len(legacy_sources)}"
        )
    digest = legacy_source_digest(legacy_sources)
    if source_digest != digest:
        errors.append(
            "legacy exemption source set changed; migrate the new service or explicitly "
            "review and refresh the baseline"
        )
    if digest != PRE_V1_LEGACY_BASELINE_SHA256:
        errors.append("pre-v1 legacy baseline is immutable; new paths must publish the envelope")
    return errors


def declaration_errors(
    root: Path,
    contracts: dict[str, dict[str, Any]],
    declarations: dict[str, Any],
) -> list[str]:
    """Normalize declarations and run each independent validation rule in one pass."""
    root = Path(root)
    collector = ErrorCollector()
    if not isinstance(declarations, dict):
        return ["stack envelope declarations must be an object"]
    canonical = canonical_envelope()
    if declarations.get("envelope") != canonical:
        collector.add(f"envelope constants differ from the canonical v1 layout: {canonical}")
    by_source = {contract["source"]: contract for contract in contracts.values()}
    migrated = declarations.get("migrated")
    migrated_valid = "migrated" in declarations and isinstance(migrated, dict)
    if not migrated_valid:
        collector.add(
            "migrated declarations are required as an object keyed by source path"
            if "migrated" not in declarations
            else "migrated declarations must be an object keyed by source path"
        )
        migrated = {}

    exemption = declarations.get("legacy_exemption")
    exemption_valid = "legacy_exemption" in declarations and isinstance(exemption, dict)
    if not exemption_valid:
        collector.add(
            "legacy_exemption is required as an object"
            if "legacy_exemption" not in declarations
            else "legacy_exemption must be an object"
        )
        exemption = {}
    if migrated_valid and exemption_valid:
        collector.errors.extend(declaration_set_errors(by_source, migrated, exemption))

    participation = declarations.get("standard_participation")
    participation_errors = (
        standard_participation_errors(migrated, participation) if migrated_valid else []
    )
    collector.errors.extend(participation_errors)
    participation_by_source = standards_by_source(participation, set(migrated))
    unavailable_standards = unavailable_standard_capabilities(participation)
    ignored_standard_bits = sum(
        STANDARD_CAPABILITY_BITS_V1[standard] for standard in unavailable_standards
    )

    canonical_pairs = canonical_schema_pairs(root)
    service_ids: dict[str, str] = {}
    for source, raw_declaration in sorted(migrated.items()):
        if source not in by_source:
            continue
        declaration, shape_errors = normalize_declaration(
            source, raw_declaration, participation_by_source.get(source, frozenset())
        )
        collector.errors.extend(shape_errors)
        if declaration is None:
            continue
        service = ErrorCollector(source)
        if declaration.service_id in service_ids:
            collector.add(
                f"duplicate semantic service_id {declaration.service_id}: "
                f"{service_ids[declaration.service_id]} and {source}"
            )
        elif SERVICE_ID_RE.fullmatch(declaration.service_id):
            service_ids[declaration.service_id] = source

        contract = by_source[source]
        rows, aliases = _parse(root / source)
        writes = _writes(rows, aliases)
        service.extend(identity_header_errors(declaration, contract))
        service.extend(schema_capability_errors(
            declaration,
            _schema_check_pairs(rows, aliases) | canonical_pairs,
            writes,
            ignored_standard_bits,
        ))
        service.extend(state_generation_rule_errors(declaration, rows, aliases, writes))
        extension = extension_rule_result(declaration, writes)
        service.extend(list(extension.errors))
        service.extend(legacy_layout_errors(
            declaration, contract, extension.reserved_cells
        ))
        service.extend(post_init_range_errors(
            declaration, contract, extension.reserved_cells
        ))
        service.extend(post_init_coverage_errors(
            root, declaration, extension.reserved_cells
        ))
        service.extend(publication_rule_errors(
            root,
            declaration,
            contract,
            extension.published_cells,
            extension.reserved_cells,
            writes,
            ignored_standard_bits,
        ))
        collector.errors.extend(service.errors)
    return collector.errors


def build_inventory(
    root: Path,
    contracts: dict[str, dict[str, Any]],
    protocol_registry: dict[str, Any],
) -> dict[str, Any]:
    root = Path(root)
    declarations = load_declarations(root)
    errors = declaration_errors(root, contracts, declarations)
    if errors:
        raise DeclarationError(errors)
    migrated = declarations["migrated"]
    participation_by_source = standards_by_source(
        declarations["standard_participation"], set(migrated)
    )
    exemption = declarations["legacy_exemption"]
    window = set(range(BASE, BASE + LENGTH))
    reservable = set(range(BASE + 2, BASE + LENGTH))
    services = []
    for contract in sorted(contracts.values(), key=lambda item: item["source"]):
        source = contract["source"]
        own = contract["own_stack"]
        declaration = migrated.get(source)
        standard_capabilities = participation_by_source.get(source, frozenset())
        capability_mask = (
            derive_capability_mask(
                has_schema=(
                    declaration["schema_id"] is not None
                    or declaration.get("schema_assigned_externally", False)
                ),
                extension_base=declaration["extension_base"],
                publishes_state=declaration["publishes_state"],
                telemetry_base=declaration["telemetry_base"],
                publishes_generation=declaration["publishes_generation"],
                standard_capabilities=standard_capabilities,
            )
            if declaration else 0
        )
        externally_assigned_fields = (
            HAS_SCHEMA
            if declaration and declaration.get("schema_assigned_externally", False)
            else 0
        )
        literal = sorted(window & (set(own["literal_reads"]) | set(own["literal_writes"])))
        dynamic_read = sorted(window & _range_cells(own["dynamic_read_ranges"]))
        dynamic_write = sorted(window & _range_cells(own["dynamic_write_ranges"]))
        fields = own["fields"]
        literal_cells = set(own["literal_reads"]) | set(own["literal_writes"])
        headers = own["headers"]
        line_count = len((root / source).read_text().splitlines())
        entry: dict[str, Any] = {
            "source": source,
            "service_contract_id": contract["identity"]["service_id"],
            "deployment_family": contract["identity"]["deployment_family"],
            "status": "migrated-v1" if declaration else "legacy-exempt",
            "current_layout": {
                "headers": headers,
                "schema_fields": _schema_fields(contract, root / source),
                "payload_bases": sorted({header["base"] for header in headers}),
                "payload_inventory_status": (
                    "declared-stack-protocol" if headers else "no-declared-stack-protocol"
                ),
                "existing_consumer_checks": _consumer_checks(source, protocol_registry),
            },
            "stack_pressure": {
                "literal_cell_count": len(literal_cells),
                "highest_literal_cell": max(literal_cells, default=None),
                "dynamic_read_ranges": own["dynamic_read_ranges"],
                "dynamic_write_ranges": own["dynamic_write_ranges"],
                "line_count": line_count,
                "line_headroom_120": 120 - line_count,
                "measured_v1_publication_cost_lines": publication_cost_lines(
                    capability_mask, externally_assigned_fields
                ),
                "measured_v1_stack_cost_cells": LENGTH,
            },
            "window_collision": {
                "literal_cells": literal,
                "dynamic_read_cells": dynamic_read,
                "dynamic_write_cells": dynamic_write,
                "dynamic_read_provenance": own["dynamic_read_range_source"],
                "dynamic_write_provenance": own["dynamic_write_range_source"],
            },
        }
        if declaration:
            entry["envelope"] = {
                "service_id": declaration["service_id"],
                "contract": declaration["contract"],
                "magic": game_hash(header_name(declaration["contract"], declaration["service_abi"])),
                "magic_token": header_token(declaration["contract"], declaration["service_abi"]),
                "service_abi": declaration["service_abi"],
                "schema_id": declaration["schema_id"],
                "schema_id_hash": (
                    None if declaration["schema_id"] is None
                    else schema_hash_token(declaration["schema_id"], declaration["schema_version"])
                ),
                "schema_version": declaration["schema_version"],
                "schema_assigned_externally": declaration.get(
                    "schema_assigned_externally", False
                ),
                "extension_base": declaration["extension_base"],
                "telemetry_base": declaration["telemetry_base"],
                "publishes_state": declaration["publishes_state"],
                "custom_state_bits": declaration.get("custom_state_bits", 0),
                "publishes_generation": declaration["publishes_generation"],
                "standard_capabilities": sorted(standard_capabilities),
                "capability_mask": capability_mask,
                "extension_flags": declaration["extension_flags"],
                "implementation_id": declaration["implementation_id"],
                "implementation_id_hash": (
                    None if declaration["implementation_id"] is None
                    else f'HASH("{declaration["implementation_id"]}")'
                ),
                "publication_validation": {
                    "source_sha256": declaration["source_sha256"],
                    "entry_path": "straight-line-before-first-yield",
                    "legacy_owned_ranges": _declared_ranges(
                        declaration["legacy_owned_ranges"]
                    ),
                    "post_init_dynamic_write_ranges": _declared_ranges(
                        declaration["post_init_dynamic_write_ranges"]
                    ),
                },
                "pilot_family": declaration["pilot_family"],
            }
        else:
            entry["legacy_exemption"] = {
                "id": exemption["id"],
                "reason": exemption["reason"],
                "migration_rule": exemption["migration_rule"],
            }
        services.append(entry)
    return {
        "$schema": "../schemas/stack_envelope_inventory.schema.json",
        "format": FORMAT,
        "envelope": declarations["envelope"],
        "hash_namespace": {
            "service_id": "HASH(canonical semantic service contract id)",
            "schema_id": "HASH(canonical schema id), or 0 when not applicable",
            "implementation_id": "optional extension field; never derived from a versioned filename",
        },
        "totals": {
            "deployable_programs": len(services),
            "migrated_v1": sum(item["status"] == "migrated-v1" for item in services),
            "legacy_exempt": sum(item["status"] == "legacy-exempt" for item in services),
            "backlog_reserved_cell_users": sum(
                bool(set(item["window_collision"]["literal_cells"]) & reservable)
                for item in services if item["status"] == "legacy-exempt"
            ),
            "backlog_dynamic_range_users": sum(
                bool(item["window_collision"]["dynamic_read_cells"] or item["window_collision"]["dynamic_write_cells"])
                for item in services if item["status"] == "legacy-exempt"
            ),
        },
        "services": services,
    }
