#!/usr/bin/env python3
"""Build a verified release archive in validation-before-manifest order."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import argparse, hashlib, shutil, subprocess, sys, zipfile
import tools.run_validation as validation

ROOT=_PROJECT_ROOT
# Local VCS/tooling state is not shippable framework content. run_validation.py
# excludes the same set from the input fingerprint, and
# validation/validators/validate_release_tooling.py fails if the two diverge.
TOOLING_DIRS={'.git','.github','.claude','.githooks'}

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def clean_transients():
    for d in ROOT.rglob('__pycache__'): shutil.rmtree(d)
    legacy=ROOT/'recipe_catalog_fixture_generated'
    if legacy.exists(): shutil.rmtree(legacy)

def write_deployment_baseline():
    files=sorted((ROOT/'ic10').rglob('*.ic10'),key=lambda p:p.relative_to(ROOT).as_posix())
    (ROOT/'DEPLOYMENT_BASELINE.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(ROOT).as_posix()}\n' for p in files))

def tracked_files(exclude=()):
    skip={'ARCHIVE_MANIFEST.sha256'}
    excluded={Path(x).resolve() for x in exclude}
    files=[]
    for p in ROOT.rglob('*'):
        if not p.is_file(): continue
        # Match inside the repository: p.parts carries the absolute path, so a checkout under a
        # directory named .git/.claude/__pycache__ would otherwise exclude the whole repository.
        inside=set(p.relative_to(ROOT).parts)
        if TOOLING_DIRS&inside or '__pycache__' in inside or p.name in skip or p.suffix=='.pyc': continue
        if p.resolve() in excluded: continue
        files.append(p)
    # Fail closed rather than shipping an empty archive under a manifest that verifies.
    if not files: raise RuntimeError('release inventory swept to empty')
    return sorted(files,key=lambda p:p.relative_to(ROOT).as_posix())

def archive_manifest(files):
    return ''.join(f'{sha(p)}  {p.relative_to(ROOT).as_posix()}\n' for p in files)

def verify_manifest(manifest):
    for line in manifest.splitlines():
        digest,rel=line.split('  ',1); p=ROOT/rel
        if not p.exists() or sha(p)!=digest: raise RuntimeError(f'manifest mismatch: {rel}')

def validation_evidence_files():
    """Return every ephemeral validation file required in a release archive."""
    return [validation.SUMMARY,validation.RUN_LOG,validation.STATE]+[
        validation.EVIDENCE/validation.evidence_name(script) for script in validation.SCRIPTS
    ]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
    out=Path(args.output).resolve()
    # Remove/exclude the requested output before any manifest inventory is built.
    if out.exists(): out.unlink()
    clean_transients()
    subprocess.run([sys.executable,str(ROOT/'tools'/'generate'/'generate_directory_adapters.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/'generate'/'update_user_deployment_inventory.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/'generate'/'generate_source_catalog.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/'generate'/'update_magic_registry.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'tools'/'generate'/'generate_script_contracts.py')],cwd=ROOT,check=True)
    # Releases always regenerate evidence from scratch. Local validation may use
    # --resume, but a release must not package output reused from an earlier run.
    subprocess.run([sys.executable,str(ROOT/'tools'/'run_validation.py')],cwd=ROOT,check=True)
    evidence=validation_evidence_files();missing=[p for p in evidence if not p.is_file()]
    if missing: raise RuntimeError(f'missing release validation evidence: {missing[0].relative_to(ROOT)}')
    # No source/generated-doc mutation is allowed after validation except release evidence/manifests.
    write_deployment_baseline(); files=tracked_files({out}); manifest=archive_manifest(files); verify_manifest(manifest)
    omitted=[p for p in evidence if p not in files]
    if omitted: raise RuntimeError(f'release inventory omitted validation evidence: {omitted[0].relative_to(ROOT)}')
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p,p.relative_to(ROOT).as_posix())
        z.writestr('ARCHIVE_MANIFEST.sha256',manifest)
    with zipfile.ZipFile(out) as z:
        bad=z.testzip()
        if bad: raise RuntimeError(f'ZIP integrity failure: {bad}')
    print(f'Built {out}')
    print(f'Tracked files: {len(files)}')
    print(f'Archive SHA-256: {sha(out)}')

if __name__=='__main__': main()
