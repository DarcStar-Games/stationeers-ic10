from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
import json,sys
from framework.job_abi import JobState,JobType,NORMAL_CHAIN,TERMINAL,WAIT_FROM,WAIT_STATES
R=_PROJECT_ROOT;fails=[]
def ck(v,msg):
    if not v:fails.append(msg)
s=json.loads((R/'data/generic_job_schema.json').read_text())
ck(s.get('format')=='GENERIC_JOB_ABI_V1','schema format')
ck(s.get('magic')==31415984 and s.get('abi')==1,'schema magic/ABI')
ck(s.get('capacity')==32,'capacity must be 32')
ck(s.get('banked_transaction_profile')=='SELECTOR_BANK','Job Store must declare SELECTOR_BANK profile')
ck(s.get('storage_compatibility')=={'magic':31415984,'abi':1,'rule':'both must match before durable stack geometry is interpreted'},'Job storage compatibility rule mismatch')
ck(s.get('logical_record_width')==11,'logical record width must be 11')
fields=['JobId','JobType','RequiredCapability','Identity','InputCount','OutputCount','RequestedQuantity','Priority','State','Generation','ErrorStatus']
ck(s.get('fields')==fields,'logical fields/order mismatch')
ck(s.get('intent_base')==32 and s.get('intent_slot_width')==8,'intent geometry mismatch')
ck(s.get('state_base')==288 and s.get('state_slot_width')==7,'state geometry mismatch')
ck(s['intent_base']+s['capacity']*s['intent_slot_width']==s['state_base'],'intent/state geometry is not contiguous')
ck(s['state_base']+s['capacity']*s['state_slot_width']==512,'job store must fit exactly in S0..S511 geometry')
for x in JobType:ck(s['job_types'].get(x.name)==x.value,f'JobType {x.name}')
for x in JobState:ck(s['states'].get(x.name)==x.value,f'JobState {x.name}')
ck({tuple(x) for x in s['normal_chain']}=={(a.value,b.value) for a,b in NORMAL_CHAIN.items()},'normal lifecycle chain mismatch')
ck(set(s['wait_from'])=={x.value for x in WAIT_FROM},'wait_from mismatch')
ck(set(s['wait_states'])=={x.value for x in WAIT_STATES},'wait_states mismatch')
ck(set(s['terminal_states'])=={x.value for x in TERMINAL},'terminal states mismatch')
src=(R/'ic10/generic-jobs/generic_job_store_v1_0.ic10').read_text();lines=src.splitlines()
ck(len(lines)<=120,f'Job Store is {len(lines)} lines > 120')
for token in ('bne r0 31415984 Reset','get r0 db 1','beq r0 1 Recover','poke 0 31415984','poke 1 1','poke 5 32','poke 23 1','poke 24 r15','poke 25 r3','poke 26 r4','beq r10 3 Reap','beq r6 7 Respond','bgt r6 10 Respond','beq r6 7 ReapOK','blt r6 11 Respond','bgt r6 12 Respond'):
    ck(token in src,f'Job Store missing {token!r}')
doc=(R/'docs/GENERIC_JOB_ABI.md').read_text()
for token in ('TRANSFORM','PRINT','TRANSFER','POWER','QUEUED -> PLANNING -> RESERVING -> READY -> RUNNING -> VERIFYING -> COMPLETE','WAIT_RESOURCE','WAIT_PROCESSOR','WAIT_CAPACITY','ExpectedJobGeneration','active state bank','same-service reflash','scheduler-neutral'):
    ck(token in doc,f'Job documentation missing {token!r}')
if fails:
    print('Generic Job contract validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Generic Job contract validation: PASS')
print(' - GENERIC_JOB_ABI_V1 schema/model/IC10 geometry agree on 32 logical eleven-field jobs')
print(' - JobType/state enums and lifecycle/wait/terminal sets are synchronized')
print(' - Store ABI1 owns optimistic generation, terminal immutability and crash journal markers')
print(' - Store magic+ABI gate protects physical queue geometry before recovery')
