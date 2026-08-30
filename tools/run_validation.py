#!/usr/bin/env python3
"""Run the complete framework validation suite with fingerprint-guarded resumable evidence."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
from framework.repository_inventory import InventoryPolicy,LOCAL_TOOLING_DIRECTORIES,repository_files
from framework.validation_suite import SuiteEntry,TEST_CATEGORY,VALIDATOR_CATEGORY,suite_entries

ROOT=_PROJECT_ROOT
EVIDENCE=ROOT/'validation'/'evidence'
RUN_LOG=ROOT/'validation'/'FULL_VALIDATION_RUN.txt'
SUMMARY=ROOT/'VALIDATION_SUMMARY.txt'
STATE=ROOT/'validation'/'VALIDATION_STATE.json'

def validation_inventory_policy():
    return InventoryPolicy(
        ignored_directories=LOCAL_TOOLING_DIRECTORIES,
        ignored_names=frozenset({'FULL_VALIDATION_RUN.txt','VALIDATION_STATE.json','VALIDATION_SUMMARY.txt','DEPLOYMENT_BASELINE.sha256','ARCHIVE_MANIFEST.sha256'}),
        ignored_suffixes=frozenset({'.zip'}),
        ignored_subtrees=frozenset({'validation/evidence','field_evidence'}),
        fail_on_empty=True,
    )

def validation_input_files(root=ROOT):
    """Return the ordered file inventory that contributes to validation state."""
    return repository_files(root,policy=validation_inventory_policy())

def input_fingerprint(root=ROOT):
    """Hash the validation inputs under `root`, excluding repository metadata and mutable validation/release outputs."""
    # `root` is a parameter so a caller can fingerprint a checkout other than this
    # one without loading a second copy of this module to move ROOT. tools/live_commission.py
    # is that caller.
    root=Path(root).resolve()
    h=hashlib.sha256()
    for p in validation_input_files(root):
        rel=p.relative_to(root).as_posix().encode();h.update(len(rel).to_bytes(4,'big'));h.update(rel)
        data=p.read_bytes();h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()

def load_state(fp,resume,entries):
    scripts=[entry.path for entry in entries]
    if resume and STATE.exists():
        try:
            s=json.loads(STATE.read_text())
            if s.get('fingerprint')==fp and s.get('scripts')==scripts:
                return s
        except Exception: pass
    if EVIDENCE.exists(): shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    s={'fingerprint':fp,'scripts':scripts,'results':{}}
    STATE.parent.mkdir(exist_ok=True);STATE.write_text(json.dumps(s,indent=2)+'\n')
    RUN_LOG.unlink(missing_ok=True);SUMMARY.unlink(missing_ok=True)
    return s

def save_state(state): STATE.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')

def execute(entry: SuiteEntry):
    script=entry.path;evidence=EVIDENCE/entry.evidence_filename
    with evidence.open('w') as out:
        try:
            proc=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,text=True,stdout=out,stderr=subprocess.STDOUT,timeout=entry.timeout_seconds)
            return proc.returncode
        except subprocess.TimeoutExpired:
            out.write(f"\nVALIDATION RUNNER TIMEOUT after {entry.timeout_seconds}s: {script}\n")
            return 124

def finalize(results,entries):
    validators=tuple(e for e in entries if e.category==VALIDATOR_CATEGORY)
    tests=tuple(e for e in entries if e.category==TEST_CATEGORY)
    run=[];failed=[]
    for entry in entries:
        script=entry.path
        code=int(results[script]);status='PASS' if code==0 else 'FAIL';run.append(f'{status} {script}')
        if code:failed.append(script)
    run.append(f"FULL_SUITE: {'PASS' if not failed else 'FAIL'} ({len(entries)-len(failed)}/{len(entries)} scripts)")
    RUN_LOG.parent.mkdir(exist_ok=True);RUN_LOG.write_text('\n'.join(run)+'\n')
    production=sorted((ROOT/'ic10').rglob('*.ic10'));counts={p.relative_to(ROOT).as_posix():len(p.read_text().splitlines()) for p in production}
    max_lines=max(counts.values(),default=0);tight=[n for n,c in counts.items() if c>=117]
    summary=['Stationeers IC10 Framework — Clean Release Validation','=====================================================','',
        f"Overall: {'PASS' if not failed else 'FAIL'} ({len(entries)-len(failed)}/{len(entries)} validation/test scripts)",
        f'Validators: {len(validators)-sum(e.path in failed for e in validators)}/{len(validators)} PASS',
        f'Execution/protocol tests: {len(tests)-sum(e.path in failed for e in tests)}/{len(tests)} PASS',
        f'Production IC10 programs: {len(production)}',f'Maximum production line count: {max_lines}/120',
        f'Tight programs (>=117 lines): {len(tight)}','', 'Release hygiene','---------------',
        '- docs/SCRIPT_INDEX.md is generated from deployable IC10 source plus data/source_manifest.json metadata.',
        '- contracts/ contains one schema-validated, source-fingerprinted contract per deployable IC10 program plus a provider/consumer protocol registry.',
        '- USER_DEPLOYMENT_GUIDE.md program inventories are machine-linked to data/source_manifest.json deployment-family/class metadata.',
        '- Repetitive Resource Endpoint/Link/Reservation directory adapters are generated from data/directory_adapter_specs.json.',
        '- Recipe Catalog test fixtures are generated into temporary directories; no generated recipe fixture is shipped.',
        '- Per-script machine output is stored only under validation/evidence/.',
        '- Validation resume is accepted only when validation/VALIDATION_STATE.json matches the complete input-tree fingerprint.',
        '- Completed Roadmap Items 1–11 are preserved in docs/COMPLETED_MILESTONES.md; Item 12 live-game commissioning remains active until field evidence closes.',
        '- ASYNC_REQUEST_V1 and BANKED_TRANSACTION_V1 remain separate request-identity and durable-commit authorities.','',
        'Evidence','--------',f'- validation/FULL_VALIDATION_RUN.txt contains the complete {len(entries)}-script pass/fail inventory.',
        '- validation/evidence/ contains stdout for each validator/test.']
    if failed: summary += ['','Failures','--------']+[f'- {s}' for s in failed]
    SUMMARY.write_text('\n'.join(summary)+'\n')
    print(run[-1]);print(f'Evidence: {EVIDENCE.relative_to(ROOT)}')
    return 1 if failed else 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    entries=suite_entries(ROOT);fp=input_fingerprint();state=load_state(fp,args.resume,entries);results=state['results']
    print(f'Validation phase: isolated sequential checks ({len(entries)}), resume={args.resume}',flush=True)
    for entry in entries:
        script=entry.path;evidence=EVIDENCE/entry.evidence_filename
        if args.resume and results.get(script)==0 and evidence.exists():
            print(f'REUSE {script}',flush=True);continue
        code=execute(entry);results[script]=code;save_state(state)
        print(f"{'PASS' if code==0 else 'FAIL'} {script}",flush=True)
    if any(entry.path not in results for entry in entries): return 2
    return finalize(results,entries)

if __name__=='__main__': raise SystemExit(main())
