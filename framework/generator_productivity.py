"""Helpers for proving that a generator reconstructs its declared outputs."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile


def _ignored(source, names):
    ignored = {name for name in names if name in {".git", "__pycache__"} or name.endswith(".pyc")}
    if Path(source).name == "validation":
        ignored.add("evidence")
    return ignored


def _snapshot(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = path.relative_to(root)
        result[rel] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    return result


def _shadow_command(command, root: Path, shadow: Path):
    translated = []
    for argument in command:
        value = os.fspath(argument)
        path = Path(value)
        if path.is_absolute():
            try:
                value = os.fspath(shadow / path.relative_to(root))
            except ValueError:
                pass
        translated.append(value)
    return translated


def _differences(baseline, actual):
    failures = []
    for rel in sorted(baseline.keys() - actual.keys()):
        failures.append(f"generator did not restore {rel}")
    for rel in sorted(actual.keys() - baseline.keys()):
        failures.append(f"generator created undeclared output {rel}")
    for rel in sorted(baseline.keys() & actual.keys()):
        if actual[rel] != baseline[rel]:
            failures.append(f"generator did not reproduce {rel} byte-for-byte with its original mode")
    return failures


def _run(command, cwd: Path, timeout):
    try:
        proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [f"generator timed out after {timeout}s"]
    failures = []
    if proc.returncode:
        failures.append(f"generator exited {proc.returncode} after all declared outputs were perturbed")
        if proc.stdout.strip():
            failures.append(f"generator stdout: {proc.stdout.strip()}")
        if proc.stderr.strip():
            failures.append(f"generator stderr: {proc.stderr.strip()}")
    return failures


def prove_restoration(root: Path, outputs, command, preserve_inputs=(), timeout=15) -> list[str]:
    """Perturb every output in an isolated checkout and require exact restoration.

    Files listed in ``preserve_inputs`` are generator inputs as well as outputs, so
    they receive valid leading JSON whitespace instead of being deleted. The whole
    checkout is compared afterward, which also rejects undeclared writes and files.
    """
    root = Path(root).resolve()
    paths = sorted({Path(path).resolve() for path in outputs})
    missing = [path for path in paths if not path.is_file()]
    if missing:
        return [f"declared output is missing before productivity test: {path.relative_to(root)}" for path in missing]
    preserved = {Path(path).resolve() for path in preserve_inputs}
    if not preserved <= set(paths):
        return ["preserved generator inputs must also appear in the declared output inventory"]
    relatives = [path.relative_to(root) for path in paths]
    preserved_relatives = {path.relative_to(root) for path in preserved}

    with tempfile.TemporaryDirectory() as temporary:
        shadow = Path(temporary) / "checkout"
        shutil.copytree(root, shadow, symlinks=True, ignore=_ignored)
        baseline = _snapshot(shadow)
        for rel in relatives:
            target = shadow / rel
            if rel in preserved_relatives:
                target.write_bytes(b"\n" + target.read_bytes())
            else:
                target.write_bytes(b"")

        failures = _run(_shadow_command(command, root, shadow), shadow, timeout)
        actual = _snapshot(shadow)
        failures += _differences(baseline, actual)
        return failures


def prove_generated_tree_restoration(output_root: Path, command, cwd: Path, timeout=15) -> list[str]:
    """Perturb and regenerate every file in a caller-owned temporary output tree."""
    output_root = Path(output_root).resolve()
    baseline = _snapshot(output_root)
    if not baseline:
        return ["generated output tree is empty before productivity test"]
    for rel in baseline:
        (output_root / rel).write_bytes(b"")
    try:
        failures = _run([os.fspath(arg) for arg in command], Path(cwd), timeout)
        failures += _differences(baseline, _snapshot(output_root))
        return failures
    finally:
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        for rel, (data, mode) in baseline.items():
            target = output_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
