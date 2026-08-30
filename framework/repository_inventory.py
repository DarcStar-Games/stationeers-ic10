"""Deterministic, policy-driven repository file inventories."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath


BASE_IGNORED_DIRECTORIES = frozenset({".git", "__pycache__"})
BASE_IGNORED_SUFFIXES = frozenset({".pyc"})
LOCAL_TOOLING_DIRECTORIES = frozenset({".github", ".claude", ".githooks"})


@dataclass(frozen=True, slots=True)
class InventoryPolicy:
    """Immutable exclusions layered on the repository inventory base policy.

    Directory names match at any depth. Subtrees are repository-relative POSIX
    paths and may identify either a file or a directory tree.
    """

    ignored_directories: frozenset[str] = frozenset()
    ignored_names: frozenset[str] = frozenset()
    ignored_suffixes: frozenset[str] = frozenset()
    ignored_subtrees: frozenset[str] = frozenset()
    fail_on_empty: bool = False

    def __post_init__(self) -> None:
        for field in ("ignored_directories", "ignored_names", "ignored_suffixes", "ignored_subtrees"):
            object.__setattr__(self, field, frozenset(getattr(self, field)))

    @property
    def effective_ignored_directories(self) -> frozenset[str]:
        return BASE_IGNORED_DIRECTORIES | self.ignored_directories

    @property
    def effective_ignored_suffixes(self) -> frozenset[str]:
        return BASE_IGNORED_SUFFIXES | self.ignored_suffixes


IncludePredicate = Callable[[Path], bool]


def repository_files(
    root: Path,
    *,
    policy: InventoryPolicy = InventoryPolicy(),
    exclude: Iterable[Path] = (),
    include: IncludePredicate | None = None,
) -> tuple[Path, ...]:
    """Return an ordered inventory beneath ``root``.

    Policy matching and ``include`` always receive paths relative to the
    selected root. ``exclude`` accepts relative paths or absolute paths inside
    the root, which supports caller-owned outputs chosen at runtime.
    """

    root = Path(root).resolve()
    excluded = _relative_exclusions(root, exclude)
    ignored_subtrees = tuple(PurePosixPath(path).parts for path in policy.ignored_subtrees)
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _ignored(relative, policy, ignored_subtrees):
            continue
        if relative in excluded or (include is not None and not include(relative)):
            continue
        files.append(path)
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    if policy.fail_on_empty and not files:
        raise RuntimeError(f"repository inventory swept to empty under {root}")
    return tuple(files)


def inventory_path_is_ignored(relative: Path, *, policy: InventoryPolicy = InventoryPolicy()) -> bool:
    """Return whether one repository-relative path is excluded by ``policy``."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"inventory policy path must be relative to its root: {relative}")
    ignored_subtrees = tuple(PurePosixPath(path).parts for path in policy.ignored_subtrees)
    return _ignored(relative, policy, ignored_subtrees)


def _ignored(relative: Path, policy: InventoryPolicy, ignored_subtrees: tuple[tuple[str, ...], ...]) -> bool:
    # Include the final component so a worktree's `.git` metadata file receives
    # the same treatment as a checkout's `.git` metadata directory.
    if set(relative.parts) & policy.effective_ignored_directories:
        return True
    if relative.name in policy.ignored_names or relative.suffix in policy.effective_ignored_suffixes:
        return True
    return any(relative.parts[: len(parts)] == parts for parts in ignored_subtrees)


def _relative_exclusions(root: Path, exclude: Iterable[Path]) -> frozenset[Path]:
    relative = set()
    for value in exclude:
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        # Canonicalize directory aliases and `..` without following the final
        # component: exclusions name inventory entries, not symlink targets.
        lexical = Path(os.path.abspath(path))
        path = lexical.parent.resolve() / lexical.name
        try:
            relative.add(path.relative_to(root))
        except ValueError:
            continue
    return frozenset(relative)
