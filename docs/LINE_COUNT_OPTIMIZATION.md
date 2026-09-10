# Line Count Optimization

The framework keeps production IC10 programs at or below a **120-line maintainability ceiling**, eight lines under the game's 128-line program limit; a program above the ceiling carries a reviewed exemption that says why, and one within two lines of the limit states its count. This document is a current line-pressure inventory, not a historical snapshot of only the original shared-input modules.

## Current line-pressure inventory

`validation/validators/validate_ic10.py` is authoritative for the 120-line project ceiling. `docs/SCRIPT_INDEX.md` is regenerated directly from source plus `data/source_manifest.json` metadata and records the exact current line count for every deployable program, so this document deliberately does not duplicate a second manually synchronized line-count table. Repetitive thin directory adapters are emitted from `data/directory_adapter_specs.json` rather than maintained as copy-pasted source.

For review, treat programs at **117 lines or more** as tight: they have at most three lines of framework headroom. The release evidence under `validation/evidence/` captures the validator result for the exact packaged source.

The three inventory figures quoted in prose are defined once, in `framework/ic10_line_budget.py`, and `validation/validators/validate_documentation.py` fails any sentence in `CLAUDE.md`, `README.md`, or `docs/DEPLOYMENT.md` that quotes a different number (issue #164):

- **programs** — every IC10 source file under `ic10/`. Release validation requires each to resolve to exactly one deployment family, so this is also the deployable-program count. It is larger than the explicit `scripts` list in `data/source_manifest.json`, whose generated-deployment rules cover whole generated families without naming their files.
- **tight programs** — programs at 117 lines or more.
- **soft-limit exemptions** — programs above the 120-line ceiling. `validation/validators/validate_ic10.py` rejects both an unexempted program over the ceiling and an exemption whose program is within it, so this count is the size of `SOFT_LIMIT_EXEMPTIONS` on any tree that validates.

An exemption says why its program is over the ceiling, not how close to the game's 128-line limit it sits, and the first edit to find out was the one that spent the last line (issue #176). The validator now prints each exempt program's headroom under 128 beside it, and an exemption within two lines of the limit states the count in its reason (`126 of 128 lines`); a stated count the tree no longer matches fails, so every edit that moves one of those programs moves the statement with it. `framework/ic10_line_budget.py` defines the margin and the rule.

## Shared-input consolidation results

Physical-resolution logic exists once in `ic10/shared-input/generic_input_resolver_v1_0.ic10`; configuration adds the 61-line `ic10/controller-config/config_input_bridge_v1_0.ic10` for ordinal-to-physical-slot publication.

Diagnostic services also stopped implementing their own Dial/Switch reads:

- `ic10/controller-discovery/controller_selector_v3_0.ic10` is screwless;
- `ic10/diagnostics/console_selector_v1_1.ic10` is screwless;
- `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` is screwless;
- `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10` remains the compact desired-selection publication bridge.

## Redundant peer ABI checks

The largest single reclamation to date came from deleting checks rather than restructuring code. Once the `S0` identity folded the ABI into its hashed name (`docs/ABI_REFERENCE.md`), a consumer's follow-up check of the peer's `S1` could never fail — it restated what the identity had already proven. Removing 106 of them across 74 programs returned **212 lines** and retired 12 soft-limit exemptions, without moving a single service boundary. `validation/validators/validate_service_identity.py` now rejects a new one.

Two neighbouring shapes are *not* redundant and were left alone: a program checking its **own** `S1` (a torn-image guard, since the stack survives reflash) and a version check on a block header away from `S0`, such as Generic Telemetry's `S97`, whose consumers accept a version range.

## Interpretation

The number of programs at 120 lines is intentional evidence of why several service boundaries remain split. Do not merge adjacent services merely to reduce IC count if the combined behavior would cross the 120-line project ceiling, obscure transactional ownership, or make automatic 128-instruction execution preemption harder to reason about.

This is not code golf: the optimization target is **fewer duplicated responsibilities per behavior**, while retaining enough source headroom and explicit publication boundaries for safe maintenance.

One class of line is never headroom worth keeping: an instruction that writes a register nothing in the file reads. `validation/validators/validate_ic10.py` refuses those (issue #160), using the instruction-set signatures to tell a destination from a source, so a "read the whole mailbox into consecutive registers" pattern has to skip the fields the program never consumes. Ten such lines across seven programs went with that rule, two of them in the transform Runtime where the loads were the start of a completion check that had never been finished.
