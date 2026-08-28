#!/usr/bin/env python3
"""Run the complete framework validation suite with fingerprint-guarded resumable evidence."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys

ROOT=_PROJECT_ROOT
EVIDENCE=ROOT/'validation'/'evidence'
RUN_LOG=ROOT/'validation'/'FULL_VALIDATION_RUN.txt'
SUMMARY=ROOT/'VALIDATION_SUMMARY.txt'
STATE=ROOT/'validation'/'VALIDATION_STATE.json'
# Local VCS/tooling state is not framework source and must never move the input
# fingerprint: doing so marks live commissioning evidence STALE with no source
# change. build_release.py excludes the same set from the release inventory, and
# validation/validators/validate_release_tooling.py fails if the two diverge.
TOOLING_DIRS={'.git','.github','.claude','.githooks'}

VALIDATORS=[
'validation/validators/validate_abi_contracts.py','validation/validators/validate_async_request_contracts.py','validation/validators/validate_banked_transaction_contracts.py',
'validation/validators/validate_catalog_storage.py','validation/validators/validate_config_contracts.py','validation/validators/validate_dependency_planning_contracts.py','validation/validators/validate_directory_contracts.py',
'validation/validators/validate_documentation.py','validation/validators/validate_ic10.py','validation/validators/validate_ic10_opcodes.py','validation/validators/validate_input_contracts.py','validation/validators/validate_job_contracts.py',
'validation/validators/validate_manufacturing_contracts.py','validation/validators/validate_power_management_contracts.py','validation/validators/validate_fault_injection_contracts.py',
'validation/validators/validate_release_tooling.py','validation/validators/validate_generated_directory_adapters.py','validation/validators/validate_script_headers.py','validation/validators/validate_source_catalog.py','validation/validators/validate_script_contracts.py','validation/validators/validate_user_deployment_guide.py','validation/validators/validate_item_storage_contracts.py','validation/validators/validate_process_utility_contracts.py','validation/validators/validate_live_commissioning_contracts.py']
TESTS=[
'tests/test_async_request.py','tests/test_banked_transaction.py','tests/test_catalog_schema.py','tests/test_controller_directory_scale.py',
'tests/test_dependency_planning.py','tests/test_generic_directory.py','tests/test_ic10_execution.py','tests/test_input_profiles.py','tests/test_job_abi.py',
'tests/test_manufacturing_execution.py','tests/test_manufacturing_scheduler.py','tests/test_material_grid_protocol.py','tests/test_script_contracts.py',
'tests/test_material_transform_protocol.py','tests/test_persistence_protocol.py','tests/test_phase_pressure_protocol.py',
'tests/test_pressure_domain_protocol.py','tests/test_pressure_grid_protocol.py','tests/test_pressure_inventory_protocol.py',
'tests/test_commission_wiring.py',
'tests/test_pressure_reservation_protocol.py','tests/test_pressure_route_cost.py','tests/test_printer_directory.py',
'tests/test_printer_execution_capacity.py','tests/test_recipe_catalog.py','tests/test_generator_productivity.py','tests/test_resource_generalization.py',
'tests/test_resource_profiles.py','tests/test_resource_transforms.py','tests/test_sequencer_protocol.py','tests/test_shared_input_protocol.py','tests/test_item_storage_protocol.py','tests/test_power_management.py','tests/test_fault_injection.py','tests/test_process_utility.py','tests/test_live_commissioning.py','tests/test_game_export.py']
SCRIPTS=VALIDATORS+TESTS

def evidence_name(script): return Path(script).stem.upper()+'.txt'

def input_fingerprint(root=ROOT):
    """Hash the validation inputs under `root`, excluding repository metadata and mutable validation/release outputs."""
    # `root` is a parameter so a caller can fingerprint a checkout other than this
    # one without loading a second copy of this module to move ROOT. tools/live_commission.py
    # is that caller.
    root=Path(root);evidence=root/'validation'/'evidence'
    h=hashlib.sha256()
    skip_names={'FULL_VALIDATION_RUN.txt','VALIDATION_STATE.json','VALIDATION_SUMMARY.txt','DEPLOYMENT_BASELINE.sha256','ARCHIVE_MANIFEST.sha256'}
    files=[]
    for p in root.rglob('*'):
        if not p.is_file(): continue
        # Match inside the repository: p.parts carries the absolute path, so a checkout under a
        # directory named .git/.claude/__pycache__ would otherwise exclude every file in it.
        inside=set(p.relative_to(root).parts)
        if TOOLING_DIRS&inside or '__pycache__' in inside or p.suffix in {'.pyc','.zip'}: continue
        if p.name in skip_names or evidence in p.parents or (root/'field_evidence') in p.parents: continue
        files.append(p)
    # Fail closed. A sweep that excluded everything would hash the empty tree, and every session
    # would match that digest forever instead of going STALE.
    if not files: raise RuntimeError(f'no validation inputs found under {root}')
    for p in sorted(files,key=lambda x:x.relative_to(root).as_posix()):
        rel=p.relative_to(root).as_posix().encode();h.update(len(rel).to_bytes(4,'big'));h.update(rel)
        data=p.read_bytes();h.update(len(data).to_bytes(8,'big'));h.update(data)
    return h.hexdigest()

def load_state(fp,resume):
    if resume and STATE.exists():
        try:
            s=json.loads(STATE.read_text())
            if s.get('fingerprint')==fp and s.get('scripts')==SCRIPTS:
                return s
        except Exception: pass
    if EVIDENCE.exists(): shutil.rmtree(EVIDENCE)
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    s={'fingerprint':fp,'scripts':SCRIPTS,'results':{}}
    STATE.parent.mkdir(exist_ok=True);STATE.write_text(json.dumps(s,indent=2)+'\n')
    RUN_LOG.unlink(missing_ok=True);SUMMARY.unlink(missing_ok=True)
    return s

def save_state(state): STATE.write_text(json.dumps(state,indent=2,sort_keys=True)+'\n')

def execute(script,timeout=90):
    evidence=EVIDENCE/evidence_name(script)
    with evidence.open('w') as out:
        try:
            proc=subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,text=True,stdout=out,stderr=subprocess.STDOUT,timeout=timeout)
            return proc.returncode
        except subprocess.TimeoutExpired:
            out.write(f"\nVALIDATION RUNNER TIMEOUT after {timeout}s: {script}\n")
            return 124

def finalize(results):
    run=[];failed=[]
    for script in SCRIPTS:
        code=int(results[script]);status='PASS' if code==0 else 'FAIL';run.append(f'{status} {script}')
        if code:failed.append(script)
    run.append(f"FULL_SUITE: {'PASS' if not failed else 'FAIL'} ({len(SCRIPTS)-len(failed)}/{len(SCRIPTS)} scripts)")
    RUN_LOG.parent.mkdir(exist_ok=True);RUN_LOG.write_text('\n'.join(run)+'\n')
    production=sorted((ROOT/'ic10').rglob('*.ic10'));counts={p.relative_to(ROOT).as_posix():len(p.read_text().splitlines()) for p in production}
    max_lines=max(counts.values(),default=0);tight=[n for n,c in counts.items() if c>=117]
    summary=['Stationeers IC10 Framework — Clean Release Validation','=====================================================','',
        f"Overall: {'PASS' if not failed else 'FAIL'} ({len(SCRIPTS)-len(failed)}/{len(SCRIPTS)} validation/test scripts)",
        f'Validators: {len(VALIDATORS)-sum(s in failed for s in VALIDATORS)}/{len(VALIDATORS)} PASS',
        f'Execution/protocol tests: {len(TESTS)-sum(s in failed for s in TESTS)}/{len(TESTS)} PASS',
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
        'Evidence','--------',f'- validation/FULL_VALIDATION_RUN.txt contains the complete {len(SCRIPTS)}-script pass/fail inventory.',
        '- validation/evidence/ contains stdout for each validator/test.']
    if failed: summary += ['','Failures','--------']+[f'- {s}' for s in failed]
    SUMMARY.write_text('\n'.join(summary)+'\n')
    print(run[-1]);print(f'Evidence: {EVIDENCE.relative_to(ROOT)}')
    return 1 if failed else 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    fp=input_fingerprint();state=load_state(fp,args.resume);results=state['results']
    print(f'Validation phase: isolated sequential checks ({len(SCRIPTS)}), resume={args.resume}',flush=True)
    for script in SCRIPTS:
        evidence=EVIDENCE/evidence_name(script)
        if args.resume and results.get(script)==0 and evidence.exists():
            print(f'REUSE {script}',flush=True);continue
        code=execute(script);results[script]=code;save_state(state)
        print(f"{'PASS' if code==0 else 'FAIL'} {script}",flush=True)
    if any(s not in results for s in SCRIPTS): return 2
    return finalize(results)

if __name__=='__main__': raise SystemExit(main())
