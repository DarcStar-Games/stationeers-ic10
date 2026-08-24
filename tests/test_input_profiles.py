from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from ic10_harness import IC10
from catalog_test_helpers import load_catalog_chain
import hashlib,json,re,subprocess,sys
R=_PROJECT_ROOT;D=json.loads((R/'input_profiles.json').read_text());P=D['profiles'];fails=[]

def files():
 M=json.loads((R/'input_profile_catalog_manifest.json').read_text())
 return [R/M['generic_store_program'],R/M['coordinator_core_program'],R/M['loader_router_program'],*[R/f for f in M['loaders']],R/'ic10/input-profile-catalog/input_profile_view_v5_0.ic10',R/'input_profile_catalog_manifest.json',R/'input_profiles.json']
def hs():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files()}
b=hs();subprocess.run([sys.executable,str(R/'generate_input_profiles.py')],cwd=R,check=True,stdout=subprocess.DEVNULL);a=hs()
if a!=b:fails.append('generation is not deterministic')
M=json.loads((R/'input_profile_catalog_manifest.json').read_text())
if D.get('catalog_schema_version') not in (2,3): pass
if (M.get('format'),M.get('catalog_store_abi'),M.get('catalog_loader_abi'),M.get('catalog_schema_version'))!=('INPUT_PROFILE_CATALOG_V4',5,4,3):fails.append('Input Profile runtime schema metadata mismatch')
if M.get('runtime_store_placement') is not True or M.get('runtime_min_store_count')!=1 or M.get('profile_count')!=6:fails.append('Input Profile runtime capacity/count mismatch')
if len(M.get('item_cell_lengths',[]))!=6 or any(n%4 for n in M['item_cell_lengths']):fails.append('Input Profile self-contained item alignment mismatch')
loaders=[R/f for f in M['loaders']]
for src in (p.read_text() for p in loaders):
 code=[z.split('#',1)[0].strip() for z in src.splitlines() if z.split('#',1)[0].strip()]
 if code[0]!='clr db' or code[-1]!='poke 12 1' or any(z.startswith(('put ','putd ','yield','j ')) for z in code):fails.append('Input loader is not one-shot sparse own-stack producer')
 if re.search(r'^poke\s+\d+\s+0(?:\s|$)',src,re.M):fails.append('Input loader emits explicit zero poke')
 if re.search(r'^poke\s+13\s+[^0]',src,re.M):fails.append('Input loader preassigns Store')
store_src=(R/M['generic_store_program']).read_text();stores,vms,groups=load_catalog_chain([store_src],[[p.read_text() for p in loaders]],store_ref_base=910,loader_ref_base=920);store=stores[0];coord=vms[0].coord
if store.stack.get(16)!=2 or int(store.stack.get(9,0))!=6 or store.stack.get(27,0)!=0:fails.append('Input Profile runtime Store publication invalid')
# Check each self-contained item exactly reproduces source fields and zero padding.
def ev(v): return 'HASH:'+v if isinstance(v,str) and (v.startswith('Controller') or v=='DiagnosticMapping') else v
for i,p in enumerate(P):
 base=int(store.stack.get(32+i*2)); n=int(store.stack.get(33+i*2));vals=[ev(p['profile_type']),p['schema'],p['field_count'],len(p['enum_pairs'])]
 for d in p['descriptors']: vals += [ev(x) for x in d]
 for pair in p['enum_pairs']: vals += [ev(x) for x in pair]
 if n%4 or n<len(vals) or [store.stack.get(base+j) for j in range(len(vals))]!=vals:fails.append(p['slug']+': self-contained item mismatch')
 if any(store.stack.get(base+j,0)!=0 for j in range(len(vals),n)):fails.append(p['slug']+': item padding nonzero')
# Legacy View ABI remains identical.
screws={'d0':store,'coord':coord,'s0':store};src=(R/'ic10/input-profile-catalog/input_profile_view_v5_0.ic10').read_text()
for p in P:
 v=IC10(src,screws);v.stack[2]='HASH:'+p['profile_type'];v.stack[3]=p['schema'];v.run(3,max_steps=50000)
 flat=[x for row in p['descriptors'] for x in row]
 if v.stack.get(4)!=p['field_count'] or v.stack.get(5,0)<=0 or [v.stack.get(32+i) for i in range(len(flat))]!=flat:fails.append(p['slug']+': descriptor View mismatch')
 for slot,val in p['enum_pairs']:
  if v.stack.get(slot)!=val:fails.append(p['slug']+f': enum slot {slot} mismatch')
text='\n'.join(p.read_text() for p in loaders)
for p in P:
 human=p.get('name') or p['profile_type']
 if '# '+human not in text:fails.append(p['slug']+': missing human-readable comment')
if fails:
 print('Input Profile catalog schema: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Input Profile catalog schema: PASS')
print(f' - 6 self-contained profiles are runtime-placed in one Generic Store from {len(loaders)} relocatable sparse loaders')
print(' - every profile keeps descriptors + enums atomic and 4-cell aligned; View ABI1 unchanged')
