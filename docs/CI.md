# Continuous Integration

GitHub Actions runs the complete framework validation from a clean checkout on
every pull request and every push to `main`. The workflow is
`.github/workflows/clean-validation.yml`; its required status check is named
**Clean validation**.

The job uses a fixed Ubuntu runner image, an exact Python patch release, and
commit-pinned GitHub Actions. Its token has read-only repository-content
permission, checkout does not persist credentials, superseded runs for the same
pull request are cancelled, and the job has an explicit timeout.

The CI command is deliberately the non-resumable form:

```text
python3 tools/run_validation.py
```

After validation, CI fails if any tracked file changed or any untracked,
non-ignored file appeared. This catches stale generated contracts, registries,
schemas, and other committed artifacts. Validation summaries, state, logs, and
per-script evidence are ignored, so generating them does not dirty the source
checkout. On failure, the job uploads those diagnostics for seven days; the
workflow never commits them. CI-generated evidence is diagnostic only.
The clean-tree step also rejects any validation-output path present in Git's
index, preventing a forced add from silently restoring committed evidence.

## Branch protection

Protect `main` with a branch ruleset or classic branch protection rule that:

1. enables **Require a pull request before merging**;
2. enables **Require status checks to pass before merging**;
3. requires the **Clean validation** status check;
4. requires branches to be up to date before merging when strict validation of
   the current `main` tip is desired.

GitHub only offers a check for selection after that check has run at least once.
If **Clean validation** is not listed, push the workflow branch, wait for its
first run, and then finish the rule configuration.

## Local reproduction

Run the same clean suite from the repository root:

```text
python3 tools/run_validation.py
git status --short
```

The command must report a full-suite PASS, and `git status --short` must show no
tracked or non-ignored changes. The generated files remain available locally but
are hidden by the normal status view. Local pre-commit validation may use
`--resume` for developer feedback; the required remote check never does.

Release builds also run the suite without `--resume`, verify the complete
evidence set, and include it in the release ZIP even though it is ignored in the
source checkout.

Workflow-only changes do not alter the framework input fingerprint or invalidate
live-game evidence: `.github/` is excluded from both that fingerprint and release
archives. The remote job still runs without `--resume`, so it always validates
the workflow policy from source.
