#!/usr/bin/env python3
"""Prove non-catalog generators reconstruct the output inventories they own."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import json,sys,tempfile
from framework.generator_productivity import prove_restoration
from tools.generate.generate_script_contracts import declared_outputs as contract_outputs
from tools.generate.generate_source_catalog import FIXED_OUTPUTS as SOURCE_OUTPUTS

R=_PROJECT_ROOT;GEN=R/'tools'/'generate';fails=[]

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

if fails:
 print('Generator productivity tests: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generator productivity tests: PASS')
print(f' - directory adapter generator restored {len(adapter_outputs)} spec-declared outputs')
print(' - source catalog generator restored docs/SCRIPT_INDEX.md')
print(f' - script contract generator restored all {len(contracts)} generated JSON artifacts')
