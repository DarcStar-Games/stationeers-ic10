#!/usr/bin/env python3
"""Shared deployable-source metadata resolution for indexes, deployment docs, and validators."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parents[1]
IC10_ROOT=ROOT/'ic10'
VALID_CLASSES={'resident','conditional-resident','commissioning','one-shot','on-demand'}

def load_manifest(root=ROOT):
    root=Path(root)
    data=json.loads((root/'data/source_manifest.json').read_text())
    if data.get('format')!='SOURCE_MANIFEST_V3':
        raise ValueError(f"unsupported source manifest format: {data.get('format')!r}")
    return data

def relative_script_path(path_or_name,root=ROOT):
    root=Path(root); p=Path(path_or_name)
    if p.is_absolute():
        try:return p.relative_to(root).as_posix()
        except ValueError:pass
    s=p.as_posix()
    if s.startswith('ic10/'):return s
    # Basenames are intentionally unique; accept them for ergonomic tests/tools.
    hits=list((root/'ic10').rglob(p.name))
    if len(hits)==1:return hits[0].relative_to(root).as_posix()
    if not hits: return s
    raise ValueError(f'ambiguous IC10 basename: {p.name}')

def resolve_script_metadata(path_or_name,manifest=None,root=ROOT):
    """Resolve layer/purpose/deployment ownership for one deployable IC10 path."""
    root=Path(root); manifest=manifest or load_manifest(root); rel=relative_script_path(path_or_name,root)
    exact=manifest.get('scripts',{}).get(rel)
    if exact:
        out=dict(exact);out['metadata_source']='exact';return out
    for rule in manifest.get('generated_deployment_rules',[]):
        if re.match(rule['pattern'],rel):
            out=dict(rule);out.pop('pattern',None);out['metadata_source']='generated-rule';return out
    raise KeyError(f'no source metadata for {rel}')

def deployable_scripts(root=ROOT):
    root=Path(root)
    return sorted((root/'ic10').rglob('*.ic10'),key=lambda p:p.relative_to(root).as_posix())

def family_inventory(root=ROOT,manifest=None):
    root=Path(root);manifest=manifest or load_manifest(root)
    inv={slug:[] for slug in manifest.get('deployment_families',{})}
    for p in deployable_scripts(root):
        meta=resolve_script_metadata(p,manifest,root)
        fam=meta.get('deployment_family')
        if fam not in inv:raise KeyError(f'{p.relative_to(root)}: unknown deployment family {fam!r}')
        inv[fam].append((p,meta))
    return inv
