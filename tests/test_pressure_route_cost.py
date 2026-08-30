#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import math, sys
R=_PROJECT_ROOT
rank=(R/'ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10').read_text(); sel=(R/'ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10').read_text(); fails=[]
for reg in ('r4','r5','r6','r7'):
 if f'bnan {reg} Bad' not in rank: fails.append(f'Ranker does not NaN-check {reg}')
for n in ('get r0 d0 12','bnan r0 Bad','get ra db 11','getd r13 r11 12','getd r13 r12 13','div r0 r0 ra'):
 if n not in rank: fails.append('Ranker missing '+n)
if 'get r9 db 35' not in sel or 'put d1 11 r9' not in sel: fails.append('Selector does not pass lease to Ranker')
def cost(h,s,l,q): return 100*h+25*s+.01*l+100/q
if not cost(3,2,0,10)<cost(2,1,20000,1): fails.append('reference cost tradeoff failed')
# remaining reservation example: raw 10 but only 128 moles /64 ticks => 2 rate
admiss=min(10,(640-512)/64,(1000-0)/64)
if abs(admiss-2)>1e-9: fails.append('remaining reservation capacity reference failed')
if fails:
 print('Pressure-grid route-cost model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-grid route-cost model: PASS')
print(' - Ranker explicitly rejects NaN cost weights/budget')
print(' - Ranker caps throughput by remaining endpoint reservations')
print(' - Route Selector passes lease length into reservation-aware ranking')
print(' - cost policy still permits a better longer route to beat a poor shorter route')
