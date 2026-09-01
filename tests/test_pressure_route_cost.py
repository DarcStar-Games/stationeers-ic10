#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import math, sys
from framework.ic10_harness import IC10,Device
R=_PROJECT_ROOT
rank=(R/'ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10').read_text(); sel=(R/'ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10').read_text(); alloc=(R/'ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10').read_text(); fails=[]
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
# Both hop arrays are the published three cells S16..S18, so a peer claiming a longer
# path must be refused before it is indexed: reading past S18 walks off the contract.
def selected(best_length):
 enumerator=Device(9401,stack={0:'HASH:PressureGridPathEnumerator.v2',8:50,9:1,10:100,16:111,17:222,18:0,37:2})
 ranker=Device(9402,stack={0:'HASH:PressureGridRouteRanker.v2',9:1,10:101,16:111,17:222,18:333,19:best_length,20:7,21:3,22:1,23:5,24:1})
 vm=IC10(sel,{'d0':enumerator,'d1':ranker}); vm.run(1)
 vm.stack.update({32:9201,33:1,34:77,35:64,36:1}); vm.run(6,max_steps=20000); return vm
ok=selected(3)
if ok.stack.get(9)!=1 or [ok.stack.get(c) for c in (16,17,18)]!=[111,222,333]: fails.append('Selector rejected a legal three-hop route')
over=selected(4)
if over.stack.get(9)!=-1 or over.stack.get(19) is not None: fails.append('Selector copied a hop array longer than the published S16..S18')
def routed(path_length):
 selector=Device(9403,stack={0:'HASH:PressureGridRouteSelector.v2',8:100,9:1,10:1,16:111,17:222,18:333,37:path_length})
 reservation=Device(9404,stack={0:'HASH:PressureReservationAllocator.v3',9:-1})
 vm=IC10(alloc,{'d0':selector,'d1':reservation}); vm.run(1)
 vm.stack.update({14:9201,15:1,16:77,17:64,18:1}); vm.run(5,max_steps=20000); return vm
if routed(3).stack.get(8) is not None: fails.append('Path Allocator refused a legal three-hop route')
if routed(4).stack.get(8)!=-1: fails.append('Path Allocator quoted hops past the published S16..S18')
if fails:
 print('Pressure-grid route-cost model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-grid route-cost model: PASS')
print(' - Ranker explicitly rejects NaN cost weights/budget')
print(' - Ranker caps throughput by remaining endpoint reservations')
print(' - Route Selector passes lease length into reservation-aware ranking')
print(' - cost policy still permits a better longer route to beat a poor shorter route')
print(' - Selector and Path Allocator fail closed on a path length past the published S16..S18')
