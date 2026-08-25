#!/usr/bin/env python3
"""Reference model for GENERIC_JOB_ABI_V1.

This is the executable semantic source of truth for lifecycle validation. IC10
writers use the same state table before issuing SET_STATE to the Job Store.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum
import math

class JobType(IntEnum):
    TRANSFORM=1; PRINT=2; TRANSFER=3; POWER=4

class JobState(IntEnum):
    QUEUED=1; PLANNING=2; RESERVING=3; READY=4; RUNNING=5; VERIFYING=6
    COMPLETE=7; WAIT_RESOURCE=8; WAIT_PROCESSOR=9; WAIT_CAPACITY=10
    FAULT=11; CANCELLED=12

NORMAL_CHAIN={
    JobState.QUEUED:JobState.PLANNING,
    JobState.PLANNING:JobState.RESERVING,
    JobState.RESERVING:JobState.READY,
    JobState.READY:JobState.RUNNING,
    JobState.RUNNING:JobState.VERIFYING,
    JobState.VERIFYING:JobState.COMPLETE,
}
WAIT_STATES={JobState.WAIT_RESOURCE,JobState.WAIT_PROCESSOR,JobState.WAIT_CAPACITY}
WAIT_FROM={JobState.PLANNING,JobState.RESERVING,JobState.READY}
TERMINAL={JobState.COMPLETE,JobState.FAULT,JobState.CANCELLED}

@dataclass(frozen=True)
class JobIntent:
    job_type:int
    required_capability:int
    identity:int
    input_count:int
    output_count:int
    requested_quantity:float
    priority:int


def _int(v):
    return isinstance(v,(int,float)) and math.isfinite(v) and int(v)==v


def validate_intent(i:JobIntent)->bool:
    return (
        _int(i.job_type) and int(i.job_type) in {x.value for x in JobType}
        and _int(i.required_capability) and i.required_capability>=0
        and _int(i.identity) and i.identity!=0
        and _int(i.input_count) and 0<=i.input_count<=32
        and _int(i.output_count) and 0<=i.output_count<=32
        and isinstance(i.requested_quantity,(int,float))
        and math.isfinite(i.requested_quantity) and i.requested_quantity>0
        and _int(i.priority)
    )


def allowed_transition(old:int,new:int,status:int=0)->bool:
    try: old=JobState(old); new=JobState(new)
    except ValueError: return False
    if old in TERMINAL: return False
    if new==JobState.FAULT:
        return _int(status) and status<0
    if new==JobState.CANCELLED:
        return _int(status)
    if NORMAL_CHAIN.get(old)==new:
        return status==0
    if old in WAIT_FROM and new in WAIT_STATES:
        return _int(status) and status>=0
    if old in WAIT_STATES and new==JobState.PLANNING:
        return status==0
    return False


def can_reap(state:int)->bool:
    try: return JobState(state) in TERMINAL
    except ValueError: return False
