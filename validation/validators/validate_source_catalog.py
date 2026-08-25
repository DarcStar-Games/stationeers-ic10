#!/usr/bin/env python3
"""Verify semantic source index and deployment metadata cover every deployable IC10 file."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import re,sys
from framework.source_metadata import load_manifest,resolve_script_metadata,deployable_scripts,VALID_CLASSES
ROOT=_PROJECT_ROOT
idx=(ROOT/'docs'/'SCRIPT_INDEX.md').read_text();rows={}
for name,lines,family,dclass in re.findall(r'^\|\s*`([^`]+\.ic10)`\s*\|\s*(\d+)\s*\|[^|]*\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|',idx,re.M):
    rows[name]=(int(lines),family,dclass)
files={p.relative_to(ROOT).as_posix():p for p in deployable_scripts(ROOT)};fails=[]
for rel,p in files.items():
    if re.match(r'^\d+_',p.name):fails.append(f'{rel}: historical numeric ordinal prefix is forbidden')
    if not re.search(r'_v\d+_\d+\.ic10$',p.name):fails.append(f'{rel}: production filename must retain _vX_Y.ic10 version suffix')
if '| Ordinal |' in idx or re.search(r'^\|\s*Ordinal\s*\|',idx,re.M):fails.append('SCRIPT_INDEX must not reintroduce an ordinal column')
try:meta=load_manifest(ROOT)
except Exception as e:
    print('Source index validation: FAIL');print(' - source_manifest.json:',e);sys.exit(1)
families=meta.get('deployment_families',{});classes=meta.get('deployment_classes',{})
if set(classes)!=VALID_CLASSES:fails.append(f'source_manifest deployment classes {sorted(classes)} != {sorted(VALID_CLASSES)}')
for slug,f in families.items():
    if not isinstance(f,dict) or not f.get('title') or not isinstance(f.get('docs'),list) or not isinstance(f.get('live_cases'),list):fails.append(f'source_manifest: incomplete deployment family {slug}')
for rel,p in files.items():
    try:m=resolve_script_metadata(p,meta,ROOT)
    except Exception as e:fails.append(f'{rel}: {e}');continue
    fam=m.get('deployment_family');dclass=m.get('deployment_class')
    if fam not in families:fails.append(f'{rel}: unknown deployment family {fam!r}')
    if dclass not in VALID_CLASSES:fails.append(f'{rel}: invalid deployment class {dclass!r}')
    if not m.get('layer') or not m.get('purpose'):fails.append(f'{rel}: incomplete layer/purpose metadata')
    if rel not in rows:fails.append(f'{rel}: missing SCRIPT_INDEX row')
    else:
        count,idxfam,idxclass=rows[rel];expected_lines=len(p.read_text().splitlines())
        if count!=expected_lines:fails.append(f'{rel}: indexed lines {count} != {expected_lines}')
        if idxfam!=fam:fails.append(f'{rel}: index family {idxfam} != {fam}')
        if idxclass!=dclass:fails.append(f'{rel}: index class {idxclass} != {dclass}')
for rel in rows:
    if rel not in files:fails.append(f'{rel}: stale SCRIPT_INDEX row')
for rel,v in meta.get('scripts',{}).items():
    if not isinstance(v,dict) or not all(v.get(k) for k in ('layer','purpose','deployment_family','deployment_class')):fails.append(f'source_manifest.json: incomplete exact metadata for {rel}')
    if rel not in files:fails.append(f'source_manifest.json: stale exact path {rel}')
if fails:
    print('Source index validation: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Source index validation: PASS')
print(f' - docs/SCRIPT_INDEX.md matches all {len(files)} semantic deployable IC10 paths, line counts, families, and classes')
print(f' - source_manifest.json defines {len(families)} deployment families and resolves every current script without numeric ordinals')
