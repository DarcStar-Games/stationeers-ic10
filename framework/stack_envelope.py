"""Build and validate the fixed-address IC10 stack-envelope inventory."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
from typing import Any

from framework.ic10_source import parse_ic10
from framework.script_contracts.parsing import collect_aliases, resolve_integer, resolve_literal
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
CAPABILITY_BITS_V1 = (
    HAS_SCHEMA | HAS_EXTENSION | HAS_STATE | HAS_TELEMETRY | HAS_GENERATION
)
STATE_VALUES = (0, 1, 2, 3, 4, 5)
STATE_FIELD_MASK = 0xF          # bits 0..3 carry the state, one value at a time
STATE_RESERVED_MASK = 0xF0      # bits 4..7 are reserved for future universal flags
CUSTOM_STATE_SHIFT = 8          # bits 8.. are service-specific and opaque to readers
VALUE_BITS = 53                 # a stack cell is a double: exact integers to 2**53


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


def legacy_source_digest(sources: list[str]) -> str:
    payload = "".join(f"{source}\n" for source in sorted(sources)).encode()
    return hashlib.sha256(payload).hexdigest()


def load_declarations(root: Path) -> dict[str, Any]:
    document = json.loads((Path(root) / "data" / "stack_envelope_declarations.json").read_text())
    if document.get("format") != DECLARATION_FORMAT:
        raise ValueError(f"unsupported stack envelope declaration format: {document.get('format')!r}")
    return document


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
                value = resolve_literal(later[2], aliases)
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


def schema_hash(schema_id: str, schema_version: int) -> str:
    """The published schema identity carries its version: one cell, one exact match."""
    return 'HASH("' + f"{schema_id}.v{schema_version}" + '")'


def _range_cells(ranges: list[dict[str, int]]) -> set[int]:
    return {cell for item in ranges for cell in range(item["start"], item["end"] + 1)}


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
    for address, values in sorted(writes.items()):
        for value in values:
            match = HASH_RE.fullmatch(value) if isinstance(value, str) else None
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
    ranges = []
    for item in value or []:
        if not isinstance(item, list) or len(item) != 2 or not all(isinstance(cell, int) for cell in item):
            raise ValueError(f"invalid reviewed dynamic range: {item!r}")
        start, end = item
        if not 0 <= start <= end <= 511:
            raise ValueError(f"reviewed dynamic range outside S0..S511: {item!r}")
        ranges.append({"start": start, "end": end})
    return ranges


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
                errors.append("control transfer occurs before the first envelope-bearing yield")
            branch_proved = not missing
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
    if first_yield is not None:
        for row in rows[first_yield + 1:]:
            op = row[0]
            if op == "clr" and len(row) >= 2 and row[1] == "db":
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


def declaration_errors(
    root: Path,
    contracts: dict[str, dict[str, Any]],
    declarations: dict[str, Any],
) -> list[str]:
    root = Path(root)
    errors: list[str] = []
    canonical = {
        "base": BASE,
        "length": LENGTH,
        "capability_bits_v1": CAPABILITY_BITS_V1,
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
    if declarations.get("envelope") != canonical:
        errors.append(f"envelope constants differ from the canonical v1 layout: {canonical}")
    by_source = {contract["source"]: contract for contract in contracts.values()}
    migrated = declarations.get("migrated", {})
    unknown = sorted(set(migrated) - set(by_source))
    if unknown:
        errors.append(f"migrated declarations reference missing scripts: {unknown}")
    exemption = declarations.get("legacy_exemption", {})
    declared_legacy = exemption.get("sources", [])
    if not isinstance(declared_legacy, list) or any(not isinstance(source, str) for source in declared_legacy):
        errors.append("legacy exemption sources must be an explicit path list")
        declared_legacy = []
    if len(declared_legacy) != len(set(declared_legacy)):
        errors.append("legacy exemption source list contains duplicates")
    legacy_sources = sorted(set(declared_legacy))
    unclassified = sorted(set(by_source) - set(migrated) - set(legacy_sources))
    if unclassified:
        errors.append(f"new deployable programs must publish the header or receive explicit exemptions: {unclassified}")
    if exemption.get("source_count") != len(legacy_sources):
        errors.append(
            f"legacy baseline count {exemption.get('source_count')} != baseline path count {len(legacy_sources)}"
        )
    digest = legacy_source_digest(legacy_sources)
    if exemption.get("source_set_sha256") != digest:
        errors.append(
            "legacy exemption source set changed; migrate the new service or explicitly review and refresh the baseline"
        )
    if digest != PRE_V1_LEGACY_BASELINE_SHA256:
        errors.append("pre-v1 legacy baseline is immutable; new paths must publish the envelope")
    canonical_pairs = canonical_schema_pairs(root)
    service_ids: dict[str, str] = {}
    for source, declaration in sorted(migrated.items()):
        if source not in by_source:
            continue
        service_id = declaration.get("service_id")
        if not isinstance(service_id, str) or not SERVICE_ID_RE.fullmatch(service_id):
            errors.append(f"{source}: invalid semantic service_id {service_id!r}")
        elif service_id in service_ids:
            errors.append(f"duplicate semantic service_id {service_id}: {service_ids[service_id]} and {source}")
        else:
            service_ids[service_id] = source
        canonical_service_id = by_source[source]["identity"]["service_id"]
        if service_id != canonical_service_id:
            errors.append(
                f"{source}: service_id {service_id!r} != canonical contract identity {canonical_service_id!r}"
            )
        magic_value = declaration.get("magic")
        service_abi_value = declaration.get("service_abi")
        schema_version_value = declaration.get("schema_version")
        extension_base_value = declaration.get("extension_base")
        magic = magic_value if type(magic_value) is int else 0
        service_abi = service_abi_value if type(service_abi_value) is int else 0
        schema_id = declaration.get("schema_id")
        schema_version = schema_version_value if type(schema_version_value) is int else -1
        extension_base = extension_base_value if type(extension_base_value) is int else -1
        extension_flags_value = declaration.get("extension_flags", -1)
        extension_flags = extension_flags_value if type(extension_flags_value) is int else -1
        implementation_id = declaration.get("implementation_id")
        telemetry_base_value = declaration.get("telemetry_base")
        telemetry_base = telemetry_base_value if type(telemetry_base_value) is int else -1
        publishes_state = declaration.get("publishes_state")
        publishes_generation = declaration.get("publishes_generation")
        if type(magic_value) is not int or magic == 0:
            errors.append(f"{source}: magic must be the service's registered nonzero integer")
        if type(service_abi_value) is not int or service_abi < 1:
            errors.append(f"{source}: service_abi must be a positive integer")
        if type(schema_version_value) is not int:
            errors.append(f"{source}: schema_version must be an integer")
        if type(extension_base_value) is not int:
            errors.append(f"{source}: extension_base must be an integer")
        if type(telemetry_base_value) is not int or not 0 <= telemetry_base <= 511:
            errors.append(f"{source}: telemetry_base must be an integer in S0..S511")
        if type(publishes_state) is not bool:
            errors.append(f"{source}: publishes_state must be a boolean")
        if type(publishes_generation) is not bool:
            errors.append(f"{source}: publishes_generation must be a boolean")
        if telemetry_base and telemetry_base < BASE + LENGTH:
            errors.append(f"{source}: telemetry_base cannot point inside the common header")
        if schema_id is not None and (not isinstance(schema_id, str) or not schema_id):
            errors.append(f"{source}: schema_id must be null or a nonempty semantic hash name")
        if (schema_id is None) != (schema_version == 0):
            errors.append(f"{source}: schema_id and schema_version must both be absent/zero or both present")
        headers = by_source[source]["own_stack"]["headers"]
        if not any(
            header["base"] == BASE and header["magic"] == magic and header["abi"] == service_abi
            for header in headers
        ):
            errors.append(f"{source}: S0/S1 do not publish the declared magic and ABI as a verified header")
        source_rows, source_aliases = _parse(root / source)
        writes = _writes(source_rows, source_aliases)
        bound_schema_pairs = _schema_check_pairs(source_rows, source_aliases) | canonical_pairs
        if schema_id is not None and (
            f'HASH("{schema_id}")', schema_version
        ) not in bound_schema_pairs:
            errors.append(f"{source}: schema/version is not canonical and is not verified by this source")
        if extension_base and not 0 <= extension_base <= 511 - EXTENSION_MIN_LENGTH + 1:
            errors.append(f"{source}: extension base cannot fit the minimum extension header")
        if type(extension_flags_value) is not int or extension_flags < 0 or extension_flags & ~1:
            errors.append(f"{source}: extension_flags may use only v1 HAS_IMPLEMENTATION_ID bit 0")
        if extension_base == 0 and (extension_flags != 0 or implementation_id is not None):
            errors.append(f"{source}: absent extension requires zero flags and no ImplementationId")
        if extension_flags & 1:
            if not isinstance(implementation_id, str) or not IMPLEMENTATION_ID_RE.fullmatch(implementation_id):
                errors.append(f"{source}: HAS_IMPLEMENTATION_ID requires a semantic ic10.implementation.* identity")
        elif implementation_id is not None:
            errors.append(f"{source}: ImplementationId requires HAS_IMPLEMENTATION_ID")
        try:
            legacy_owned_ranges = _declared_ranges(declaration.get("legacy_owned_ranges"))
        except ValueError as error:
            errors.append(f"{source}: {error}")
            legacy_owned_ranges = []
        capability_mask = (
            (HAS_SCHEMA if schema_id is not None else 0)
            | (HAS_EXTENSION if extension_base else 0)
            | (HAS_STATE if publishes_state is True else 0)
            | (HAS_TELEMETRY if telemetry_base else 0)
            | (HAS_GENERATION if publishes_generation is True else 0)
        )
        expected: dict[int, Any] = {
            BASE: magic,
            BASE + 1: service_abi,
            CAPABILITY_MASK_CELL: capability_mask,
        }
        if capability_mask & HAS_SCHEMA:
            expected[SCHEMA_ID_CELL] = schema_hash(schema_id, schema_version)
        if capability_mask & HAS_EXTENSION:
            expected[EXTENSION_BASE_CELL] = extension_base
        if capability_mask & HAS_TELEMETRY:
            expected[TELEMETRY_BASE_CELL] = telemetry_base
        if capability_mask & HAS_GENERATION:
            expected[GENERATION_CELL] = 0
        errors.extend(
            f"{source}: {error}"
            for error in generation_errors(
                source_rows, source_aliases, bool(capability_mask & HAS_GENERATION)
            )
        )
        state_writes = writes.get(STATE_CELL, set())
        custom_state_bits = declaration.get("custom_state_bits", 0)
        if type(custom_state_bits) is not int or not 0 <= custom_state_bits < 2 ** (
            VALUE_BITS - CUSTOM_STATE_SHIFT
        ):
            errors.append(f"{source}: custom_state_bits must fit the service-specific state range")
            custom_state_bits = 0
        if capability_mask & HAS_STATE:
            if not state_writes:
                errors.append(f"{source}: HAS_STATE requires the source to publish S{STATE_CELL}")
            errors.extend(
                f"{source}: {error}" for error in state_errors(state_writes, custom_state_bits)
            )
        elif custom_state_bits:
            errors.append(f"{source}: custom state bits require HAS_STATE")
        elif state_writes:
            errors.append(f"{source}: S{STATE_CELL} is reserved unless the service declares HAS_STATE")
        for cell in range(BASE, BASE + LENGTH):
            if cell not in expected and cell not in (STATE_CELL, GENERATION_CELL) and writes.get(cell):
                errors.append(f"{source}: S{cell} is reserved and must not be written undeclared")
        published_expected = dict(expected)
        reserved_cells = set(range(BASE, BASE + LENGTH))
        extension_cells: set[int] = set()
        for address, value in expected.items():
            written = writes.get(address, set())
            if address == GENERATION_CELL:
                # a generation starts at zero — written, or cleared with the whole stack —
                # and only ever advances dynamically after that
                initialized = value in written or clears_before_yield(source_rows)
                if not initialized or any(other is not None for other in written - {value}):
                    errors.append(
                        f"{source}: S{address} must be initialized to {value} and only advanced dynamically"
                    )
            elif written != {value}:
                errors.append(f"{source}: S{address} must be written exactly as {value}")
        if extension_base:
            for address, value in {
                extension_base: EXTENSION_MAGIC,
                extension_base + 1: EXTENSION_VERSION,
                extension_base + 3: extension_flags,
            }.items():
                if writes.get(address) != {value}:
                    errors.append(f"{source}: extension S{address} must be written exactly as {value}")
            lengths = writes.get(extension_base + 2, set())
            if len(lengths) != 1 or not isinstance(next(iter(lengths), None), int):
                errors.append(f"{source}: extension length must be one literal integer")
            else:
                extension_length = next(iter(lengths))
                extension_end = extension_base + extension_length
                published_expected.update({
                    extension_base: EXTENSION_MAGIC,
                    extension_base + 1: EXTENSION_VERSION,
                    extension_base + 2: extension_length,
                    extension_base + 3: extension_flags,
                })
                if 0 <= extension_base < extension_end <= 512:
                    extension_cells = set(range(extension_base, extension_end))
                    reserved_cells.update(extension_cells)
                    errors.extend(
                        f"{source}: {error}"
                        for error in extension_ownership_errors(
                            legacy_owned_ranges, extension_base, extension_length
                        )
                    )
                if not EXTENSION_MIN_LENGTH <= extension_length <= EXTENSION_MAX_LENGTH:
                    errors.append(f"{source}: extension length is outside v1 bounds")
                if extension_end > 512:
                    errors.append(f"{source}: extension exceeds the 512-cell stack")
                if extension_base < BASE + LENGTH:
                    errors.append(f"{source}: extension overlaps the fixed header")
                if extension_flags & 1:
                    if extension_length < 5:
                        errors.append(f"{source}: HAS_IMPLEMENTATION_ID extension is shorter than five cells")
                    implementation_value = f'HASH("{implementation_id}")'
                    published_expected[extension_base + 4] = implementation_value
                    if writes.get(extension_base + 4) != {implementation_value}:
                        errors.append(
                            f"{source}: extension ImplementationId must be written exactly as {implementation_value}"
                        )
        actual_legacy_cells = (
            set(by_source[source]["own_stack"]["literal_reads"])
            | set(by_source[source]["own_stack"]["literal_writes"])
        ) - set(range(BASE, BASE + LENGTH)) - extension_cells
        try:
            reviewed_dynamic_ranges = _declared_ranges(
                declaration.get("post_init_dynamic_write_ranges", [])
            )
        except ValueError:
            reviewed_dynamic_ranges = []
        actual_legacy_cells.update(_range_cells(reviewed_dynamic_ranges))
        if actual_legacy_cells != _range_cells(legacy_owned_ranges):
            errors.append(f"{source}: legacy_owned_ranges no longer match the pre-extension stack layout")
        errors.extend(
            f"{source}: {error}"
            for error in publication_errors(
                root / source, published_expected, declaration, reserved_cells,
                reference_writes_own_stack=bool(
                    by_source[source]["own_stack"]["dynamic_write_ranges"]
                ),
                mutable_cells=frozenset(
                    ({STATE_CELL} if capability_mask & HAS_STATE else set())
                    | ({GENERATION_CELL} if capability_mask & HAS_GENERATION else set())
                ),
            )
        )
        # validate_ic10.py owns the 120-line soft ceiling and its reviewed exemptions.
        line_count = len((root / source).read_text().splitlines())
        if line_count > 128:
            errors.append(f"{source}: migrated pilot is {line_count} lines, above the 128-line hard limit")
    return errors


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
    exemption = declarations["legacy_exemption"]
    window = set(range(BASE, BASE + LENGTH))
    reservable = set(range(BASE + 2, BASE + LENGTH))
    services = []
    for contract in sorted(contracts.values(), key=lambda item: item["source"]):
        source = contract["source"]
        own = contract["own_stack"]
        declaration = migrated.get(source)
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
                "measured_v1_publication_cost_lines": LENGTH,
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
                "magic": declaration["magic"],
                "service_abi": declaration["service_abi"],
                "schema_id": declaration["schema_id"],
                "schema_id_hash": (
                    None if declaration["schema_id"] is None
                    else schema_hash(declaration["schema_id"], declaration["schema_version"])
                ),
                "schema_version": declaration["schema_version"],
                "extension_base": declaration["extension_base"],
                "telemetry_base": declaration["telemetry_base"],
                "publishes_state": declaration["publishes_state"],
                "custom_state_bits": declaration.get("custom_state_bits", 0),
                "publishes_generation": declaration["publishes_generation"],
                "capability_mask": (
                    (HAS_SCHEMA if declaration["schema_id"] is not None else 0)
                    | (HAS_EXTENSION if declaration["extension_base"] else 0)
                    | (HAS_STATE if declaration["publishes_state"] else 0)
                    | (HAS_TELEMETRY if declaration["telemetry_base"] else 0)
                    | (HAS_GENERATION if declaration["publishes_generation"] else 0)
                ),
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
