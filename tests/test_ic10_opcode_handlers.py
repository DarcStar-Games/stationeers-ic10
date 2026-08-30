#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from framework.ic10_harness import Device, IC10
from framework.ic10_opcodes import (
    ARITHMETIC_OPCODES,
    BRANCH_OPCODES,
    COMPARISON_OPCODES,
    DEVICE_PROBE_OPCODES,
    OPCODE_HANDLERS,
    PROPERTY_OPCODES,
    STACK_AND_DEVICE_OPCODES,
    handle_arithmetic,
    handle_branch,
    handle_comparison,
    handle_device_probe,
    handle_property_io,
    handle_stack_and_device_io,
)


failures = []


def check(condition, message):
    if not condition:
        failures.append(message)


# Registration is explicit, complete for every handler family, and non-overlapping.
families = (
    (STACK_AND_DEVICE_OPCODES, handle_stack_and_device_io),
    (PROPERTY_OPCODES, handle_property_io),
    (ARITHMETIC_OPCODES, handle_arithmetic),
    (COMPARISON_OPCODES, handle_comparison),
    (BRANCH_OPCODES, handle_branch),
    (DEVICE_PROBE_OPCODES, handle_device_probe),
)
registered = set()
for opcodes, expected_handler in families:
    check(not (registered & opcodes), f"overlapping opcode registration: {registered & opcodes}")
    registered.update(opcodes)
    for opcode in opcodes:
        check(OPCODE_HANDLERS.get(opcode) is expected_handler, f"{opcode} uses the wrong handler")
check(registered == set(OPCODE_HANDLERS), "handler registry differs from its opcode families")


# Direct/indirect registers plus local, direct-device, and reference-addressed stacks.
stack_device = Device(700)
stack_vm = IC10(
    """move r8 5
move rr8 19
poke 2 7
get r0 db 2
push 9
pop r1
put d0 3 11
get r2 d0 3
move r3 700
putd r3 4 12
getd r4 r3 4
move r9 0
s dr9 On 1
yield""",
    {"d0": stack_device},
)
check(stack_vm.run(1) == "yield", "stack/device fixture did not yield")
check(stack_vm.reg["r5"] == 19, "indirect register write changed")
check(stack_vm.reg["r0"] == 7 and stack_vm.reg["r1"] == 9, "local stack IO changed")
check(stack_vm.reg["r2"] == 11 and stack_vm.reg["r4"] == 12, "device stack IO changed")
check(stack_device.props.get("On") == 1, "indirect device resolution changed")


# Direct, reference-addressed, and slot property IO.
property_device = Device(701, props={"Setting": 4}, slots={1: {"Quantity": 6}})
property_vm = IC10(
    """l r0 d0 Setting
s d0 Setting 8
move r1 701
ld r2 r1 Setting
sd r1 Setting 9
ls r3 d0 1 Quantity
ss d0 1 Quantity 12
yield""",
    {"d0": property_device},
)
property_vm.run(1)
check(property_vm.reg["r0"] == 4 and property_vm.reg["r2"] == 8, "property loads changed")
check(property_device.props["Setting"] == 9, "property stores changed")
check(property_vm.reg["r3"] == 6 and property_device.slots[1]["Quantity"] == 12, "slot IO changed")


# Property stores retain destination/key/value resolution and exception order.
exception_order_cases = (
    ("move r0 99\nmove r1 98\ns d9 rr0 rr1", {}, "d9", "s"),
    ("move r0 701\nmove r1 99\nmove r2 98\nsd r0 rr1 rr2", {"d0": property_device}, "r99", "sd"),
    ("move r0 99\nmove r1 98\nss d0 0 rr0 rr1", {"d0": property_device}, "r99", "ss"),
)
for source, screws, expected_key, opcode in exception_order_cases:
    try:
        IC10(source, screws).run(1)
        failures.append(f"{opcode} invalid operands did not fail")
    except KeyError as error:
        check(error.args == (expected_key,), f"{opcode} operand exception order changed: {error.args}")


# Scalar/bitwise arithmetic, comparisons, and selection.
math_vm = IC10(
    """add r0 7 5
mul r1 r0 2
and r2 7 3
srl r3 -1 63
clamp r4 20 2 10
seq r5 r0 12
sgtz r6 -1
snan r7 nan
select r8 r5 44 55
yield"""
)
math_vm.run(1)
check(math_vm.reg["r0"] == 12 and math_vm.reg["r1"] == 24, "scalar arithmetic changed")
check(math_vm.reg["r2"] == 3 and math_vm.reg["r3"] == 1, "bitwise arithmetic changed")
check(math_vm.reg["r4"] == 10, "clamp behavior changed")
check(
    math_vm.reg["r5"] == 1
    and math_vm.reg["r6"] == 0
    and math_vm.reg["r7"] == 1
    and math_vm.reg["r8"] == 44,
    "comparison or selection behavior changed",
)


# Conditional branches, calls, return-address resolution, and device probes.
branch_vm = IC10(
    """move r0 1
beq r0 1 Taken
move r1 -1
Taken:
jal Subroutine
yield
Subroutine:
move r1 7
j ra"""
)
check(branch_vm.run(1) == "yield" and branch_vm.reg["r1"] == 7, "branch/call behavior changed")

probe_device = Device(702, props={"On": 1})
probe_vm = IC10(
    """bdns d1 MissingDevice
move r0 -1
MissingDevice:
bdnvl d0 MissingProperty MissingProperty
move r0 -2
MissingProperty:
move r0 1
yield""",
    {"d0": probe_device},
)
probe_vm.run(1)
check(probe_vm.reg["r0"] == 1, "device-probe branches changed")


# The loop retains scheduling responsibilities after opcode dispatch is extracted.
quantum_vm = IC10("Loop:\nadd r0 r0 1\nj Loop")
check(quantum_vm.run_tick(2) == "quantum" and quantum_vm.reg["r0"] == 1, "quantum scheduling changed")


# Unsupported instructions retain their exact original source row in the failure.
unsupported_vm = IC10("move r0 1\nteleport r0 r1 # preserve this source")
try:
    unsupported_vm.run(1)
    failures.append("unsupported opcode did not fail")
except NotImplementedError as error:
    message = str(error)
    check("teleport" in message, "unsupported-opcode diagnostic omits the opcode")
    check("source line 2" in message, "unsupported-opcode diagnostic omits its line number")
    check(
        "teleport r0 r1 # preserve this source" in message,
        "unsupported-opcode diagnostic omits the original source line",
    )


if failures:
    print("IC10 opcode handlers: FAIL")
    for failure in failures:
        print(" -", failure)
    raise SystemExit(1)

print("IC10 opcode handlers: PASS")
print(" - explicit handler families cover stack/device, property, arithmetic, comparison, branch, and probes")
print(" - direct/reference addressing, scheduling, and unsupported-source diagnostics are preserved")
