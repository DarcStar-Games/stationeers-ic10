#!/usr/bin/env python3
"""Static size/style/label checks for the IC10 scripts in this directory."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import re
import sys

from framework.ic10_source import parse_ic10

ROOT = _PROJECT_ROOT
LIMIT_LINES = 128
LIMIT_CHARS = 90
LIMIT_BYTES = 4096
MAINTAINABILITY_LINES = 120
# Reviewed spends of the deliberate 120..128 margin. The hard limit still applies.
SOFT_LIMIT_EXEMPTIONS = {
    "ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10":
        "capability-fenced transform view publishing the common header above a 60-cell"
        " resolved-request table",
    "ic10/material-transform/material_transform_admission_v1_0.ic10":
        "admission gate re-checking the transform view's echo/status/generation fence after"
        " every payload read",
    "ic10/material-transform/material_transform_link_resolver_v1_0.ic10":
        "link resolver re-checking the transform view's echo/status/generation fence after"
        " its input-descriptor loop",
    "ic10/manufacturing/print_candidate_executor_v2_0.ic10":
        "four-phase print launch fencing four devices; publishes the common header with its"
        " request mailbox relocated above it",
    "ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10":
        "operator-facing editor wiring six diagnostic devices; publishes the common header"
        " with its payload relocated above it",
    "ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10":
        "publishes the common S0 header; its Generic Telemetry block stays at S96",
    "ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10":
        "publishes the common S0 header; its Generic Telemetry block stays at S96",
    "ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10":
        "publishes the common S0 header; its Generic Telemetry block stays at S96",
    "ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10":
        "publishes the common S0 header; its Generic Telemetry block stays at S96",
    "ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10":
        "publishes the common S0 header; its Generic Telemetry block stays at S96",
    "ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10":
        "publishes the common S0 header with its Feeder ABI1 payload relocated above it",
    "ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10":
        "publishes the common S0 header with its Feeder ABI1 payload relocated above it",
    "ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10":
        "publishes the common S0 header with its Endpoint ABI1 payload relocated above it",
    "ic10/controller-config/generic_persistent_config_host_v1_1.ic10":
        "publishes the common S0 header above its banked A/B config storage",
    "ic10/controller-config/generic_config_loader_v1_2.ic10":
        "gains the common S0 header and a newly registered service magic",
    "ic10/printer-directory/printer_execution_bank_v2_0.ic10":
        "publishes the common S0 header above its six-pin ownership arrays",
    "ic10/printer-directory/printer_capacity_client_v2_0.ic10":
        "publishes the common S0 header with its request mailbox relocated above it",
    "ic10/generic-jobs/generic_job_store_v1_0.ic10":
        "publishes the common S0 header above its 32-slot durable job records",
    "ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10":
        "publishes the common S0 header above its four producer lanes",
    "ic10/generic-jobs/generic_job_selector_v3_0.ic10":
        "publishes the common S0 header with its request mailbox relocated above it",
}


def inspect(path: Path):
    text = path.read_text()
    parsed = parse_ic10(text)
    lines = [line.raw_text for line in parsed.lines]
    max_len = max((len(line) for line in lines), default=0)
    crlf_bytes = len(("\r\n".join(lines) + "\r\n").encode())
    comment_lines = sum("#" in line for line in lines)

    labels = {}
    duplicates = []
    relative_branches = []
    for label in parsed.labels:
        name = label.name
        n = label.line.number
        if name in labels:
            duplicates.append((name, labels[name], n))
        else:
            labels[name] = n
    for row in parsed.rows:
        if row.opcode.startswith("br"):
            relative_branches.append((row.line.number, row.opcode))
    malformed_labels = [
        (diagnostic.line_number, diagnostic.message)
        for diagnostic in parsed.diagnostics
        if diagnostic.code == "malformed-label"
    ]

    invalid_registers = []
    invalid_devices = []
    invalid_stack_addresses = []
    invalid_direct_stack_operands = []
    tokens_by_line = {row.line.number: row.tokens for row in parsed.rows}
    for line in parsed.lines:
        n = line.number
        code = line.code_text
        for value in re.findall(r"\br(\d+)\b", code):
            if int(value) > 15:
                invalid_registers.append((n, f"r{value}"))
        for value in re.findall(r"\bd(\d+)\b", code):
            if int(value) > 5:
                invalid_devices.append((n, f"d{value}"))
        tokens = tokens_by_line.get(n, ())
        if tokens:
            op = tokens[0]
            if op in {"add","sub","mul","div","min","max","pow","and","or","sll"} and "db" in tokens[1:]:
                invalid_direct_stack_operands.append((n, code.strip()))
            pos = {"poke": 1, "get": 3, "getd": 3, "put": 2, "putd": 2}.get(op)
            if pos is not None and len(tokens) > pos and re.fullmatch(r"-?\d+", tokens[pos]):
                address = int(tokens[pos])
                if not 0 <= address <= 511:
                    invalid_stack_addresses.append((n, address))

    unresolved = []
    for row in parsed.rows:
        n = row.line.number
        code = row.line.code_text
        if code.endswith(":"):
            continue
        tokens = row.tokens
        op = row.opcode
        target = None
        if op in {"j", "jal"} and len(tokens) >= 2:
            target = tokens[1]
        elif op.startswith("b") and not op.startswith("br") and len(tokens) >= 2:
            target = tokens[-1]
        if target and target != "ra" and re.match(r"^[A-Za-z_]", target):
            if target not in labels:
                unresolved.append((n, op, target))

    failures = []
    if len(lines) > LIMIT_LINES:
        failures.append(f"{len(lines)} lines > hard limit {LIMIT_LINES}")
    if (len(lines) > MAINTAINABILITY_LINES
            and str(path.relative_to(ROOT)) not in SOFT_LIMIT_EXEMPTIONS):
        failures.append(f"{len(lines)} lines > framework soft limit {MAINTAINABILITY_LINES}")
    if max_len > LIMIT_CHARS:
        failures.append(f"longest line {max_len} > {LIMIT_CHARS}")
    if crlf_bytes > LIMIT_BYTES:
        failures.append(f"CRLF size {crlf_bytes} > {LIMIT_BYTES}")
    if duplicates:
        failures.append(f"duplicate labels: {duplicates}")
    if malformed_labels:
        failures.append(f"malformed labels: {malformed_labels}")
    if unresolved:
        failures.append(f"unresolved targets: {unresolved}")
    if relative_branches:
        failures.append(f"relative branch offsets used: {relative_branches}")
    if invalid_registers:
        failures.append(f"invalid CPU registers: {invalid_registers}")
    if invalid_devices:
        failures.append(f"invalid device registers: {invalid_devices}")
    if invalid_stack_addresses:
        failures.append(f"invalid literal stack addresses: {invalid_stack_addresses}")
    if invalid_direct_stack_operands:
        failures.append(f"direct db stack operand in arithmetic: {invalid_direct_stack_operands}")

    return len(lines), max_len, crlf_bytes, comment_lines, failures


def main():
    failed = False
    rows = []
    for path in sorted((ROOT/"ic10").rglob("*.ic10")):
        result = inspect(path)
        rows.append((path.relative_to(ROOT).as_posix(), *result))
        failed |= bool(result[-1])

    print("IC10 static validation")
    print("=" * 100)
    for name, lines, chars, size, comments, failures in rows:
        state = "FAIL" if failures else "PASS"
        print(
            f"{state:4} {name:42} lines={lines:3} "
            f"headroom={LIMIT_LINES-lines:2} max={chars:2} "
            f"CRLF={size:4} comments={comments:2}"
        )
        for failure in failures:
            print(f"     - {failure}")
    print("=" * 100)
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
