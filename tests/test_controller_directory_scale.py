#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import IC10,Device
R=_PROJECT_ROOT
D=(R/'ic10/controller-discovery/controller_directory_adapter_v4_0.ic10').read_text();B=(R/'ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10').read_text();H=(R/'ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10').read_text();S=(R/'ic10/controller-discovery/controller_selector_v3_0.ic10').read_text();A=(R/'ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10').read_text();L=(R/'ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10').read_text();P=(R/'ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10').read_text();fails=[]
for n in ('poke 0 31415983','poke 3 HASH("DirectorySchema.Controller.v1")','poke 10 2','poke 11 64','poke 15 1'):
 if n not in D:fails.append('Controller adapter missing '+n)
for n in ('put d1 9 r0','put d1 11 r2','put d1 12 r3','move r6 2'):
 if n not in B:fails.append('Directory bridge missing '+n)
for n in ('poke 0 31415981','poke 1 1','bgt r3 64 Error','add r10 r6 7','poke r10 r9','mul r4 r2 r3'):
 if n not in H:fails.append('Generic Directory Host missing '+n)
for n in ('poke 1 2','HASH("DirectorySchema.Controller.v1")','bgtz r0 Overflow','Scan:','SameType:','getd r0 directory 2','bne r0 r10 Updating'):
 if n not in S:fails.append('Direct Controller Selector missing '+n)
if not all(x in A for x in ('bne r0 31415981 BadDirectory','HASH("DirectorySchema.Controller.v1")','bgtz r0 BadDirectory')):fails.append('Arbiter does not validate generic schema/refuse overflow')
if not all(x in L for x in ('bne r0 31415981 Publish','HASH("DirectorySchema.Controller.v1")','bgtz r0 SourceOverflow')):fails.append('Pressure Link adapter does not validate/refuse source snapshot')
if not all(x in P for x in ('mul r13 r0 4','add r13 r13 16','max r13 r13 64')):fails.append('adaptive lease missing')
if max(64,4*64+16)!=272:fails.append('64-link lease !=272')
# Execute the direct Selector against a sorted 64-capable snapshot. It must derive groups without 02.
dir=Device(700,stack={0:31415981,1:1,2:0,3:9,5:5,7:0,9:'HASH:DirectorySchema.Controller.v1',11:2,12:64})
records=[('HASH:ControllerA',101),('HASH:ControllerA',102),('HASH:ControllerB',201),('HASH:ControllerB',202),('HASH:ControllerC',301)]
for i,(typ,ref) in enumerate(records):dir.stack[32+2*i]=typ;dir.stack[33+2*i]=ref
import re
execS='\n'.join(x for x in S.splitlines() if not x.lstrip().startswith('alias '))
execS=re.sub(r'\bdirectory\b','r1',execS)
vm=IC10(execS,{'d0':dir});vm.stack[2]=700;vm.stack[10]=2;vm.stack[11]=2;vm.stack[12]=1
vm.run(3,max_steps=10000)
if (vm.stack.get(3),vm.stack.get(4),vm.stack.get(5),vm.stack.get(6),vm.stack.get(7),vm.stack.get(8))!=(2,2,202,3,'HASH:ControllerB',1):fails.append('Selector direct type/member resolution failed')
# Out-of-range type/member clamp to final type/final member.
vm.stack[10]=99;vm.stack[11]=99;vm.stack[12]=2;vm.run(2,max_steps=10000)
if (vm.stack.get(3),vm.stack.get(4),vm.stack.get(5),vm.stack.get(7))!=(3,1,301,'HASH:ControllerC'):fails.append('Selector direct clamp failed')
# Incomplete snapshots remain fail-closed.
dir.stack[7]=1;dir.stack[3]=10;vm.run(2,max_steps=10000)
if vm.stack.get(8)!=-3:fails.append('Selector does not surface overflow')
if fails:
 print('Controller/grid-directory scale model: FAIL');[print(' -',f) for f in fails];sys.exit(1)
print('Controller/grid-directory scale model: PASS')
print(' - Controller Selector derives type/member groups directly from the sorted Generic Snapshot Directory')
print(' - Generic Snapshot Directory supports 64 packed records; overflow remains fail-closed')
