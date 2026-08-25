from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
"""Refresh only generated program-inventory blocks inside USER_DEPLOYMENT_GUIDE.md."""
from pathlib import Path
import re
from framework.source_metadata import load_manifest,family_inventory
ROOT=_PROJECT_ROOT
GUIDE=ROOT/'USER_DEPLOYMENT_GUIDE.md'
START='<!-- FAMILY_PROGRAMS:{slug} START -->'
END='<!-- FAMILY_PROGRAMS:{slug} END -->'

def render(slug,items):
    out=[START.format(slug=slug),'| Program | Deployment class | Purpose |','|---|---|---|']
    for p,meta in items:
        purpose=str(meta.get('purpose','')).replace('|','\\|')
        out.append(f"| `{p.relative_to(ROOT).as_posix()}` | `{meta['deployment_class']}` | {purpose} |")
    out.append(END.format(slug=slug))
    return '\n'.join(out)

def main():
    text=GUIDE.read_text()
    manifest=load_manifest(ROOT);inv=family_inventory(ROOT,manifest)
    for slug,items in inv.items():
        a=re.escape(START.format(slug=slug));b=re.escape(END.format(slug=slug))
        pat=re.compile(a+r'.*?'+b,re.S)
        block=render(slug,items)
        text,n=pat.subn(lambda _:block,text,count=1)
        if n!=1: raise SystemExit(f'{slug}: expected exactly one program inventory block, found {n}')
    GUIDE.write_text(text)
    print(f'Updated USER_DEPLOYMENT_GUIDE.md program inventory for {len(inv)} families / {sum(map(len,inv.values()))} IC10 files')
if __name__=='__main__':main()
