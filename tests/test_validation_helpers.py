#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile

from framework.json_schema import (
    SchemaValidationError,
    ValidationContext,
    _validate_array,
    _validate_combinators,
    _validate_numeric,
    _validate_object,
    _validate_reference,
    _validate_scalar,
    _validate_string,
    validate,
)
from framework.scan_coverage import (
    inspect_suite_globs,
    require_nonempty,
    require_nonempty_glob,
)
from framework.validation import Validation
from framework.validation_suite import (
    SuiteEntry,
    SuiteManifestError,
    TEST_CATEGORY,
    VALIDATOR_CATEGORY,
    suite_entries,
    test_entries,
    validate_suite_entries,
    validator_entries,
)


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

    second = root / "second.py"
    second.write_text("pass\n")
    valid_entry = SuiteEntry("example.ic10", VALIDATOR_CATEGORY, "EXAMPLE", 1)
    assert validate_suite_entries((valid_entry,), root) == (valid_entry,)

    malformed_manifests = (
        ((SuiteEntry("missing.py", TEST_CATEGORY, "MISSING"),), "registered script does not exist"),
        ((valid_entry, SuiteEntry("example.ic10", TEST_CATEGORY, "SECOND", 2)), "duplicate path"),
        ((valid_entry, SuiteEntry("second.py", TEST_CATEGORY, "EXAMPLE", 2)), "duplicate evidence identifier"),
        ((SuiteEntry("example.ic10", "other", "OTHER"),), "invalid category"),
        ((SuiteEntry("example.ic10", TEST_CATEGORY, "TIMEOUT", 0),), "timeout must be a positive finite number"),
    )
    for entries, expected in malformed_manifests:
        try:
            validate_suite_entries(entries, root)
        except SuiteManifestError as error:
            assert expected in str(error), (expected, str(error))
        else:
            raise AssertionError(f"suite manifest accepted malformed registration: {expected}")

    def issue_text(context):
        return [str(issue) for issue in context.issues]

    scalar_context = ValidationContext({})
    assert not _validate_scalar(
        scalar_context,
        3,
        {"const": 4, "enum": [1, 2], "type": "string"},
        "$.scalar",
    )
    assert issue_text(scalar_context) == [
        "$.scalar: expected 4, got 3",
        "$.scalar: 3 is not one of [1, 2]",
        "$.scalar: expected type 'string', got int",
    ]

    reference_schema = {"$defs": {"text": {"type": "string", "minLength": 3}}}
    reference_context = ValidationContext(reference_schema)
    _validate_reference(
        reference_context, "x", {"$ref": "#/$defs/text"}, "$.reference"
    )
    assert issue_text(reference_context) == ["$.reference: string is too short"]

    combinator_context = ValidationContext({})
    combinator_context.add("$.existing", "keep this issue")
    _validate_combinators(
        combinator_context,
        "ok",
        {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        "$.choice",
    )
    assert issue_text(combinator_context) == ["$.existing: keep this issue"]
    _validate_combinators(
        combinator_context,
        "ok",
        {"oneOf": [{"type": "string"}, {"minLength": 1}]},
        "$.exclusive",
    )
    assert issue_text(combinator_context)[-1] == (
        "$.exclusive: 2 oneOf branches matched, expected exactly one"
    )

    all_of_context = ValidationContext({})
    _validate_combinators(
        all_of_context,
        3,
        {"allOf": [{"minimum": 4}, {"maximum": 2}]},
        "$.combined",
    )
    assert issue_text(all_of_context) == [
        "$.combined: 3 is below 4",
        "$.combined: 3 is above 2",
    ]

    unmatched_context = ValidationContext({})
    _validate_combinators(
        unmatched_context,
        False,
        {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        "$.alternative",
    )
    _validate_combinators(
        unmatched_context,
        False,
        {"oneOf": [{"type": "integer"}, {"type": "string"}]},
        "$.exclusive",
    )
    assert issue_text(unmatched_context) == [
        "$.alternative: no anyOf branch matched",
        "$.exclusive: no oneOf branch matched",
    ]

    object_context = ValidationContext({})
    _validate_object(
        object_context,
        {"name": 3, "extra": True},
        {
            "properties": {"name": {"type": "string"}},
            "required": ["missing"],
            "additionalProperties": False,
        },
        "$.object",
    )
    assert issue_text(object_context) == [
        "$.object: missing required property 'missing'",
        "$.object.name: expected type 'string', got int",
        "$.object: unexpected property 'extra'",
    ]

    array_context = ValidationContext({})
    _validate_array(
        array_context,
        [1, 1, 3],
        {"minItems": 4, "maxItems": 2, "uniqueItems": True, "items": {"maximum": 2}},
        "$.array",
    )
    assert issue_text(array_context) == [
        "$.array: expected at least 4 items",
        "$.array: expected at most 2 items",
        "$.array: items are not unique",
        "$.array[2]: 3 is above 2",
    ]

    string_context = ValidationContext({})
    _validate_string(
        string_context,
        "abc",
        {"minLength": 4, "maxLength": 2, "pattern": "Z"},
        "$.string",
    )
    assert issue_text(string_context) == [
        "$.string: string is too short",
        "$.string: string is too long",
        "$.string: 'abc' does not match 'Z'",
    ]

    numeric_context = ValidationContext({})
    _validate_numeric(
        numeric_context, 5, {"minimum": 6, "maximum": 4}, "$.number"
    )
    assert issue_text(numeric_context) == [
        "$.number: 5 is below 6",
        "$.number: 5 is above 4",
    ]

    try:
        validate(
            {"name": "x", "extra": True},
            {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 2}},
                "required": ["missing"],
                "additionalProperties": False,
            },
        )
    except SchemaValidationError as error:
        assert str(error).splitlines() == [
            "$: missing required property 'missing'",
            "$.name: string is too short",
            "$: unexpected property 'extra'",
        ]
    else:
        raise AssertionError("JSON Schema validation did not aggregate all failures")

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "present" / "nested").mkdir(parents=True)
    (root / "root.txt").write_text("root")
    (root / "present" / "one.txt").write_text("one")
    (root / "present" / "nested" / "two.cfg").write_text("two")

    source = root / "scan_subject.py"
    source.write_text(
        "_PROJECT_ROOT = bootstrap()\n"
        "ROOT = _PROJECT_ROOT\n"
        "TREE = ROOT / 'present'\n"
        "text = list(TREE.glob('*.txt'))\n"
        "configs = list(ROOT.rglob('*.cfg'))\n"
        "missing = list(ROOT.glob('missing/*.txt'))\n"
        "dynamic = list(output.glob('*.dat'))\n"
        "patterned = list(ROOT.glob(pattern))\n"
        "filtered = [path for path in ROOT.glob('*.txt') if False]\n"
        "def shadowed(ROOT):\n"
        "    return list(ROOT.glob('*.txt'))\n"
    )
    scans = inspect_suite_globs(root, (source,))
    assert len(scans) == 7
    assert [(scan.method, scan.pattern, scan.match_count) for scan in scans[:3]] == [
        ("glob", "*.txt", 1),
        ("rglob", "*.cfg", 1),
        ("glob", "missing/*.txt", 0),
    ]
    assert scans[0].relative_base == Path("present") and scans[0].problem is None
    assert scans[2].problem == "glob scan matches no paths"
    assert "base is not a repository-root literal" in scans[3].problem
    assert "pattern is not a string literal" in scans[4].problem
    assert "filtered and may iterate zero times" in scans[5].problem
    assert "base is not a repository-root literal" in scans[6].problem

    assert require_nonempty(
        (value for value in (1, 2) if value > 1), "filtered values"
    ) == (2,)
    try:
        require_nonempty((value for value in (1, 2) if value > 2), "filtered values")
    except RuntimeError as error:
        assert str(error) == "filtered values is empty"
    else:
        raise AssertionError("filtered collection helper accepted an empty scan")

    assert require_nonempty_glob(root / "present", "*.txt") == (
        root / "present" / "one.txt",
    )
    assert require_nonempty_glob(root / "present", "*.cfg", recursive=True) == (
        root / "present" / "nested" / "two.cfg",
    )
    try:
        require_nonempty_glob(root / "present", "*.missing")
    except RuntimeError as error:
        assert "matched no paths" in str(error)
    else:
        raise AssertionError("dynamic glob helper accepted an empty scan")

entries = suite_entries(_PROJECT_ROOT)
validators = validator_entries(_PROJECT_ROOT)
tests = test_entries(_PROJECT_ROOT)
assert len(entries) == 76 and len(validators) == 30 and len(tests) == 46
assert entries == validators + tests
assert entries[0].evidence_filename == "VALIDATE_ABI_CONTRACTS.txt"
assert entries[-1].evidence_filename == "TEST_GAME_EXPORT.txt"

print("Validation helper unit tests: PASS")
print(" - cached source assertions collect precise multi-failure diagnostics")
print(" - one finalizer preserves executable validator PASS/FAIL and exit behavior")
print(" - suite manifest rejects missing, duplicate, uncategorized, and invalid-timeout entries")
print(" - JSON Schema keyword handlers preserve paths and isolate combinator branches")
print(" - literal, dynamic, and filtered filesystem scans fail closed when empty")
