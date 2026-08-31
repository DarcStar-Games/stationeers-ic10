"""Fail-closed helpers and a narrow policy check for filesystem scans."""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

_Item = TypeVar("_Item")
_SCAN_METHODS = frozenset({"glob", "rglob"})


@dataclass(frozen=True, slots=True)
class GlobScan:
    """One direct ``Path.glob`` or ``Path.rglob`` call in suite source."""

    source: Path
    line: int
    expression: str
    method: str
    pattern: str | None
    relative_base: Path | None
    match_count: int | None
    error: str | None = None
    filtered: bool = False

    @property
    def problem(self) -> str | None:
        if self.pattern is None:
            return (
                "glob scan pattern is not a string literal; use require_nonempty_glob"
            )
        if self.relative_base is None:
            return "glob scan base is not a repository-root literal; use require_nonempty_glob"
        if self.error is not None:
            return f"glob scan could not be evaluated: {self.error}"
        if self.match_count == 0:
            return "glob scan matches no paths"
        if self.filtered:
            return "glob scan is filtered and may iterate zero times; use require_nonempty after filtering"
        return None


def require_nonempty(values: Iterable[_Item], description: str) -> tuple[_Item, ...]:
    """Materialize ``values`` and raise if a dynamic or filtered scan is empty."""
    items = tuple(values)
    if not items:
        raise RuntimeError(f"{description} is empty")
    return items


def require_nonempty_glob(
    base: Path,
    pattern: str,
    *,
    recursive: bool = False,
) -> tuple[Path, ...]:
    """Return deterministic glob matches and raise if the scan is empty."""
    base = Path(base)
    matches = tuple(sorted(base.rglob(pattern) if recursive else base.glob(pattern)))
    if not matches:
        method = "rglob" if recursive else "glob"
        raise RuntimeError(f"{base}.{method}({pattern!r}) matched no paths")
    return matches


def inspect_suite_globs(
    root: Path,
    sources: Iterable[str | Path],
) -> tuple[GlobScan, ...]:
    """Evaluate direct literal glob calls rooted at the repository.

    This deliberately recognizes only the suite's conventional module-level
    aliases for ``_PROJECT_ROOT`` and literal ``/`` path extensions. Dynamic
    scans use :func:`require_nonempty_glob`; filtered results use
    :func:`require_nonempty`. The checker does not attempt Python data-flow
    analysis.
    """
    root = Path(root).resolve()
    scans: list[GlobScan] = []
    for source in sources:
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = root / source_path
        relative_source = source_path.relative_to(root)
        tree = ast.parse(source_path.read_text(), filename=relative_source.as_posix())
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        bindings = _root_bindings(tree)

        for call in ast.walk(tree):
            if not _is_direct_glob(call):
                continue
            pattern = _literal_pattern(call)
            relative_base = _relative_path(call.func.value, bindings, call, parents)
            match_count = None
            error = None
            if pattern is not None and relative_base is not None:
                try:
                    base = root / relative_base
                    matches = (
                        base.rglob(pattern)
                        if call.func.attr == "rglob"
                        else base.glob(pattern)
                    )
                    match_count = sum(1 for _ in matches)
                except (NotImplementedError, OSError, ValueError) as exc:
                    error = str(exc)
            scans.append(
                GlobScan(
                    source=relative_source,
                    line=call.lineno,
                    expression=ast.unparse(call),
                    method=call.func.attr,
                    pattern=pattern,
                    relative_base=relative_base,
                    match_count=match_count,
                    error=error,
                    filtered=_locally_filtered(call, parents),
                )
            )

    return tuple(
        sorted(
            scans, key=lambda scan: (scan.source.as_posix(), scan.line, scan.expression)
        )
    )


def _is_direct_glob(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _SCAN_METHODS
    )


def _literal_pattern(call: ast.Call) -> str | None:
    value = call.args[0] if call.args else None
    if value is None:
        value = next(
            (keyword.value for keyword in call.keywords if keyword.arg == "pattern"),
            None,
        )
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    return None


def _root_bindings(tree: ast.Module) -> dict[str, Path]:
    """Resolve unambiguous module-level aliases derived from ``_PROJECT_ROOT``."""
    assignments: dict[str, ast.expr] = {}
    counts: Counter[str] = Counter()
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets = (statement.target,)
            value = statement.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                counts[target.id] += 1
                assignments[target.id] = value

    bindings = {"_PROJECT_ROOT": Path()}
    changed = True
    while changed:
        changed = False
        for name, value in assignments.items():
            if name in bindings or counts[name] != 1:
                continue
            relative = _relative_path(value, bindings)
            if relative is not None:
                bindings[name] = relative
                changed = True
    return bindings


def _relative_path(
    node: ast.AST,
    bindings: dict[str, Path],
    use: ast.AST | None = None,
    parents: dict[ast.AST, ast.AST] | None = None,
) -> Path | None:
    if isinstance(node, ast.Name):
        if (
            use is not None
            and parents is not None
            and _locally_shadowed(node.id, use, parents)
        ):
            return None
        return bindings.get(node.id)
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, str)
    ):
        left = _relative_path(node.left, bindings, use, parents)
        return left / node.right.value if left is not None else None
    return None


def _locally_shadowed(
    name: str,
    use: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    current = use
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = current.args
            argument_names = {
                argument.arg
                for argument in (
                    *arguments.posonlyargs,
                    *arguments.args,
                    *arguments.kwonlyargs,
                )
            }
            if arguments.vararg is not None:
                argument_names.add(arguments.vararg.arg)
            if arguments.kwarg is not None:
                argument_names.add(arguments.kwarg.arg)
            if name in argument_names:
                return True
            return any(
                isinstance(candidate, ast.Name)
                and isinstance(candidate.ctx, ast.Store)
                and candidate.id == name
                for candidate in ast.walk(current)
            )
    return False


def _locally_filtered(
    call: ast.Call,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    """Recognize only filtering visible in the expression containing the glob."""
    current: ast.AST = call
    while current in parents:
        current = parents[current]
        if isinstance(
            current, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
        ):
            return len(current.generators) > 1 or any(
                generator.ifs for generator in current.generators
            )
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Name)
            and current.func.id == "filter"
        ):
            return True
        if isinstance(current, ast.stmt):
            return False
    return False
