# Generic Config Persistence Standard

This service is the `REVISION_BANK` profile of `BANKED_TRANSACTION_V1`. See `docs/BANKED_TRANSACTION_STANDARD.md` for the shared commit-point, replay, and compatibility invariants used by both configuration persistence and Generic Job state.

The durable configuration format is now reusable and controller-independent.

## Roles

- `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` owns the public Generic Config Host ABI, effective/candidate images, A/B persistence, and transaction publication.
- A controller-specific Config Policy writes schema metadata/defaults into the Host and validates/normalizes candidate images in place.
- Controller runtimes consume only the Host effective image and do not know how persistence works.

The exact same Generic Host script is used for all production families and by the test-only ControllerTest fixture.

## Policy-to-Host private contract

The Policy is wired to the Generic Host on Policy `d0` and writes:

```text
Host S2      ControllerType hash
Host S4      controller schema
Host S10     blockCount 1..4
Host S16..19 block validity masks
Host S12     persistence schema signature
Host S13     Policy generation, written after metadata/defaults
Host S20     Policy response generation
Host S21     Policy result
Host S32..63 default physical image
```

On every new Host request generation `S52`, Policy validates Host candidate `S128..159`, rewrites the valid candidate slots to their canonical normalized form, then publishes `S21` and writes matching `S20` last.

## Persistence signature

The standard signature source string is:

```text
CFG1|<ControllerType>|<schema>|<blockCount>|<mask0>|<mask1>|<mask2>|<mask3>
```

Example PI signature:

```text
HASH("CFG1|ControllerPI|1|2|255|63|0|0")
```

The signature binds a stored bank to the exact storage geometry. Any incompatible type/schema/block/mask change naturally invalidates prior banks.

## Bank layout

```text
S160..191 bank A physical image (32 slots)
S192..223 bank B physical image (32 slots)

S224 A schema signature
S225 A controller config revision
S226 A bank revision / commit token LAST

S227 B schema signature
S228 B controller config revision
S229 B bank revision / commit token LAST
```

Private Host cache:

```text
S24 active bank: -1 none, 0 A, 1 B
S25 newest bank revision
```

## Commit ordering

1. Policy validates and normalizes candidate image.
2. Host selects inactive bank.
3. Host writes destination `bankRevision = 0` first, invalidating it.
4. Host copies the complete fixed-width physical image (`blockCount * 8`).
5. Host rechecks request generation.
6. Host writes schema signature.
7. Host writes controller config revision.
8. Host writes incremented bank revision LAST.
9. Only after durable commit does Host copy candidate to effective image and publish success.

If power is lost anywhere before step 8, the destination bank is invalid and the previous valid bank wins during recovery. If power is lost after step 8, recovery selects the new bank even if the effective mirror was not yet republished.

After recovery, if the outstanding Host request generation already equals the recovered `controllerConfigRevision`, that request crossed the durable commit point. The Host republishes success/response generation directly and **does not** write the same image to the other bank again. This is the common BANKED_TRANSACTION replay rule: pre-commit retries; post-commit acknowledges.

## Recovery

At boot/reflash the Generic Host validates A and B by signature and positive bank revision, chooses the larger bank revision (A wins ties), restores the controller config revision, and reconstructs the effective physical image. If neither bank is valid, Policy defaults are used. The persistence signature is the REVISION_BANK compatibility token; incompatible geometry is never interpreted as current durable configuration.

## Why the footer is only three slots

Earlier designs repeated ControllerType, schema, block count, and all four masks in each footer. That is correct but expensive in IC10 source. The compile-time signature carries the same compatibility decision in one value, leaving a compact footer that can be implemented generically within the 120-line framework soft ceiling.

## Human mental model

Think of the Host as having three levels of configuration state:

1. **Candidate** — “what the user is asking to apply.” It may still be invalid.
2. **Effective** — “what the runtime is currently allowed to use.” It changes only after validation and durable commit succeed.
3. **Durable A/B banks** — “what can be reconstructed after power loss/reflash.” One completed bank is always preferred over an incomplete destination bank.

The Policy sits between candidate and durable state. It decides whether the candidate is semantically legal and rewrites it into canonical form if necessary. The Host then decides whether that accepted canonical image is durably committed.

This separation prevents two common bugs:

- treating “Policy accepted” as equivalent to “persistent commit finished”; and
- letting Runtime read transient candidate data before it is durable.

## Why two banks are enough

A/B persistence is a copy-on-write scheme:

```text
current valid bank = A
next commit target = B

invalidate B revision
write B image + footer metadata
write B revision LAST   <- B becomes committed

next transaction reverses roles
```

At every interruption point before the final token, A remains the newest valid completed bank. After the final token, B is a complete committed bank. Recovery therefore needs only to validate both footers and select the greatest positive bank revision matching the current schema signature.

## Example interrupted commit

Assume bank A revision 10 is valid and a new candidate should become revision 11 in bank B.

If power fails after only half of B's image is written, B still has revision `0` because Host invalidated it before copying. Recovery ignores B and restores A revision 10.

If power fails immediately after B revision 11 is written but before Host republishes its in-memory effective image, recovery sees B as the newest valid bank and reconstructs the new effective image from B. This is why the durable token is written before success/effective publication.

## Schema changes and stored banks

The persistence signature binds a bank to ControllerType, controller schema, block count, and all four masks. A Policy change that alters any of those geometry inputs produces a different signature and naturally invalidates old banks.

Changing validation limits/defaults **without** changing geometry is a separate compatibility decision. If old stored values may no longer be valid, the family author should deliberately decide whether to bump schema/signature semantics, provide migration logic in a future design, or continue accepting the old representation. v1 intentionally does not contain a legacy migration layer.

## Operational debugging checklist

When a controller comes up with unexpected config:

1. Confirm Policy type/schema/masks/signature are the expected values.
2. Inspect A/B footer signatures and positive bank revisions.
3. Identify which valid bank has the newest revision.
4. Compare that bank image with Host effective image after recovery.
5. Check Host effective config revision/generation.
6. Check Runtime is reading the paired Host, not a stale/wrong ReferenceId.
7. If neither bank matches the signature, expect Policy defaults rather than guessing that persistence is corrupt.

The model test `tests/test_persistence_protocol.py` exercises the write-order invariant at 21 simulated interruption points; live-game cases are listed in `docs/FRAMEWORK_HARDENING_TESTS.md`.
