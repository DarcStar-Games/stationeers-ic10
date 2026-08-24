#!/usr/bin/env python3
from pathlib import Path
import re
from source_metadata import load_manifest,resolve_script_metadata,deployable_scripts
ROOT=Path(__file__).resolve().parent
MANIFEST=load_manifest(ROOT)

def human_name(filename):
    stem=Path(filename).stem
    stem=re.sub(r'_v\d+_\d+$','',stem)
    return ' '.join(w.upper() if w in {'pi','ic10'} else w.capitalize() for w in stem.split('_'))

files=deployable_scripts(ROOT)
lines=['# IC10 Script Index','',
'Generated from the deployable `ic10/` inventory. Semantic paths plus version suffixes are the executable source identity; historical numeric source ordinals are intentionally not part of filenames. Deployment family/class metadata is resolved from `source_manifest.json`.','',
f'Production IC10 programs: {len(files)}','',
'## Script index','',
'| Current file | Lines | Layer | Deployment family | Class | Human purpose |','|---|---:|---|---|---|---|']
for p in files:
    rel=p.relative_to(ROOT).as_posix();meta=resolve_script_metadata(p,MANIFEST,ROOT)
    lines.append(f"| `{rel}` | {len(p.read_text().splitlines())} | {meta['layer']} | `{meta['deployment_family']}` | `{meta['deployment_class']}` | {meta['purpose']} |")
lines += ['', '## Pressure-grid dependency map','', '```text',
'Generic Snapshot Controller Directory ABI1 + DirectorySchema.Controller','        |','        +--> PhasePressure Request Arbiter --> PressureDomain telemetry ABI2','        |                                      |','        |                               Purity Guard <--- Resource Profile View','        |                                      |','        |                                 Inventory ABI2','        |                                      |','        |                              Reservation ledger ABI1','        |                                      |','        +--> PressureGridLink Snapshot Directory +','                 |                              |','                 +--> Path Enumerator --> Route Selector ABI2 --> Path Allocator --+','                 |                         ^                         |               |','                 +--> Single-Hop Builder --|-------------------------+               |','                                           |                                         v','                    Cost Profile --> Route Ranker ABI2        Allocator ABI3 (quote/commit)','                                                                  |','                                                             staged topology grant','                                                                  |','                 Plan Builder --> Planner ABI2 commit LAST --> Grant Guard --> Transfer ABI2 --> pump','```','',
'Route classes are `1 LOW->HIGH`, `2 LOW->STORAGE`, `3 STORAGE->HIGH`, and `4 STORAGE->STORAGE`. Route class 4 is path-only. Automatic routed reuse is currently bounded to two or three physical hops.','',
'## Resource-grid generalization map','', '```text','Pressure Inventory -> Pressure Endpoint Adapter --+ ','                                                  +-> Generic Resource Endpoint -> Generic Resource Reservation','Vending + ITEM Resource Profile View -> Material Inventory -+ ','Cargo LArRE -> Storage Service -> LArRE ITEM Endpoint --------+ ','','PressureTransfer + matching generic reservations -> Generic Resource Link','','Vending -> Stacker -> Logic Sorter -> Material Link -> processor/import endpoint','                        |                 ^','                        +-> Grant Guard <-+-> Multi Material Allocator ABI2','','Material Link + Transform Profile + output Reservation -> Admission -> Link Resolver','                                                         -> Multi Stager -> Multi Allocator -> Generic Runtime','','Generic Job Store -> Generic Job Selector -> Manufacturing Scheduler -> TRANSFORM / PRINT drivers','                         |                                      |','                         |                         +------------+------------+','                         |                         |                         |','                         |                 TransformLane             PrinterExecution','                         |                         |                         |','                         +-------------------------+--> existing Multi Reservation / Allocation substrates','```','',
'## Deployment ownership','',
'Every deployable program resolves to exactly one `deployment_family` and one deployment class in `source_manifest.json` (directly or through a generated-file rule). See `USER_DEPLOYMENT_GUIDE.md` for operator procedures, prerequisites, wiring, health checks, commissioning proof, restart behavior, and reclaim guidance.','',
'## Source of truth','',
'The deployable programs under `ic10/<deployment-family>/` are canonical. Use this index for navigation and line-pressure review; inspect the source file directly for exact code.','']
out=ROOT/'docs'/'SCRIPT_INDEX.md';out.write_text('\n'.join(lines)+'\n')
print(f'Generated docs/SCRIPT_INDEX.md for {len(files)} IC10 files')
