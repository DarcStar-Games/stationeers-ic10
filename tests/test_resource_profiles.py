from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from framework.ic10_harness import IC10
from framework.catalog_test_helpers import load_catalog_chain
import hashlib,json,subprocess,sys,re
R=_PROJECT_ROOT;D=json.loads((R/'data/resource_profiles.json').read_text());P=D['profiles'];fails=[]

def generated_files():
 M=json.loads((R/'data/resource_profile_catalog_manifest.json').read_text())
 return [R/M['generic_store_program'],R/M['coordinator_core_program'],R/M['loader_router_program'],*[R/f for p in M['partitions'] for f in p['loaders']],R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10',R/'ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10',R/'data/resource_profile_catalog_manifest.json']
def hashes():return {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in generated_files()}
b=hashes();subprocess.run([sys.executable,str(R/'generate_resource_profiles.py')],cwd=R,check=True,stdout=subprocess.DEVNULL);a=hashes()
if a!=b:fails.append('generation is not deterministic')
M=json.loads((R/'data/resource_profile_catalog_manifest.json').read_text())
if (M.get('format'),M.get('catalog_store_abi'),M.get('catalog_loader_abi'),M.get('catalog_coordinator_abi'))!=('RESOURCE_PROFILE_CATALOG_V6',5,4,3):fails.append('runtime-placement ABI metadata mismatch')
if M.get('runtime_store_placement') is not True or M.get('runtime_min_store_count')!=5 or M.get('profile_count')!=39 or M.get('physical_item_width')!=16:fails.append('Resource Profile runtime geometry/count mismatch')
if [(p['partition_key'],p['item_count']) for p in M['partitions']]!=[(1,10),(2,27),(4,1),(5,1)]:fails.append('ResourceClass partition/count mismatch')
loader_sources=[[(R/f).read_text() for f in p['loaders']] for p in M['partitions']]
for src in (x for g in loader_sources for x in g):
 code=[z.split('#',1)[0].strip() for z in src.splitlines() if z.split('#',1)[0].strip()]
 if code[0]!='clr db' or code[-1]!='poke 12 1' or any(z.startswith(('put ','putd ','yield','j ')) for z in code):fails.append('loader is not one-shot sparse own-stack producer')
 if re.search(r'^poke\s+\d+\s+0(?:\s|$)',src,re.M):fails.append('loader emits explicit zero payload write')
 # Loader ABI4 has no physical Store or StoreOrdinal assignment; S13/S14 are runtime handoff fields left zero by one-shot producer.
 if re.search(r'^poke\s+13\s+[^0]',src,re.M) or re.search(r'^poke\s+14\s+[^0]',src,re.M):fails.append('loader preassigns physical Store')
store_src=(R/M['generic_store_program']).read_text();stores,vms,loader_groups=load_catalog_chain([store_src]*M['runtime_min_store_count'],loader_sources,store_ref_base=830,loader_ref_base=1200)
coord=vms[0].coord;active=[s for s in stores if s.stack.get(16)==2]
if len(active)!=5:fails.append(f'runtime placement expected 5 ACTIVE Stores, got {len(active)}')
partitions={1:[],2:[],4:[],5:[]}
for s in active:partitions.setdefault(s.stack.get(23),[]).append(s)
if sorted(int(s.stack.get(9,0)) for s in partitions.get(1,[]))!=[10]:fails.append('FLUID runtime placement must fit one Store with 10 items')
if sorted(int(s.stack.get(9,0)) for s in partitions.get(2,[]))!=[1,26]:fails.append('ITEM runtime placement must be capacity-derived 26+1')
if sorted(int(s.stack.get(9,0)) for s in partitions.get(4,[]))!=[1]:fails.append('POWER runtime placement must contain one profile')
if sorted(int(s.stack.get(9,0)) for s in partitions.get(5,[]))!=[1]:fails.append('ENERGY runtime placement must contain one profile')
for s in active:
 if s.stack.get(11)!=coord.ref or s.stack.get(27,0)!=0:fails.append('Store Coordinator/reservation state invalid after imports')
 # every item location is whole, block-aligned and padding remains zero
 for i in range(int(s.stack.get(9,0))):
  base=s.stack.get(32+i*2); n=int(s.stack.get(33+i*2,0))
  if n!=16 or int(base)%4:fails.append('Resource Profile item geometry is not complete/aligned');break
  if s.stack.get(int(base)+14,0)!=0 or s.stack.get(int(base)+15,0)!=0:fails.append('Resource Profile canonical padding is not zero');break
all_loaders=[d for g in loader_groups for d in g]
if any(int(d.stack.get(15,0))!=int(d.stack.get(8,0)) or d.stack.get(13,0)!=0 for d in all_loaders):fails.append('not all Loader items were imported/assignment-cleared')
# View must resolve every profile from an arbitrary runtime Store anchor.
screws={f's{i}':s for i,s in enumerate(stores)};screws['coord']=coord;screws['d0']=stores[-1]
viewsrc=(R/'ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10').read_text()
for i,p in enumerate(P):
 typ='HASH:'+p['resource_type'] if p['resource_type_kind']=='hash_name' else p['resource_type']
 v=IC10(viewsrc,screws,self_ref=900+i);v.stack[2]=p['resource_class'];v.stack[3]=typ;v.run(3,max_steps=50000)
 exp=[p['resource_class'],typ,p['unit'],p['profile_kind'],p['profile_schema'],*p['params']]
 if v.stack.get(4)!=1 or [v.stack.get(x) for x in range(8,22)]!=exp:fails.append(p['slug']+': View mismatch')
by_slug={p['slug']:p for p in P};expected_groups={'ORE':10,'BASIC_INGOT':7,'ALLOY':5,'SUPERALLOY':5}
for g,n in expected_groups.items():
 if sum(p.get('material_group')==g for p in P)!=n:fails.append(f'{g}: expected {n} profiles')
if by_slug.get('electrum_ingot',{}).get('params',[None])[0]!=50:fails.append('Electrum native max stack must be 50')
if 'cobalt_ingot' in by_slug or 'uranium_ingot' in by_slug:fails.append('non-current Cobalt/Uranium ingot profiles should not exist')
loader_text='\n'.join(src for group in loader_sources for src in group)
for p in P:
 human=p.get('description') or p.get('resource_type_name') or p['slug']
 if '# '+human not in loader_text:fails.append(p['slug']+': missing human-readable inline comment')
if fails:
 print('Unified Resource Profile catalog schema: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Unified Resource Profile catalog schema: PASS')
print(f' - 39 profiles placed at runtime into FLUID=10, ITEM=26+1, POWER=1, ENERGY=1 across 5 generic Stores')
print(f' - {len(all_loaders)} sparse relocatable loaders contain only whole 16-cell profile items')
print(' - no Loader preassigns a Store; Router capacity placement leaves no outstanding reservations')
print(' - View resolves all profiles from an arbitrary Store anchor; human-name comments preserved')
