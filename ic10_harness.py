#!/usr/bin/env python3
"""Tiny deterministic IC10 interpreter for transaction-critical regression tests.
Not a Stationeers emulator. Supports only the instruction subset exercised by tests/test_ic10_execution.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import math, re, shlex

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
        self.labels={}
        self.code=[]
        for raw in source.splitlines():
            raw=raw.split('#',1)[0].strip()
            if not raw: continue
            if raw.endswith(':'):
                self.labels[raw[:-1]]=len(self.code); continue
            self.code.append(raw)
        self.pc=0; self.yields=0
    def val(self,t):
        if t in self.reg: return self.reg[t]
        if re.fullmatch(r'rr(?:[0-9]|1[0-5])',t):
            return self.reg['r'+str(int(self.reg['r'+t[2:]]))]
        if t=='nan': return math.nan
        if t=='pinf': return math.inf
        if t=='ninf': return -math.inf
        if t.startswith('HASH('): return 'HASH:'+t[5:-1].strip('"')
        try: return float(t) if any(c in t for c in '.eE') else int(t)
        except ValueError: return t  # LogicType symbolic value
    def setreg(self,r,v):
        if re.fullmatch(r'rr(?:[0-9]|1[0-5])',r):
            r='r'+str(int(self.reg['r'+r[2:]]))
        self.reg[r]=v
    def stack_get(self,idx): return self.stack.get(int(self.val(idx)),0.0)
    def stack_put(self,idx,v): self.stack[int(self.val(idx))]=v
    def device(self,t):
        if t=='db': return Device(self.self_ref,self.stack,{'ReferenceId':self.self_ref})
        if t.startswith('dr') and t[2:].isdigit():
            key='d'+str(int(self.reg['r'+t[2:]]))
            if key in self.screws: return self.screws[key]
            raise KeyError(key)
        if t in self.screws: return self.screws[t]
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
            line=self.code[self.pc]; self.pc+=1
            toks=shlex.split(line, posix=False)
            op=toks[0]; a=toks[1:]
            if op=='yield':
                self.yields+=1
                if self.yields>=target: return "yield"
            elif op=='clr':
                if a[0]=='db': self.stack.clear()
                else: self.device(a[0]).stack.clear()
            elif op=='move': self.setreg(a[0],self.val(a[1]))
            elif op=='round': self.setreg(a[0],round(self.val(a[1])))
            elif op=='abs': self.setreg(a[0],abs(self.val(a[1])))
            elif op=='floor': self.setreg(a[0],math.floor(self.val(a[1])))
            elif op=='poke': self.stack_put(a[0],self.val(a[1]))
            elif op=='push':
                self.stack_put('sp',self.val(a[0])); self.reg['sp']=self.val('sp')+1
            elif op=='pop':
                self.reg['sp']=self.val('sp')-1; self.setreg(a[0],self.stack_get('sp'))
            elif op=='get':
                dev=a[1]
                if dev=='db': v=self.stack_get(a[2])
                elif dev=='db:0':
                    idx=int(self.val(a[2])); seen=[]
                    for d in self.screws.values():
                        if d.ref not in [x.ref for x in seen]: seen.append(d)
                    v=seen[idx].ref if 0 <= idx < len(seen) else -1
                else: v=self.device(dev).stack.get(int(self.val(a[2])),0.0)
                self.setreg(a[0],v)
            elif op=='put': self.device(a[0]).stack[int(self.val(a[1]))]=self.val(a[2])
            elif op=='getd':
                ref=int(self.val(a[1])); dev=self.ref_device(ref)
                self.setreg(a[0],dev.stack.get(int(self.val(a[2])),0.0))
            elif op=='putd':
                ref=int(self.val(a[0])); dev=self.ref_device(ref)
                dev.stack[int(self.val(a[1]))]=self.val(a[2])
            elif op=='l':
                dev=self.device(a[1]); key=self.propkey(a[2]); self.setreg(a[0], dev.props.get(key, math.nan))
            elif op=='ld':
                ref=int(self.val(a[1])); dev=self.ref_device(ref)
                key=self.propkey(a[2]); self.setreg(a[0],dev.props.get(key,math.nan))
            elif op=='s':
                dev=self.device(a[0]); key=self.propkey(a[1]); dev.props[key]=self.val(a[2])
            elif op=='sd':
                ref=int(self.val(a[0])); dev=self.ref_device(ref); key=self.propkey(a[1]); dev.props[key]=self.val(a[2])
            elif op=='ls':
                dev=self.device(a[1]); idx=int(self.val(a[2])); key=self.propkey(a[3])
                self.setreg(a[0],dev.slots.get(idx,{}).get(key,0.0))
            elif op in ('add','sub','mul','div','min','max','pow','mod'):
                x,y=self.val(a[1]),self.val(a[2]);
                f={'add':lambda:x+y,'sub':lambda:x-y,'mul':lambda:x*y,'div':lambda:x/y,'min':lambda:min(x,y),'max':lambda:max(x,y),'pow':lambda:x**y,'mod':lambda:x%y}[op]
                self.setreg(a[0],f())
            elif op in ('and','or','sll'):
                x,y=int(self.val(a[1])),int(self.val(a[2]))
                v={'and':x & y,'or':x | y,'sll':x << y}[op]; self.setreg(a[0],v)
            elif op=='clamp': self.setreg(a[0],max(self.val(a[2]),min(self.val(a[1]),self.val(a[3]))))
            elif op in ('seq','sne','slt','sgt'):
                x,y=self.val(a[1]),self.val(a[2]); f={'seq':x==y,'sne':x!=y,'slt':x<y,'sgt':x>y}[op]; self.setreg(a[0],1 if f else 0)
            elif op=='select': self.setreg(a[0],self.val(a[2]) if self.val(a[1])!=0 else self.val(a[3]))
            elif op=='j': self.branch(a[0])
            elif op=='jal': self.reg['ra']=self.pc; self.branch(a[0])
            elif op=='beq':
                if self.val(a[0])==self.val(a[1]): self.branch(a[2])
            elif op=='bne':
                if self.val(a[0])!=self.val(a[1]): self.branch(a[2])
            elif op=='blt':
                if self.val(a[0])<self.val(a[1]): self.branch(a[2])
            elif op=='bgt':
                if self.val(a[0])>self.val(a[1]): self.branch(a[2])
            elif op=='ble':
                if self.val(a[0])<=self.val(a[1]): self.branch(a[2])
            elif op=='bge':
                if self.val(a[0])>=self.val(a[1]): self.branch(a[2])
            elif op=='beqz':
                if self.val(a[0])==0: self.branch(a[1])
            elif op=='bnez':
                if self.val(a[0])!=0: self.branch(a[1])
            elif op=='blez':
                if self.val(a[0])<=0: self.branch(a[1])
            elif op=='bgtz':
                if self.val(a[0])>0: self.branch(a[1])
            elif op=='bltz':
                if self.val(a[0])<0: self.branch(a[1])
            elif op=='bgez':
                if self.val(a[0])>=0: self.branch(a[1])
            elif op=='bnan':
                v=self.val(a[0]);
                if isinstance(v,float) and math.isnan(v): self.branch(a[1])
            elif op=='bdns':
                try: self.device(a[0]); exists=True
                except KeyError: exists=False
                if not exists: self.branch(a[1])
            elif op in ('bdnvl','bdnvs'):
                try: dev=self.device(a[0]); exists=self.propkey(a[1]) in dev.props
                except KeyError: exists=False
                if op=='bdnvl' and not exists: self.branch(a[2])
                if op=='bdnvs' and not exists: self.branch(a[2])
            else:
                raise NotImplementedError(f'{op}: {line}')
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
