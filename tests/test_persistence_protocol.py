from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
"""Model-check Generic Config REVISION_BANK ordering via BANKED_TRANSACTION_V1."""
from framework.banked_transaction import RevisionBank, choose_revision_bank, revision_commit_trace

def run():
    sig=123456; old=[10+i for i in range(16)]; new=[100+i for i in range(16)]
    a=RevisionBank(old.copy(),sig,7,11)
    steps=revision_commit_trace(a,new,sig,8,12)
    for label,state in steps[:-1]:
        assert state==(7,old), (label,state)
    assert steps[-1][1]==(8,new)
    assert choose_revision_bank(a,RevisionBank(new,sig,8,12),sig+1) is None
    print('Persistence protocol simulation: PASS')
    print(f' - {len(steps)} interruption points checked through shared REVISION_BANK model')
    print(' - old bank wins until destination bankRevision is written LAST')
    print(' - committed bank wins after final token')
    print(' - schema-signature mismatch invalidates both banks')
if __name__=='__main__': run()
