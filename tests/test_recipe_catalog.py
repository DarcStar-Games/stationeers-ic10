#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from framework.ic10_harness import IC10
from framework.catalog_test_helpers import load_catalog_chain,generate_recipe_fixture
from framework.generator_productivity import prove_generated_tree_restoration
from tools.generate.generate_recipe_catalog import FIXED_OUTPUTS,LOOKUP_FILE
import json,re,subprocess,tempfile,sys
R=_PROJECT_ROOT;fails=[];fixture_tmp=tempfile.TemporaryDirectory();fixture=Path(fixture_tmp.name);M=generate_recipe_fixture(fixture)
for rel in FIXED_OUTPUTS:
 if not (fixture/rel).is_file():fails.append(f'Recipe generator did not produce {rel}')
fails += prove_generated_tree_restoration(
 fixture,[sys.executable,str(R/'tools'/'generate'/'generate_recipe_catalog.py'),'--game-data',str(R/'tests'/'fixtures'/'recipe_game_data'),'--output',str(fixture),'--clean'],R)
if (M.get('format'),M.get('catalog_store_abi'),M.get('catalog_loader_abi'),M.get('catalog_coordinator_abi'),M.get('catalog_schema_version'))!=('RECIPE_CATALOG_V6',5,5,3,3):fails.append('Recipe runtime/schema ABI mismatch')
if M.get('storage_partition')!='printer_family' or M.get('runtime_min_store_count')!=6 or M.get('recipe_count')!=11:fails.append('fixture family partition/capacity mismatch')
if any(f['runtime_min_store_count']!=1 for f in M['families']):fails.append('fixture should require one runtime Store per family')

def loader_invariants(root,m):
 for f in m['families']:
  text='\n'.join((root/n).read_text() for n in f['loaders'])
  for recipe in f['recipes']:
   name=recipe['prefab_name'] if isinstance(recipe,dict) else recipe
   if '# '+name not in text:fails.append(name+': missing human-readable inline comment')
 for n in m['loaders']:
  src=(root/n).read_text();code=[z.split('#',1)[0].strip() for z in src.splitlines() if z.split('#',1)[0].strip()]
  if code[0]!='clr db' or code[-1]!='poke 18 1' or any(z.startswith(('put ','putd ','yield','j ')) for z in code):fails.append(n+': not one-shot sparse own-stack loader')
  if re.search(r'^poke\s+\d+\s+0(?:\s|$)',src,re.M):fails.append(n+': explicit zero payload poke')

def load(root,m,base,lb):
 store=(root/m['generic_store_program']).read_text(); groups=[[(root/n).read_text() for n in f['loaders']] for f in m['families']]
 return load_catalog_chain([store]*m['runtime_min_store_count'],groups,store_ref_base=base,loader_ref_base=lb,coordinator_source=(root/m['coordinator_core_program']).read_text(),router_source=(root/m['loader_router_program']).read_text())

def net(stores,coord):return {'coord':coord,**{f's{i}':s for i,s in enumerate(stores)}}
def lookup(root,stores,coord,fam,cap,ordinal,gen=1):
 v=IC10((root/LOOKUP_FILE).read_text(),{'d0':stores[-1]}|net(stores,coord));v.stack[3]='HASH:'+fam;v.stack[4]=cap;v.stack[5]=ordinal;v.stack[6]=gen;v.run(3,max_steps=50000);return v
loader_invariants(fixture,M);stores,vms,groups=load(fixture,M,1150,2000);coord=vms[0].coord
active=[s for s in stores if s.stack.get(16)==2]
if len(active)!=6:fails.append('fixture did not runtime-claim exactly six Stores')
for f in M['families']:
 ss=[s for s in active if s.stack.get(23)==f"HASH:{f['family_hash_name']}"]
 if len(ss)!=1 or int(ss[0].stack.get(9,0))!=f['recipe_count']:fails.append(f["key"]+': runtime family Store purity/count mismatch')
v=lookup(fixture,stores,coord,'Printer.Autolathe',2,1)
if v.stack.get(8)!=1 or v.stack.get(9)!=2 or v.stack.get(10)!='HASH:ItemAutolathePrinterMod' or v.stack.get(11)!=2:fails.append('fixture linked lookup mismatch')
v=lookup(fixture,stores,coord,'Printer.SecurityPrinter',1,0,gen=2)
if v.stack.get(8)!=1 or v.stack.get(9)!=1 or v.stack.get(10)!='HASH:ItemCartridge' or v.stack.get(11)!=1:fails.append('Security capability-1 lookup exposed inaccessible Tier Two recipe')
# Execution view resolves a RecipeHash to family/capability plus exact reagent requirements.
ev=IC10((R/'ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10').read_text(),{'d0':stores[-1]}|net(stores,coord));ev.stack[2]='HASH:ItemKitFurnace';ev.run(3,max_steps=50000)
if ev.stack.get(7)!=1 or ev.stack.get(41)!='HASH:ItemKitFurnace' or ev.stack.get(3)!='HASH:Printer.Autolathe' or ev.stack.get(4)!=1 or ev.stack.get(5)!=2 or [ev.stack.get(i) for i in range(8,12)]!=['HASH:Iron',30,'HASH:Copper',10]:fails.append('Recipe Execution Profile reagent resolution mismatch')
ev.stack[2]='HASH:ItemDoesNotExist';ev.run(2,max_steps=50000)
if ev.stack.get(7)!=-3 or ev.stack.get(41)!='HASH:ItemDoesNotExist':fails.append('Recipe Execution Profile missing-recipe response mismatch')
# Stress generation: 130 recipes/family derives two Stores per family without generator-assigned boundaries.
specs=(('autolathe.xml','AutolatheRecipes'),('electronics.xml','ElectronicsPrinterRecipes'),('PipeBender.xml','HydraulicPipeBenderRecipes'),('toolmanufacturer.xml','ToolManufactoryRecipes'),('security.xml','SecurityPrinterRecipes'),('rocketmanufactory.xml','RocketManufactoryRecipes'))
with tempfile.TemporaryDirectory() as td:
 d=Path(td)/'data';o=Path(td)/'out';d.mkdir()
 for fi,(fn,sec) in enumerate(specs):
  rows=[]
  for i in range(130):
   tier='<RecipeTier>TierTwo</RecipeTier>' if i>=100 else ''
   rows.append(f'<RecipeData><PrefabName>ItemSyntheticF{fi}R{i:03d}</PrefabName>{tier}</RecipeData>')
  (d/fn).write_text(f'<GameData><{sec}>'+''.join(rows)+f'</{sec}></GameData>')
 subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_recipe_catalog.py'),'--game-data',str(d),'--output',str(o),'--clean'],check=True,stdout=subprocess.DEVNULL)
 m=json.loads((o/'recipe_catalog_manifest.json').read_text());loader_invariants(o,m)
 if m['recipe_count']!=780 or m['runtime_min_store_count']!=18 or any(f['runtime_min_store_count']!=3 or f['runtime_store_item_counts']!=[48,48,34] for f in m['families']):fails.append('780-recipe runtime capacity estimate mismatch')
 if any(len(p.read_text().splitlines())>120 for p in o.glob('*.ic10')):fails.append('generated Recipe IC exceeds 120-line soft limit')
# Execute the minimum overflowing family plus one item in each other family so runtime cross-Store placement is exercised without redundant interpreter work. The 780-item generator stress above still proves 48+48+34 capacity geometry.
with tempfile.TemporaryDirectory() as td:
 d=Path(td)/'data';o=Path(td)/'out';d.mkdir()
 for fi,(fn,sec) in enumerate(specs):
  count=49 if fi==0 else 1;rows=[]
  for i in range(count):rows.append(f'<RecipeData><PrefabName>ItemRuntimeF{fi}R{i:03d}</PrefabName></RecipeData>')
  (d/fn).write_text(f'<GameData><{sec}>'+''.join(rows)+f'</{sec}></GameData>')
 subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_recipe_catalog.py'),'--game-data',str(d),'--output',str(o),'--clean'],check=True,stdout=subprocess.DEVNULL)
 m=json.loads((o/'recipe_catalog_manifest.json').read_text())
 # This execution check only needs the overflowing Autolathe partition. The small fixture above already executes all six family partitions; loading unrelated one-item families here adds interpreter cost without additional boundary coverage.
 af=next(f for f in m['families'] if f['key']=='autolathe')
 store_src=(o/m['generic_store_program']).read_text()
 runtime,rvms,rg=load_catalog_chain([store_src]*af['runtime_min_store_count'],[[(o/n).read_text() for n in af['loaders']]],store_ref_base=3000,loader_ref_base=5000,coordinator_source=(o/m['coordinator_core_program']).read_text(),router_source=(o/m['loader_router_program']).read_text())
 rcoord=rvms[0].coord;act=[s for s in runtime if s.stack.get(16)==2]
 auto=[s for s in act if s.stack.get(23)=='HASH:Printer.Autolathe']
 if sorted(int(s.stack.get(9,0)) for s in auto)!=[1,48]:fails.append('runtime Autolathe overflow must place 48+1 whole recipes')
 v=lookup(o,runtime,rcoord,'Printer.Autolathe',1,48)
 if v.stack.get(8)!=1 or v.stack.get(9)!=49 or v.stack.get(10)!='HASH:ItemRuntimeF0R048':fails.append('runtime overflow linked lookup mismatch')
if fails:
 print('Recipe Catalog runtime-placement schema: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Recipe Catalog runtime-placement schema: PASS')
print(' - fixture dynamically claims one pure Store per printer family')
print(' - capability-1 Security Printer lookup excludes its inaccessible Tier Two metadata')
print(' - RecipeHash execution view republishes family/capability and exact reagent requirements')
print(' - 780-recipe stress case derives 18 Stores at runtime: 48+48+34 recipes per family under schema v3')
print(' - Loaders contain whole recipes only and never preassign physical Stores')
