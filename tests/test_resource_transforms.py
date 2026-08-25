from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from framework.ic10_harness import IC10
from framework.catalog_test_helpers import load_catalog_chain
import hashlib,json,re,subprocess,sys
R=_PROJECT_ROOT;fails=[]

def files():
 M=json.loads((R/'data/resource_transform_catalog_manifest.json').read_text())
 return [R/M['generic_store_program'],R/M['coordinator_core_program'],R/M['loader_router_program'],*[R/f for f in M['loaders']],R/'ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10',R/'ic10/dependency-planning/item_producer_resolver_v1_0.ic10',R/'data/resource_transform_catalog_manifest.json']
def hs():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files()}
b=hs();subprocess.run([sys.executable,str(R/'generate_resource_transforms.py')],cwd=R,check=True,stdout=subprocess.DEVNULL);a=hs()
if a!=b:fails.append('generation is not deterministic')
D=json.loads((R/'data/resource_transforms.json').read_text());T=D['transforms'];M=json.loads((R/'data/resource_transform_catalog_manifest.json').read_text())
if len(T)!=17:fails.append(f'expected 17 transforms, got {len(T)}')
if (M.get('format'),M.get('catalog_store_abi'),M.get('catalog_loader_abi'),M.get('catalog_schema_version'),M.get('view_abi'))!=('RESOURCE_TRANSFORM_CATALOG_V6',5,4,4,4):fails.append('Transform runtime/schema ABI metadata mismatch')
if M.get('runtime_min_store_count')!=1 or M.get('input_descriptor_count')!=32 or M.get('output_descriptor_count')!=17:fails.append('Transform runtime capacity/count mismatch')
loaders=[R/f for f in M['loaders']]
for src in (p.read_text() for p in loaders):
 code=[z.split('#',1)[0].strip() for z in src.splitlines() if z.split('#',1)[0].strip()]
 if code[0]!='clr db' or code[-1]!='poke 12 1' or any(z.startswith(('put ','putd ','yield','j ')) for z in code):fails.append('Transform loader is not one-shot sparse own-stack producer')
 if re.search(r'^poke\s+\d+\s+0(?:\s|$)',src,re.M):fails.append('Transform loader emits explicit zero poke')
store_src=(R/M['generic_store_program']).read_text();stores,vms,groups=load_catalog_chain([store_src],[[p.read_text() for p in loaders]],store_ref_base=1030,loader_ref_base=1040);store=stores[0];coord=vms[0].coord
if store.stack.get(16)!=2 or int(store.stack.get(9,0))!=17 or store.stack.get(27,0)!=0:fails.append('Transform runtime Store publication invalid')
items={}
for i in range(int(store.stack.get(9,0))):
 base=int(store.stack.get(32+i*2));n=int(store.stack.get(33+i*2));items[store.stack.get(base)]=(base,n)
for x in T:
 key='HASH:'+x['name']; pair=items.get(key)
 if not pair:fails.append(x['name']+': item not found');continue
 base,n=pair;c=x['conditions'];flags=4|(1 if c['min_pressure_kpa'] or c['max_pressure_kpa'] else 0)|(2 if c['min_temperature_k'] or c['max_temperature_k'] else 0)
 vals=[key,x['required_capability_mask'],len(x['inputs']),len(x['outputs']),c['min_pressure_kpa'],c['max_pressure_kpa'],c['min_temperature_k'],c['max_temperature_k'],flags,0,0,0]
 for d in x['inputs']+x['outputs']:vals += [d['resource_class'],d['resource_type'],d['unit'],d['quantity']]
 if n%4 or n<len(vals) or [store.stack.get(base+j) for j in range(len(vals))]!=vals:fails.append(x['name']+': self-contained transform item mismatch')
 if any(store.stack.get(base+j,0)!=0 for j in range(len(vals),n)):fails.append(x['name']+': item padding nonzero')
 screws={'d0':store,'coord':coord,'s0':store};v=IC10((R/'ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10').read_text(),screws);v.stack[2]=key;v.run(3,max_steps=50000)
 if v.stack.get(6,0)<=0 or v.stack.get(3)!=x['required_capability_mask'] or v.stack.get(4)!=len(x['inputs']) or v.stack.get(5)!=len(x['outputs']):fails.append(x['name']+': View header mismatch')
 for j,d in enumerate(x['inputs']):
  if [v.stack.get(8+j*4+k) for k in range(4)]!=[d['resource_class'],d['resource_type'],d['unit'],d['quantity']]:fails.append(x['name']+': View input mismatch')
 for j,d in enumerate(x['outputs']):
  if [v.stack.get(32+j*4+k) for k in range(4)]!=[d['resource_class'],d['resource_type'],d['unit'],d['quantity']]:fails.append(x['name']+': View output mismatch')
 if [v.stack.get(64+k) for k in range(4)]!=[c['min_pressure_kpa'],c['max_pressure_kpa'],c['min_temperature_k'],c['max_temperature_k']]:fails.append(x['name']+': View bounds mismatch')
text='\n'.join(p.read_text() for p in loaders)
for x in T:
 if '# '+x['display_name'] not in text:fails.append(x['name']+': missing human transform comment')
# Capability hierarchy is intentionally cumulative: Furnace handles 1/2-input basic+alloy, Advanced handles all current classes.
cap=D.get('processor_capability_model',{})
if cap.get('StructureArcFurnace')!=1 or cap.get('StructureFurnace')!=3 or cap.get('StructureAdvancedFurnace')!=7:fails.append('processor capability hierarchy mismatch')
if any(x['required_capability_mask'] not in (1,2,4) for x in T):fails.append('invalid transform capability requirement')
if fails:
 print('Resource Transform catalog schema: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Resource Transform catalog schema: PASS')
print(f' - 17 self-contained transform items runtime-place into one Generic Store from {len(loaders)} sparse loaders')
print(' - each item carries its complete input/output descriptors; View ABI4 and capability hierarchy are preserved')
