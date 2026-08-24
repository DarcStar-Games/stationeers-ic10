from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
"""Small executable model for diagnostic input state and selector transaction invariants."""

def update(state, control, value):
    if control != 7:
        state['commit_raw']=0
    if control == 1:
        v=max(1,min(16,round(value)))
        if v != state['type']:
            state['type']=v; state['controller_gen']+=1
    elif control == 2:
        v=max(1,min(16,round(value)))
        if v != state['member']:
            state['member']=v; state['controller_gen']+=1
    elif control == 3:
        v=max(1,min(64,round(value)))
        if v != state['console']:
            state['console']=v; state['console_gen']+=1
    elif control == 4: state['channel']=max(1,min(16,round(value)))
    elif control == 5: state['mode']=max(0,min(14,round(value)))
    elif control == 6: state['color']=max(0,min(11,round(value)))
    elif control == 7:
        now=1 if value>0 else 0
        old=state['commit_raw']; state['commit_raw']=now
        if now and not old: state['commit_gen']+=1
    return state

def console_step(sel, desired, desired_gen, handled_desired, advance_gen, handled_advance, count):
    value=sel or 1
    if desired_gen != handled_desired:
        value=desired
    if advance_gen != handled_advance:
        value=max(1,min(count,value)); value=(value % count)+1
    value=max(1,min(count,value))
    return value, desired_gen, advance_gen

s=dict(type=1,member=1,console=1,channel=1,mode=0,color=6,commit_raw=0,
       commit_gen=0,controller_gen=1,console_gen=1)
# Same value must not produce selector churn.
update(s,1,1); assert s['controller_gen']==1
update(s,1,2); assert (s['type'],s['controller_gen'])==(2,2)
update(s,2,4); assert (s['member'],s['controller_gen'])==(4,3)
update(s,3,7); assert (s['console'],s['console_gen'])==(7,2)
# Commit is rising-edge generated once until release/leave-control rearms it.
update(s,7,1); assert s['commit_gen']==1
update(s,7,1); assert s['commit_gen']==1
update(s,7,0); update(s,7,1); assert s['commit_gen']==2
update(s,4,8); update(s,7,1); assert s['commit_gen']==3
# A handled desired request must NOT be reapplied when Mapping Editor advances console.
sel,hd,ha=console_step(7,7,2,2,1,1,10); assert sel==7
sel,hd,ha=console_step(sel,7,2,hd,2,ha,10); assert sel==8
# Repeated old desired generation leaves the advanced selection at 8.
sel,hd,ha=console_step(sel,7,2,hd,2,ha,10); assert sel==8
# A new user console request deliberately overrides it.
sel,hd,ha=console_step(sel,3,3,hd,2,ha,10); assert sel==3
print('Shared input protocol simulation: PASS')
print(' - unchanged controls do not churn selector generations')
print(' - commit uses a true rising-edge generation')
print(' - Console auto-advance survives stale desired values')
print(' - a new console request intentionally overrides auto-advance')
