#!/usr/bin/env python3
"""Hold every LogicType and LogicSlotType name in IC10 source to the target build's enum.

The game folds a bare enum name (`Pressure`, `RatioMethane`, `Occupied`) or a dotted literal
(`LogicType.Setting`) to the enum's integer when it compiles the line, so a name the build no
longer has is a program that compiles nowhere. validate_ic10_opcodes.py holds the mnemonic and
its operand count to the game-extracted instruction set; this validator holds the operands.
Each operand position takes its class from the same official signature: a `logicType` position
and any untyped numeric position must name a LogicType member, a `logicSlotType` position a
LogicSlotType member, and a dotted literal must name a member of its enum and sit in a position
of that enum. A `batchMode` or `reagentMode` position takes the words the instruction set's own
description lists for it. The table is data/logic_enums.json, extracted from the target build's
assembly (docs/SOURCES.md), and its build must equal the target the instruction set records (#326).
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import json,re,collections

from framework.ic10_source import DIRECTIVE_OPCODES, LABEL_NAME_RE, parse_ic10
from framework.validation import Validation
from tools.export_to_game import ExportError, target_game_version

ROOT=_PROJECT_ROOT
TABLE=ROOT/'data/logic_enums.json'
SET=ROOT/'data/ic10_instruction_set.json'
# Operands the game reads as something other than a name: registers, devices, numbers, hashes.
OPERAND_RE=re.compile(r'^(?:r(?:[0-9]|1[0-5])|rr(?:[0-9]|1[0-5])|sp|ra|d[0-5]|db|dr(?:[0-9]|1[0-5])|(?:d[0-5]|db):\d+'
                      r'|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|\$[0-9A-Fa-f]+|%[01]+|HASH\(".*"\)|nan|pinf|ninf)$')
TYPED={'logicType':'LogicType','logicSlotType':'LogicSlotType'}
# The words the game's own signature descriptions give these positions (data/ic10_instruction_set.json).
WORDS={'batchMode':{'Average','Sum','Minimum','Maximum'},'reagentMode':{'Contents','Required','Recipe'}}

def sources():
    return sorted((ROOT/'ic10').rglob('*.ic10'))+sorted((ROOT/'tests'/'ic10').rglob('*.ic10'))

def operand_classes(example):
    """Position classes from the game's own signature: 'l r? device(d?|r?|id) logicType' -> ('r?','device','logicType')."""
    return tuple(re.sub(r'\(.*\)$','',tok) for tok in example.split()[1:])

def main():
    result=Validation(ROOT)
    table=json.loads(TABLE.read_text())
    if table.get('format')!='STATIONEERS_LOGIC_ENUMS_V1':raise SystemExit(f"unsupported enum table format: {table.get('format')!r}")
    enums={name:{n:int(v) for n,v in body['values'].items()} for name,body in table['enums'].items()}
    build=table['game_build']
    try:target=target_game_version(ROOT)
    except ExportError as exc:target=None;result.fail('target game build is readable',path='data/ic10_instruction_set.json',detail=str(exc))
    if target is not None and target!=build:
        result.fail('the enum table was extracted from the target build',path='data/logic_enums.json',detail=f'table build {build}, target {target}')
    signatures={n:operand_classes(e['example']) for n,e in json.loads(SET.read_text())['instructions'].items()}
    checked=collections.Counter();bare=collections.Counter();dotted=collections.Counter()
    for path in sources():
        rel=path.relative_to(ROOT).as_posix();src=parse_ic10(path.read_text())
        names=set(src.directive_values());labels=set(src.label_indices())
        for row in src.rows:
            op=row.opcode
            if op in DIRECTIVE_OPCODES or op not in signatures:continue  # validate_ic10_opcodes.py owns unknown mnemonics
            for cls,tok in zip(signatures[op],row.tokens[1:]):
                if OPERAND_RE.fullmatch(tok) or tok in names or tok in labels:continue
                checked[cls]+=1;site=f'{rel}:{row.line.number}';code=row.line.code_text
                enum,dot,member=tok.partition('.')
                if dot:
                    dotted[tok]+=1
                    if enum not in enums:result.fail(f'{site}: {tok!r} names no enum the game folds to an integer',detail=code)
                    elif member not in enums[enum]:result.fail(f'{site}: {tok!r} names no member of {enum} at build {build}',detail=code)
                    elif cls in TYPED and TYPED[cls]!=enum:result.fail(f'{site}: {tok!r} sits in a {TYPED[cls]} position',detail=code)
                    continue
                if not LABEL_NAME_RE.fullmatch(tok):result.fail(f'{site}: {tok!r} is not an operand the game accepts',detail=code);continue
                bare[tok]+=1
                if cls in WORDS:
                    if tok not in WORDS[cls]:result.fail(f'{site}: {tok!r} is not a {cls} word ({", ".join(sorted(WORDS[cls]))})',detail=code)
                    continue
                want=TYPED.get(cls,'LogicType')
                if tok in enums[want]:continue
                other=[e for e,members in enums.items() if tok in members]
                why=f'it is a {other[0]} member; write {other[0]}.{tok}' if other else f'no enum has it at build {build}'
                result.fail(f'{site}: {tok!r} is not a {want} member ({why})',detail=code)
    if not checked:result.fail('no enum-name operand was found in any program')
    print(f"Enum table: {sum(len(v) for v in enums.values())} members across {', '.join(enums)} at build {build} (extracted {table['extracted']})")
    print(f"Checked {sum(checked.values())} name operands across {len(sources())} programs: "+', '.join(f'{c} {k}' for k,c in sorted(checked.items())))
    print(f"  {len(bare)} distinct bare names, {len(dotted)} distinct dotted literals")
    return result.finish('Logic enum tokens',[
        'every bare LogicType or LogicSlotType name is a member of the enum extracted from the target build',
        'every dotted enum literal names a member and sits in a position of its enum',
        'a batchMode or reagentMode position holds one of the words its signature description lists',
        'data/logic_enums.json was extracted from the build data/ic10_instruction_set.json targets'])

if __name__=='__main__':raise SystemExit(main())
