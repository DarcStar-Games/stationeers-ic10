from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
from pathlib import Path
from banked_transaction import (
    RevisionBank, SelectorState, choose_revision_bank, revision_commit_trace,
    selector_commit_trace, request_recovery, storage_compatible)
from ic10_harness import IC10
R=_PROJECT_ROOT
fails=[]
def ck(v,m):
    if not v:fails.append(m)

# Shared profile theorem: authority written/flipped LAST => recovery sees old or new only.
sig=123456
old_payload=[10+i for i in range(8)];new_payload=[100+i for i in range(8)]
old=RevisionBank(old_payload.copy(),sig,7,11)
trace=revision_commit_trace(old,new_payload,sig,8,12)
for label,state in trace[:-1]:ck(state==(7,old_payload),(label,state))
ck(trace[-1][1]==(8,new_payload),'REVISION_BANK final authority did not expose new payload')
ck(choose_revision_bank(old,RevisionBank(new_payload,sig,8,12),sig+1) is None,'signature mismatch accepted')

sel_old=SelectorState(1,4,0);sel_new=SelectorState(2,5,0)
strace=selector_commit_trace(sel_old,sel_new)
ck(strace[0][1]==sel_old and strace[1][1]==sel_old and strace[2][1]==sel_new,'SELECTOR_BANK was not old-or-new')
ck(request_recovery(9,8,7)=='retry','pre-commit request should retry')
ck(request_recovery(9,9,7)=='ack-committed','post-commit request should ack')
ck(request_recovery(9,9,9)=='already-acked','already acknowledged request misclassified')
ck(storage_compatible(1,2,1,2) and not storage_compatible(1,1,1,2),'ABI compatibility predicate wrong')

# Actual Job Store: same magic + incompatible ABI must reset rather than interpret old geometry.
job=(R/'ic10/generic-jobs/generic_job_store_v1_0.ic10').read_text();vm=IC10(job)
vm.stack={0:31415984,1:99,2:7,23:55,288:1,289:12,290:44,291:-5}
vm.run(1)
ck(vm.stack.get(0)==31415984 and vm.stack.get(1)==1,'Job Store did not reset incompatible ABI')
ck(vm.stack.get(2,0)==0 and vm.stack.get(23)==1 and vm.stack.get(288,0)==0,'Job Store interpreted incompatible durable geometry')

# Actual Config Host: a durable request generation is acknowledged after reflash without recommit.
host=(R/'ic10/controller-config/generic_persistent_config_host_v1_1.ic10').read_text();vm=IC10(host)
sig=777;image=[200+i for i in range(8)]
vm.stack={10:1,12:sig,13:1,6:7,7:6,5:3}
for i,v in enumerate(image):vm.stack[160+i]=v
vm.stack.update({224:sig,225:7,226:4})
vm.run(2)
ck(vm.stack.get(9)==7,'Config Host did not restore durable config revision')
ck(vm.stack.get(7)==7 and vm.stack.get(11)==5,'Config Host did not acknowledge already-durable request')
ck(vm.stack.get(25)==4,'Config Host replay acknowledgement performed another bank commit')
ck([vm.stack.get(96+i,0) for i in range(8)]==image,'Config Host did not republish durable image')

if fails:
    print('Banked transaction standard validation: FAIL')
    for x in fails:print(' -',x)
    raise SystemExit(1)
print('Banked transaction standard validation: PASS')
print(' - REVISION_BANK and SELECTOR_BANK reference profiles are old-or-new at every authority boundary')
print(' - request replay classifies retry / acknowledge-committed / already-acknowledged consistently')
print(' - Job Store rejects incompatible ABI geometry before recovery')
print(' - Config Host acknowledges an already-durable request without a duplicate bank commit')
