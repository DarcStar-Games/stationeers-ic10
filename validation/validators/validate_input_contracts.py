#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT;fails=[]
def text(n):return (R/n).read_text()
def need(t,s,l):
 if s not in t:fails.append(l+': missing '+repr(s))
scanner=text('ic10/shared-input/generic_input_scanner_v1_1.ic10');resolver=text('ic10/shared-input/generic_input_resolver_v1_0.ic10');config=text('ic10/controller-config/config_input_bridge_v1_0.ic10');view=text('ic10/input-profile-catalog/input_profile_view_v5_0.ic10')
for name,src in [('Scanner',scanner),('Resolver',resolver)]:
 for forbidden in ('ControllerPI','ControllerTest','DiagnosticMapping','22360680','17320508','17320509','17320510'):
  if forbidden in src:fails.append(f'{name}: domain-specific token leaked: {forbidden}')
for s in ('poke 0 31415930','poke 1 1','poke 10 r9'):need(scanner,s,'Scanner')
for s in ('poke 0 31415931','putd scanner 9 r6','poke 5 r9'):need(resolver,s,'Resolver')
for s in ('getd r12 editor r0','putd editor 20 r12','putd editor 25 1'):need(config,s,'Config Bridge')
for s in ('poke 0 31415929','poke 1 1','bne r0 31415968 Bad','bne r0 5 Bad','bne r0 HASH("CatalogSchema.InputProfile") Bad','bne r0 3 Bad','poke 5 r14'):need(view,s,'Input Profile View')
data=json.loads((R/'data/input_profiles.json').read_text());diag=[p for p in data['profiles'] if p['profile_type']=='DiagnosticMapping']
if data.get('catalog_schema_version')!=3 or len(diag)!=1 or diag[0]['field_count']!=7:fails.append('Input schema v3 / DiagnosticMapping mismatch')
loaders=sorted((R/'ic10'/'input-profile-catalog').glob('input_profile_catalog_loader_*_v4_0.ic10'))
if len(loaders)!=3:fails.append(f'Input Profile expected 3 relocatable sparse loaders, found {len(loaders)}')
for p in loaders:
 t=p.read_text()
 if 'clr db' not in t or 'poke 1 4' not in t or 'poke 12 1' not in t or 'putd ' in t or '\nyield' in t:fails.append(p.name+': Loader ABI4 contract invalid')
for name in ('ic10/controller-discovery/controller_selector_v3_0.ic10','ic10/diagnostics/console_selector_v1_1.ic10','ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10'):
 if re.search(r'\bd[0-5]\b',text(name)):fails.append(name+': still owns physical screw')
if fails:
 print('Shared input contract validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Shared input contract validation: PASS')
print(' - Scanner/Resolver remain domain-neutral; Input schema v3 uses self-contained relocatable profile items')
print(' - three Loader ABI4 producers keep each profile directory/descriptors/enums atomic')
