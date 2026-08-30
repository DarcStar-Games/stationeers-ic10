"""Reusable opcode-family handlers for the deterministic IC10 test harness."""
from __future__ import annotations

from collections.abc import Callable
import math
from typing import Protocol

from framework.ic10_source import SourceRow


class DeviceRuntime(Protocol):
    ref: int
    stack: dict[int, object]
    props: dict[object, object]
    slots: dict[int, dict[object, object]]


class OpcodeRuntime(Protocol):
    stack: dict[int, object]
    reg: dict[str, object]
    screws: dict[str, DeviceRuntime]
    pc: int

    def val(self, token: str): ...
    def num(self, token: str): ...
    def setreg(self, register: str, value: object) -> None: ...
    def stack_get(self, index: str): ...
    def stack_put(self, index: str, value: object) -> None: ...
    def device(self, token: str) -> DeviceRuntime: ...
    def ref_device(self, reference: object) -> DeviceRuntime: ...
    def propkey(self, token: str): ...
    def branch(self, label: str) -> None: ...


OpcodeHandler = Callable[[OpcodeRuntime, SourceRow], None]


def _write(vm: OpcodeRuntime, row: SourceRow, value: object) -> None:
    vm.setreg(row.operands[0], value)


def handle_stack_and_device_io(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute register, stack, and device-stack operations."""
    op, a = row.opcode, row.operands
    if op == "clr":
        (vm.stack if a[0] == "db" else vm.device(a[0]).stack).clear()
    elif op == "move":
        _write(vm, row, vm.val(a[1]))
    elif op == "round":
        _write(vm, row, round(vm.val(a[1])))
    elif op == "abs":
        _write(vm, row, abs(vm.val(a[1])))
    elif op == "floor":
        _write(vm, row, math.floor(vm.val(a[1])))
    elif op == "poke":
        vm.stack_put(a[0], vm.val(a[1]))
    elif op == "push":
        vm.stack_put("sp", vm.val(a[0]))
        vm.reg["sp"] = vm.val("sp") + 1
    elif op == "pop":
        vm.reg["sp"] = vm.val("sp") - 1
        _write(vm, row, vm.stack_get("sp"))
    elif op == "get":
        device_token = a[1]
        if device_token == "db":
            value = vm.stack_get(a[2])
        elif device_token == "db:0":
            index = int(vm.val(a[2]))
            seen_references: set[int] = set()
            devices = []
            for device in vm.screws.values():
                if device.ref not in seen_references:
                    seen_references.add(device.ref)
                    devices.append(device)
            value = devices[index].ref if 0 <= index < len(devices) else -1
        else:
            value = vm.device(device_token).stack.get(int(vm.val(a[2])), 0.0)
        _write(vm, row, value)
    elif op == "put":
        vm.device(a[0]).stack[int(vm.val(a[1]))] = vm.val(a[2])
    elif op == "getd":
        device = vm.ref_device(int(vm.val(a[1])))
        _write(vm, row, device.stack.get(int(vm.val(a[2])), 0.0))
    elif op == "putd":
        device = vm.ref_device(int(vm.val(a[0])))
        device.stack[int(vm.val(a[1]))] = vm.val(a[2])


def handle_property_io(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute direct, reference-addressed, and slot property operations."""
    op, a = row.opcode, row.operands
    if op == "l":
        _write(vm, row, vm.device(a[1]).props.get(vm.propkey(a[2]), math.nan))
    elif op == "ld":
        device = vm.ref_device(int(vm.val(a[1])))
        _write(vm, row, device.props.get(vm.propkey(a[2]), math.nan))
    elif op == "s":
        device = vm.device(a[0])
        key = vm.propkey(a[1])
        value = vm.val(a[2])
        device.props[key] = value
    elif op == "sd":
        device = vm.ref_device(int(vm.val(a[0])))
        key = vm.propkey(a[1])
        value = vm.val(a[2])
        device.props[key] = value
    elif op == "ls":
        device = vm.device(a[1])
        slot = int(vm.val(a[2]))
        _write(vm, row, device.slots.get(slot, {}).get(vm.propkey(a[3]), 0.0))
    elif op == "ss":
        device = vm.device(a[0])
        slot = int(vm.val(a[1]))
        key = vm.propkey(a[2])
        value = vm.val(a[3])
        device.slots.setdefault(slot, {})[key] = value


BINARY_ARITHMETIC: dict[str, Callable[[object, object], object]] = {
    "add": lambda x, y: x + y,
    "sub": lambda x, y: x - y,
    "mul": lambda x, y: x * y,
    "div": lambda x, y: x / y,
    "min": min,
    "max": max,
    "pow": lambda x, y: x**y,
    "mod": lambda x, y: x % y,
}


def handle_arithmetic(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute scalar and bitwise arithmetic operations."""
    op, a = row.opcode, row.operands
    if op in BINARY_ARITHMETIC:
        _write(vm, row, BINARY_ARITHMETIC[op](vm.num(a[1]), vm.num(a[2])))
    elif op in ("and", "or", "sll", "srl"):
        left, right = int(vm.num(a[1])), int(vm.num(a[2]))
        values = {
            "and": left & right,
            "or": left | right,
            "sll": left << right,
            "srl": (left & 0xFFFFFFFFFFFFFFFF) >> right,
        }
        _write(vm, row, values[op])
    elif op == "clamp":
        _write(vm, row, max(vm.val(a[2]), min(vm.val(a[1]), vm.val(a[3]))))


BINARY_COMPARISONS: dict[str, Callable[[object, object], bool]] = {
    "seq": lambda x, y: x == y,
    "sne": lambda x, y: x != y,
    "slt": lambda x, y: x < y,
    "sgt": lambda x, y: x > y,
}


def handle_comparison(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute comparison and conditional selection operations."""
    op, a = row.opcode, row.operands
    if op in BINARY_COMPARISONS:
        result = BINARY_COMPARISONS[op](vm.val(a[1]), vm.val(a[2]))
        _write(vm, row, 1 if result else 0)
    elif op == "sgtz":
        _write(vm, row, 1 if vm.num(a[1]) > 0 else 0)
    elif op == "snan":
        value = vm.val(a[1])
        _write(vm, row, 1 if isinstance(value, float) and math.isnan(value) else 0)
    elif op == "select":
        _write(vm, row, vm.val(a[2]) if vm.val(a[1]) != 0 else vm.val(a[3]))


BINARY_BRANCHES: dict[str, Callable[[object, object], bool]] = {
    "beq": lambda x, y: x == y,
    "bne": lambda x, y: x != y,
    "blt": lambda x, y: x < y,
    "bgt": lambda x, y: x > y,
    "ble": lambda x, y: x <= y,
    "bge": lambda x, y: x >= y,
}
ZERO_BRANCHES: dict[str, Callable[[object], bool]] = {
    "beqz": lambda x: x == 0,
    "bnez": lambda x: x != 0,
    "blez": lambda x: x <= 0,
    "bgtz": lambda x: x > 0,
    "bltz": lambda x: x < 0,
    "bgez": lambda x: x >= 0,
}


def handle_branch(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute unconditional, call, numeric, and NaN branches."""
    op, a = row.opcode, row.operands
    if op == "j":
        vm.branch(a[0])
    elif op == "jal":
        vm.reg["ra"] = vm.pc
        vm.branch(a[0])
    elif op in BINARY_BRANCHES:
        if BINARY_BRANCHES[op](vm.val(a[0]), vm.val(a[1])):
            vm.branch(a[2])
    elif op in ZERO_BRANCHES:
        if ZERO_BRANCHES[op](vm.val(a[0])):
            vm.branch(a[1])
    elif op == "bnan":
        value = vm.val(a[0])
        if isinstance(value, float) and math.isnan(value):
            vm.branch(a[1])


def handle_device_probe(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Execute device and device-property existence branches."""
    op, a = row.opcode, row.operands
    if op == "bdns":
        try:
            vm.device(a[0])
            exists = True
        except KeyError:
            exists = False
        if not exists:
            vm.branch(a[1])
    elif op in ("bdnvl", "bdnvs"):
        try:
            exists = vm.propkey(a[1]) in vm.device(a[0]).props
        except KeyError:
            exists = False
        if not exists:
            vm.branch(a[2])


STACK_AND_DEVICE_OPCODES = frozenset({
    "clr", "move", "round", "abs", "floor", "poke", "push", "pop",
    "get", "put", "getd", "putd",
})
PROPERTY_OPCODES = frozenset({"l", "ld", "s", "sd", "ls", "ss"})
ARITHMETIC_OPCODES = frozenset({*BINARY_ARITHMETIC, "and", "or", "sll", "srl", "clamp"})
COMPARISON_OPCODES = frozenset({*BINARY_COMPARISONS, "sgtz", "snan", "select"})
BRANCH_OPCODES = frozenset({*BINARY_BRANCHES, *ZERO_BRANCHES, "j", "jal", "bnan"})
DEVICE_PROBE_OPCODES = frozenset({"bdns", "bdnvl", "bdnvs"})


OPCODE_HANDLERS: dict[str, OpcodeHandler] = {
    **{opcode: handle_stack_and_device_io for opcode in STACK_AND_DEVICE_OPCODES},
    **{opcode: handle_property_io for opcode in PROPERTY_OPCODES},
    **{opcode: handle_arithmetic for opcode in ARITHMETIC_OPCODES},
    **{opcode: handle_comparison for opcode in COMPARISON_OPCODES},
    **{opcode: handle_branch for opcode in BRANCH_OPCODES},
    **{opcode: handle_device_probe for opcode in DEVICE_PROBE_OPCODES},
}


def execute_opcode(vm: OpcodeRuntime, row: SourceRow) -> None:
    """Dispatch one parsed instruction, retaining its source in diagnostics."""
    try:
        handler = OPCODE_HANDLERS[row.opcode]
    except KeyError:
        raise NotImplementedError(
            f"unsupported opcode {row.opcode!r} at source line "
            f"{row.line.number}: {row.line.raw_text}"
        ) from None
    handler(vm, row)
