"""The IC10 line budget and the inventory figures quoted from it.

Three counts appear in hand-written prose (``CLAUDE.md``, ``README.md``,
``docs/DEPLOYMENT.md``) and in the validation summary. Each is defined once here so
the runner that prints the summary and the validator that holds the prose to the
tree cannot disagree about what is being counted (issue #164):

- **programs** — every ``*.ic10`` file under ``ic10/``. Release validation requires
  each one to resolve to exactly one deployment family, so this is also the count of
  deployable programs. It exceeds the explicit ``scripts`` list in
  ``data/source_manifest.json``, whose ``generated_deployment_rules`` cover whole
  generated families without naming their files.
- **tight programs** — programs at ``TIGHT_LINES`` or more, leaving at most three
  lines of headroom under the ceiling.
- **soft-limit exemptions** — programs above ``CEILING_LINES``.
  ``validation/validators/validate_ic10.py`` fails an unexempted program over the
  ceiling and an exemption whose program is within it, so on a tree that validates
  this count is exactly the size of its ``SOFT_LIMIT_EXEMPTIONS``.

A program's line count is what ``framework.ic10_source.parse_ic10`` sees, the same
measure ``validate_ic10.py`` applies its limits to.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from framework.ic10_source import parse_ic10
from framework.scan_coverage import require_nonempty_glob

HARD_LIMIT_LINES = 128  # the game's program limit
CEILING_LINES = 120  # the project's maintainability ceiling; the margin is deliberate
TIGHT_LINES = 117  # at most three lines of headroom under the ceiling


def production_line_counts(root: Path) -> dict[str, int]:
    """Line count of every production program, keyed by repository-relative POSIX path."""
    root = Path(root)
    return {
        path.relative_to(root).as_posix(): len(parse_ic10(path.read_text()).lines)
        for path in require_nonempty_glob(root / "ic10", "*.ic10", recursive=True)
    }


@dataclass(frozen=True)
class LinePressure:
    """The inventory figures the prose quotes, measured from one scan of ``ic10/``."""

    programs: int
    tight: int
    exempt: int
    max_lines: int


def line_pressure(root: Path) -> LinePressure:
    counts = production_line_counts(root)
    return LinePressure(
        programs=len(counts),
        tight=sum(lines >= TIGHT_LINES for lines in counts.values()),
        exempt=sum(lines > CEILING_LINES for lines in counts.values()),
        max_lines=max(counts.values()),
    )
