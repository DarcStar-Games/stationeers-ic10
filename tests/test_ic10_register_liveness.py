#!/usr/bin/env python3
"""Exercise the register read/write roles behind validate_ic10.py's dead-write rule.

The rule (issue #160) refuses an instruction that writes a register nothing in the
file reads. Its operand roles come from the game's own instruction signatures, so
the cases here pin the roles the rule depends on rather than the shape of any one
production program: the store family reads its value operand, an alias stands for
its register, `drN` reads only the index register, and one `rrN` read makes every
register live.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import sys

from framework.ic10_registers import (
    dead_register_writes,
    load_instruction_signatures,
    writes_first_operand,
)

failures = []


def ck(condition, message):
    if not condition:
        failures.append(message)


def dead(source):
    return [(write.line_number, write.register) for write in dead_register_writes(source, SIGNATURES)]


SIGNATURES = load_instruction_signatures(_PROJECT_ROOT)
WRITERS = writes_first_operand(SIGNATURES)

ck(SIGNATURES["get"] == ("r?", "device(d?|r?|id)", "address(r?|num)"),
   "signature tokens are not the official operand list")
ck({"get", "getd", "l", "ld", "ls", "lr", "lb", "peek", "pop", "move", "add", "seq", "select",
    "rand", "sdns"} <= WRITERS, "a register-writing opcode is missing from the writer set")
ck(not ({"put", "putd", "poke", "push", "s", "sd", "ss", "sb", "bne", "beqz", "j", "jal",
         "yield", "clr", "clrd"} & WRITERS), "a store, branch, or device-only opcode is a writer")

# The shape the issue measured: a mailbox read into consecutive registers where one
# field is never consumed. Only that one register is reported, at its own line.
mailbox = """get r1 db 14
get r2 db 15
get r6 db 19
blez r6 Bad
put d3 12 r1
Bad:
yield
"""
ck(dead(mailbox) == [(2, "r2")], f"mailbox dead load not isolated: {dead(mailbox)}")

# Any writer counts, not just loads: an arithmetic result nothing reads is dead too,
# while the registers it consumed are live.
arithmetic = """get r1 db 8
get r2 db 9
add r6 r1 r2
move r7 0
poke 10 r7
"""
ck(dead(arithmetic) == [(3, "r6")], f"dead arithmetic result not reported: {dead(arithmetic)}")

# The store family's value operand is a read even though the signature spells it r?.
stores = """move r3 1
move r4 2
move r5 3
move r6 4
move r7 5
s d0 Setting r3
sd r9 Setting r4
put d1 5 r5
push r6
poke 7 r7
get r9 db 1
"""
ck(dead(stores) == [], f"store value operands were not counted as reads: {dead(stores)}")

# An alias is its register on both sides of the rule.
aliased = """alias input r4
alias scratch r8
get input db 13
blez input NoService
get scratch db 14
NoService:
yield
"""
ck(dead(aliased) == [(5, "r8")], f"alias reads/writes not resolved: {dead(aliased)}")

# rrN in a read position may name any register, so its presence makes every write live;
# rrN as a destination writes an unknown register and only reads the index.
indirect_read = """move r10 HASH("ConsoleSelector.v1")
move r7 1
add r8 r7 9
getd r0 rr7 0
bne r0 rr8 NoService
NoService:
yield
"""
ck(dead(indirect_read) == [], f"rrN read did not make every register live: {dead(indirect_read)}")
indirect_write = """move r7 3
move rr7 5
move r2 1
"""
ck(dead(indirect_write) == [(3, "r2")], f"rrN destination handling wrong: {dead(indirect_write)}")

# drN selects a device pin through rN and reads nothing else.
device_indirect = """move r3 1
move r2 9
l r0 dr3 Setting
poke 0 r0
"""
ck(dead(device_indirect) == [(2, "r2")], f"drN read the wrong registers: {dead(device_indirect)}")

# sp and ra are implicit operands of push/pop/peek and jal, so they are outside the rule.
implicit = """add sp sp r5
move r5 1
jal Sub
j End
Sub:
j ra
End:
yield
"""
ck(dead(implicit) == [], f"sp/ra were reported: {dead(implicit)}")

# Reads and writes are counted over the whole file, so a write that is only read on
# another path, or later in the file, is live. This is the conservative choice.
whole_file = """get r2 db 15
j Skip
poke 16 r2
Skip:
yield
"""
ck(dead(whole_file) == [], f"whole-file rule reported a path-dead write: {dead(whole_file)}")

if failures:
    print("IC10 register liveness: FAIL")
    for failure in failures:
        print(" -", failure)
    sys.exit(1)
print("IC10 register liveness: PASS")
print(" - operand roles come from the official instruction signatures: first r? writes, the rest read")
print(" - the store family, aliases, rrN, drN, and sp/ra resolve the way the game reads them")
print(" - a dead write is reported at its own line and only when no path in the file reads it")
