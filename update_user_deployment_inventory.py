#!/usr/bin/env python3
"""Refresh only generated program-inventory blocks inside USER_DEPLOYMENT_GUIDE.md."""
from pathlib import Path
import re
from source_metadata import load_manifest,family_inventory
ROOT=Path(__file__).resolve().parent
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
