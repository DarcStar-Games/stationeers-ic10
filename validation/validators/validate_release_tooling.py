#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import re,tempfile,sys
import tools.build_release as br
import tools.run_validation as rv
R=_PROJECT_ROOT;fails=[]

def ck(x,msg):
 if not x:fails.append(msg)

def canonical_read_permissions(text):
 lines=text.splitlines()
 declarations=[i for i,line in enumerate(lines) if 'permissions' in line]
 if len(declarations)!=1 or lines[declarations[0]]!='permissions:': return False
 body=[]
 for line in lines[declarations[0]+1:]:
  if line and not line[0].isspace(): break
  if line.strip(): body.append(line)
 return body==['  contents: read']
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
ck('.github' in br.TOOLING_DIRS,'.github automation tooling is included in releases or live-evidence fingerprints')
# CI is the independent release gate: it must run the whole suite from a clean
# checkout, fail on regenerated tracked/untracked output, and retain diagnostics
# without granting a pull request a write-capable token. Keep these as policy
# checks rather than depending on a contributor to review workflow YAML by eye.
workflow=R/'.github/workflows/clean-validation.yml';ci_doc=R/'docs/CI.md'
if not workflow.exists():
 fails.append('clean validation GitHub Actions workflow is missing')
else:
 w=workflow.read_text()
 ck(workflow not in br.tracked_files(),'CI workflow leaked into the release inventory')
 required_markers=(
  'name: Validation','  pull_request:','  push:','      - main',
  'permissions:\n  contents: read','cancel-in-progress: true',
  'name: Clean validation','runs-on: ubuntu-24.04','timeout-minutes: 20',
  'persist-credentials: false','run: python3 tools/run_validation.py',
  'if: ${{ always() }}','git diff --exit-code --stat',
  'git status --porcelain=v1 --untracked-files=all','if: ${{ failure() }}',
  'validation/FULL_VALIDATION_RUN.txt','validation/evidence/',
 )
 for marker in required_markers:
  ck(marker in w,f'CI workflow is missing policy marker {marker!r}')
 ck('pull_request_target:' not in w,'CI workflow uses privileged pull_request_target')
 ck('--resume' not in w,'CI workflow reuses local validation evidence with --resume')
 ck(canonical_read_permissions(w),'CI permissions must be exactly one top-level contents: read block')
 for expanded in (
  w.replace('  contents: read','  contents: read\n  actions: write # accidental expansion'),
  w.replace('jobs:','jobs:\n  unsafe:\n    permissions:\n      actions: write',1),
 ):
  ck(not canonical_read_permissions(expanded),'CI permission policy accepts an expanded permission block')
 version=re.search(r'(?m)^\s*python-version:\s*["\'](\d+\.\d+\.\d+)["\']\s*$',w)
 ck(bool(version),'CI Python version is not pinned to an exact patch release')
 uses=re.findall(r'(?m)^\s*uses:\s*([^\s#]+)',w)
 expected={'actions/checkout','actions/setup-python','actions/upload-artifact'}
 seen=set()
 for use in uses:
  match=re.fullmatch(r'([^@]+)@([0-9a-f]{40})',use)
  if not match:
   fails.append(f'CI action is not pinned to an immutable commit SHA: {use!r}')
  else: seen.add(match.group(1))
 ck(seen==expected,f'CI action set differs from the reviewed set: {sorted(seen)}')
if not ci_doc.exists():
 fails.append('docs/CI.md is missing')
else:
 d=ci_doc.read_text()
 for marker in ('.github/workflows/clean-validation.yml','Clean validation',
                'Require status checks to pass before merging','python3 tools/run_validation.py',
                'CI-generated evidence is diagnostic only'):
  ck(marker in d,f'docs/CI.md is missing policy marker {marker!r}')
# Both sweeps match on the path *inside* the repository. A tooling-dir name in the
# absolute path above it must not exclude the repository: without that, a checkout
# under any .git/.claude/__pycache__ directory sweeps to empty, and an empty sweep
# hashes the empty tree so no commissioning session is ever STALE again.
with tempfile.TemporaryDirectory() as td:
 fake=Path(td)/'.claude'/'checkout';(fake/'validation'/'evidence').mkdir(parents=True)
 (fake/'.github/workflows').mkdir(parents=True)
 (fake/'source.txt').write_text('x');(fake/'validation'/'evidence'/'E.txt').write_text('y')
 (fake/'.github/workflows'/'ci.yml').write_text('name: old')
 try:
  base=rv.input_fingerprint(fake)
  (fake/'.github/workflows'/'ci.yml').write_text('name: new')
  ck(base==rv.input_fingerprint(fake),'workflow-only change invalidated live commissioning evidence')
  (fake/'source.txt').write_text('z');moved=rv.input_fingerprint(fake)
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
print(' - CI runs clean validation with read-only permissions, pinned dependencies, clean-tree enforcement, and failure evidence')
print(' - exclusion matches inside the repository only, and a sweep that finds nothing fails closed')
