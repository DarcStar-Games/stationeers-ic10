#!/usr/bin/env python3
"""Structural checks on Python source: the entry-point contract, bootstrap placement, import names, import-time work."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import ast
import sys

ROOT = _PROJECT_ROOT
SHEBANG = "#!/usr/bin/env python3"
# Modules under these roots are command-line entry points, run as scripts by the
# validation runner and by hand. Everything else -- framework/ reference models
# and package markers -- is imported and must not advertise an entry point.
ENTRY_ROOTS = {"tools", "tests", "validation"}
# A tools/ entry point is a command: running it does the work, importing it must
# not. Four generators once ran their entire body at module level, so
# `import tools.generate.generate_source_catalog` rewrote docs/SCRIPT_INDEX.md --
# invisible only because regeneration happens to be byte-stable. Tests and
# validators under the other entry roots do run at import -- CLAUDE.md defines them
# as plain scripts -- and several regenerate tracked output by subprocess to assert
# byte-stability: `import tests.test_input_profiles` writes seventeen tracked files.
# Their exemption is about their contract, not about being side-effect free.
WORK_FREE_ROOT = "tools"
SKIP_PARTS = {".git", ".claude", ".githooks", "__pycache__", "field_evidence"}
# The kernel honours an interpreter line only at byte 0, so a shebang pushed
# below the bootstrap hands Python source to /bin/sh, which hangs. The line-1
# checks below are the primary guard; scanning the rest of the header names the
# stray copy too, which is the difference between "wrong first line" and a
# diagnosis. Stop at the header: '#!' deeper in a module is prose, not a claim.
HEADER_WINDOW = 10
BOOTSTRAP = (
    "from pathlib import Path as _ProjectPath",
    "import sys as _project_sys",
    "_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[{depth}]",
    "if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))",
)


def is_entry_point(rel: Path) -> bool:
    return rel.parts[0] in ENTRY_ROOTS and rel.name != "__init__.py"


def shadowable_modules(paths):
    """Map each module a bare-name import can reach to the package name it must be imported by.

    Python puts the running script's own directory on sys.path before the
    bootstrap inserts the repository root, and leaves it there for the whole
    run: `python3 tools/run_validation.py` keeps <root>/tools live on the path.
    So every module beside an entry point answers to two names, and
    `import tools.build_release` and `import build_release` return two distinct
    module objects loaded from one file -- two copies of ROOT, TOOLING_DIRS,
    SCRIPTS, with nothing keeping them equal. A divergence would be silent and
    would land in release inventory or validation scope, so a module gets
    exactly one name: the package form, rooted at the repository root.
    """
    dirs = {p.parent for p in paths if is_entry_point(p.relative_to(ROOT))}
    return {
        q.stem: ".".join(q.relative_to(ROOT).with_suffix("").parts)
        for d in sorted(dirs)
        for q in sorted(d.glob("*.py"))
        if q.stem != "__init__"
    }


def check_import_names(tree, shadowable, failures):
    """An in-tree module must be imported through its package, never by bare name.

    Naming the package is the whole rule here, but it is not the whole advice: outside
    tools/, where check_work_in_main holds the line, most entry points work at
    module level rather than behind `if __name__`, and importing tests/test_job_abi.py
    under either name runs the whole test. A handful are guarded, which is why the
    message says "usually" instead of asserting it. Say so, so a corrected import does
    not become a second mistake.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        # A relative import already names its package, so only absolute ones can go bare.
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            package = shadowable.get(name.split(".")[0])
            if package:
                # Only tools/ is proven work-free; elsewhere the fixed import still runs the file.
                runs = "" if package.startswith(WORK_FREE_ROOT + ".") else " -- and outside tools/ importing an entry point usually runs it"
                failures.append(
                    f"line {node.lineno}: bare-name import of {name!r}; its only name is {package!r}{runs}"
                )


def is_docstring(node) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def is_future(node) -> bool:
    return isinstance(node, ast.ImportFrom) and node.module == "__future__"


def header_end(body) -> int:
    """Index of the first statement past the docstring and any __future__ imports."""
    at = 0
    if body and is_docstring(body[0]):
        at = 1
    while at < len(body) and is_future(body[at]):
        at += 1
    return at


def check_bootstrap(rel: Path, lines, tree, failures):
    """The bootstrap must be the first executable statement and name the right depth."""
    body = tree.body
    at = header_end(body)
    if at >= len(body):
        failures.append("bootstrap missing")
        return
    start = body[at].lineno - 1
    found = lines[start:start + len(BOOTSTRAP)]
    # parents[N] must climb exactly to the repository root from this file's directory.
    depth = len(rel.parts) - 1
    expected = [line.format(depth=depth) for line in BOOTSTRAP]
    if found != expected:
        failures.append("bootstrap is not the canonical four lines directly after the header")
        for want, got in zip(expected, found + [""] * len(expected)):
            if want != got:
                failures.append(f"  want {want!r}")
                failures.append(f"  got  {got!r}")
                break


def check_work_in_main(rel: Path, tree, entry, has_bootstrap, failures):
    """Under tools/, module level may import, define and name constants -- main() acts.

    Two halves, and the second is the one that fails open. Nothing may run at import:
    no static check can prove a call is pure, so this one allows none outside the
    bootstrap, because `COORD_PROGRAMS=ensure_coordination_programs(R)` reads like a
    constant and writes eleven IC10 programs. A pure value that genuinely wants to be a
    module constant can be written as a literal. Decorator calls are the one call this
    does not inspect, since every decorator worth having here is pure and rejecting
    `@lru_cache()` would buy nothing.

    And something must still run when the file is executed. A body moved into main()
    with the guard forgotten is a command that exits 0 having done nothing:
    build_release.py runs three generators with check=True and would accept it, and the
    byte-stability tests hash the tree, regenerate, and compare -- which a generator
    that writes nothing passes trivially. So an entry point here must carry the guard.

    The first half covers the package markers too. Work in tools/__init__.py would run
    on every `import tools.anything`, which is the worst place in the tree for it, so
    the bootstrap is skipped by whether it is there rather than by role.
    """
    if rel.parts[0] != WORK_FREE_ROOT:
        return
    guarded = False
    for node in tree.body[header_end(tree.body) + (len(BOOTSTRAP) if has_bootstrap else 0):]:
        if isinstance(node, ast.If) and any(isinstance(n, ast.Name) and n.id == "__name__" for n in ast.walk(node.test)):
            guarded = True
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and not any(isinstance(n, ast.Call) for n in ast.walk(node)):
            continue
        source = ast.unparse(node).splitlines()[0]
        failures.append(f"line {node.lineno}: {source[:60]!r} runs at import; under tools/ the work belongs in main()")
    if entry and not guarded:
        failures.append("nothing runs when this is executed: no `if __name__` guard to call main()")


def inspect(path: Path, shadowable):
    rel = path.relative_to(ROOT)
    entry = is_entry_point(rel)
    text = path.read_text()
    lines = text.split("\n")
    # Only the owner-execute bit is tracked by git and checked below. The rest of
    # the mode is whatever umask happened to be in effect when git materialised
    # the file, so it must not reach the printed row: this output is committed
    # evidence, and a group-write bit would churn it between machines with no
    # source change.
    executable = bool(path.stat().st_mode & 0o100)
    failures = []

    if entry:
        if lines[0] != SHEBANG:
            failures.append(f"entry point must open with {SHEBANG!r}, found {lines[0]!r}")
        if not executable:
            failures.append("entry point is not executable")
    else:
        if lines[0].startswith("#!"):
            failures.append("imported module carries a shebang it cannot honour")
        if executable:
            failures.append("imported module has the executable bit set")
    for n, line in enumerate(lines[1:HEADER_WINDOW], 2):
        if line.startswith("#!"):
            failures.append(f"dead shebang at line {n}: the kernel reads an interpreter line only at line 1")

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        failures.append(f"does not parse: {exc}")
        return entry, executable, failures

    if not ast.get_docstring(tree) and any(is_docstring(node) for node in tree.body):
        failures.append("module docstring is demoted to a dead expression by a statement above it")
    has_bootstrap = "_ProjectPath" in text
    if entry != has_bootstrap:
        failures.append("entry point without the bootstrap" if entry else "imported module carries the bootstrap")
    elif has_bootstrap:
        check_bootstrap(rel, lines, tree, failures)
    check_import_names(tree, shadowable, failures)
    check_work_in_main(rel, tree, entry, has_bootstrap, failures)

    return entry, executable, failures


def main():
    paths = sorted(
        p for p in ROOT.rglob("*.py")
        if not SKIP_PARTS & set(p.relative_to(ROOT).parts)
    )
    shadowable = shadowable_modules(paths)
    rows = [(p.relative_to(ROOT).as_posix(), *inspect(p, shadowable)) for p in paths]
    failed = any(row[-1] for row in rows)

    print("Python script header validation")
    print("=" * 100)
    for name, entry, executable, failures in rows:
        state = "FAIL" if failures else "PASS"
        role = "entry" if entry else "module"
        print(f"{state:4} {name:58} {role:6} {'+x' if executable else '-x'}")
        for failure in failures:
            print(f"     - {failure}")
    print("=" * 100)
    entries = sum(1 for row in rows if row[1])
    print(f"Checked {len(rows)} files: {entries} entry points, {len(rows)-entries} imported modules")
    print(f"Single import name enforced for {len(shadowable)} modules reachable from a script directory")
    scoped = [row for row in rows if row[0].startswith(WORK_FREE_ROOT + "/")]
    print(f"No work at import for all {len(scoped)} modules under {WORK_FREE_ROOT}/,"
          f" and a guard reaches main() in each of the {sum(1 for row in scoped if row[1])} entry points")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
