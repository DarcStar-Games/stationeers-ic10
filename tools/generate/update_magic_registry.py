#!/usr/bin/env python3
"""Refresh the generated published-header block inside docs/ABI_REFERENCE.md."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,re,sys
from framework.source_metadata import resolve_script_metadata
ROOT=_PROJECT_ROOT
REFERENCE=ROOT/'docs'/'ABI_REFERENCE.md'
HEADERS=ROOT/'data'/'script_protocol_headers.json'
START='<!-- PUBLISHED_HEADERS START -->'
END='<!-- PUBLISHED_HEADERS END -->'
SUMMARY='Published header registry: CHECK PASS ({rows} headers, {magics} magics)'

def rows():
    """One row per declared header: a program may publish a service header and a telemetry block."""
    data=json.loads(HEADERS.read_text())
    if data.get('format')!='IC10_PROTOCOL_HEADERS_V1':
        raise SystemExit('unsupported script protocol header format')
    out=[]
    for path,headers in data['scripts'].items():
        for header in headers:
            meta=resolve_script_metadata(path,root=ROOT)
            out.append((header['magic'],header['abi'],header['base'],path,str(meta.get('purpose',''))))
    return sorted(out,key=lambda row:(row[0],row[2],row[3]))

def render(table):
    out=[START,'| Magic | ABI | Cell | Program | Purpose |','|---:|---:|---:|---|---|']
    for magic,abi,base,path,purpose in table:
        out.append(f"| `{magic}` | {abi} | `S{base}` | `{path}` | {purpose.replace('|',chr(92)+'|')} |")
    out.append(END)
    return '\n'.join(out)

def main():
    table=rows()
    block=render(table)
    text=REFERENCE.read_text()
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S)
    updated,found=pattern.subn(lambda _:block,text,count=1)
    if found!=1:
        raise SystemExit(f'expected exactly one published-header block, found {found}')
    summary=SUMMARY.format(rows=len(table),magics=len({row[0] for row in table}))
    if '--check' in sys.argv:
        if updated!=text:
            raise SystemExit('docs/ABI_REFERENCE.md published-header block is stale; run tools/generate/update_magic_registry.py')
        print(summary)
        return
    REFERENCE.write_text(updated)
    print(f'Updated docs/ABI_REFERENCE.md with {len(table)} published headers across {len({row[0] for row in table})} magics')
if __name__=='__main__':main()
