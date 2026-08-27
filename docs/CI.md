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
schemas, evidence summaries, and other committed artifacts. On failure, the job
uploads the generated validation summary, state, full run inventory, and
per-script evidence for seven days. CI-generated evidence is diagnostic only and
is never committed by the workflow.

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

The command must report a full-suite PASS, and `git status --short` must print
nothing. Local pre-commit validation may use `--resume` for developer feedback;
the required remote check never does.

Workflow-only changes do not alter the framework input fingerprint or invalidate
live-game evidence: `.github/` is excluded from both that fingerprint and release
archives. The remote job still runs without `--resume`, so it always validates
the workflow policy from source.
