"""Immutable, import-safe manifest for the repository validation suite."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math
from numbers import Real
from pathlib import Path, PurePosixPath
import re


VALIDATOR_CATEGORY = "validator"
TEST_CATEGORY = "test"
VALID_CATEGORIES = frozenset({VALIDATOR_CATEGORY, TEST_CATEGORY})
DEFAULT_TIMEOUT_SECONDS = 90
_EVIDENCE_ID = re.compile(r"[A-Z][A-Z0-9_]*")


@dataclass(frozen=True, slots=True)
class SuiteEntry:
    """One explicitly registered, independently executed suite script."""

    path: str
    category: str
    evidence_id: str
    timeout_seconds: int | float = DEFAULT_TIMEOUT_SECONDS

    @property
    def evidence_filename(self) -> str:
        return f"{self.evidence_id}.txt"


class SuiteManifestError(ValueError):
    """Raised when suite registration is ambiguous or cannot be executed."""


SUITE_ENTRIES = (
    SuiteEntry("validation/validators/validate_abi_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_ABI_CONTRACTS"),
    SuiteEntry("validation/validators/validate_async_request_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_ASYNC_REQUEST_CONTRACTS"),
    SuiteEntry("validation/validators/validate_banked_transaction_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_BANKED_TRANSACTION_CONTRACTS"),
    SuiteEntry("validation/validators/validate_catalog_storage.py", VALIDATOR_CATEGORY, "VALIDATE_CATALOG_STORAGE"),
    SuiteEntry("validation/validators/validate_config_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_CONFIG_CONTRACTS"),
    SuiteEntry("validation/validators/validate_dependency_planning_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_DEPENDENCY_PLANNING_CONTRACTS"),
    SuiteEntry("validation/validators/validate_directory_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_DIRECTORY_CONTRACTS"),
    SuiteEntry("validation/validators/validate_documentation.py", VALIDATOR_CATEGORY, "VALIDATE_DOCUMENTATION"),
    SuiteEntry("validation/validators/validate_ic10.py", VALIDATOR_CATEGORY, "VALIDATE_IC10"),
    SuiteEntry("validation/validators/validate_ic10_opcodes.py", VALIDATOR_CATEGORY, "VALIDATE_IC10_OPCODES"),
    SuiteEntry("validation/validators/validate_input_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_INPUT_CONTRACTS"),
    SuiteEntry("validation/validators/validate_job_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_JOB_CONTRACTS"),
    SuiteEntry("validation/validators/validate_manufacturing_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_MANUFACTURING_CONTRACTS"),
    SuiteEntry("validation/validators/validate_power_management_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_POWER_MANAGEMENT_CONTRACTS"),
    SuiteEntry("validation/validators/validate_fault_injection_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_FAULT_INJECTION_CONTRACTS"),
    SuiteEntry("validation/validators/validate_release_tooling.py", VALIDATOR_CATEGORY, "VALIDATE_RELEASE_TOOLING"),
    SuiteEntry("validation/validators/validate_generated_directory_adapters.py", VALIDATOR_CATEGORY, "VALIDATE_GENERATED_DIRECTORY_ADAPTERS"),
    SuiteEntry("validation/validators/validate_script_headers.py", VALIDATOR_CATEGORY, "VALIDATE_SCRIPT_HEADERS"),
    SuiteEntry("validation/validators/validate_scan_coverage.py", VALIDATOR_CATEGORY, "VALIDATE_SCAN_COVERAGE"),
    SuiteEntry("validation/validators/validate_source_catalog.py", VALIDATOR_CATEGORY, "VALIDATE_SOURCE_CATALOG"),
    SuiteEntry("validation/validators/validate_stock_target_ingress_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_STOCK_TARGET_INGRESS_CONTRACTS"),
    SuiteEntry("validation/validators/validate_script_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_SCRIPT_CONTRACTS"),
    SuiteEntry("validation/validators/validate_script_wiring.py", VALIDATOR_CATEGORY, "VALIDATE_SCRIPT_WIRING"),
    SuiteEntry("validation/validators/validate_service_identity.py", VALIDATOR_CATEGORY, "VALIDATE_SERVICE_IDENTITY"),
    SuiteEntry("validation/validators/validate_stack_envelopes.py", VALIDATOR_CATEGORY, "VALIDATE_STACK_ENVELOPES"),
    SuiteEntry("validation/validators/validate_user_deployment_guide.py", VALIDATOR_CATEGORY, "VALIDATE_USER_DEPLOYMENT_GUIDE"),
    SuiteEntry("validation/validators/validate_item_storage_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_ITEM_STORAGE_CONTRACTS"),
    SuiteEntry("validation/validators/validate_process_utility_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_PROCESS_UTILITY_CONTRACTS"),
    SuiteEntry("validation/validators/validate_live_commissioning_contracts.py", VALIDATOR_CATEGORY, "VALIDATE_LIVE_COMMISSIONING_CONTRACTS"),
    SuiteEntry("tests/test_async_request.py", TEST_CATEGORY, "TEST_ASYNC_REQUEST"),
    SuiteEntry("tests/test_banked_transaction.py", TEST_CATEGORY, "TEST_BANKED_TRANSACTION"),
    SuiteEntry("tests/test_catalog_schema.py", TEST_CATEGORY, "TEST_CATALOG_SCHEMA"),
    SuiteEntry("tests/test_controller_directory_scale.py", TEST_CATEGORY, "TEST_CONTROLLER_DIRECTORY_SCALE"),
    SuiteEntry("tests/test_dependency_planning.py", TEST_CATEGORY, "TEST_DEPENDENCY_PLANNING"),
    SuiteEntry("tests/test_stock_target_ingress.py", TEST_CATEGORY, "TEST_STOCK_TARGET_INGRESS"),
    SuiteEntry("tests/test_diagnostics_execution.py", TEST_CATEGORY, "TEST_DIAGNOSTICS_EXECUTION"),
    SuiteEntry("tests/test_generic_directory.py", TEST_CATEGORY, "TEST_GENERIC_DIRECTORY"),
    SuiteEntry("tests/test_ic10_execution.py", TEST_CATEGORY, "TEST_IC10_EXECUTION"),
    SuiteEntry("tests/test_ic10_opcode_handlers.py", TEST_CATEGORY, "TEST_IC10_OPCODE_HANDLERS"),
    SuiteEntry("tests/test_input_profiles.py", TEST_CATEGORY, "TEST_INPUT_PROFILES"),
    SuiteEntry("tests/test_job_abi.py", TEST_CATEGORY, "TEST_JOB_ABI"),
    SuiteEntry("tests/test_manufacturing_execution.py", TEST_CATEGORY, "TEST_MANUFACTURING_EXECUTION"),
    SuiteEntry("tests/test_manufacturing_scheduler.py", TEST_CATEGORY, "TEST_MANUFACTURING_SCHEDULER"),
    SuiteEntry("tests/test_material_grid_protocol.py", TEST_CATEGORY, "TEST_MATERIAL_GRID_PROTOCOL"),
    SuiteEntry("tests/test_script_contracts.py", TEST_CATEGORY, "TEST_SCRIPT_CONTRACTS"),
    SuiteEntry("tests/test_material_transform_protocol.py", TEST_CATEGORY, "TEST_MATERIAL_TRANSFORM_PROTOCOL"),
    SuiteEntry("tests/test_persistence_protocol.py", TEST_CATEGORY, "TEST_PERSISTENCE_PROTOCOL"),
    SuiteEntry("tests/test_phase_pressure_protocol.py", TEST_CATEGORY, "TEST_PHASE_PRESSURE_PROTOCOL"),
    SuiteEntry("tests/test_pressure_domain_protocol.py", TEST_CATEGORY, "TEST_PRESSURE_DOMAIN_PROTOCOL"),
    SuiteEntry("tests/test_pressure_grid_protocol.py", TEST_CATEGORY, "TEST_PRESSURE_GRID_PROTOCOL"),
    SuiteEntry("tests/test_pressure_inventory_protocol.py", TEST_CATEGORY, "TEST_PRESSURE_INVENTORY_PROTOCOL"),
    SuiteEntry("tests/test_validation_helpers.py", TEST_CATEGORY, "TEST_VALIDATION_HELPERS"),
    SuiteEntry("tests/test_repository_inventory.py", TEST_CATEGORY, "TEST_REPOSITORY_INVENTORY"),
    SuiteEntry("tests/test_commission_wiring.py", TEST_CATEGORY, "TEST_COMMISSION_WIRING"),
    SuiteEntry("tests/test_commissioning_validators.py", TEST_CATEGORY, "TEST_COMMISSIONING_VALIDATORS"),
    SuiteEntry("tests/test_pressure_reservation_protocol.py", TEST_CATEGORY, "TEST_PRESSURE_RESERVATION_PROTOCOL"),
    SuiteEntry("tests/test_pressure_route_cost.py", TEST_CATEGORY, "TEST_PRESSURE_ROUTE_COST"),
    SuiteEntry("tests/test_printer_directory.py", TEST_CATEGORY, "TEST_PRINTER_DIRECTORY"),
    SuiteEntry("tests/test_script_wiring.py", TEST_CATEGORY, "TEST_SCRIPT_WIRING"),
    SuiteEntry("tests/test_stack_envelope.py", TEST_CATEGORY, "TEST_STACK_ENVELOPE"),
    SuiteEntry("tests/test_printer_execution_capacity.py", TEST_CATEGORY, "TEST_PRINTER_EXECUTION_CAPACITY"),
    SuiteEntry("tests/test_recipe_catalog.py", TEST_CATEGORY, "TEST_RECIPE_CATALOG"),
    SuiteEntry("tests/test_generator_productivity.py", TEST_CATEGORY, "TEST_GENERATOR_PRODUCTIVITY"),
    SuiteEntry("tests/test_resource_generalization.py", TEST_CATEGORY, "TEST_RESOURCE_GENERALIZATION"),
    SuiteEntry("tests/test_resource_profiles.py", TEST_CATEGORY, "TEST_RESOURCE_PROFILES"),
    SuiteEntry("tests/test_resource_transforms.py", TEST_CATEGORY, "TEST_RESOURCE_TRANSFORMS"),
    SuiteEntry("tests/test_sequencer_protocol.py", TEST_CATEGORY, "TEST_SEQUENCER_PROTOCOL"),
    SuiteEntry("tests/test_shared_input_protocol.py", TEST_CATEGORY, "TEST_SHARED_INPUT_PROTOCOL"),
    SuiteEntry("tests/test_item_storage_protocol.py", TEST_CATEGORY, "TEST_ITEM_STORAGE_PROTOCOL"),
    SuiteEntry("tests/test_power_management.py", TEST_CATEGORY, "TEST_POWER_MANAGEMENT"),
    SuiteEntry("tests/test_fault_injection.py", TEST_CATEGORY, "TEST_FAULT_INJECTION"),
    SuiteEntry("tests/test_process_utility.py", TEST_CATEGORY, "TEST_PROCESS_UTILITY"),
    SuiteEntry("tests/test_live_commissioning.py", TEST_CATEGORY, "TEST_LIVE_COMMISSIONING"),
    SuiteEntry("tests/test_game_export.py", TEST_CATEGORY, "TEST_GAME_EXPORT"),
)


def validate_suite_entries(entries: Iterable[SuiteEntry], root: Path) -> tuple[SuiteEntry, ...]:
    """Validate and return ``entries`` without changing their declared order."""
    entries = tuple(entries)
    root = Path(root)
    failures: list[str] = []
    paths: dict[str, int] = {}
    evidence_ids: dict[str, int] = {}

    if not entries:
        failures.append("suite must register at least one script")

    for index, entry in enumerate(entries):
        label = f"entry {index + 1}"
        if not isinstance(entry, SuiteEntry):
            failures.append(f"{label} is not a SuiteEntry")
            continue

        if isinstance(entry.path, str):
            relative = PurePosixPath(entry.path)
            path_valid = bool(entry.path) and entry.path == relative.as_posix()
            path_valid = path_valid and not relative.is_absolute() and ".." not in relative.parts
        else:
            relative = None
            path_valid = False
        if not path_valid:
            failures.append(f"{label} has invalid repository-relative path {entry.path!r}")
        elif not (root / Path(*relative.parts)).is_file():
            failures.append(f"{entry.path}: registered script does not exist")

        if isinstance(entry.path, str):
            if entry.path in paths:
                failures.append(f"{entry.path}: duplicate path (entries {paths[entry.path]} and {index + 1})")
            else:
                paths[entry.path] = index + 1

        if not isinstance(entry.category, str) or entry.category not in VALID_CATEGORIES:
            failures.append(f"{entry.path}: invalid category {entry.category!r}")

        if not isinstance(entry.evidence_id, str) or not _EVIDENCE_ID.fullmatch(entry.evidence_id):
            failures.append(f"{entry.path}: invalid evidence identifier {entry.evidence_id!r}")
        elif entry.evidence_id in evidence_ids:
            failures.append(
                f"{entry.path}: duplicate evidence identifier {entry.evidence_id!r} "
                f"(entries {evidence_ids[entry.evidence_id]} and {index + 1})"
            )
        else:
            evidence_ids[entry.evidence_id] = index + 1

        timeout = entry.timeout_seconds
        try:
            timeout_valid = (
                not isinstance(timeout, bool)
                and isinstance(timeout, Real)
                and timeout > 0
                and math.isfinite(float(timeout))
            )
        except (OverflowError, TypeError, ValueError):
            timeout_valid = False
        if not timeout_valid:
            failures.append(f"{entry.path}: timeout must be a positive finite number, got {timeout!r}")

    if failures:
        raise SuiteManifestError("invalid validation suite manifest:\n - " + "\n - ".join(failures))
    return entries


def suite_entries(root: Path) -> tuple[SuiteEntry, ...]:
    """Return the complete validated suite in execution order."""
    return validate_suite_entries(SUITE_ENTRIES, root)


def category_entries(root: Path, category: str) -> tuple[SuiteEntry, ...]:
    """Return one validated category subset in suite order."""
    if category not in VALID_CATEGORIES:
        raise SuiteManifestError(f"invalid validation suite category: {category!r}")
    return tuple(entry for entry in suite_entries(root) if entry.category == category)


def validator_entries(root: Path) -> tuple[SuiteEntry, ...]:
    return category_entries(root, VALIDATOR_CATEGORY)


def test_entries(root: Path) -> tuple[SuiteEntry, ...]:
    return category_entries(root, TEST_CATEGORY)
