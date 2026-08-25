#!/usr/bin/env python3
"""Validate operator deployment-guide coverage against deployable source metadata."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import json,re,sys
from framework.source_metadata import load_manifest,family_inventory,deployable_scripts,VALID_CLASSES
ROOT=_PROJECT_ROOT
GUIDE=ROOT/'USER_DEPLOYMENT_GUIDE.md'
fails=[]
if not GUIDE.exists():
    print('User deployment guide validation: FAIL\n - USER_DEPLOYMENT_GUIDE.md missing');sys.exit(1)
text=GUIDE.read_text();manifest=load_manifest(ROOT);families=manifest['deployment_families'];inv=family_inventory(ROOT,manifest)
case_data=json.loads((ROOT/'data/live_commissioning_cases.json').read_text());case_ids={c['id'] for c in case_data.get('cases',[])}
required_headings=['Purpose','Use this when','Deployment class','Programs','Prerequisites','Wiring and configuration','Deployment procedure','Healthy state','Commissioning proof','Common failures','Reflash / replacement','What can be removed','Technical references']
seen_programs={}
for slug,meta in families.items():
    marker=f'<!-- DEPLOYMENT_FAMILY:{slug} -->'
    if text.count(marker)!=1:fails.append(f'{slug}: family marker count {text.count(marker)} != 1')
    # Slice section from its H2 to the next H2.
    mm=re.search(rf'^##\s+{re.escape(meta["title"])}\s*\n{re.escape(marker)}\s*$',text,re.M)
    if not mm:
        fails.append(f'{slug}: missing exact section title/marker');continue
    nxt=re.search(r'^##\s+',text[mm.end():],re.M)
    section=text[mm.start(): mm.end()+(nxt.start() if nxt else len(text)-mm.end())]
    for h in required_headings:
        if f'### {h}' not in section:fails.append(f'{slug}: missing heading {h!r}')
    for doc in meta.get('docs',[]):
        if not (ROOT/doc).exists():fails.append(f'{slug}: referenced technical doc missing: {doc}')
        if f'`{doc}`' not in section:fails.append(f'{slug}: technical reference not listed in family section: {doc}')
    for cid in meta.get('live_cases',[]):
        if cid not in case_ids:fails.append(f'{slug}: unknown live case {cid}')
        if cid not in section:fails.append(f'{slug}: live case {cid} not named in Commissioning proof section')
    start=f'<!-- FAMILY_PROGRAMS:{slug} START -->';end=f'<!-- FAMILY_PROGRAMS:{slug} END -->'
    if text.count(start)!=1 or text.count(end)!=1:
        fails.append(f'{slug}: generated program block markers are not unique');continue
    bm=re.search(re.escape(start)+r'(.*?)'+re.escape(end),section,re.S)
    if not bm:
        fails.append(f'{slug}: program block not inside family section');continue
    rows=re.findall(r'^\|\s*`([^`]+\.ic10)`\s*\|\s*`([^`]+)`\s*\|',bm.group(1),re.M)
    actual=[(name,dclass) for name,dclass in rows]
    expected=[(p.relative_to(ROOT).as_posix(),m['deployment_class']) for p,m in inv[slug]]
    if actual!=expected:
        fails.append(f'{slug}: program inventory differs from source metadata (expected {len(expected)}, found {len(actual)})')
    for name,dclass in actual:
        if dclass not in VALID_CLASSES:fails.append(f'{slug}/{name}: invalid class {dclass}')
        if name in seen_programs:fails.append(f'{name}: appears in multiple family program blocks ({seen_programs[name]}, {slug})')
        seen_programs[name]=slug
all_files={p.relative_to(ROOT).as_posix() for p in deployable_scripts(ROOT)}
if set(seen_programs)!=all_files:
    for name in sorted(all_files-set(seen_programs)):fails.append(f'{name}: absent from guide program inventories')
    for name in sorted(set(seen_programs)-all_files):fails.append(f'{name}: stale guide program inventory entry')
# Guide is intended to be discoverable from primary operator docs.
for doc in ['README.md','docs/DEPLOYMENT.md','docs/COMMISSIONING_QUICKSTART.md']:
    body=(ROOT/doc).read_text()
    if 'USER_DEPLOYMENT_GUIDE.md' not in body:fails.append(f'{doc}: does not link USER_DEPLOYMENT_GUIDE.md')
if fails:
    print('User deployment guide validation: FAIL')
    for x in fails:print(' -',x)
    sys.exit(1)
print('User deployment guide validation: PASS')
print(f' - {len(families)} deployment families cover all {len(all_files)} deployable IC10 programs exactly once')
print(' - every family has the standard operator procedure headings, current technical references, and declared live-case links')
