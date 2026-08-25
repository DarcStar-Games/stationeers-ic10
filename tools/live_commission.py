from __future__ import annotations
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
"""Create and maintain field commissioning evidence bound to one framework input fingerprint."""
from pathlib import Path
import argparse, datetime as dt, hashlib, json, sys

ROOT=_PROJECT_ROOT
CATALOG=ROOT/'data/live_commissioning_cases.json'
FORMAT='LIVE_COMMISSION_SESSION_V1'
VALID={'PASS','FAIL','BLOCKED'}

def sha_bytes(data:bytes)->str: return hashlib.sha256(data).hexdigest()
def load_catalog(root=ROOT):
    p=root/'data/live_commissioning_cases.json'; data=json.loads(p.read_text())
    if data.get('format')!='LIVE_COMMISSIONING_CASES_V1': raise ValueError('unsupported commissioning catalog')
    return data

def framework_fingerprint(root=ROOT):
    # Reuse the release validator's immutable-input fingerprint. field_evidence is excluded there.
    import importlib.util
    spec=importlib.util.spec_from_file_location('_rv',root/'tools'/'run_validation.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.input_fingerprint()

def catalog_sha(root=ROOT): return sha_bytes((root/'data/live_commissioning_cases.json').read_bytes())
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def case_map(root=ROOT): return {c['id']:c for c in load_catalog(root)['cases']}

def new_session(root=ROOT,label=''):
    return {'format':FORMAT,'framework_fingerprint':framework_fingerprint(root),'catalog_sha256':catalog_sha(root),'created_at':now(),'label':label,'results':{}}

def read_session(path):
    s=json.loads(Path(path).read_text())
    if s.get('format')!=FORMAT: raise ValueError('unsupported session format')
    return s

def write_session(path,s):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(s,indent=2,sort_keys=True)+'\n');tmp.replace(p)

def session_fresh(s,root=ROOT): return s.get('framework_fingerprint')==framework_fingerprint(root) and s.get('catalog_sha256')==catalog_sha(root)
def latest_status(s,cid):
    runs=s.get('results',{}).get(cid,{}).get('runs',[]);return runs[-1]['status'] if runs else 'UNRUN'

def verify_session(s,root=ROOT):
    if not session_fresh(s,root): return {'fresh':False,'required_pass':0,'required_total':0,'failed':[],'blocked':[],'unrun':[]}
    cases=load_catalog(root)['cases']; req=[c for c in cases if c.get('required',True)]
    failed=[];blocked=[];unrun=[];passed=0
    for c in req:
        st=latest_status(s,c['id'])
        if st=='PASS': passed+=1
        elif st=='FAIL': failed.append(c['id'])
        elif st=='BLOCKED': blocked.append(c['id'])
        else: unrun.append(c['id'])
    return {'fresh':True,'required_pass':passed,'required_total':len(req),'failed':failed,'blocked':blocked,'unrun':unrun}

def render_report(s,root=ROOT):
    v=verify_session(s,root); cases=load_catalog(root)['cases']
    lines=['# Live Commissioning Evidence','',f"Framework fingerprint: `{s.get('framework_fingerprint','')}`",f"Catalog SHA-256: `{s.get('catalog_sha256','')}`",f"Session created: {s.get('created_at','')}",f"Label: {s.get('label','') or '-'}",'']
    if not v['fresh']: lines += ['**STALE:** framework or case catalog changed after this session was created.','']
    lines += [f"Required suites passing: **{v['required_pass']}/{v['required_total']}**",'', '| Suite | Required | Status | Latest observation |','|---|---:|---|---|']
    for c in cases:
        runs=s.get('results',{}).get(c['id'],{}).get('runs',[]); st=runs[-1]['status'] if runs else 'UNRUN';obs=(runs[-1].get('observed','') if runs else '').replace('|','\\|')
        lines.append(f"| `{c['id']}` | {'yes' if c.get('required',True) else 'no'} | {st} | {obs} |")
    lines += ['','Automated release evidence under `validation/evidence/` is intentionally separate from these live observations.']
    return '\n'.join(lines)+'\n'

def main(argv=None):
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('init');p.add_argument('--session',required=True);p.add_argument('--label',default='')
    p=sp.add_parser('list');p.add_argument('--category')
    p=sp.add_parser('show');p.add_argument('case_id')
    p=sp.add_parser('record');p.add_argument('--session',required=True);p.add_argument('--case',required=True);p.add_argument('--status',choices=sorted(VALID),required=True);p.add_argument('--precondition',required=True);p.add_argument('--action',required=True);p.add_argument('--observed',required=True);p.add_argument('--refs',default='');p.add_argument('--notes',default='')
    p=sp.add_parser('verify');p.add_argument('--session',required=True)
    p=sp.add_parser('report');p.add_argument('--session',required=True);p.add_argument('--output')
    a=ap.parse_args(argv); cases=case_map()
    if a.cmd=='init':
        s=new_session(label=a.label);write_session(a.session,s);print(f'Created {a.session}');print(f"Framework fingerprint: {s['framework_fingerprint']}");return 0
    if a.cmd=='list':
        for c in load_catalog()['cases']:
            if not a.category or c['category']==a.category: print(f"{c['id']}  {'REQ' if c.get('required',True) else 'OPT'}  {c['title']}")
        return 0
    if a.cmd=='show':
        if a.case_id not in cases: print('unknown case',file=sys.stderr);return 2
        print(json.dumps(cases[a.case_id],indent=2));return 0
    s=read_session(a.session)
    if not session_fresh(s): print('STALE SESSION: framework or commissioning catalog changed',file=sys.stderr);return 2
    if a.cmd=='record':
        if a.case not in cases: print('unknown case',file=sys.stderr);return 2
        run={'status':a.status,'recorded_at':now(),'precondition':a.precondition,'action':a.action,'observed':a.observed,'reference_ids':[x.strip() for x in a.refs.split(',') if x.strip()],'notes':a.notes}
        s.setdefault('results',{}).setdefault(a.case,{'runs':[]})['runs'].append(run);write_session(a.session,s);print(f"Recorded {a.case}: {a.status}");return 0
    if a.cmd=='verify':
        v=verify_session(s);print(f"Required suites: {v['required_pass']}/{v['required_total']} PASS")
        for k in ('failed','blocked','unrun'):
            if v[k]: print(f"{k.upper()}: {', '.join(v[k])}")
        return 0 if v['required_pass']==v['required_total'] else 1
    if a.cmd=='report':
        text=render_report(s)
        if a.output: Path(a.output).write_text(text);print(f'Wrote {a.output}')
        else: print(text,end='')
        return 0
    return 2

if __name__=='__main__': raise SystemExit(main())
