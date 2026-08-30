#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.validation import Validation
from pathlib import Path
import json,re,sys
R=_PROJECT_ROOT;result=Validation(R)
scanner_path='ic10/shared-input/generic_input_scanner_v1_1.ic10';resolver_path='ic10/shared-input/generic_input_resolver_v1_0.ic10';config_path='ic10/controller-config/config_input_bridge_v1_0.ic10';view_path='ic10/input-profile-catalog/input_profile_view_v5_0.ic10'
scanner=result.source(scanner_path);resolver=result.source(resolver_path);config=result.source(config_path);view=result.source(view_path)
for name,src in [('Scanner',scanner),('Resolver',resolver)]:
 for forbidden in ('ControllerPI','ControllerTest','DiagnosticMapping','GenericConfigEditor.v1','ControllerSelector.v2','ConsoleSelector.v1','DiagnosticMappingEditor.v1'):
  if forbidden in src:result.fail(f'{name}: domain-specific token leaked: {forbidden}')
result.contains(scanner_path,'poke 0 HASH("GenericInputScanner.v1")','poke 1 1','poke 10 r9',rule='Scanner contract')
result.contains(resolver_path,'poke 0 HASH("GenericInputResolver.v1")','putd scanner 9 r6','poke 13 r9',rule='Resolver contract')
result.contains(config_path,'getd r12 editor r0','putd editor 20 r12','putd editor 25 1',rule='Config Bridge contract')
result.contains(view_path,'poke 0 HASH("InputProfileView.v1")','poke 1 1','bne r0 HASH("GenericCatalogStore.v6") Bad','bne r0 6 Bad','bne r0 HASH("CatalogSchema.InputProfile.v3") Bad','poke 11 r14',rule='Input Profile View contract')
data=json.loads((R/'data/input_profiles.json').read_text());diag=[p for p in data['profiles'] if p['profile_type']=='DiagnosticMapping']
if data.get('catalog_schema_version')!=3 or len(diag)!=1 or diag[0]['field_count']!=7:result.fail('Input schema v3 / DiagnosticMapping mismatch')
loaders=sorted((R/'ic10'/'input-profile-catalog').glob('input_profile_catalog_loader_*_v4_0.ic10'))
if len(loaders)!=3:result.fail(f'Input Profile expected 3 relocatable sparse loaders, found {len(loaders)}')
for p in loaders:
 t=p.read_text()
 if 'clr db' not in t or 'poke 1 5' not in t or 'poke 18 1' not in t or 'putd ' in t or '\nyield' in t:result.fail(p.name+': Loader ABI5 contract invalid')
for name in ('ic10/controller-discovery/controller_selector_v3_0.ic10','ic10/diagnostics/console_selector_v1_1.ic10','ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10'):
 if re.search(r'\bd[0-5]\b',result.source(name)):result.fail(name+': still owns physical screw')
raise SystemExit(result.finish('Shared input contract validation',[
 'Scanner/Resolver remain domain-neutral; Input schema v3 uses self-contained relocatable profile items',
 'three Loader ABI4 producers keep each profile directory/descriptors/enums atomic']))
