#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,sys
R=_PROJECT_ROOT;fails=[]
def ck(v,m):
    if not v:fails.append(m)
std=(R/'docs/BANKED_TRANSACTION_STANDARD.md').read_text()
for token in ('BANKED_TRANSACTION_V1','REVISION_BANK','SELECTOR_BANK','authority marker LAST','acknowledge committed request','physical Job Store geometry change therefore requires a Store ABI bump'):
    ck(token in std,f'standard missing {token!r}')
job=(R/'ic10/generic-jobs/generic_job_store_v1_0.ic10').read_text();cfg=(R/'ic10/controller-config/generic_persistent_config_host_v1_1.ic10').read_text()
ck(len(job.splitlines())<=120,f'Job Store >120 lines: {len(job.splitlines())}')
ck(len(cfg.splitlines())<=120,f'Config Host >120 lines: {len(cfg.splitlines())}')
for token in ('bne r0 31415984 Reset','get r0 db 1','beq r0 1 Recover'):
    ck(token in job,f'Job Store missing storage compatibility gate {token!r}')
for token in ('get r15 db 6','get r0 db 9','bne r15 r0 NoReplay','poke 11 5','poke 7 r15'):
    ck(token in cfg,f'Config Host missing replay acknowledgement {token!r}')
ck('push r11 # bank revision/commit token LAST' in cfg,'Config REVISION_BANK authority-last marker missing')
ck('poke r3 r2' in job,'Job SELECTOR_BANK selector flip missing')
s=json.loads((R/'data/generic_job_schema.json').read_text())
ck(s.get('banked_transaction_profile')=='SELECTOR_BANK','Job schema profile mismatch')
compat=s.get('storage_compatibility',{})
ck(compat.get('magic')==s.get('magic') and compat.get('abi')==s.get('abi'),'Job compatibility token must equal schema magic+ABI')
for f in ('framework/banked_transaction.py','tests/test_banked_transaction.py','tests/test_persistence_protocol.py'):
    ck((R/f).exists(),f'missing shared transaction artifact {f}')
if fails:
    print('Banked transaction contract validation: FAIL')
    for x in fails:print(' -',x)
    sys.exit(1)
print('Banked transaction contract validation: PASS')
print(' - Config Host implements REVISION_BANK with post-commit replay acknowledgement')
print(' - Job Store implements SELECTOR_BANK and gates recovery on exact magic+ABI')
print(' - both production ICs remain within the 120-line project ceiling')
