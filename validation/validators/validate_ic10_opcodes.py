from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
#!/usr/bin/env python3
"""Check every IC10 mnemonic and operand count against official game-extracted data.

validate_ic10.py enforces size, labels, register/device range and stack addresses but
never that an instruction exists. The instruction set in ic10_instruction_set.json is
extracted from Stationeers game data rather than wiki prose, so an opcode removed or
renamed by a game update is caught here instead of in a live commissioning session.
"""
from pathlib import Path
import json,re,sys

ROOT=_PROJECT_ROOT
SET=ROOT/'ic10_instruction_set.json'
LABEL=re.compile(r'[A-Za-z_][A-Za-z0-9_]*:')

def load_instruction_set():
    data=json.loads(SET.read_text())
    if data.get('format')!='IC10_INSTRUCTION_SET_V1':
        raise SystemExit(f'unsupported instruction set format: {data.get("format")!r}')
    return data

def expected_operands(name,entry):
    """Operand count from the game's own signature, e.g. 'add r? a(r?|num) b(r?|num)' -> 3."""
    tokens=entry.get('example','').split()
    if not tokens or tokens[0]!=name: return None
    return len(tokens)-1

def sources():
    return sorted((ROOT/'ic10').rglob('*.ic10'))+sorted((ROOT/'tests'/'ic10').rglob('*.ic10'))

def main():
    data=load_instruction_set()
    table=data['instructions']
    arity={n:expected_operands(n,e) for n,e in table.items()}
    unknown=[];mismatch=[];used=set();count=0
    for path in sources():
        rel=path.relative_to(ROOT).as_posix()
        for n,raw in enumerate(path.read_text().splitlines(),1):
            code=raw.split('#',1)[0].strip()
            if not code or LABEL.fullmatch(code): continue
            tokens=code.split();op=tokens[0];count+=1;used.add(op)
            if op not in table:
                unknown.append((rel,n,op,code));continue
            want=arity[op]
            if want is not None and len(tokens)-1!=want:
                mismatch.append((rel,n,op,len(tokens)-1,want,table[op]['example'],code))

    prov=data['provenance'];minimum=data['minimum_build']
    print('IC10 opcode validation')
    print('='*100)
    print(f"Instruction set: {len(table)} instructions from {prov['source_repository']}")
    print(f"  path {prov['source_path']} @ {prov['source_commit'][:10]} (updated {prov['source_last_updated']})")
    print(f"  extracted from game data by {prov['extractor'].split(' ')[0]}")
    print(f"  target build: {prov['target_game_build']}; minimum build {minimum['date']} ({minimum['reason'].split('.')[0]})")
    print(f"Checked {count} instructions across {len(sources())} programs; {len(used)} distinct mnemonics.")
    for rel,n,op,code in unknown:
        print(f"FAIL {rel}:{n} unknown instruction {op!r} -> {code}")
    for rel,n,op,got,want,example,code in mismatch:
        print(f"FAIL {rel}:{n} {op} takes {want} operands, found {got}")
        print(f"       official signature: {example}")
        print(f"       source: {code}")
    print('='*100)
    failed=bool(unknown or mismatch)
    if not failed:
        print('  - every mnemonic exists in the official instruction set')
        print('  - every operand count matches the official signature')
    print('Result:','FAIL' if failed else 'PASS')
    return 1 if failed else 0

if __name__=='__main__': sys.exit(main())
