#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import subprocess,sys
R=_PROJECT_ROOT
p=subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_directory_adapters.py'),'--check'],cwd=R,text=True,capture_output=True)
print(p.stdout,end='')
if p.stderr:print(p.stderr,end='')
raise SystemExit(p.returncode)
