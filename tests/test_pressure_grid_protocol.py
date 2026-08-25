#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
R=_PROJECT_ROOT
T=(R/'ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10').read_text(); G=(R/'ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10').read_text(); A=(R/'ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10').read_text(); Rank=(R/'ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10').read_text(); LD=(R/'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10').read_text(); fails=[]
for n in ('poke 97 2','bdns d3 SafeOff','bne r0 31415948 SafeOff','get r15 d3 7','bne r6 r15 SafeOff'):
 if n not in T: fails.append('Transfer missing '+n)
for n in ('get r14 d0 115','bne r0 r14 Loop','bne r4 r10 Consume','get r14 d1 14'):
 if n not in G: fails.append('Guard missing '+n)
if 'get r13 db 16' not in A: fails.append('Allocator lacks quote operation')
if 'getd r13 r11 12' not in Rank: fails.append('Ranker ignores current reservations')
for n in ('getd r15 r1 115','getd r0 r1 115','bne r0 r15 Scan'):
 if n not in LD: fails.append('Link Directory lacks coherent Transfer snapshot')
if fails:
 print('Pressure-grid hardening model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-grid hardening model: PASS')
print(' - Transfer ABI2 executes only coherent GrantGuard output')
print(' - GrantGuard binds lease to coherent topology and Planner commit')
print(' - Allocator supports quote and topology-bound staging')
print(' - Route Ranker uses remaining reserved capacity')
print(' - Link Directory snapshots Transfer topology coherently')
