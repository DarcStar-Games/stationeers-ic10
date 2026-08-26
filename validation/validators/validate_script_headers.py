#!/usr/bin/env python3
"""Structural checks on Python source: what counts as an entry point, the bootstrap, import names, import-time work."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path, PurePosixPath
import ast
import sys
import tools.run_validation as run_validation

ROOT = _PROJECT_ROOT
SHEBANG = "#!/usr/bin/env python3"
# An entry point is a file something runs, and the repository already says which
# files those are in two places -- neither of them the shape of a path. tools/ is
# the command directory: every module there is run by hand or by another command.
# Under tests/ and validation/, tools/run_validation.py's VALIDATORS + TESTS lists
# are the release contract for what runs, so appearing in them is what makes a file
# there a script. Everything else -- framework/ reference models, package markers,
# fixture input -- is imported or read, and must not advertise an entry point.
#
# Reading the first path component instead classified every .py beneath those roots
# as a script, fixture subtrees included: tests/fixtures/ and tests/ic10/ hold input
# a test consumes, and a .py added there would have been required to carry a
# shebang, mode 755 and the bootstrap for a script nothing executes. Both hold no
# Python today, so that was a trap set for whoever added the first one, not a live
# failure: replacing the rule reclassified nothing, and the summary below prints the
# two populations separately so a later divergence is visible rather than inferred.
COMMAND_ROOT = "tools"
# Importing a command to read its list is safe here for one reason: nothing under
# tools/ acts at import. That is check_work_in_main's rule, enforced by this file,
# now also against this import -- run_validation.py does its work in main().
REGISTERED = frozenset(run_validation.SCRIPTS)
# The directories the runner actually draws scripts from -- tests/ and
# validation/validators/ as it stands. unregistered_script() reads a claim only here,
# and nowhere below: a fixture subtree is where input lives, so nothing about a file
# there may be inferred from the shape of a script. Registered names are all test_ or
# validate_ today, and that convention is one of the marks; it only ever widens what
# is caught, so a script registered under some other name costs nothing.
REGISTERED_DIRS = frozenset(str(PurePosixPath(name).parent) for name in REGISTERED)
SCRIPT_PREFIXES = ("test_", "validate_")
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
    if rel.name == "__init__.py":
        return False
    return rel.parts[0] == COMMAND_ROOT or rel.as_posix() in REGISTERED


def unregistered_script(rel: Path, lines, text, executable):
    """A file beside the registered scripts that dresses as one nothing runs.

    Registration is not paperwork here: tools/run_validation.py executes the paths in
    VALIDATORS and TESTS and nothing else, so a checker absent from those lists never
    runs, and the suite reports PASS over the gap it left. CLAUDE.md says as much --
    anything not listed there is not part of the release contract -- and this is the
    check for it, which the old classification could not express because it read
    every .py under these roots as a script whether or not anything ran it.

    Say the cause, because the symptoms mislead. Sorted as an imported module, the
    same unregistered test draws three complaints -- shebang, executable bit,
    bootstrap -- and each invites stripping exactly what a real test needs, which
    silences the validator and leaves the test just as unrun. Stripping all three
    leaves the fourth mark below. A file wearing none of the four is checked as what
    it is: a helper a test imports.

    Read strictly beside the registered scripts, never below. Two of the marks are
    textual -- a shebang, and the substring the bootstrap check already keys off --
    and a fixture is free to contain either as data: tests/fixtures/ exists to hold a
    malformed header a test reads as text, which would otherwise be convicted of
    carrying a bootstrap it is only quoting. Judging fixture input by the shape of a
    script is the whole of #18, and this check must not reintroduce it one level down.
    """
    # An entry point is by definition not a file nothing runs, and it is the first
    # test because REGISTERED_DIRS is derived: registering one tools/ command would
    # otherwise make tools/ a script directory and accuse every command beside it,
    # in rows that still read "entry".
    if is_entry_point(rel) or rel.name == "__init__.py" or rel.parent.as_posix() not in REGISTERED_DIRS:
        return None
    marks = [name for name, worn in (
        ("a shebang", lines[0].startswith("#!")),
        ("the executable bit", executable),
        ("the bootstrap", "_ProjectPath" in text),
        # The other three are what a new test inherits from the file it was copied
        # from, which is the likely way one arrives unregistered. This one holds when
        # it was written from scratch and none of them were: a test_ or validate_ name
        # beside the registered scripts is the claim on its own.
        ("a script's name", rel.name.startswith(SCRIPT_PREFIXES)),
    ) if worn]
    if not marks:
        return None
    return (f"nothing runs this: tools/run_validation.py lists no VALIDATORS/TESTS entry for it,"
            f" yet it carries {', '.join(marks)}")


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
                runs = "" if package.startswith(COMMAND_ROOT + ".") else " -- and outside tools/ importing an entry point usually runs it"
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

    Only tools/ is held to this. Four generators once ran their whole body at module
    level, so `import tools.generate.generate_source_catalog` rewrote
    docs/SCRIPT_INDEX.md -- invisible only because regeneration happens to be
    byte-stable. Tests and validators do run at import: CLAUDE.md defines them as
    plain scripts, and several regenerate tracked output by subprocess to assert
    byte-stability, so `import tests.test_input_profiles` writes seventeen tracked
    files. Their exemption is about their contract, not about being side-effect free.

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
    if rel.parts[0] != COMMAND_ROOT:
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

    # One cause, reported alone: every check below reads from a role this file is
    # claiming and has not been given, so their verdicts would describe the wrong fix.
    claim = unregistered_script(rel, lines, text, executable)
    if claim:
        return entry, executable, [claim]

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
    # The list is load-bearing now, so read it in both directions. A path renamed or
    # deleted out from under it still fails the run -- python3 on a missing file exits
    # non-zero -- but it fails as a traceback inside one evidence file among the whole
    # suite's, rather than as the one sentence that names it.
    missing = sorted(name for name in REGISTERED if not (ROOT / name).is_file())
    failed = any(row[-1] for row in rows) or bool(missing)

    print("Python script header validation")
    print("=" * 100)
    for name, entry, executable, failures in rows:
        state = "FAIL" if failures else "PASS"
        role = "entry" if entry else "module"
        print(f"{state:4} {name:58} {role:6} {'+x' if executable else '-x'}")
        for failure in failures:
            print(f"     - {failure}")
    for name in missing:
        print(f"FAIL {name:58} {'listed':6} --")
        print("     - tools/run_validation.py runs this path and no such file exists")
    print("=" * 100)
    entries = sum(1 for row in rows if row[1])
    print(f"Checked {len(rows)} files: {entries} entry points, {len(rows)-entries} imported modules")
    print(f"Single import name enforced for {len(shadowable)} modules reachable from a script directory")
    # Both counts come from the rows, so they partition `entries` by construction. Taking
    # the second from len(REGISTERED) instead reads the same today and stops summing the
    # moment a tools/ command is also registered -- committed evidence must not be able
    # to contradict the line above it.
    commands = sum(1 for row in rows if row[1] and row[0].startswith(COMMAND_ROOT + "/"))
    print(f"Entry points are the {commands} commands under {COMMAND_ROOT}/ plus the {entries - commands}"
          f" scripts tools/run_validation.py runs elsewhere; nothing is an entry point by location")
    scoped = [row for row in rows if row[0].startswith(COMMAND_ROOT + "/")]
    print(f"No work at import for all {len(scoped)} modules under {COMMAND_ROOT}/,"
          f" and a guard reaches main() in each of the {sum(1 for row in scoped if row[1])} entry points")
    print("Result:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
