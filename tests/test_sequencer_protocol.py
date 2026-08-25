#!/usr/bin/env python3
"""Small executable model of ControllerSequencer state/timeout semantics."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from dataclasses import dataclass

FILL, SETTLE, DRAIN, COMPLETE, TIMEOUT, NUMERIC = range(6)

@dataclass
class S:
    state: int = FILL
    ticks: int = 0
    cycles: int = 0


def step(s, *, enabled, process, low=100, high=200, settle=2, timeout=4, repeat=True):
    if not enabled:
        return S(FILL, 0, s.cycles), (0, 0), 0
    if process is None:
        return s, (0, 0), -1
    if process != process:
        return S(NUMERIC, s.ticks, s.cycles), (0, 0), -5
    if s.state == COMPLETE:
        return s, (0, 0), 0
    if s.state == TIMEOUT:
        return s, (0, 0), -6
    if s.state == NUMERIC:
        return s, (0, 0), -5
    if s.state == FILL:
        if process >= high:
            return S(SETTLE, 0, s.cycles), (0, 0), 0
        t = s.ticks + 1
        if t >= timeout:
            return S(TIMEOUT, t, s.cycles), (0, 0), -6
        return S(FILL, t, s.cycles), (1, 0), 0
    if s.state == SETTLE:
        t = s.ticks + 1
        if t < settle:
            return S(SETTLE, t, s.cycles), (0, 0), 0
        return S(DRAIN, 0, s.cycles), (0, 1), 0
    if s.state == DRAIN:
        if process <= low:
            cycles = s.cycles + 1
            if repeat:
                return S(FILL, 0, cycles), (1, 0), 0
            return S(COMPLETE, 0, cycles), (0, 0), 0
        t = s.ticks + 1
        if t >= timeout:
            return S(TIMEOUT, t, s.cycles), (0, 0), -6
        return S(DRAIN, t, s.cycles), (0, 1), 0
    raise AssertionError(s.state)


def main():
    # One-shot: fill threshold -> settle -> drain threshold -> complete.
    s=S()
    s,out,st=step(s,enabled=True,process=150,repeat=False); assert (s.state,out,st)==(FILL,(1,0),0)
    s,out,st=step(s,enabled=True,process=200,repeat=False); assert (s.state,out)==(SETTLE,(0,0))
    s,out,st=step(s,enabled=True,process=200,repeat=False); assert s.state==SETTLE and out==(0,0)
    s,out,st=step(s,enabled=True,process=200,repeat=False); assert s.state==DRAIN and out==(0,1)
    s,out,st=step(s,enabled=True,process=100,repeat=False); assert s.state==COMPLETE and s.cycles==1 and out==(0,0)
    s2,out,st=step(s,enabled=True,process=50,repeat=False); assert s2.state==COMPLETE and out==(0,0)

    # Disable acknowledges terminal states and always commands safe-off.
    s2,out,st=step(S(TIMEOUT,4,7),enabled=False,process=150); assert s2.state==FILL and s2.cycles==7 and out==(0,0)

    # Repeat immediately begins the next fill leg after drain reaches low threshold.
    s,out,st=step(S(DRAIN,1,3),enabled=True,process=100,repeat=True); assert s.state==FILL and s.cycles==4 and out==(1,0)

    # Active phase timeout is terminal/safe-off while enabled.
    s=S()
    for _ in range(3):
        s,out,st=step(s,enabled=True,process=150,timeout=4)
    assert s.state==FILL
    s,out,st=step(s,enabled=True,process=150,timeout=4); assert s.state==TIMEOUT and out==(0,0) and st==-6

    # Missing input pauses state and commands safe-off; NaN enters numeric fault.
    prior=S(DRAIN,2,5)
    s,out,st=step(prior,enabled=True,process=None); assert s==prior and out==(0,0) and st==-1
    s,out,st=step(S(),enabled=True,process=float('nan')); assert s.state==NUMERIC and out==(0,0) and st==-5

    print('Sequencer protocol model: PASS')
    print(' - one-shot cycle reaches COMPLETE safely')
    print(' - repeat cycle re-enters FILL and increments cycle count')
    print(' - timeout, missing input, numeric fault, and disable are safe-off')

if __name__ == '__main__':
    main()
