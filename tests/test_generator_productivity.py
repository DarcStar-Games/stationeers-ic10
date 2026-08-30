#!/usr/bin/env python3
"""Prove non-catalog generators reconstruct the output inventories they own."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import json,sys,tempfile
from framework.catalog_generation import CatalogFamily,CatalogPartition,run_catalog_generation
from framework.catalog_schema import CatalogItem
from framework.generator_productivity import prove_restoration
from tools.generate.generate_script_contracts import declared_outputs as contract_outputs
from tools.generate.generate_source_catalog import FIXED_OUTPUTS as SOURCE_OUTPUTS

R=_PROJECT_ROOT;GEN=R/'tools'/'generate';fails=[]

def pipeline_family(root,*,partitions,loader_filename,manifest_extensions=lambda source,result:{},rendered_outputs=()):
 source=root/'data'/'catalog.json';source.parent.mkdir(parents=True,exist_ok=True);source.write_text(json.dumps({'items':[1]})+'\n')
 return CatalogFamily(root=root,source_file='data/catalog.json',manifest_file='data/manifest.json',schema_name='CatalogSchema.Test',schema_version=1,instance_name='Catalog.Test',collection_key='items',digest_prefix='TEST',cleanup_globs=(),rendered_output_files=tuple(rendered_outputs),build_partitions=lambda source:partitions,loader_filename=loader_filename,render_outputs=lambda source:{name:'# test\n' for name in rendered_outputs},manifest_extensions=manifest_extensions,source_extensions=lambda source,result:{},summary_label='Test',summary_item_name='items')

def expect_pipeline_error(family,message):
 try:run_catalog_generation(family)
 except ValueError as error:
  if message not in str(error):fails.append(f'catalog pipeline reported the wrong error: {error}')
 else:fails.append(f'catalog pipeline accepted {message}')

specs=json.loads((R/'data'/'directory_adapter_specs.json').read_text())['adapters']
adapter_outputs=[R/spec['file'] for spec in specs]
fails += prove_restoration(
 R,adapter_outputs,[sys.executable,str(GEN/'generate_directory_adapters.py')])

fails += prove_restoration(
 R,[R/rel for rel in SOURCE_OUTPUTS],[sys.executable,str(GEN/'generate_source_catalog.py')])

contracts=contract_outputs(R)
fails += prove_restoration(
 R,[R/rel for rel in contracts],[sys.executable,str(GEN/'generate_script_contracts.py')])

with tempfile.TemporaryDirectory() as temporary:
 root=_ProjectPath(temporary);a=root/'a.txt';b=root/'b.txt';a.write_text('a');b.write_text('b')
 partial=root/'partial.py';partial.write_text("from pathlib import Path\nPath('a.txt').write_text('a')\n")
 if not prove_restoration(root,[a,b],[sys.executable,partial]):
  fails.append('productivity helper accepted a generator that restored only one declared output')
 extra=root/'extra.py';extra.write_text("from pathlib import Path\nPath('a.txt').write_text('a')\nPath('b.txt').write_text('b')\nPath('extra.txt').write_text('extra')\n")
 if not prove_restoration(root,[a,b],[sys.executable,extra]):
  fails.append('productivity helper accepted an undeclared generated file')
 slow=root/'slow.py';slow.write_text("import time\ntime.sleep(1)\n")
 timeout_failures=prove_restoration(root,[a,b],[sys.executable,slow],timeout=.05)
 if not any(message.startswith('generator timed out after ') for message in timeout_failures):
  fails.append('productivity helper did not enforce or report its generator timeout')

with tempfile.TemporaryDirectory() as temporary:
 root=_ProjectPath(temporary);item=CatalogItem((1,0,0,0),'test')
 one=(CatalogPartition('0','test',(item,)),)
 two=(CatalogPartition('0','first',(item,)),CatalogPartition('1','second',(item,)))
 override=pipeline_family(root/'override',partitions=one,loader_filename=lambda partition,ordinal:'generated/loader.ic10',manifest_extensions=lambda source,result:{'store_count':999})
 expect_pipeline_error(override,'manifest extensions override shared fields')
 duplicate=pipeline_family(root/'duplicate',partitions=two,loader_filename=lambda partition,ordinal:'generated/loader.ic10')
 expect_pipeline_error(duplicate,'generated output path collision')
 overlap=pipeline_family(root/'overlap',partitions=one,loader_filename=lambda partition,ordinal:'generated/fixed.ic10',rendered_outputs=('generated/fixed.ic10',))
 expect_pipeline_error(overlap,'generated output path collision')
 for family in (override,duplicate,overlap):
  if (family.root/'ic10').exists() or (family.root/'generated').exists():fails.append('catalog pipeline changed outputs before preflight failure')

if fails:
 print('Generator productivity tests: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generator productivity tests: PASS')
print(f' - directory adapter generator restored {len(adapter_outputs)} spec-declared outputs')
print(' - source catalog generator restored docs/SCRIPT_INDEX.md')
print(f' - script contract generator restored all {len(contracts)} generated JSON artifacts')
print(' - catalog pipeline rejects protected manifest overrides and output path collisions before writing')
