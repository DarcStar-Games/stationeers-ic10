# Async Request Standard

`ASYNC_REQUEST_V1` is the reusable framework rule for request/response work that can span ticks. It is a protocol, not a dedicated IC housing: each service reuses its existing request/state/result cells and applies the same publication ordering.

## Core rule

The caller writes the complete request payload first and writes `RequestToken` last. A consumer never interprets request-specific state, error, or result cells until the callee has published the matching request identity.

Two profiles are supported.

### LIVE_CURRENT

Use when progress state is meaningful before terminal completion.

```text
caller: payload ... -> RequestToken LAST
callee: InitialState -> Error=0 -> CurrentToken=RequestToken LAST
later:  State/Error may change while CurrentToken remains unchanged
reader: require CurrentToken == ExpectedToken before reading State/Error
```

The callee must publish the matching `CurrentToken` even when the accepted request is invalid and immediately faults. Otherwise the caller can wait forever for identity that will never arrive. Validation may happen after the initial state/token publication; an invalid request then transitions to a fault state under that same token.

### TERMINAL_RESPONSE

Use when only completion/result is externally useful.

```text
caller: payload ... -> RequestToken LAST
callee: Result/Status ... -> ResponseToken=RequestToken LAST
reader: require ResponseToken == ExpectedToken before reading Result/Status
```

A stale result with a nonmatching token is indistinguishable from no result and must be ignored. In prose: the current token equals the expected request token before request-specific state is consumed.

## Invariants

1. Request payload precedes `RequestToken`.
2. For `LIVE_CURRENT`, initial request-specific state/error is reset before `CurrentToken` is published.
3. For `TERMINAL_RESPONSE`, result/status is complete before `ResponseToken` is published.
4. A consumer fences every request-specific read on exact token equality.
5. An accepted invalid request still publishes its identity and a terminal fault; it must not strand the caller.
6. A token identifies one logical request. Retries may reassert the same payload/token when the service contract is idempotent; a new logical request uses a new token.
7. Transaction commit tokens remain separate authority. `ASYNC_REQUEST_V1` fences observation; it does not replace `BANKED_TRANSACTION_V1`, reservation epochs, directory generations, or ownership tokens.
8. Field locations are service-specific. The protocol standardizes semantics and ordering, not absolute stack addresses.

## Current framework users

`LIVE_CURRENT` is used where progress is meaningful while work is in flight: Multi Material Allocator, Material Vending/Stacker Feeder, SDB/Stacker Feeder, Generic Material Transform Runtime, Transform/Print Candidate Executors, Transform/Print Job Drivers, Generic Print Runtime, and the Manufacturing Driver Router surface. Material Transfer Executor consumes Feeder status only after Feeder `CurrentToken` matches the active grant epoch.

`TERMINAL_RESPONSE` covers Controller/Console selectors, pressure reservation/routing services, Generic Config Host and every Config Policy response, Recipe Catalog Lookup, Multi Reservation Stager, Generic Job Store, manufacturing candidate/readiness/capacity services, Print Material Resolver, the per-pin Printer Execution Bank request streams, Generic Snapshot Directory command/ack, Generic Directory Adapter freeze/ack handshakes, ITEM split-reservation Selector/Allocator/Releaser, and reserved LArRE movement. Console selection has two independent terminal streams (desired selection and automatic advance); a consumer that depends on the resolved console requires both streams to be settled.

Transform Profile View is not itself an async-request service; it is a continuously published snapshot. Readiness therefore fences it with the selected `TransformType` echo plus its publication generation before accepting Admission/Resolver generations. Directory snapshot generations, bank revisions, reservation/build epochs, and ownership tokens likewise remain their own authorities rather than being relabeled as async request tokens.

The reference semantics are in `framework/async_request.py`; reviewed membership lives in `data/stack_envelope_declarations.json`; static conformance checks are in `validation/validators/validate_async_request_contracts.py`; adversarial execution checks are in `tests/test_async_request.py`. Adding a new request/handled-generation pair must add both its `LIVE_CURRENT` or `TERMINAL_RESPONSE` contract check and its reviewed participation entry instead of introducing an unregistered handshake.

### Item storage request chains

`ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` is a `TERMINAL_RESPONSE` service. `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` is its serialized client and publishes every SCAN/MOVE/RECOVER payload before the Cargo RequestToken; it consumes status/quantity only after the exact Cargo ResponseToken matches. The Item Reservation Selector, Item Reservation Allocator, Resource Reservation Releaser, and reserved LArRE move client are likewise `TERMINAL_RESPONSE`. `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` is `LIVE_CURRENT`, matching the existing feeder contract.

Async identity is not reservation authority: physical movement additionally requires owner ReferenceId/epoch and the committed live Endpoint PublicationGeneration. Native LArRE motion/hand state and SDB inventory precision remain physical specialization.
