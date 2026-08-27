#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,subprocess,sys
R=_PROJECT_ROOT
p=subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_directory_adapters.py'),'--check'],cwd=R,text=True,capture_output=True)
print(p.stdout,end='')
if p.stderr:print(p.stderr,end='')
count=len(json.loads((R/'data'/'directory_adapter_specs.json').read_text())['adapters'])
summary=f'Generated directory adapters: CHECK PASS ({count})'
if p.returncode or summary not in p.stdout.splitlines():
 print(f'Generated directory adapter validation: FAIL - missing expected summary {summary!r}')
 raise SystemExit(1)
