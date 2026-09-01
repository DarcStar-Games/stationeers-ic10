# Generic Directory Standard

## Purpose

Directories represent **live/discovered entities**. Catalogs represent durable schema-defined data. Both use versioned schemas and coherent publication, but directory membership is expected to change as devices appear, disappear, or change health.

The current directory architecture has one discovery boundary and two generic publication modes:

```text
Domain Adapter
   |
   | DIRECTORY_ADAPTER_ABI_V3
   v
169 Generic Directory Adapter Bridge
   |
   v
166 Generic Snapshot Directory Host
```

or, for persistent identity-indexed membership:

```text
Domain Adapter
   |
   | DIRECTORY_ADAPTER_ABI_V3
   v
167 Generic Registry Directory Host
```

Canonical schema metadata lives in `data/directory_schemas.json`. There are **no domain-specific directory magic compatibility facades** in the current baseline.

## Directory Adapter ABI3

Adapters own their candidate stack and never write directly into Host storage.
ABI3 publishes the common stack header at `S0..S7`, so the payload starts at `S8`
and candidate records at `S18`.

| Cell | Meaning |
|---:|---|
| S0 | AdapterMagic = `HASH("DirectoryAdapter.v3")` |
| S1 | AdapterABI = `3` |
| S2 | CapabilityMask = `49` (`HAS_SCHEMA` + `HAS_GENERATION` + `HAS_ASYNC_REQUEST_V1`) |
| S3 | SchemaId = `HASH("<DirectorySchema.X>.v<version>")` |
| S7 | CandidateGeneration, the common publication fence |
| S10 | EntryWidth |
| S11 | Capacity |
| S12 | CandidateCount |
| S13 | sequence; odd while rebuilding, even when stable |
| S14 | overflow; nonzero means the candidate set is incomplete |
| S15 | mode: `1 SNAPSHOT`, `2 REGISTRY` |
| S16 | freeze request token; `0` releases |
| S17 | freeze acknowledgement token; stable while frozen |
| S18.. | packed complete candidate records |

`S3` is the only schema identity an adapter publishes. Both hosts fold too, so a
schema and its version are one exact comparison everywhere in the framework.

Publication lifecycle:

```text
S13 -> odd
S14 -> 0
scan domain devices
write complete records only
S12 -> candidate count
S13 -> even
S7  -> next candidate generation LAST
```

The generation moved to last because `S7` is the common header fence: a generic
reader that knows nothing about directories can snapshot it, read, and re-check
it. The `S13` sequence still marks a rebuild in progress, and the freeze
handshake below still provides multi-tick coherence.

A consumer that spans yields writes a nonzero token to S16 and waits until S17 matches. The Adapter acknowledges only after its current rebuild is complete, then stops rebuilding until S16 returns to zero. This guarantees one coherent candidate generation across multi-tick Bridge/Registry reads.

Adapters may reject a source snapshot rather than publish derived records when that source is incomplete or incoherent. In particular, Pressure Grid Link discovery refuses an overflowed Controller directory and snapshots PressureTransfer telemetry generation around topology reads.

## Snapshot Host ABI1

`ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` publishes one canonical generic snapshot ABI:

```text
S0      GenericSnapshotDirectoryMagic = GenericSnapshotDirectoryHost.v1
S1      ABI = 1
S2      CapabilityMask = 32 (HAS_ASYNC_REQUEST_V1)
S9      DirectorySchemaId, HASH("<schema>.v<version>")
S11     EntryWidth
S12     Capacity
S14     bridge request generation
S15     acknowledged request generation
S16     command: 1 BEGIN, 2 ADD, 3 COMMIT
S17..   one candidate record during ADD
S20     inactive bank selected during rebuild
S21     staging count
S22     staging overflow
S23     host error/status
S24     active bank: 0=A, 1=B
S25/S26 generation A/B
S27/S28 record count A/B
S29/S30 overflow A/B
S32..   packed A/B banks
```

The Host supports widths 1..3 and capacities up to 64, with at most 192 cells per bank. It owns sorting, exact-record deduplication, complete-record overflow behavior, bank switching, and stable generations.
`S23` is a latched diagnostic error indicator for malformed Host requests; successful snapshot publication does not depend on clearing it, and normal Bridge traffic never intentionally triggers it.

`ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` validates Adapter ABI3 and snapshot mode, acquires the Adapter freeze handshake, captures generation/sequence, copies SchemaId/Version and geometry into the Host, propagates adapter overflow into the staging snapshot, sends complete records, revalidates the frozen generation/sequence before publication, compares the staged result with the active snapshot, and suppresses COMMIT when nothing changed.

A snapshot consumer validates at minimum:

```text
S0  GenericSnapshotDirectoryMagic
S1  ABI
S9  expected DirectorySchemaId, version included
```

Consumers then use the schema-defined width/capacity and the ordinary active-bank/count/generation/overflow fields. A schema mismatch is a hard failure, not a fallback to a previous domain ABI.

## Registry Host ABI3

`ic10/directory-core/generic_registry_directory_host_v2_0.ic10` publishes:

```text
S0   GenericRegistryDirectoryMagic = GenericRegistryDirectoryHost.v3
S1   ABI = 3
S2   CapabilityMask = 33 (HAS_SCHEMA + HAS_ASYNC_REQUEST_V1)
S3   DirectorySchemaId, adapter-assigned folded hash
S16  status/error
S20  published record width
S21  registry capacity
S23  publication sequence; odd while mutating, even when stable
S24  freeze-token counter
S25  last accepted candidate generation
S26  registry publication generation
S64.. registry records
```

The current `DirectorySchema.CatalogStoreNode` registry uses NodeId 1..64 as its identity key. Its published record is six cells:

```text
[ReferenceId, State, UsedCells, AssignmentEpoch, CatalogInstanceId, LastSeenEpoch]
```

The discovery adapter supplies six cells `[NodeId, ReferenceId, State, UsedCells, AssignmentEpoch, CatalogInstanceId]`, deduplicating NodeId before publication and faulting duplicate live Stores. The Registry Host freezes and validates exactly `DirectorySchema.CatalogStoreNode` v1, indexes by NodeId, rejects overflow/incoherence, marks absent previously known nodes MISSING, preserves RETIRED records, and publishes the schema/version with S23 written even LAST. Consumers require S23 even and unchanged around every registry read that can trigger side effects.

## Canonical schemas

`data/directory_schemas.json` currently defines:

### DirectorySchema.Controller

```text
[ControllerType, ReferenceId]
```

Snapshot mode, width 2, capacity 64, sorted by `(ControllerType, ReferenceId)`.

### DirectorySchema.PressureGridLink

```text
[LinkRef, SourceRef, SinkRef]
```

Snapshot mode, width 3, capacity 64.

### DirectorySchema.ResourceEndpoint

```text
[ResourceClass, ResourceType, ReferenceId]
```

Snapshot mode, width 3, capacity 64.

### DirectorySchema.ResourceReservation

```text
[ResourceClass, ResourceType, ReservationReferenceId]
```

Snapshot mode, width 3, capacity 64. `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` discovers coherent Generic Resource Reservation mirrors. This directory identifies reservation candidates; owner ReferenceId/epoch and owner/epoch plus committed semantic Reservation-generation cells remain the mutation authority.

### DirectorySchema.ResourceLink

```text
[ReferenceId]
```

Snapshot mode, width 1, capacity 64.

### DirectorySchema.Printer v2

```text
[ReferenceId, FamilyHash, ProcessorSpec]
```

Snapshot mode, width 3, capacity 64. `FamilyHash` is exactly the Recipe Catalog `PartitionKey`. `ProcessorSpec` uses bits 0..7 for printer tier and bits 8..12 for Power/Busy/Error/On/Lock. `ic10/printer-directory/printer_directory_adapter_v1_0.ic10` is the thin domain adapter; Bridge and Snapshot Host are unchanged. See `docs/PRINTER_DIRECTORY.md`.

### DirectorySchema.TransformLane v1

```text
[RuntimeReferenceId, ProcessorReferenceId, ProcessorSpec]
```

Snapshot mode, width 3, capacity 64. Transform `ProcessorSpec` uses bits 0..7 as capability mask and bits 8..10 as Power/Busy/Error. `ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` discovers generic Transform Runtime lanes.

### DirectorySchema.PrinterExecution v1

```text
[PrinterReferenceId, FamilyHash, ProcessorSpec]
```

Snapshot mode, width 3, capacity 64. `ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` joins Printer v2 against live `ic10/printer-directory/printer_execution_bank_v2_0.ic10` instances and overlays locally verified output capacity plus pin identity. The first field remains the exact PrinterReferenceId so a later reservation can reject a device swap. See `docs/MANUFACTURING_SCHEDULER.md`.

### DirectorySchema.CatalogStoreNode

Registry mode, NodeId-indexed, published width 6, capacity 64.

## Adapter responsibility

A domain adapter should do only domain-specific work:

1. discover candidate devices;
2. validate source service ABI and coherent generation where required;
3. extract one complete schema record;
4. expose it through Adapter ABI2, including the standard freeze request/ack handshake.

It must not implement A/B publication, generic sorting, exact dedupe, registry missing-state persistence, or consumer-specific header emulation.

## Why schema-qualified generic headers are the final contract

The project has no deployed predecessor that requires compatibility with earlier directory wire formats. Carrying separate Controller, Pressure Grid Link, Resource Endpoint, Resource Link, or Catalog Store directory magic values would therefore create permanent duplicate contracts without protecting a real deployment.

The current rule is:

> Directory implementation ABI identifies the generic publication mechanism; DirectorySchemaId/Version identifies record semantics.

Adding ResourceReservation v1, Printer v2, TransformLane v1, or PrinterExecution v1 therefore does not require another bespoke directory ABI.

## Directory vs catalog

Use a directory when membership should change as live entities appear or disappear. Use a catalog when data remains durable after its Loader/source disappears.

A disappearing directory entry and deletion of a catalog item are deliberately different operations.

## Power Reservation snapshot schema

Item 9 adds `DirectorySchema.PowerReservation` v1 through the same Adapter ABI2 -> Bridge -> Generic Snapshot Host path. Records are `[DispatchKey, PolicyId, ReservationReferenceId]`, width 3, capacity 64. The directory orders supply/load policy; Generic Resource Reservation ownership and the Power Allocator epoch remain mutation authority. See `docs/POWER_MANAGEMENT.md`.
