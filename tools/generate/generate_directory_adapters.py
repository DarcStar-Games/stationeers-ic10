#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import argparse,json
from framework.protocol_headers import header_token
from framework.stack_envelope import declared_capability_mask
R=_PROJECT_ROOT
SPECS=R/'data/directory_adapter_specs.json'

def render(s):
 fields=s['fields']; w=len(fields); g=s['generation_offset']
 capability_mask=declared_capability_mask(R,s['file'])
 lines=[f"# {s['comment']}",'Boot:','clr db','poke 0 HASH("DirectoryAdapter.v3")','poke 1 3',f'poke 2 {capability_mask}',f'poke 3 HASH("{s["schema"]}.v1")','poke 10 {}'.format(w),'poke 11 64','poke 15 1']
 lines += ['Loop:','yield','get r0 db 16','beqz r0 ScanStart','poke 17 r0','j Loop','ScanStart:','poke 17 0','get r15 db 13','add r15 r15 1','poke 13 r15','poke 14 0','move r7 0','move r8 0','Scan:','get r1 db:0 r7','blt r1 0 Publish','add r7 r7 1','ld r0 r1 PrefabHash','beq r0 -128473777 Probe','bne r0 2037291645 Scan','Probe:','getd r0 r1 0',f'bne r0 {header_token(s["provider_contract"],s["provider_abi"])} Scan',f'getd r15 r1 {g}','blez r15 Scan']
 for i,f in enumerate(fields):
  if f=='ref': continue
  reg='r2' if i==0 else 'r3' if i==1 else f'r{2+i}'
  lines.append(f'getd {reg} r1 {f}')
 lines += [f'getd r0 r1 {g}','bne r0 r15 Scan','bge r8 64 Overflow']
 if w==1:
  lines += ['add r3 r8 18','poke r3 r1']
 else:
  lines += [f'mul r4 r8 {w}','add r4 r4 18']
  for i,f in enumerate(fields):
   if i: lines.append('add r4 r4 1')
   if f=='ref': val='r1'
   else: val='r2' if i==0 else 'r3' if i==1 else f'r{2+i}'
   lines.append(f'poke r4 {val}')
 lines += ['add r8 r8 1','j Scan','Overflow:','poke 14 1','j Scan','Publish:','poke 12 r8','get r0 db 13','add r0 r0 1','poke 13 r0','get r0 db 7','add r0 r0 1','poke 7 r0','j Loop']
 return '\n'.join(lines)+'\n'

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args()
 specs=json.loads(SPECS.read_text())['adapters'];bad=[]
 for s in specs:
  p=R/s['file']; text=render(s)
  if a.check:
   if not p.exists() or p.read_text()!=text: bad.append(s['file'])
  else:p.write_text(text)
 if bad:
  print('Generated directory adapters: FAIL');[print(' - drift:',x) for x in bad];return 1
 print(f"Generated directory adapters: {'CHECK PASS' if a.check else 'PASS'} ({len(specs)})")
 return 0
if __name__=='__main__':raise SystemExit(main())
