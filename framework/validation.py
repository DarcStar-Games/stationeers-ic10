"""Small, import-safe assertions for executable repository validators.

This module deliberately stops short of defining a rule language.  Validators
retain their domain-specific loops and checks; :class:`Validation` only owns
source access, common source assertions, failure collection, and reporting.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path


class Validation:
    """Collect failures for one validator rooted at a repository checkout."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.failures: list[str] = []
        self._sources: dict[Path, str] = {}

    @property
    def failed(self) -> bool:
        return bool(self.failures)

    def fail(self, rule: str, *, path: str | Path | None = None, detail: str | None = None) -> None:
        """Record one failure with optional repository path and diagnostic detail."""
        prefix = f"{self._display_path(path)}: " if path is not None else ""
        suffix = f": {detail}" if detail else ""
        self.failures.append(f"{prefix}{rule}{suffix}")

    def check(
        self,
        condition: object,
        rule: str,
        *,
        path: str | Path | None = None,
        detail: str | None = None,
    ) -> bool:
        """Record ``rule`` when ``condition`` is false and return its truth value."""
        passed = bool(condition)
        if not passed:
            self.fail(rule, path=path, detail=detail)
        return passed

    def extend(self, failures: Iterable[str]) -> None:
        """Record already-formatted failures produced by a domain-specific check."""
        self.failures.extend(failures)

    def source(self, path: str | Path, *, rule: str = "source is readable") -> str:
        """Read a repository-relative source once, caching the result for the run."""
        resolved = self._resolve(path)
        if resolved in self._sources:
            return self._sources[resolved]
        try:
            text = resolved.read_text()
        except (OSError, UnicodeError) as error:
            self.fail(rule, path=path, detail=str(error))
            self._sources[resolved] = ""
            return ""
        self._sources[resolved] = text
        return text

    def file_exists(self, path: str | Path, *, rule: str = "file exists") -> bool:
        """Require ``path`` to be an existing file."""
        exists = self._resolve(path).is_file()
        if not exists:
            self.fail(rule, path=path, detail="file does not exist")
        return exists

    def contains(self, path: str | Path, *tokens: str, rule: str = "required token") -> bool:
        """Require every literal token in a cached source file."""
        text = self.source(path)
        passed = True
        for token in tokens:
            if token not in text:
                self.fail(rule, path=path, detail=f"missing {token!r}")
                passed = False
        return passed

    def excludes(self, path: str | Path, *tokens: str, rule: str = "forbidden token") -> bool:
        """Require every literal token to be absent from a cached source file."""
        text = self.source(path)
        passed = True
        for token in tokens:
            if token in text:
                self.fail(rule, path=path, detail=f"present {token!r}")
                passed = False
        return passed

    def ordered(
        self,
        path: str | Path,
        *tokens: str,
        rule: str = "ordered tokens",
        after: str | None = None,
    ) -> bool:
        """Require literal tokens to occur in order, optionally after an anchor."""
        text = self.source(path)
        if after is not None:
            anchor_index = text.find(after)
            if anchor_index < 0:
                self.fail(rule, path=path, detail=f"missing anchor {after!r}")
                return False
            text = text[anchor_index + len(after):]

        positions: list[int] = []
        passed = True
        for token in tokens:
            position = text.find(token)
            positions.append(position)
            if position < 0:
                qualifier = " after anchor" if after is not None else ""
                self.fail(rule, path=path, detail=f"missing{qualifier} {token!r}")
                passed = False

        if passed:
            for index, (previous, token) in enumerate(zip(tokens, tokens[1:])):
                previous_position = positions[index]
                position = positions[index + 1]
                if position <= previous_position:
                    self.fail(
                        rule,
                        path=path,
                        detail=f"out-of-order token {token!r}; expected after {previous!r}",
                    )
                    return False
        return passed

    def line_limit(self, path: str | Path, maximum: int, *, rule: str = "line limit") -> bool:
        """Require a source file to contain no more than ``maximum`` lines."""
        actual = len(self.source(path).splitlines())
        if actual > maximum:
            self.fail(rule, path=path, detail=f"{actual} lines exceeds limit {maximum}")
            return False
        return True

    def finish(
        self,
        summary: str,
        pass_details: Iterable[str] | Callable[[], Iterable[str]] = (),
    ) -> int:
        """Print the executable-validator result and return its process exit code."""
        if self.failures:
            print(f"{summary}: FAIL")
            for failure in self.failures:
                print(" -", failure)
            return 1
        print(f"{summary}: PASS")
        details = pass_details() if callable(pass_details) else pass_details
        for detail in details:
            print(" -", detail)
        return 0

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_absolute() else self.root / candidate

    def _display_path(self, path: str | Path) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            try:
                return candidate.relative_to(self.root).as_posix()
            except ValueError:
                return candidate.as_posix()
        return candidate.as_posix()
