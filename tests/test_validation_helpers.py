#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile

from framework.validation import Validation


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "example.ic10"
    source.write_text("alpha\nbeta\ngamma\n")

    validation = Validation(root)
    assert validation.contains("example.ic10", "alpha", "beta", rule="protocol markers")
    assert validation.excludes("example.ic10", "delta", rule="retired markers")
    assert validation.ordered("example.ic10", "alpha", "gamma", rule="publication order")
    assert validation.ordered("example.ic10", "beta", "gamma", after="alpha", rule="post-anchor order")
    assert validation.file_exists("example.ic10", rule="program exists")
    assert validation.line_limit("example.ic10", 3, rule="IC10 budget")

    # The first source snapshot is authoritative for the run: later assertions
    # must neither reread nor observe a mid-validation file mutation.
    source.write_text("changed\nlater\n")
    assert validation.source("example.ic10") == "alpha\nbeta\ngamma\n"

    failures = Validation(root)
    failures.contains("example.ic10", "missing", rule="required marker")
    failures.excludes("example.ic10", "changed", rule="stale marker")
    failures.ordered("example.ic10", "changed", "absent", rule="write order")
    failures.ordered("example.ic10", "later", "changed", rule="publication order")
    failures.ordered("example.ic10", "changed", after="no-anchor", rule="anchored write order")
    failures.file_exists("absent.ic10", rule="service source")
    failures.line_limit("example.ic10", 0, rule="IC10 budget")
    failures.check(False, "custom domain invariant", path="data/schema.json", detail="bad width")

    output = StringIO()
    def success_details_must_stay_lazy():
        raise AssertionError("failure reporting evaluated PASS details")

    with redirect_stdout(output):
        code = failures.finish("Validation helper tests", success_details_must_stay_lazy)
    rendered = output.getvalue()
    assert code == 1
    assert rendered.startswith("Validation helper tests: FAIL\n")
    assert rendered.count("\n -") == 8
    for expected in (
        "example.ic10: required marker: missing 'missing'",
        "example.ic10: stale marker: present 'changed'",
        "example.ic10: write order: missing 'absent'",
        "example.ic10: publication order: out-of-order token 'changed'; expected after 'later'",
        "example.ic10: anchored write order: missing anchor 'no-anchor'",
        "absent.ic10: service source: file does not exist",
        "example.ic10: IC10 budget: 2 lines exceeds limit 0",
        "data/schema.json: custom domain invariant: bad width",
    ):
        assert expected in rendered, expected

    success_output = StringIO()
    with redirect_stdout(success_output):
        code = validation.finish(
            "Validation helper tests",
            lambda: ["cached assertions and reporting are stable"],
        )
    assert code == 0
    assert success_output.getvalue() == (
        "Validation helper tests: PASS\n"
        " - cached assertions and reporting are stable\n"
    )

print("Validation helper unit tests: PASS")
print(" - cached source assertions collect precise multi-failure diagnostics")
print(" - one finalizer preserves executable validator PASS/FAIL and exit behavior")
