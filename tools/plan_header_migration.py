#!/usr/bin/env python3
"""Plan a family's move onto the common stack header, from the generated contracts."""
from __future__ import annotations
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import argparse, glob, json, re

ROOT = _PROJECT_ROOT
INVENTORY = ROOT / 'contracts/stack_envelope_inventory.json'
SOFT_LIMIT = 120
HARD_LIMIT = 128
PORT_ACCESS = r'^(put|get)d? (?:(\S+) )?(d[0-9]|\S+) (\d+)\b'
COMPUTED_WRITE = r'^poke (r[0-9]+|ra|sp) '
ADDRESS_BASE = r'^(?:add|move) (r[0-9]+|ra|sp) (?:\S+ )?(\d+)$'


def occupied(own):
    """Every cell a program can touch: literal, and anything a computed address reaches."""
    cells = set(own['literal_reads']) | set(own['literal_writes'])
    for key in ('dynamic_read_ranges', 'dynamic_write_ranges'):
        for item in own[key]:
            cells |= set(range(item['start'], item['end'] + 1))
    return cells


def computed_write_bases(source, window=6):
    """Literal bases feeding a `poke r?`, so a reviewer can see where a table starts."""
    lines = [line.split('#', 1)[0].strip() for line in Path(ROOT / source).read_text().splitlines()]
    bases = {}
    for index, line in enumerate(lines):
        match = re.match(COMPUTED_WRITE, line)
        if not match:
            continue
        register = match.group(1)
        for previous in reversed(lines[max(0, index - window):index]):
            found = re.match(ADDRESS_BASE, previous)
            if found and found.group(1) == register:
                bases.setdefault(int(found.group(2)), []).append(index + 1)
                break
    return bases


def plan_program(own, base, length):
    used = occupied(own)
    move = sorted(c for c in (set(own['literal_reads']) | set(own['literal_writes'])) if base + 2 <= c < base + length)
    free = [c for c in range(base + length, 512) if c not in used]
    if len(free) < len(move):
        return None
    return dict(zip(move, free))


def port_edges(docs, family, magics):
    """Low-cell accesses through a port or reference, which carry no magic to key on.

    Reported for the family itself and for any program naming one of its magics,
    because those are the only ones that can be addressing a migrating program.
    """
    interesting = set(family)
    for source in docs:
        text = Path(ROOT / source).read_text()
        if any(str(magic) in text for magic in magics):
            interesting.add(source)
    edges = []
    for source in sorted(interesting):
        for number, line in enumerate(Path(ROOT / source).read_text().splitlines(), 1):
            code = line.split('#', 1)[0].strip()
            match = re.match(PORT_ACCESS, code)
            if not match or match.group(3) == 'db':
                continue
            if 2 <= int(match.group(4)) < 8:
                edges.append((source, number, code))
    return edges


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('family')
    parser.add_argument('--base', type=int, default=0)
    parser.add_argument('--length', type=int, default=8)
    arguments = parser.parse_args()
    inventory = json.loads(INVENTORY.read_text())
    docs = {json.load(open(path))['source']: json.load(open(path))
            for path in glob.glob(str(ROOT / 'contracts/**/*.contract.json'), recursive=True)}
    family = sorted(item['source'] for item in inventory['services']
                    if item['deployment_family'] == arguments.family and item['status'] == 'legacy-exempt')
    if not family:
        raise SystemExit(f'no unmigrated programs in family {arguments.family!r}')
    names = {Path(source).name for source in family}
    print(f'{arguments.family}: {len(family)} unmigrated programs')
    for source in family:
        own = docs[source]['own_stack']
        plan = plan_program(own, arguments.base, arguments.length)
        lines = len(Path(ROOT / source).read_text().splitlines()) + 1
        notes = []
        header = set(range(arguments.base, arguments.base + arguments.length))
        reaches_header = any(header & set(range(item['start'], item['end'] + 1))
                             for item in own['dynamic_write_ranges'])
        if reaches_header:
            notes.append(f"REVIEW dynamic writes ({own['dynamic_write_range_source']}) can reach the header;"
                         " bound them in the source or relocate what they target")
        elif own['dynamic_write_ranges']:
            notes.append(f"dynamic writes {own['dynamic_write_ranges']} kept clear of the plan")
        if reaches_header or plan is None:
            bases = computed_write_bases(source)
            if bases:
                detail = ', '.join(f'S{cell} (line {lines[0]})' for cell, lines in sorted(bases.items()))
                notes.append(f'computed writes appear based at {detail}')
        if plan is None:
            notes.append('BLOCKED no free cells remain outside the analysed footprint;'
                         ' bound the writes or relocate what they target, then re-run')
        if lines > HARD_LIMIT:
            notes.append(f'BLOCKED {lines} lines exceeds the {HARD_LIMIT}-line hard limit')
        elif lines > SOFT_LIMIT:
            notes.append(f'{lines} lines needs a reviewed soft-limit exemption')
        print(f'   {Path(source).name:46} {plan}')
        for note in notes:
            print(f'      {note}')
    magics = {header['magic'] for source in family for header in docs[source]['own_stack']['headers']}
    print('\nport and reference accesses to S2..S7 in the family and its namers:')
    print('   (a port carries no magic to key on; confirm each target before remapping)')
    for source, number, code in port_edges(docs, family, magics):
        marker = 'IN FAMILY' if Path(source).name in names else '         '
        print(f'   {marker} {Path(source).name}:{number}: {code}')
    print('\nvalidators and tests naming these programs:')
    for path in sorted(glob.glob(str(ROOT / 'tests/test_*.py')) + glob.glob(str(ROOT / 'validation/validators/*.py'))):
        text = Path(path).read_text()
        hits = sorted(name for name in names if name in text)
        if hits:
            print(f'   {Path(path).name:44} {len(hits)} program(s)')


if __name__ == '__main__':
    main()
