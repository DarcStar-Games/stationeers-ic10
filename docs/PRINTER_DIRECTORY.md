# Printer Directory

Printer discovery is a native Generic Directory domain. It does not define a printer-specific Host ABI.

## Discovery path

```text
network printers
      |
ic10/printer-directory/printer_directory_adapter_v1_0.ic10
      | DIRECTORY_ADAPTER_ABI_V3
      v
ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10
      v
ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10
      |
      | DirectorySchema.Printer v2
      v
manufacturing consumers
```

The Adapter owns family recognition and live printer-state packing. Generic Bridge/Host infrastructure owns freeze, sorting, exact deduplication, overflow, A/B snapshot publication, and generation semantics.

## DirectorySchema.Printer v2

Each record is three cells:

```text
[ReferenceId, FamilyHash, ProcessorSpec]
```

Capacity remains 64 because the Generic Snapshot Host universally supports width `<=3` and capacity `<=64`.

`ReferenceId` is the exact printer ReferenceId.

`FamilyHash` is also the Recipe Catalog `PartitionKey`:

```text
Printer.Autolathe
Printer.ElectronicsPrinter
Printer.HydraulicPipeBender
Printer.ToolManufactory
Printer.SecurityPrinter
Printer.RocketManufactory
```

There is no separate recipe-partition identity.

## ProcessorSpec

Printer schema v2 replaces the older PrinterStatusSpec encoding with the common manufacturing `ProcessorSpec` shape used by TransformLane selection.

```text
bits 0..7   capability tier
bit 8       Power
bit 9       Busy / Active
bit 10      Error
bit 11      On
bit 12      Lock
bits 13+    reserved in DirectorySchema.Printer
```

The common candidate selector interprets printer capability as a **minimum tier**. A required capability of 2 therefore rejects a tier-1 printer.

### Capabilities

Upgradeable families advertise:

```text
base machine = 1
MKII         = 2
```

Current fixed-capability families:

```text
Security Printer    = 1
Rocket Manufactory  = 1
```

Security recipe metadata may contain a Tier-Two recipe that is not reachable on the current machine. The directory intentionally advertises the machine's usable capability rather than the maximum tier appearing in source recipe data, so normal capability filtering excludes inaccessible work.

## Supported PrefabHash families

The Adapter recognizes current canonical prefab names and retained aliases where the game has historically used more than one name for the same supported family.

Fabricator semantics are deliberately excluded. In particular, `StructureFabricator` never enters this directory.

## Publication

Adapter ABI3 publishes:

```text
S0  31415983
S1  2
S2  HASH("DirectorySchema.Printer")
S3  2
S4  3
S5  64
S6  candidate count
S7  candidate generation
S8  candidate sequence
S9  overflow
S10 snapshot mode = 1
S11 freeze request
S12 freeze acknowledgement
S16.. candidate records
```

Live `Power`, `On`, `Activate`, `Error`, and `Lock` changes alter `ProcessorSpec` and therefore cause the published candidate generation to change. The Generic Bridge freezes one coherent Adapter generation before copying it into the Snapshot Host.

## Relationship to manufacturing execution

Normal Printer Directory v2 deliberately does **not** claim output-slot capacity, because central ReferenceId access is not used for device-slot reads.

Roadmap item 6 adds a separate execution-capacity overlay:

```text
Printer Directory v2
       +
184 Printer Execution Bank(s)
       |
185 Printer Execution Directory Adapter
       v
DirectorySchema.PrinterExecution v1
[PrinterReferenceId, FamilyHash, ProcessorSpec]
```

The execution overlay reuses this directory's exact printer identity, FamilyHash, capability, and live logic state. It adds only locally verified output occupancy/reservation state plus the Execution Bank pin index. See `docs/MANUFACTURING_SCHEDULER.md`.

## Deployment

For ordinary discovery:

1. deploy `ic10/printer-directory/printer_directory_adapter_v1_0.ic10`;
2. deploy one `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10`;
3. deploy one dedicated `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`;
4. connect Bridge `d0 -> Printer Adapter`, `d1 -> Snapshot Host`;
5. consumers use the Snapshot Host and require `DirectorySchema.Printer` version 2.

For scheduled printing, keep this path running and additionally deploy the PrinterExecution overlay described in `docs/MANUFACTURING_SCHEDULER.md`.

## Validation

`tests/test_printer_directory.py` verifies:

- all six supported families;
- FamilyHash agreement with the Recipe Catalog generator;
- ProcessorSpec capability and Power/Busy/Error/On/Lock bits;
- Security/Rocket fixed capabilities;
- Fabricator exclusion;
- retained prefab aliases;
- live-state generation changes;
- 64-record capacity;
- explicit overflow on candidate 65 without splitting records.

`validation/validators/validate_directory_contracts.py` additionally proves Printer is schema v2 and that PrinterExecution consumes it as its source directory.
