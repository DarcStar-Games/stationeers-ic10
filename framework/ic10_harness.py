"""Tiny deterministic IC10 interpreter for transaction-critical regression tests.
Not a Stationeers emulator. Supports only the instruction subset exercised by tests/test_ic10_execution.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math, re, zlib

from framework.ic10_opcodes import execute_opcode
from framework.ic10_source import parse_ic10

@dataclass
class Device:
    ref: int
    stack: dict[int, object] = field(default_factory=dict)
    props: dict[object, object] = field(default_factory=dict)
    slots: dict[int, dict[object, object]] = field(default_factory=dict)

class IC10:
    def __init__(self, source: str, screws: dict[str, Device] | None = None, self_ref: int = 999):
        self.stack: dict[int, object] = {}
        self.reg = {f'r{i}':0.0 for i in range(16)} | {'sp':0.0,'ra':0.0}
        self.screws = screws or {}
        self.self_ref = self_ref
        parsed=parse_ic10(source)
        self.labels=parsed.label_indices()
        self._instruction_rows=parsed.instructions
        self.code=[row.line.code_text for row in parsed.instructions]
        self.names=parsed.directive_values()
        self.pc=0; self.yields=0
    def val(self,t):
        t=self.names.get(t,t)
        if t in self.reg: return self.reg[t]
        if re.fullmatch(r'rr(?:[0-9]|1[0-5])',t):
            return self.reg['r'+str(int(self.reg['r'+t[2:]]))]
        if t=='nan': return math.nan
        if t=='pinf': return math.inf
        if t=='ninf': return -math.inf
        if t.startswith('HASH('): return 'HASH:'+t[5:-1].strip('"')
        try: return float(t) if any(c in t for c in '.eE') else int(t)
        except ValueError: return t  # LogicType symbolic value
    def num(self,t):
        """Hashes are int32 in game, so arithmetic sees a number, never the 'HASH:' token."""
        v=self.val(t)
        if isinstance(v,str) and v.startswith('HASH:'):
            crc=zlib.crc32(v[5:].encode())
            return crc-(1<<32) if crc>=(1<<31) else crc
        return v
    def setreg(self,r,v):
        r=self.names.get(r,r)
        if re.fullmatch(r'rr(?:[0-9]|1[0-5])',r):
            r='r'+str(int(self.reg['r'+r[2:]]))
        self.reg[r]=v
    def stack_get(self,idx): return self.stack.get(int(self.val(idx)),0.0)
    def stack_put(self,idx,v): self.stack[int(self.val(idx))]=v
    def device(self,t):
        t=self.names.get(t,t)
        if t=='db': return Device(self.self_ref,self.stack,{'ReferenceId':self.self_ref})
        if t.startswith('dr') and t[2:].isdigit():
            key='d'+str(int(self.reg['r'+t[2:]]))
            if key in self.screws: return self.screws[key]
            raise KeyError(key)
        if t in self.screws: return self.screws[t]
        # device(d?|r?|id) operands accept a ReferenceId held in a register or literal.
        v=self.val(t)
        if isinstance(v,(int,float)) and not (isinstance(v,float) and math.isnan(v)):
            try: return self.ref_device(v)
            except StopIteration: raise KeyError(t) from None
        raise KeyError(t)
    def ref_device(self,ref):
        ref=int(ref)
        if ref==self.self_ref: return Device(self.self_ref,self.stack,{'ReferenceId':self.self_ref})
        return next(d for d in self.screws.values() if d.ref==ref)
    def propkey(self,t):
        v=self.val(t)
        return v
    def branch(self,label):
        self.pc=int(self.reg['ra']) if label=='ra' else self.labels[label]
    def cmp(self,a,b,op):
        try: return op(self.val(a),self.val(b))
        except TypeError: return False
    def run(self, until_yields=1, max_steps=10000, instruction_quantum=None):
        target=self.yields+until_yields
        steps=0
        while self.pc < len(self.code) and steps < max_steps:
            if instruction_quantum is not None and steps >= instruction_quantum:
                return "quantum"
            steps+=1
            row=self._instruction_rows[self.pc];self.pc+=1
            if row.opcode=='yield':
                self.yields+=1
                if self.yields>=target: return "yield"
            else:
                execute_opcode(self,row)
        if instruction_quantum is not None and steps >= instruction_quantum:
            return "quantum"
        if steps>=max_steps: raise RuntimeError('step limit exceeded')

    def run_tick(self, max_instructions=128):
        """Run one Stationeers-like execution slice: explicit yield or instruction quantum."""
        return self.run(1, max_steps=max_instructions, instruction_quantum=max_instructions)

def run_round_robin(vms, rounds=1, max_instructions=128):
    """Deterministically interleave ICs one execution slice at a time."""
    for _ in range(rounds):
        for vm in vms:
            vm.run_tick(max_instructions)
