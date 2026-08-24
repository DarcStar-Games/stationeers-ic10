#!/usr/bin/env python3
"""Reusable deterministic interruption-campaign helper.

Tests define ordered mutation steps plus recovery/invariant callbacks. The helper
replays the scenario with a crash after every operation boundary, including the
pre-operation and fully-complete states.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Generic, Iterable, TypeVar

T=TypeVar('T')

@dataclass(frozen=True)
class Step(Generic[T]):
    name:str
    apply:Callable[[T],None]

@dataclass(frozen=True)
class CutResult:
    cut:int
    after:str


def inject_every_boundary(initial:T,steps:Iterable[Step[T]],recover:Callable[[T,int],T],check:Callable[[T,int],None])->list[CutResult]:
    """Crash after each prefix of *steps*, recover, then assert the invariant.

    `cut == 0` means before the first mutation. `cut == len(steps)` means after
    the complete transaction. State is deep-copied so each cut is independent.
    """
    seq=list(steps);results=[]
    for cut in range(len(seq)+1):
        state=deepcopy(initial)
        for step in seq[:cut]: step.apply(state)
        state=recover(state,cut)
        check(state,cut)
        results.append(CutResult(cut,'START' if cut==0 else seq[cut-1].name))
    return results
