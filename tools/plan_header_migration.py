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
SELF_OFFSET = r'^add (r[0-9]+|ra|sp) \1 (\d+)$'
MOVE_BASE = r'^move (r[0-9]+|ra|sp) (\d+)$'
ADD_BASE = r'^add (r[0-9]+|ra|sp) (r[0-9]+|ra|sp) (\d+)$'
SCALED_BASE = r'^mul (r[0-9]+|ra|sp) (r[0-9]+|ra|sp) (?:\d+)$'


def boot_clear_only(source):
    """True when a full-stack range is a boot-time `clr db` and nothing else.

    A clear zeroes every cell; it does not claim any. Treating it as occupancy
    would block every program that resets its stack before publishing.
    """
    lines = [line.split('#', 1)[0].strip() for line in Path(ROOT / source).read_text().splitlines()]
    cleared = False
    for line in lines:
        if line == 'yield':
            break
        if line.startswith('clr db'):
            cleared = True
    computed = any(line.startswith(('poke r', 'push', 'pop', 'putd', 'clrd', 'peek')) for line in lines)
    return cleared and not computed


def occupied(own, source):
    """Every cell a program can touch: literal, and anything a computed address reaches."""
    cells = set(own['literal_reads']) | set(own['literal_writes'])
    for key in ('dynamic_read_ranges', 'dynamic_write_ranges'):
        for item in own[key]:
            if item['start'] == 0 and item['end'] == 511 and boot_clear_only(source):
                continue
            cells |= set(range(item['start'], item['end'] + 1))
    return cells


def computed_write_floor(source, window=12):
    """Lowest cell each `poke r?` can reach, by walking its address back to a base.

    Chained `add rX rX K` are offsets, not bases: the walk accumulates them and
    keeps going, so a table written as `mul r0 r7 4 / add r0 r0 16 / poke r0 ...`
    floors at S16 rather than at the S1 the last increment would suggest. A scaled
    base contributes zero, which is sound only while the index register is
    non-negative -- so the index is reported for a reviewer to confirm.
    """
    lines = [line.split('#', 1)[0].strip() for line in Path(ROOT / source).read_text().splitlines()]
    floors = {}
    for index, line in enumerate(lines):
        match = re.match(COMPUTED_WRITE, line)
        if not match:
            continue
        register, offset, scaled_by = match.group(1), 0, None
        for previous in reversed(lines[max(0, index - window):index]):
            self_offset = re.match(SELF_OFFSET, previous)
            if self_offset and self_offset.group(1) == register:
                offset += int(self_offset.group(2))
                continue
            moved = re.match(MOVE_BASE, previous)
            if moved and moved.group(1) == register:
                offset += int(moved.group(2))
                break
            added = re.match(ADD_BASE, previous)
            if added and added.group(1) == register:
                offset += int(added.group(3))
                register = added.group(2)
                continue
            scaled = re.match(SCALED_BASE, previous)
            if scaled and scaled.group(1) == register:
                scaled_by = scaled.group(2)
                break
        else:
            continue
        floors.setdefault((offset, scaled_by), []).append(index + 1)
    return floors


def narrowed_write_ranges(own, source):
    """Replace a conservative full-stack write range with the source-derived floor.

    The analyser widens an unbounded computed write to the whole stack. When every
    computed write in the program floors above the header, planning against that
    floor is what a reviewer would do by hand -- and it is reported as an assumption.
    """
    ranges = own['dynamic_write_ranges']
    if own['dynamic_write_range_source'] != 'conservative-full-stack':
        return ranges, None
    floors = computed_write_floor(source)
    if not floors:
        return ranges, None
    lowest = min(offset for offset, _ in floors)
    narrowed = [dict(item, start=max(item['start'], lowest))
                if item['start'] == 0 and item['end'] == 511 else item for item in ranges]
    return narrowed, (lowest, floors)


def plan_program(own, source, base, length):
    used = occupied(own, source)
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
        declared = docs[source]['own_stack']
        writes, derived = narrowed_write_ranges(declared, source)
        own = dict(declared, dynamic_write_ranges=writes)
        plan = plan_program(own, source, arguments.base, arguments.length)
        count = len(Path(ROOT / source).read_text().splitlines()) + 1
        notes = []
        header = set(range(arguments.base, arguments.base + arguments.length))
        reaches_header = (not boot_clear_only(source)) and any(
            header & set(range(item['start'], item['end'] + 1)) for item in writes)
        if derived:
            floor, floors = derived
            detail = ', '.join(
                f"S{offset}{'' if index is None else f' + {index}*n'} (line {at[0]})"
                for (offset, index), at in sorted(floors.items()))
            notes.append(f'ASSUMES computed writes floor at S{floor}, from {detail};'
                         ' confirm each index register is non-negative')
        if reaches_header:
            notes.append(f"REVIEW dynamic writes ({declared['dynamic_write_range_source']}) can reach"
                         ' the header; bound them in the source or relocate what they target')
        elif writes:
            notes.append(f'dynamic writes {writes} kept clear of the plan')
        if plan is None:
            notes.append('BLOCKED no free cells remain outside the analysed footprint;'
                         ' bound the writes or relocate what they target, then re-run')
        if count > HARD_LIMIT:
            notes.append(f'BLOCKED {count} lines exceeds the {HARD_LIMIT}-line hard limit')
        elif count > SOFT_LIMIT:
            notes.append(f'{count} lines needs a reviewed soft-limit exemption')
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
