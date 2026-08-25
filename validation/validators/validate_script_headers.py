#!/usr/bin/env python3
"""Structural checks on Python headers: the entry-point contract and bootstrap placement."""
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
SKIP_PARTS = {".git", ".claude", ".githooks", "__pycache__", "field_evidence"}
# The kernel honours an interpreter line only at byte 0, so a shebang pushed
# below the bootstrap hands Python source to /bin/sh, which hangs. Scan the
# header window rather than the whole file: '#!' deeper in a module is prose.
HEADER_WINDOW = 10
BOOTSTRAP = (
    "from pathlib import Path as _ProjectPath",
    "import sys as _project_sys",
    "_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[{depth}]",
    "if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))",
)


def is_entry_point(rel: Path) -> bool:
    return rel.parts[0] in ENTRY_ROOTS and rel.name != "__init__.py"


def is_docstring(node) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def is_future(node) -> bool:
    return isinstance(node, ast.ImportFrom) and node.module == "__future__"


def check_bootstrap(rel: Path, lines, tree, failures):
    """The bootstrap must be the first executable statement and name the right depth."""
    body = tree.body
    at = 0
    if body and is_docstring(body[0]):
        at = 1
    while at < len(body) and is_future(body[at]):
        at += 1
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


def inspect(path: Path):
    rel = path.relative_to(ROOT)
    entry = is_entry_point(rel)
    text = path.read_text()
    lines = text.split("\n")
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

    return entry, executable, failures


def main():
    paths = sorted(
        p for p in ROOT.rglob("*.py")
        if not SKIP_PARTS & set(p.relative_to(ROOT).parts)
    )
    rows = [(p.relative_to(ROOT).as_posix(), *inspect(p)) for p in paths]
    failed = any(row[-1] for row in rows)

    print("Python script header validation")
    print("=" * 100)
    for name, entry, executable, failures in rows:
        state = "FAIL" if failures else "PASS"
        role = "entry" if entry else "module"
        print(f"{state:4} {name:58} {role:6} mode={'755' if executable else '644'}")
        for failure in failures:
            print(f"     - {failure}")
    print("=" * 100)
    entries = sum(1 for row in rows if row[1])
    print(f"Checked {len(rows)} files: {entries} entry points, {len(rows)-entries} imported modules")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
