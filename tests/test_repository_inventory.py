#!/usr/bin/env python3
"""Exercise the shared repository inventory and its policy boundaries."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import tempfile
from framework.generator_productivity import PRODUCTIVITY_INVENTORY_POLICY,_copy_ignore,_snapshot
from framework.repository_inventory import InventoryPolicy,repository_files
from framework.validation import Validation

result=Validation(_PROJECT_ROOT)

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)/'.git'/'checkout'
    (root/'z').mkdir(parents=True)
    (root/'a').mkdir()
    (root/'nested'/'__pycache__').mkdir(parents=True)
    (root/'nested'/'.github').mkdir()
    (root/'z'/'last.txt').write_text('z')
    (root/'a'/'first.txt').write_text('a')
    (root/'a'/'skip.pyc').write_bytes(b'cache')
    (root/'.git').write_text('gitdir: elsewhere')
    (root/'nested'/'__pycache__'/'skip.txt').write_text('cache')
    (root/'nested'/'.github'/'workflow.yml').write_text('ci')
    output=root/'output.zip';output.write_bytes(b'output')
    ignored_directories={'.github'}
    policy=InventoryPolicy(ignored_directories=ignored_directories)
    ignored_directories.add('a')
    result.check(policy.ignored_directories==frozenset({'.github'}),'inventory policy retained a mutable input set')
    files=repository_files(root,policy=policy,exclude=(output,))
    relative=[path.relative_to(root).as_posix() for path in files]
    result.check(relative==['a/first.txt','z/last.txt'],'inventory order or exclusions changed',detail=repr(relative))
    result.check(repository_files(root,policy=policy,exclude=(output,),include=lambda path:path.suffix=='.txt')==files,
                 'relative-path inclusion predicate changed the expected inventory')
    target=root/'target.zip';target.write_bytes(b'target')
    linked_output=root/'linked-output.zip';linked_output.symlink_to(target.name)
    symlink_relative=[path.relative_to(root).as_posix() for path in
                      repository_files(root,policy=policy,exclude=(output,linked_output))]
    result.check('linked-output.zip' not in symlink_relative,'explicit exclusion retained a symlink output')
    result.check('target.zip' in symlink_relative,'explicit symlink exclusion removed its target instead')

with tempfile.TemporaryDirectory() as temporary:
    empty=Path(temporary)
    result.check(repository_files(empty)==(),'an empty inventory is not allowed by default')
    try:
        repository_files(empty,policy=InventoryPolicy(fail_on_empty=True))
    except RuntimeError:
        pass
    else:
        result.fail('fail-closed inventory accepted an empty sweep')

with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    (root/'validation'/'evidence').mkdir(parents=True)
    (root/'validation'/'keep.txt').write_text('keep')
    (root/'validation'/'evidence'/'result.txt').write_text('generated')
    snapshot=_snapshot(root)
    result.check(Path('validation/keep.txt') in snapshot,'productivity snapshot omitted ordinary validation input')
    result.check(Path('validation/evidence/result.txt') not in snapshot,
                 'productivity snapshot included policy-excluded validation evidence')
    ignored=_copy_ignore(root)(root/'validation',{'evidence','keep.txt'})
    result.check(ignored=={'evidence'},'productivity copy filter diverged from its inventory policy',detail=repr(ignored))
    result.check(PRODUCTIVITY_INVENTORY_POLICY.ignored_subtrees==frozenset({'validation/evidence'}),
                 'productivity evidence exclusion is not explicit in its immutable policy')

raise SystemExit(result.finish('Repository inventory tests',[
    'tooling-named checkout parents do not affect relative exclusion matching',
    'nested ignored directories, bytecode, explicit outputs, predicates, and ordering are enforced',
    'empty inventories are allowed or rejected according to immutable policy',
    'productivity copying and snapshots share one explicit evidence-exclusion policy',
]))
