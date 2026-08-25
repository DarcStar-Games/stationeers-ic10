#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import tempfile,sys
import tools.build_release as br
import tools.run_validation as rv
R=_PROJECT_ROOT;fails=[]

def ck(x,msg):
 if not x:fails.append(msg)
# A requested in-tree output must never be part of the tracked release inventory.
probe=R/'_release_self_include_probe.zip'
probe.write_bytes(b'old release')
try:
 files=br.tracked_files({probe})
 ck(probe not in files,'explicit release output exclusion failed')
 ck(probe in br.tracked_files(),'probe did not demonstrate self-inclusion risk without exclusion')
finally:
 probe.unlink(missing_ok=True)
# Main build order must unlink output before source/index/validation/manifest work.
s=(R/'tools'/'build_release.py').read_text()
try:
 unlink=s.index('if out.exists(): out.unlink()')
 guide=s.index("update_user_deployment_inventory.py")
 gen=s.index("generate_source_catalog.py")
 manifest=s.index('write_archive_manifest({out})')
 ck(unlink<guide<gen<manifest,'release output / deployment guide / source index ordering is invalid')
except ValueError: fails.append('release build ordering markers missing')
ck('tracked_files({out})' in s,'ZIP creation does not exclude requested output')
# Both sweeps carry their own copy of the same exclusion set: build_release keeps
# local tooling out of the release inventory, run_validation keeps it out of the
# input fingerprint. Each copy says "keep in sync with" the other, which is a
# comment, not a check -- and a one-sided edit would either ship .git or mark
# live commissioning evidence STALE with no source change. This is the check.
ck(br.TOOLING_DIRS==rv.TOOLING_DIRS,f'TOOLING_DIRS diverged: build_release {sorted(br.TOOLING_DIRS)} vs run_validation {sorted(rv.TOOLING_DIRS)}')
if fails:
 print('Release tooling validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Release tooling validation: PASS')
print(' - in-tree output archive is excluded before manifest and ZIP inventory')
print(' - build ordering removes stale output, refreshes deployment inventory, then source index before validation/manifest generation')
print(f' - release inventory and validation fingerprint exclude the same tooling dirs: {sorted(br.TOOLING_DIRS)}')
