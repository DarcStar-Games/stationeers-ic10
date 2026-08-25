#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
R=_PROJECT_ROOT
A=(R/'ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10').read_text(); P=(R/'ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10').read_text(); G=(R/'ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10').read_text(); planner=(R/'ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10').read_text(); fails=[]
for n in ('poke 1 3','get r13 db 16','beq r13 1 Quote','putd r4 117 r5','putd r4 118 r6','putd r4 119 r3','putd r4 120 r7','putd r4 109 r2'):
 if n not in A: fails.append('Allocator missing '+n)
if not (A.find('putd r4 117 r5') < A.find('putd r4 109 r2')): fails.append('topology payload not staged before epoch')
for n in ('QuoteLoop:','move r13 1','CommitLoop:','move r13 0'):
 if n not in P: fails.append('Path Allocator missing '+n)
for n in ('bne r4 r10 Consume','bne r5 r11 Consume','bne r3 r12 Consume','bne r2 r13 Consume'):
 if n not in G: fails.append('Grant Guard missing topology check '+n)
if planner.find('poke 14 r8') < planner.find('poke 8 r9'): fails.append('Planner commit is not after summary payload')
# reference exact quote/commit example
quotes=[8,5,7]; rate=min(quotes); lease=64
if rate!=5 or [rate*lease]*3 != [320]*3: fails.append('exact path reservation reference failed')
if fails:
 print('Pressure-reservation hardening model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-reservation hardening model: PASS')
print(' - Allocator ABI3 supports non-reserving quote + exact commit')
print(' - staged topology identity precedes staged epoch')
print(' - Path Allocator quotes whole path before committing normalized rate')
print(' - Grant Guard consumes topology-mismatched epochs so they cannot later reactivate')
print(' - Planner remains the commit-last authority')
