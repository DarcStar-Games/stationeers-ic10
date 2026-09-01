#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import argparse,json,re,shutil,sys
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET
from framework.catalog_schema import *
from framework.stack_envelope import declared_capability_mask
SCHEMA='CatalogSchema.Recipe';SCHEMA_VERSION=3;INSTANCE='Catalog.Recipes.Printers.Schema3';MAX_INPUTS=16
MANIFEST_FILE='recipe_catalog_manifest.json';LOOKUP_FILE='ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10';FIXED_OUTPUTS=COORDINATION_PROGRAM_FILES+(MANIFEST_FILE,LOOKUP_FILE)
FAMILIES=(('autolathe','Printer.Autolathe','autolathe.xml','AutolatheRecipes'),('electronics','Printer.ElectronicsPrinter','electronics.xml','ElectronicsPrinterRecipes'),('pipe_bender','Printer.HydraulicPipeBender','PipeBender.xml','HydraulicPipeBenderRecipes'),('tool_manufactory','Printer.ToolManufactory','toolmanufacturer.xml','ToolManufactoryRecipes'),('security','Printer.SecurityPrinter','security.xml','SecurityPrinterRecipes'),('rocket_manufactory','Printer.RocketManufactory','rocketmanufactory.xml','RocketManufactoryRecipes'))
TIER_WORDS={'TierOne':1,'Tier1':1,'One':1,'TierTwo':2,'Tier2':2,'Two':2,'TierThree':3,'Tier3':3,'Three':3,'TierFour':4,'Tier4':4,'Four':4,'TierFive':5,'Tier5':5,'Five':5}
@dataclass(frozen=True)
class Recipe:
 family_key:str;family_hash_name:str;prefab_name:str;required_capability:int;source_order:int;inputs:tuple;family_ordinal:int=0

def tag(x):return x.rsplit('}',1)[-1]
def child(e,n):
 for c in e:
  if tag(c.tag)==n:return c
 return None
def child_text(e,n):
 c=child(e,n);return None if c is None else c.text
def find_section(root,n):
 for e in root.iter():
  if tag(e.tag)==n:return e
 return None
def tier(text):
 if text is None or not text.strip():return 1
 x=text.strip()
 if x in TIER_WORDS:return TIER_WORDS[x]
 m=re.fullmatch(r'Tier\s*(\d+)',x,re.I)
 if m and int(m.group(1))>=1:return int(m.group(1))
 if x.isdigit() and int(x)>=1:return int(x)
 raise ValueError(f'unsupported RecipeTier {x!r}')
def quantity(text,name):
 try:q=float((text or '').strip())
 except Exception:raise ValueError(f'non-numeric Recipe field {name}={text!r}')
 if not (q>=0) or q==float('inf'):raise ValueError(f'invalid Recipe quantity {name}={text!r}')
 return int(q) if q.is_integer() else q
def recipe_inputs(e):
 r=child(e,'Recipe')
 if r is None:return ()
 out=[]
 for c in r:
  name=tag(c.tag)
  if name in ('Time','Energy'):continue
  q=quantity(c.text,name)
  if q>0:out.append((name,q))
 if len(out)>MAX_INPUTS:raise ValueError(f'recipe has {len(out)} material inputs; max {MAX_INPUTS}')
 return tuple(out)
def locate(data,filename):
 p=data/filename
 if p.exists():return p
 m={q.name.lower():q for q in data.glob('*.xml')}.get(filename.lower())
 if m:return m
 raise FileNotFoundError(filename)
def parse_family(data,spec):
 key,fhash,fn,section=spec;sec=find_section(ET.parse(locate(data,fn)).getroot(),section)
 if sec is None:raise ValueError(f'{fn}: missing {section}')
 rows=[]
 for i,e in enumerate(x for x in sec if tag(x.tag)=='RecipeData'):
  prefab=(child_text(e,'PrefabName') or '').strip()
  if not prefab:raise ValueError(f'{fn}: recipe {i+1} missing PrefabName')
  rows.append(Recipe(key,fhash,prefab,tier(child_text(e,'RecipeTier')),i,recipe_inputs(e)))
 if not rows:raise ValueError(f'{fn}: no recipes')
 rows.sort(key=lambda r:(r.required_capability,r.source_order))
 return [Recipe(r.family_key,r.family_hash_name,r.prefab_name,r.required_capability,r.source_order,r.inputs,i) for i,r in enumerate(rows)]
def discover(arg):
 if arg:
  p=Path(arg).expanduser();opts=[p,p/'rocketstation_Data'/'StreamingAssets'/'Data',p/'StreamingAssets'/'Data',p/'Data']
  for o in opts:
   if (o/'autolathe.xml').exists() or (o/'Autolathe.xml').exists():return o
 raise FileNotFoundError('pass --game-data pointing to Stationeers GameData')
def recipe_item(r):
 p=[f'HASH("{r.prefab_name}")',f'HASH("{r.family_hash_name}")',r.required_capability,r.family_ordinal,len(r.inputs)]
 for name,q in r.inputs:p += [f'HASH("{name}")',q]
 while len(p)%CELL_BLOCK_WIDTH:p.append(0)
 return CatalogItem(tuple(p),r.prefab_name)
def lookup_program():
 template='# Recipe Catalog Lookup v8: Store ABI6 dynamic item heap; d0=any Recipe Store.\n# Request S12 Family,S13 Cap,S14 Ordinal,S15 Gen. Response S8..S11,S16 token.\npoke 0 HASH("RecipeCatalogLookup.v3")\npoke 1 3\npoke 2 __CAPABILITY_MASK__\npoke 16 0\nLoop:\nyield\nget r15 db 15\nget r0 db 16\nbeq r15 r0 Loop\nget r3 db 12\nget r4 db 13\nget r5 db 14\nbltz r5 BadRequest\nbdns d0 CatalogBad\nl r1 d0 ReferenceId\nget r12 d0 11\nblez r12 CatalogBad\ngetd r0 r12 0\nbne r0 HASH("CatalogCoordinatorCore.v4") CatalogBad\ngetd r14 r12 22\nmod r0 r14 2\nbnez r0 CatalogBad\nFirst:\ngetd r0 r1 21\nblez r0 Start\nmove r1 r0\nj First\nStart:\nmove r7 0\nmove r8 0\nmove r9 0\nStore:\ngetd r0 r1 0\nbne r0 HASH("GenericCatalogStore.v6") CatalogBad\ngetd r0 r1 1\nbne r0 6 CatalogBad\ngetd r0 r1 3\nbne r0 HASH("CatalogSchema.Recipe.v3") CatalogBad\ngetd ra r1 17\nmod r0 ra 2\nbnez r0 Loop\ngetd r11 r1 9\nadd r7 r7 r11\ngetd r0 r1 23\nbne r0 r3 StoreDone\nmove sp 0\nRecords:\nbge sp r11 StoreDone\nmul r0 sp 2\nadd r0 r0 32\ngetd r10 r1 r0\nadd r0 r10 1\ngetd r2 r1 r0\nbne r2 r3 NextRec\nadd r0 r10 2\ngetd r2 r1 r0\nbgt r2 r4 NextRec\nadd r8 r8 1\nadd r0 r10 3\ngetd r0 r1 r0\nbne r0 r5 NextRec\nbnez r9 CatalogBad\ngetd r0 r1 r10\npoke 10 r0\npoke 11 r2\nmove r9 1\nNextRec:\nadd sp sp 1\ngetd r11 r1 9\nj Records\nStoreDone:\ngetd r0 r1 17\nbne r0 ra Loop\ngetd r10 r1 24\nblez r10 Finish\nmove r1 r10\nj Store\nFinish:\ngetd r0 r12 22\nbne r0 r14 Loop\nbeqz r8 NotFound\nbge r5 r8 NotFound\nbnez r9 Found\nj CatalogBad\nFound:\npoke 8 1\npoke 9 r8\npoke 16 r15\nj Loop\nBadRequest:\nmove r0 -1\nj Fail\nCatalogBad:\nmove r0 -2\nj Fail\nNotFound:\nmove r0 -3\nFail:\npoke 8 r0\npoke 9 r8\npoke 10 0\npoke 16 r15\nj Loop\n'
 return template.replace(
  '__CAPABILITY_MASK__',
  str(declared_capability_mask(_PROJECT_ROOT,LOOKUP_FILE)),
 )
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--game-data');ap.add_argument('--output',default='recipe_catalog/generated');ap.add_argument('--clean',action='store_true');a=ap.parse_args();data=discover(a.game_data);out=Path(a.output)
 if a.clean and out.exists():shutil.rmtree(out)
 out.mkdir(parents=True,exist_ok=True);prod=out/'ic10'/'recipe-catalog';prod.mkdir(parents=True,exist_ok=True);coord=ensure_coordination_programs(out)
 family_rows=[];allr=[]
 for spec in FAMILIES:
  fam=parse_family(data,spec);family_rows.append((spec,fam));allr+=fam
 canonical={'schema':SCHEMA,'schema_version':SCHEMA_VERSION,'recipes':[(r.family_hash_name,r.required_capability,r.family_ordinal,r.prefab_name,r.inputs) for r in allr]};digest,token=stable_hash_token('RC6',canonical)
 manifest=common_manifest(schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,store_count=0,total_items=len(allr),catalog_digest=digest)
 manifest.update({'format':'RECIPE_CATALOG_V6','catalog_token':token,'recipe_count':len(allr),'item_model':'header5_plus_reagent_pairs_block_aligned','max_material_inputs':MAX_INPUTS,'storage_partition':'printer_family','runtime_store_placement':True,'families':[],'loaders':[],'loader_item_atomicity':'recipe_never_split','loader_sparse_zero_init':True,'generic_store_program':GENERIC_STORE_FILE,'coordinator_core_program':coord[1],'loader_router_program':coord[2]})
 total_min=0
 for spec,fam in family_rows:
  key,fhash,fn,section=spec;partition=f'HASH("{fhash}")';items=[recipe_item(r) for r in fam]
  parts=split_catalog_items(label=f'GENERATED Recipe {key} loader',schema_name=SCHEMA,schema_version=SCHEMA_VERSION,instance_name=INSTANCE,partition_key_expr=partition,items=items)
  lfiles=[]
  for li,(subset,text) in enumerate(parts):
   name=f'recipe_{key}_loader_{li:02d}_v4_0.ic10';(prod/name).write_text(text);rel=f'ic10/recipe-catalog/{name}';lfiles.append(rel);manifest['loaders'].append(rel)
  counts=pack_store_counts([x.cells for x in items]);total_min+=len(counts)
  manifest['families'].append({'key':key,'family_hash_name':fhash,'source_file':fn,'source_section':section,'recipe_count':len(fam),'max_capability':max(r.required_capability for r in fam),'max_material_inputs':max(len(r.inputs) for r in fam),'runtime_min_store_count':len(counts),'runtime_store_item_counts':counts,'loader_count':len(parts),'loaders':lfiles,'recipes':[{'prefab_name':r.prefab_name,'required_capability':r.required_capability,'family_ordinal':r.family_ordinal,'inputs':[{'reagent':n,'quantity':q} for n,q in r.inputs]} for r in fam]})
 manifest['store_count']=total_min;manifest['runtime_min_store_count']=total_min
 (out/MANIFEST_FILE).write_text(json.dumps(manifest,indent=2)+'\n')
 (out/LOOKUP_FILE).write_text(lookup_program())
 print(f'Recipe Catalog generation: PASS - {len(allr)} recipes / runtime min {total_min} stores / {len(manifest["loaders"])} relocatable loaders')
if __name__=='__main__':
 try:main()
 except Exception as e:print('Recipe Catalog generation: FAIL:',e,file=sys.stderr);raise SystemExit(1)
