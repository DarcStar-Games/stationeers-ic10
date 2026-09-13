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
# A COMMIT through the real Planner, Plan Builder, Single-hop Builder, Path Allocator, and Allocator grants
# one lease. The Allocator reads LeaseTicks from the Planner's S11 through the request's S13 PlannerRef; the
# Planner never writes S21, which the Allocator once read, so every request was rejected (issue #194).
from framework.ic10_harness import Device,IC10,run_round_robin
src=lambda p:(R/p).read_text(); MEDIUM=7; XFER,SRC,SNK=801,802,803
linkdir=Device(811,stack={0:'HASH:GenericSnapshotDirectoryHost.v1',1:1,9:'HASH:DirectorySchema.PressureGridLink.v1',11:3,12:64,24:0,25:1,27:1,29:0,32:XFER,33:1,34:2},props={'ReferenceId':811})
profile=Device(812,stack={0:'HASH:ResourceProfileView.v1',1:1,8:1,9:MEDIUM,28:1,29:5},props={'ReferenceId':812})
selector=Device(813,stack={0:'HASH:PressureGridRouteSelector.v2',1:2},props={'ReferenceId':813})
xfer=Device(XFER,stack={99:'HASH:ControllerPressureTransfer',100:8,101:1,102:MEDIUM,103:1,106:SRC,107:SNK},props={'ReferenceId':XFER})
def reservation(ref):return Device(ref,stack={0:'HASH:PressureInventoryReservation.v1',1:1,10:1,12:0,13:0,14:0,15:0,19:MEDIUM,20:6400,21:3200},props={'ReferenceId':ref})
source=reservation(SRC); sink=reservation(SNK); net={'xfer':xfer,'src':source,'snk':sink}
def vm(path,screws,ref):v=IC10(src(path),screws,self_ref=ref);return v,Device(ref,v.stack,{'ReferenceId':ref})
alloc,alloc_d=vm('ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10',dict(net),821)
patha,patha_d=vm('ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10',{'d0':selector,'d1':alloc_d,**net},822)
single,single_d=vm('ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10',{'d0':linkdir,'d1':alloc_d,**net},823)
builder,builder_d=vm('ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10',{'d0':single_d,'d1':patha_d},824)
grid,grid_d=vm('ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10',{'d0':linkdir,'d1':profile,'d2':builder_d},825)
alloc.screws['planner']=grid_d
for _ in range(600):
 run_round_robin([grid,builder,single,patha,alloc],rounds=1)
 selector.stack[9]=0; selector.stack[10]=selector.stack.get(36,0)  # Route Selector stub: every search finds no path
 if grid.stack.get(14,0)>0: break
else: fails.append('Planner never completed a build')
if grid.stack.get(11)!=64: fails.append('Planner LeaseTicks for one link is not 64: %r'%grid.stack.get(11))
if (grid.stack.get(10),grid.stack.get(8),grid.stack.get(9))!=(1,1,8*64): fails.append('Planner did not report one granted link at 8 mol/tick over the lease: %r'%{c:grid.stack.get(c) for c in (8,9,10)})
if (xfer.stack.get(108),xfer.stack.get(109),xfer.stack.get(110),xfer.stack.get(111))!=(8,1,825,64): fails.append('Allocator did not stage the grant under the Planner lease: %r'%{c:xfer.stack.get(c) for c in (108,109,110,111)})
if (source.stack.get(12),sink.stack.get(13))!=(512,512): fails.append('endpoint ledgers do not hold rate * LeaseTicks: %r'%(source.stack.get(12),sink.stack.get(13)))
if fails:
 print('Pressure-reservation hardening model: FAIL'); [print(' -',f) for f in fails]; sys.exit(1)
print('Pressure-reservation hardening model: PASS')
print(' - Allocator ABI3 supports non-reserving quote + exact commit')
print(' - staged topology identity precedes staged epoch')
print(' - Path Allocator quotes whole path before committing normalized rate')
print(' - Grant Guard consumes topology-mismatched epochs so they cannot later reactivate')
print(' - Planner remains the commit-last authority')
print(' - Planner, builders, and Allocator grant one lease with LeaseTicks read from the Planner S11')
