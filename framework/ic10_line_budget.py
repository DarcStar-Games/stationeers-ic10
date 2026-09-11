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

Every other check that names a limit imports it from here: the generators that refuse
to emit over the ceiling, the catalog splitter that sizes a loader to it, the envelope
inventory that records headroom under it, and the family validators that take no
exemption. A limit restated as a number elsewhere is a copy that can drift, and a
per-file ceiling beside ``SOFT_LIMIT_EXEMPTIONS`` is a second list saying less than the
exemption already does (issue #172).

An exemption says why its program is over the ceiling, not how close to the game's
limit it sits. ``hard_limit_margin_failures`` holds the ones within
``HARD_LIMIT_MARGIN_LINES`` of ``HARD_LIMIT_LINES`` to stating the count, so the margin
is reviewed by the edit that moves it rather than discovered by the one that spends
it (issue #176).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from framework.ic10_source import parse_ic10
from framework.scan_coverage import require_nonempty_glob

HARD_LIMIT_LINES = 128  # the game's program limit
CEILING_LINES = 120  # the project's maintainability ceiling; the margin is deliberate
TIGHT_LINES = 117  # at most three lines of headroom under the ceiling
HARD_LIMIT_MARGIN_LINES = 2  # an exemption this close to the hard limit states its count


def hard_limit_note(lines: int) -> str:
    """The phrase an exemption states its program's line count with."""
    return f"{lines} of {HARD_LIMIT_LINES} lines"


def hard_limit_margin_failures(reasons: dict[str, str], counts: dict[str, int]) -> list[str]:
    """Exemptions that misstate their program's line count, or within the margin omit it.

    ``reasons`` maps each exempt program to its exemption text and ``counts`` each program
    to its measured lines. A program within ``HARD_LIMIT_MARGIN_LINES`` of the hard limit
    must state its count in the ``hard_limit_note`` form; a stated count that no longer
    matches the tree fails wherever the program sits. A program ``counts`` lacks is left to
    the caller, which reports a missing file on its own.
    """
    failures = []
    for name in sorted(reasons):
        lines = counts.get(name)
        if lines is None:
            continue
        note = hard_limit_note(lines)
        stated = re.findall(rf"\b(\d+) of {HARD_LIMIT_LINES} lines\b", reasons[name])
        if stated and note not in reasons[name]:
            failures.append(
                f"{name} is {lines} lines but its exemption says {stated[0]} of"
                f" {HARD_LIMIT_LINES}; state {note!r}"
            )
        elif HARD_LIMIT_LINES - lines <= HARD_LIMIT_MARGIN_LINES and not stated:
            failures.append(
                f"{name} is {lines} lines, within {HARD_LIMIT_MARGIN_LINES} of the"
                f" {HARD_LIMIT_LINES}-line hard limit; its exemption must state {note!r}"
            )
    return failures


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
