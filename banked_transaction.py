#!/usr/bin/env python3
"""Reference model for BANKED_TRANSACTION_V1.

This module models the invariants shared by persistent IC10 services without
forcing their physical layouts into one runtime implementation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum

class BankedProfile(IntEnum):
    REVISION_BANK = 1
    SELECTOR_BANK = 2

@dataclass
class RevisionBank:
    payload: list = field(default_factory=list)
    signature: int = 0
    logical_generation: int = 0
    commit_revision: int = 0


def valid_revision(bank: RevisionBank, signature: int) -> int:
    return bank.commit_revision if bank.signature == signature and bank.commit_revision > 0 else 0


def choose_revision_bank(a: RevisionBank, b: RevisionBank, signature: int):
    """Choose newest valid bank; A wins ties, matching Generic Config Host."""
    ar, br = valid_revision(a, signature), valid_revision(b, signature)
    if ar <= 0 and br <= 0:
        return None
    return b if br > ar else a


def revision_commit_trace(old: RevisionBank, new_payload: list, signature: int,
                          logical_generation: int, new_revision: int):
    """Return recovery-visible values at each REVISION_BANK commit boundary."""
    dst = RevisionBank([0] * len(new_payload), 0, 0, 0)
    states = []
    def snap(label):
        chosen = choose_revision_bank(old, dst, signature)
        states.append((label, None if chosen is None else (chosen.logical_generation, list(chosen.payload))))
    snap('before')
    dst.commit_revision = 0; snap('invalidated')
    for i, value in enumerate(new_payload):
        dst.payload[i] = value; snap(f'payload-{i}')
    dst.signature = signature; snap('signature')
    dst.logical_generation = logical_generation; snap('logical-generation')
    dst.commit_revision = new_revision; snap('authority-last')
    return states

@dataclass(frozen=True)
class SelectorState:
    state: int
    generation: int
    status: int


def selector_commit_trace(old: SelectorState, new: SelectorState):
    """Model SELECTOR_BANK: inactive payload first, selector flip is authority."""
    banks = [old, old]
    active = 0
    states = [('before', banks[active])]
    banks[1] = new
    states.append(('inactive-written', banks[active]))
    active = 1
    states.append(('selector-flipped', banks[active]))
    return states


def request_recovery(outstanding_generation: int, committed_generation: int,
                     response_generation: int) -> str:
    """Common replay rule used by both profiles."""
    if outstanding_generation == response_generation:
        return 'already-acked'
    if outstanding_generation == committed_generation:
        return 'ack-committed'
    return 'retry'


def storage_compatible(observed_magic: int, observed_abi: int,
                       expected_magic: int, expected_abi: int) -> bool:
    return observed_magic == expected_magic and observed_abi == expected_abi
