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
 contracts=s.index("generate_script_contracts.py")
 manifest=s.index('write_archive_manifest({out})')
 ck(unlink<guide<gen<contracts<manifest,'release output / deployment guide / source index / script contract ordering is invalid')
except ValueError: fails.append('release build ordering markers missing')
ck('tracked_files({out})' in s,'ZIP creation does not exclude requested output')
# Both sweeps carry their own copy of the same exclusion set: build_release keeps
# local tooling out of the release inventory, run_validation keeps it out of the
# input fingerprint. Each copy says "keep in sync with" the other, which is a
# comment, not a check -- and a one-sided edit would either ship .git or mark
# live commissioning evidence STALE with no source change. This is the check.
ck(br.TOOLING_DIRS==rv.TOOLING_DIRS,f'TOOLING_DIRS diverged: build_release {sorted(br.TOOLING_DIRS)} vs run_validation {sorted(rv.TOOLING_DIRS)}')
# Both sweeps match on the path *inside* the repository. A tooling-dir name in the
# absolute path above it must not exclude the repository: without that, a checkout
# under any .git/.claude/__pycache__ directory sweeps to empty, and an empty sweep
# hashes the empty tree so no commissioning session is ever STALE again.
with tempfile.TemporaryDirectory() as td:
 fake=Path(td)/'.claude'/'checkout';(fake/'validation'/'evidence').mkdir(parents=True)
 (fake/'source.txt').write_text('x');(fake/'validation'/'evidence'/'E.txt').write_text('y')
 try:
  base=rv.input_fingerprint(fake);(fake/'source.txt').write_text('z');moved=rv.input_fingerprint(fake)
  ck(base!=moved,'source under a tooling-named parent directory is excluded from the fingerprint')
  (fake/'validation'/'evidence'/'E.txt').write_text('z')
  ck(moved==rv.input_fingerprint(fake),'validation evidence leaked into the input fingerprint')
 except RuntimeError as e: fails.append(f'fingerprint swept a tooling-named parent directory to empty: {e}')
 empty=Path(td)/'empty';empty.mkdir()
 try: rv.input_fingerprint(empty);fails.append('an input sweep that found nothing did not fail closed')
 except RuntimeError: pass
if fails:
 print('Release tooling validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Release tooling validation: PASS')
print(' - in-tree output archive is excluded before manifest and ZIP inventory')
print(' - build ordering removes stale output, refreshes deployment inventory, source index, and script contracts before validation/manifests')
print(f' - release inventory and validation fingerprint exclude the same tooling dirs: {sorted(br.TOOLING_DIRS)}')
print(' - exclusion matches inside the repository only, and a sweep that finds nothing fails closed')
