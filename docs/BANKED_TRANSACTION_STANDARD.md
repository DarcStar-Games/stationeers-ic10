# Generic Banked Transaction Standard

`BANKED_TRANSACTION_V1` is the framework-level persistence/publication rule shared by services that need an **old-or-new** result across interruption without requiring one common physical storage layout.

It standardizes transaction semantics, not a runtime IC. The Generic Persistent Config Host and Generic Job Store deliberately remain separate programs because their commit units, access rates, and stack geometries are different.

## Core invariant

Every profile follows the same authority ordering:

```text
identify authoritative old state
choose/write inactive destination
write the complete new payload
write or flip the authority marker LAST
publish response/generation after the commit point
```

At every interruption point recovery must expose exactly one of:

```text
old complete committed state
new complete committed state
```

A partially mixed state is never authoritative.

`banked_transaction.py` is the executable reference model. `tests/test_banked_transaction.py` checks the shared invariants and executes the actual Config Host and Job Store recovery paths.

## Profile 1 — REVISION_BANK

Current user: `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`.

A whole logical image is copied to an inactive bank. Each bank carries compatibility metadata plus a positive monotonically increasing commit revision. The destination revision is invalidated before mutation and written last.

```text
inactive bank revision = 0
write payload
write compatibility signature
write logical/request generation
write positive bank revision LAST   <- commit point
```

Recovery validates compatibility and chooses the valid bank with the greatest positive commit revision. A wins ties.

The Config Host additionally treats `controllerConfigRevision == outstanding RequestGeneration` as evidence that a request crossed the durable commit point. After same-service reflash it republishes the durable image and acknowledges that request instead of writing the same configuration to the opposite bank a second time.

## Profile 2 — SELECTOR_BANK

Current user: `ic10/generic-jobs/generic_job_store_v1_0.ic10`.

Each mutable record has two state banks and a selector naming the authoritative one:

```text
write journal metadata
queue sequence -> odd
write inactive state triplet completely
flip active-bank selector            <- commit point
advance queue generation
queue sequence -> even LAST
publish response generation
```

Recovery uses the journal plus active selector to distinguish a pre-flip interruption from a post-flip interruption:

- selector still equals the old bank -> old state remains authoritative and the request retries;
- selector changed -> new state committed and the request is acknowledged without replaying the mutation.

## Request replay rule

Both profiles use the same logical classification:

```text
RequestGeneration == ResponseGeneration
    -> already acknowledged

RequestGeneration == durable committed logical generation
    -> acknowledge committed request; do not recommit

otherwise
    -> request did not cross this service's commit point; retry/re-evaluate
```

The physical source of the durable logical generation differs by profile. The rule does not require common stack addresses.

## Compatibility rule

A service must prove that durable cells use the layout it expects **before interpreting them**.

- REVISION_BANK Config persistence uses its schema signature to bind ControllerType, schema, block count, and masks to a bank.
- SELECTOR_BANK Job persistence uses Store magic + Store ABI. Any physical Job Store geometry change therefore requires a Store ABI bump. A program must not recover cells written by an incompatible Store ABI.

ABI/schema numbers belonging to unrelated services are not compared or globally synchronized.

## What is intentionally not unified

The standard does **not** require common:

- stack addresses;
- bank sizes;
- mailbox cells;
- policy validation;
- queue seqlocks when a whole-image service does not need one;
- whole-image banks for per-record services;
- per-record generations for configuration images.

Those would be false reuse and would increase IC10 size/coupling.

## Commit-profile matrix

| Property | REVISION_BANK / Config | SELECTOR_BANK / Job |
|---|---|---|
| Commit unit | complete config image | one mutable job-state triplet |
| Authority | positive bank revision | per-slot active-bank selector |
| Compatibility | schema signature | Store magic + ABI |
| Optimistic record generation | not required | required |
| Queue-wide seqlock | not required | required |
| Pre-commit recovery | old bank | old selected state |
| Post-commit recovery | newest valid revision | new selected state |
| Post-commit request replay | acknowledge durable config revision | acknowledge journaled selector flip |

## Extension rule

A future transactional service may adopt one of these profiles or define another profile under the same invariant. It should share the reference theorem and terminology, but it should not reuse an existing runtime IC unless its commit unit and physical geometry genuinely match.
