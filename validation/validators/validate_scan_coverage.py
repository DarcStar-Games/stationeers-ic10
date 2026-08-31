#!/usr/bin/env python3
"""Reject empty or unverifiable direct glob scans in registered suite scripts."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from framework.scan_coverage import inspect_suite_globs
from framework.validation import Validation
from framework.validation_suite import suite_entries


ROOT = _PROJECT_ROOT
validation = Validation(ROOT)
entries = suite_entries(ROOT)
try:
    scans = inspect_suite_globs(ROOT, (entry.path for entry in entries))
except (OSError, SyntaxError, ValueError) as error:
    validation.fail("suite glob scan analysis failed", detail=str(error))
    scans = ()

for scan in scans:
    if scan.problem is not None:
        validation.fail(
            scan.problem,
            path=scan.source,
            detail=f"line {scan.line}: {scan.expression}",
        )

raise SystemExit(validation.finish("Suite scan coverage validation", [
    f"{len(scans)} direct glob scans checked across {len(entries)} registered scripts",
    "dynamic glob scans fail closed through require_nonempty_glob",
    "filtered scan results fail closed through require_nonempty",
]))
