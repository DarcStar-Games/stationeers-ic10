# User Deployment Guide

This is the operator-facing deployment manual for the Stationeers IC10 framework. It answers **what to install, in what order, what stays resident, what can be reclaimed, what healthy state looks like, and how to prove each family in game**. Exact stack-cell ABI layouts remain in `docs/ABI_REFERENCE.md`; architecture rationale remains in the domain documents. This guide is intentionally procedural.

The program inventory under every family is machine-linked to `data/source_manifest.json`. `update_user_deployment_inventory.py` refreshes those blocks, and release validation fails if any deployable IC10 program has no deployment family or if a family disappears from this guide.

## Before deploying anything

1. Use one verified framework release. Do not mix IC10 programs from different archives unless you are deliberately developing the framework.
2. Run `python run_validation.py --resume` before field deployment. Automated PASS means the source/contracts are internally consistent; it does **not** replace Item-12 live evidence.
3. Build from dependencies upward. A consumer should be powered only after its Host/View/Directory/Reservation dependencies publish the expected magic, ABI, schema, and positive generation.
4. Treat all actuator paths as fail-closed. Pumps, transformers, managed loads, LArRE moves, feeders, mixers, furnaces, printers, and generators must remain safe/off until current authority is visible.
5. Use the same semantic `ResourceType`/profile everywhere in a path. Never fix a mismatch by weakening a type or generation check.
6. Set human-owned identities before starting a service when required: for example Catalog Store `NodeId` and commissioned physical topology identifiers.
7. Record physical commissioning through `live_commission.py`. Automated evidence lives under `validation/evidence/`; live evidence is deliberately separate.

## Deployment classes

| Class | Meaning |
|---|---|
| `resident` | Normally stays powered whenever the family is installed. |
| `conditional-resident` | Stays powered only while the optional subsystem/live consumer that uses it is enabled. |
| `commissioning` | Used to discover, select, map, or configure; reclaimable when no live consumer depends on it. |
| `one-shot` | Immutable catalog/import producer; reclaim after durable import is verified. |
| `on-demand` | Diagnostic, lifecycle, migration, recovery, or field-evidence tool; deploy only when needed. |

A program being production-capable does **not** mean it needs a permanent IC housing.

## Common health checks

Before troubleshooting a domain algorithm, verify its substrates in this order:

```text
physical device/network
    -> provider telemetry / endpoint
    -> profile/view identity
    -> directory snapshot (if used)
    -> reservation / plan
    -> final authority fence
    -> actuator
```

For controller families, use:

```text
physical commissioning input
    -> Scanner / Resolver
    -> Editor / Committer
    -> Generic Host durable image
    -> Config Policy
    -> Runtime telemetry
```

A positive generation/token is meaningful only with the expected magic/ABI/schema and after a coherent read. Stale state is not authority.

## Standard family procedure

Every family below uses the same headings. **Programs** is generated. **Wiring and configuration** lists the operator-significant connections; use source header comments and `docs/ABI_REFERENCE.md` for exact stack cells when a service exposes a larger mailbox. **Commissioning proof** names the Item-12 live suite where one exists.

---

## Generic Directory Infrastructure
<!-- DEPLOYMENT_FAMILY:directory-core -->

### Purpose
Use this substrate whenever a domain needs a coherent sorted snapshot or persistent NodeId-indexed registry rather than direct device discovery.

### Use this when
Use this substrate whenever a domain needs a coherent sorted snapshot or persistent NodeId-indexed registry rather than direct device discovery.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:directory-core START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` | `conditional-resident` | Consumes frozen Adapter ABI2 snapshots and drives Generic Snapshot Host BEGIN/ADD/COMMIT. |
| `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` | `conditional-resident` | Generic Registry Directory Host ABI3; consumes Adapter ABI2 and persists NodeId-indexed membership. |
| `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` | `conditional-resident` | Generic sorted A/B Snapshot Directory Host: width 1..3, capacity 64, dedupe/overflow/generation. |
<!-- FAMILY_PROGRAMS:directory-core END -->

### Prerequisites
Working data/network segment and at least one schema-specific Adapter producer. Know whether the consumer expects Snapshot Directory ABI1 (`ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`) or Registry Directory ABI3 (`ic10/directory-core/generic_registry_directory_host_v2_0.ic10`).

### Wiring and configuration
For a snapshot directory use `Adapter -> ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10 -> ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`. The bridge `d0` is the schema adapter and `d1` is the Snapshot Host. For a registry directory, wire the schema-specific adapter/control plane to `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` according to that domain document. Never mix different DirectorySchema IDs in one Host.

### Deployment procedure
1. Program the Host first and verify its magic/ABI. 2. Program the schema Adapter. 3. Program `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` for snapshot directories. 4. Wait for a stable positive generation and expected schema ID/version/entry width. 5. Point selectors/planners at the **Host**, not at the adapter.

### Healthy state
Host publishes expected schema identity, count, overflow flag=0, and a stable generation. Duplicate providers are either deduplicated by the documented identity or make the schema fail closed.

### Commissioning proof
`LG-SHARED-INPUT` covers snapshot coherence/overflow behavior; pressure/manufacturing suites additionally exercise domain directories.

### Common failures
Wrong schema/version, count=0 despite live providers, overflow=1, or generation changing continuously. Check adapter network visibility and do not bypass overflow.

### Reflash / replacement
Reflash the Bridge/Host with consumers able to tolerate no-current-directory. Consumers must wait for a fresh generation; do not preserve an old snapshot as authority manually.

### What can be removed
Keep directory infrastructure only while a live consumer needs discovery. Purely commissioned standalone controllers can reclaim controller-directory housings.

### Technical references
`docs/DIRECTORY_STANDARD.md`, `docs/ARCHITECTURE.md`

---

## Controller Discovery and Selection
<!-- DEPLOYMENT_FAMILY:controller-discovery -->

### Purpose
Use this to discover framework telemetry controllers and resolve a human type/member selection to one exact ReferenceId.

### Use this when
Use this to discover framework telemetry controllers and resolve a human type/member selection to one exact ReferenceId.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:controller-discovery START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/controller-discovery/controller_directory_adapter_v4_0.ic10` | `commissioning` | Publishes Controller Directory Adapter ABI2 candidates; Generic Adapter Bridge + Snapshot Host own publication. |
| `ic10/controller-discovery/controller_selector_v3_0.ic10` | `commissioning` | Directly derives type/member groups from the sorted Generic Controller Directory and resolves one ReferenceId; rejects overflowed discovery. |
<!-- FAMILY_PROGRAMS:controller-discovery END -->

### Prerequisites
Generic Snapshot Directory family and live framework controllers publishing generic telemetry.

### Wiring and configuration
`ic10/controller-discovery/controller_directory_adapter_v4_0.ic10` publishes Controller Directory adapter candidates. Wire it through `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` to a dedicated `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`. Set `ic10/controller-discovery/controller_selector_v3_0.ic10` S2 to the Controller Directory **Host**. The selector derives type/member groups directly; there is no separate Controller Type Catalog.

### Deployment procedure
Bring up the Host/Bridge, then adapter, then selector. Verify controller count and overflow before selecting. Exercise at least two instances of one family to verify member ordering.

### Healthy state
`ic10/controller-discovery/controller_selector_v3_0.ic10` returns the intended exact controller ReferenceId, changes selection coherently, and rejects overflow/incomplete snapshots.

### Commissioning proof
`LG-SHARED-INPUT`.

### Common failures
Selection resolves the wrong member after add/remove, or controller 65+ does not mark overflow. Fix directory identity/snapshot behavior; never hard-code discovered ReferenceIds into generic UI.

### Reflash / replacement
After reflash/replacement, wait for a new directory generation and re-resolve the selection. ReferenceId replacement is expected to invalidate stale selection.

### What can be removed
Reclaim `01/169/166/04` only if no live service (for example PressureDomain arbitration) needs controller discovery.

### Technical references
`docs/DIRECTORY_STANDARD.md`, `docs/COMMISSIONING_QUICKSTART.md`

---

## Controller Configuration and Persistence
<!-- DEPLOYMENT_FAMILY:controller-config -->

### Purpose
Use this shared configuration/persistence path for every configurable controller family.

### Use this when
Use this shared configuration/persistence path for every configurable controller family.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:controller-config START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/controller-config/config_input_bridge_v1_0.ic10` | `commissioning` | Maps Resolver active ordinal/value into Editor physical slots. |
| `ic10/controller-config/generic_config_committer_v1_1.ic10` | `commissioning` | Copies staged values into Host candidate config and starts apply. |
| `ic10/controller-config/generic_config_editor_v1_0.ic10` | `commissioning` | Owns staged config image and Save/Reload/Apply UI state. |
| `ic10/controller-config/generic_config_loader_v1_2.ic10` | `commissioning` | Loads selected Host/Profile state and builds active-ordinal mapping. |
| `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` | `resident` | BANKED_TRANSACTION REVISION_BANK host: owns candidate/effective config, A/B persistence, recovery, and post-commit replay acknowledgement. |
<!-- FAMILY_PROGRAMS:controller-config END -->

### Prerequisites
A family Config Policy, optional Input Profile View, selected controller/Host, and commissioning controls or direct stack editing.

### Wiring and configuration
Each controller gets its own `ic10/controller-config/generic_persistent_config_host_v1_1.ic10`. Runtime/Policy connect to that Host as documented by the family. Commissioning path is `Scanner/Resolver -> Config Input Bridge -> Generic Config Editor -> Generic Config Committer -> Host`; `ic10/controller-config/generic_config_loader_v1_2.ic10` reads Host/Profile into the Editor. The Host owns durable A/B banks.

### Deployment procedure
Power Host + Policy first. Load defaults/current effective image with `ic10/controller-config/generic_config_loader_v1_2.ic10`, edit through `ic10/controller-config/generic_config_editor_v1_0.ic10`, then commit through `ic10/controller-config/generic_config_committer_v1_1.ic10`. Do not directly overwrite durable banks. After Apply, require a new positive effective revision and Policy-valid signature before trusting runtime output.

### Healthy state
Host recovers exactly one complete effective image; invalid candidates never replace it. Runtime telemetry reflects the committed config revision, not partial UI state.

### Commissioning proof
`LG-PERSISTENCE` and `LG-SHARED-INPUT`.

### Common failures
Candidate applies but runtime does not reload, Host reports wrong signature, or a reflash exposes mixed fields. Stop actuator-dependent runtimes and verify Policy signature/masks plus bank revision ordering.

### Reflash / replacement
Reflash/power-loss must recover old-complete or new-complete state. Replaying an already committed request must acknowledge rather than double-commit.

### What can be removed
Keep Host resident with the controller. Editor/Loader/Committer/Input Bridge are commissioning-only unless you intentionally maintain a permanent panel.

### Technical references
`docs/CONFIG_INPUTS.md`, `docs/CONFIG_BLOCKS.md`, `docs/CONFIG_POLICY.md`, `docs/PERSISTENCE_STANDARD.md`

---

## Shared Commissioning Input Panel
<!-- DEPLOYMENT_FAMILY:shared-input -->

### Purpose
Use one physical Dial/Switch/Memory panel to edit configuration and diagnostics across many controller families.

### Use this when
Use one physical Dial/Switch/Memory panel to edit configuration and diagnostics across many controller families.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:shared-input START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/shared-input/generic_input_resolver_v1_0.ic10` | `commissioning` | Resolves logical commissioning controls from Scanner + Profile metadata. |
| `ic10/shared-input/generic_input_scanner_v1_1.ic10` | `commissioning` | Discovers/classifies physical commissioning controls. |
<!-- FAMILY_PROGRAMS:shared-input END -->

### Prerequisites
Input Profile Catalog + configured `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`; physical controls on the scanner network.

### Wiring and configuration
`ic10/shared-input/generic_input_scanner_v1_1.ic10` scans/classifies controls. `ic10/shared-input/generic_input_resolver_v1_0.ic10` reads Scanner + active Input Profile View and resolves logical field/value semantics. Domain bridges consume Resolver output; do not put controller-family special cases in Scanner/Resolver.

### Deployment procedure
Load Input Profile catalog first. Select the desired profile context in `ic10/input-profile-catalog/input_profile_view_v5_0.ic10`, then power Scanner and Resolver. Verify field ordinal, input kind, scaling, enum/switch mapping, and fallback behavior before committing any controller config.

### Healthy state
Changing the Field Dial changes logical field without corrupting staged values; missing preferred control falls back only as documented; generations remain coherent.

### Commissioning proof
`LG-SHARED-INPUT`.

### Common failures
Wrong physical device class, Dial scaling mismatch, removed control leaves stale value, or Resolver advances on stale Profile generation.

### Reflash / replacement
Reflash Scanner/Resolver safely; downstream bridges must require current generations before accepting a new value.

### What can be removed
Reclaim after commissioning if there is no permanent configuration/diagnostic panel.

### Technical references
`docs/SHARED_INPUT_SYSTEM.md`, `docs/COMMISSIONING_QUICKSTART.md`

---

## Diagnostics and Console Mapping
<!-- DEPLOYMENT_FAMILY:diagnostics -->

### Purpose
Use this family to map controller telemetry channels to registered displays without embedding controller-specific display logic.

### Use this when
Use this family to map controller telemetry channels to registered displays without embedding controller-specific display logic.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:diagnostics START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/diagnostics/console_registry_v1_1.ic10` | `commissioning` | Discovers diagnostic consoles and mirror sinks and publishes stable identities. |
| `ic10/diagnostics/console_selector_v1_1.ic10` | `commissioning` | Resolves console ordinals and post-commit advance. |
| `ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10` | `commissioning` | Sets Console circuitboard Mode (HashType) from IC through logic slot set. |
| `ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10` | `commissioning` | Owns diagnostic desired-state/change generations. |
| `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` | `commissioning` | Commits resolved display/controller/channel mappings. |
| `ic10/diagnostics/diagnostic_renderer_v1_1.ic10` | `commissioning` | Renders generic telemetry into committed displays; accepts compatible telemetry ABI revisions. |
| `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10` | `commissioning` | Publishes atomic desired controller/console selection. |
<!-- FAMILY_PROGRAMS:diagnostics END -->

### Prerequisites
Controller Discovery, Shared Input if using the panel, compatible telemetry controllers, and display devices named/enrolled for Console Registry. For circuitboard mirrors, one Logic Memory per mirrored value plus a Console holding the Hash Display or Graph Display circuitboard.

### Wiring and configuration
`ic10/diagnostics/console_registry_v1_1.ic10` discovers consoles and mirror sinks. `ic10/diagnostics/console_selector_v1_1.ic10` selects console ordinal. `ic10/diagnostics/diagnostic_renderer_v1_1.ic10` renders telemetry. `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` owns committed mapping. With the shared panel use `ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10` then `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10` to atomically drive Controller/Console selectors.

### Deployment procedure
Bring up controller and console discovery, then selectors, mapping editor, renderer, then shared-input bridges. Commit one mapping and verify the expected channel appears. Test console advance only after a successful commit.

### Healthy state
Renderer shows current generation-stamped telemetry for the selected exact controller/console; device replacement invalidates stale mapping instead of silently binding another device.

### Commissioning proof
`LG-SHARED-INPUT`, `LG-DIAG-MIRROR`, and `LG-DIAG-HASHMODE`.

### Console circuitboard displays
Hash Display and Graph Display circuitboards read a linked device rather than accepting a written value, so IC10 drives them indirectly. Name a Logic Memory with the Console Registry enrollment tag (`DiagAuto` by default); Registry v1.1 enrols it as a mirror sink because it accepts a written `Setting` without `Mode`/`Color`, and the Renderer writes telemetry into it while skipping presentation properties it cannot set. Link the Console's circuitboard to that Memory once, by hand, during commissioning: the link is player-owned and is not settable from logic. A Hash Display then renders the item thumbnail for a prefab hash written into the Memory, and a Graph Display plots the Memory's `Setting` over time using the Console colour.

Gas Display is deliberately not mirrored. It reads pressure and temperature from a gas-containing device, which a Logic Memory cannot present, so link it directly to the tank or pipe the PressureGrid already manages. No framework program is involved.

`ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10` optionally switches a Hash Display board between `HashType.Prefab` and `HashType.GasLiquid` through the logic slot instructions. Its `S3` counts writes issued and `S4` counts records it could not read; a non-zero `S4` across every record means the slot index or the board itself is wrong. Confirm the slot index in-game before trusting it — see `LG-DIAG-HASHMODE`.

### Common failures
Blank display with healthy controller usually means console registration/mapping mismatch; wrong controller usually means stale directory/selection. Do not bypass exact ReferenceId checks.

### Reflash / replacement
After display/controller replacement, rediscover and recommit mapping. Reflash should not mutate mappings unless a new commit is requested.

### What can be removed
Keep Registry/Renderer only for persistent diagnostics. Mapping UI and shared-input bridges may be reclaimed after setup. Hash Console Mode writes durable device state, so reclaim its housing once every board reads correctly.

### Technical references
`docs/DIAGNOSTIC_INPUTS.md`, `docs/COMMISSIONING_QUICKSTART.md`

---

## PI Controller
<!-- DEPLOYMENT_FAMILY:controller-pi -->

### Purpose
Use for continuous closed-loop proportional/integral control of one process LogicType and one actuator LogicType.

### Use this when
Use for continuous closed-loop proportional/integral control of one process LogicType and one actuator LogicType.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:controller-pi START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/controller-pi/controller_pi_runtime_v1_1.ic10` | `resident` | Continuous PI controller consuming Generic Host effective config. |
| `ic10/controller-pi/pi_config_policy_v1_0.ic10` | `resident` | PI defaults, masks, validation, normalization, signature. |
<!-- FAMILY_PROGRAMS:controller-pi END -->

### Prerequisites
Generic Host + PI Policy and physical process/actuator devices supporting the configured LogicTypes.

### Wiring and configuration
For `ic10/controller-pi/controller_pi_runtime_v1_1.ic10`, `d0` is the process device, `d1` the actuator, and `d2` the Generic Host. `ic10/controller-pi/pi_config_policy_v1_0.ic10` attaches to the same Host per Config Policy wiring. Configure setpoint, gains, output bounds, LogicTypes and inversion/enable fields through the shared config path.

### Deployment procedure
Commission with actuator in a safe operating range. Apply valid config, verify runtime telemetry/config generation, then enable closed-loop control. Step the setpoint modestly and confirm error/output direction before wider use.

### Healthy state
Process value is finite, output remains inside configured bounds, Host generation matches runtime loaded generation, and disabling/faulting drives the documented safe state.

### Commissioning proof
Use `LG-PERSISTENCE` for Host behavior plus a local PI step-response smoke test during commissioning.

### Common failures
Runaway output: disable, verify process/actuator LogicTypes and sign/inversion before tuning gains. NaN/device loss must fail safe.

### Reflash / replacement
Reflash runtime with actuator in safe state; runtime must reload current Host image before resuming control. Host replacement requires explicit config recovery/reapply.

### What can be removed
Keep `08 + 18 + 09` resident. Reclaim commissioning UI/input services.

### Technical references
`README.md`, `docs/COMMISSIONING_QUICKSTART.md`

---

## Sequencer Controller
<!-- DEPLOYMENT_FAMILY:controller-sequencer -->

### Purpose
Use for discrete FILL -> SETTLE -> DRAIN sequences with repeat/complete and timeout safety.

### Use this when
Use for discrete FILL -> SETTLE -> DRAIN sequences with repeat/complete and timeout safety.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:controller-sequencer START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` | `resident` | Fill/settle/drain discrete state-machine controller. |
| `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10` | `resident` | Sequencer defaults, timing/threshold validation, signature. |
<!-- FAMILY_PROGRAMS:controller-sequencer END -->

### Prerequisites
Generic Host + Sequencer Policy; configured sensor/action devices.

### Wiring and configuration
`ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` connects to its physical inputs/outputs and Generic Host according to `docs/SEQUENCER_CONTROLLER.md`; `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10` validates the family configuration. Two action outputs are mutually exclusive by design.

### Deployment procedure
Apply config with conservative thresholds/timeouts. Start one cycle manually, observe FILL, SETTLE, DRAIN, then COMPLETE/repeat. Test each timeout and device-loss path before unattended operation.

### Healthy state
State transitions only on documented conditions, actions are mutually exclusive, timeouts fault safely, telemetry generation remains coherent.

### Commissioning proof
`LG-SEQUENCER`.

### Common failures
Stuck phase indicates threshold direction/input mismatch or no physical progress. Both outputs active is a release blocker.

### Reflash / replacement
Reflash must restart/recover to documented safe behavior, never infer completion from stale phase state.

### What can be removed
Keep Host + Policy + Runtime resident; reclaim shared commissioning tools.

### Technical references
`docs/SEQUENCER_CONTROLLER.md`, `docs/COMMISSIONING_QUICKSTART.md`

---

## PhasePressure Controller
<!-- DEPLOYMENT_FAMILY:controller-phase-pressure -->

### Purpose
Use when a process needs pressure targets derived from current temperature and a selected working-medium phase boundary.

### Use this when
Use when a process needs pressure targets derived from current temperature and a selected working-medium phase boundary.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:controller-phase-pressure START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10` | `resident` | Derives pressure requirements from a coherently committed medium profile; telemetry ABI2. |
| `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10` | `resident` | PhasePressure bounds/factors/mode validation and signature. |
<!-- FAMILY_PROGRAMS:controller-phase-pressure END -->

### Prerequisites
Generic Host + PhasePressure Policy + `114 Resource Profile View` selecting a FLUID/phase medium. For grid integration, Controller Directory and PressureDomain infrastructure.

### Wiring and configuration
`ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10` consumes Host plus coherent Resource Profile View and process temperature/pressure devices as documented. `DirectWrite=1` lets the family own its chamber pressure-setting device; publish-only mode leaves external actuation elsewhere.

### Deployment procedure
Load Resource Profile catalog and select medium first. Apply controller config. Verify HOLD/EVAPORATE/CONDENSE requests over safe test temperatures before connecting a shared PressureDomain arbiter.

### Healthy state
Publishes coherent ABI2 telemetry with medium identity, requested pressure, mode and status; invalid/missing profile suppresses unsafe actuation.

### Commissioning proof
`LG-PHASE-PRESSURE`.

### Common failures
Wrong phase target usually means wrong medium/profile generation or temperature units. Do not substitute a profile by hash without a current View generation.

### Reflash / replacement
After reflash/profile replacement, require current Host and profile generations before direct-write resumes.

### What can be removed
Keep Host + Policy + Runtime resident; Resource Profile View remains resident while the runtime uses it.

### Technical references
`docs/PHASE_PRESSURE_CONTROLLER.md`, `docs/PHASE_MEDIUM_PROFILE.md`

---

## PressureDomain and Request Arbitration
<!-- DEPLOYMENT_FAMILY:pressure-domain -->

### Purpose
Use to combine one or more phase/process pressure requests into a local LOW/HIGH/STORAGE domain target and inventory surface.

### Use this when
Use to combine one or more phase/process pressure requests into a local LOW/HIGH/STORAGE domain target and inventory surface.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:pressure-domain START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` | `resident` | Owns LOW/HIGH target or passive STORAGE envelope; telemetry ABI2. |
| `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10` | `conditional-resident` | Reduces coherent PhasePressure ABI2 requests for one LOW/HIGH domain; rejects directory overflow. |
| `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10` | `resident` | PressureDomain role/bounds validation and signature. |
<!-- FAMILY_PROGRAMS:pressure-domain END -->

### Prerequisites
Controller Directory for request arbitration, medium Resource Profile View, analyzer/network instrumentation, and PressureGrid if routing externally.

### Wiring and configuration
`ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10` reads the live Controller Directory and filters compatible PhasePressure requests. `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` is the domain runtime with its Config Host on `d5`; role-specific physical devices occupy the remaining screws per `docs/PRESSURE_DOMAIN_CONTROLLER.md`. `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10` is its Policy. Attach `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10` and `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` when the domain participates in PressureGrid.

### Deployment procedure
Commission role/medium/bounds first. Verify standby with no requests, then inject compatible and incompatible request producers. For STORAGE verify passive envelope semantics before enabling routes.

### Healthy state
One coherent target is published, bounded by config; incompatible media/modes are ignored; standby and device-loss states fail safe.

### Commissioning proof
`LG-PRESSURE-DOMAIN`.

### Common failures
Unexpected target: inspect request directory membership, medium identity and arbiter filter. No capacity: inspect purity guard/analyzer and inventory P/T/V inputs.

### Reflash / replacement
Reflash domain/arbiter with transfers disabled or guarded; PressureGrid must wait for fresh domain generation and reservation capacity.

### What can be removed
Keep domain runtime/Policy/Host and Inventory/Reservation resident while routed. Arbiter/controller directory may be reclaimed only if no dynamic request producer exists.

### Technical references
`docs/PRESSURE_DOMAIN_CONTROLLER.md`, `docs/PRESSURE_INVENTORY_MODEL.md`

---

## PressureGrid Routing and Transfer
<!-- DEPLOYMENT_FAMILY:pressure-grid -->

### Purpose
Use to reserve and move a typed gas/phase medium across LOW/HIGH/STORAGE domains through direct or bounded multi-hop pump routes.

### Use this when
Use to reserve and move a typed gas/phase medium across LOW/HIGH/STORAGE domains through direct or bounded multi-hop pump routes.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:pressure-grid START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` | `conditional-resident` | One physical pump edge; publishes coherent candidate topology and executes only Guard-authorized leases. |
| `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10` | `conditional-resident` | Purity-gated gas inventory; converts P/T/V/n into molar export/import capacity. |
| `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` | `conditional-resident` | Publishes dimensionless route-ranking weights and candidate budget. |
| `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` | `conditional-resident` | Publishes coherent Pressure Link Adapter ABI2 candidates from the schema-qualified Generic Snapshot Controller directory and Transfer telemetry. |
| `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` | `conditional-resident` | Quotes every selected path hop, then exact-commits one common mol/tick rate. |
| `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` | `conditional-resident` | Incrementally enumerates available 2/3-hop LOW-to-HIGH candidates through STORAGE. |
| `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` | `conditional-resident` | Orchestrates direct reuse -> ranked routed reuse -> fallback before Planner commit. |
| `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` | `conditional-resident` | Medium-specific commit authority; publishes plan epoch only after successful construction. |
| `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` | `conditional-resident` | Route Ranker ABI2: scores using remaining endpoint capacity, lift, hops, storage and throughput. |
| `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` | `conditional-resident` | Route Selector ABI2: bounded reservation-aware candidate comparison. |
| `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` | `conditional-resident` | Stages direct reuse or storage fallback while preserving fallback anti-circulation. |
| `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` | `conditional-resident` | Mirrors one Inventory ABI2 and owns mutable per-build endpoint reservation counters. |
| `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` | `conditional-resident` | Verifies actual analyzer gas ratio against the selected medium profile purity threshold. |
| `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` | `conditional-resident` | Allocator ABI3: non-mutating quote, exact commit, topology-bound staged grants. |
| `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10` | `conditional-resident` | Validates the four-field PressureTransfer schema. |
| `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` | `conditional-resident` | Topology-binds staged grants to Planner commit and consumes each committed epoch at most once. |
<!-- FAMILY_PROGRAMS:pressure-grid END -->

### Prerequisites
Healthy PressureDomains with Inventory/Reservation, Resource Profile View for the medium, Controller/Link directories, and commissioned transfer topology.

### Wiring and configuration
Core chain: `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` publishes one pump edge; `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` exposes links to a snapshot directory. On `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10`, `d0` is Link Directory, `d1` the medium View, and `d2` the Plan Builder. Planning composes the path enumerator, route selector/ranker, path allocator, single-hop builder, and plan builder; `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` owns quote/exact commit; `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` is the final GrantGuard before pump actuation. `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` supplies route-cost weights and `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` purity-gates inventory.

### Deployment procedure
Commission every domain and transfer edge with pumps safe/off. Verify one direct LOW->HIGH route first, then storage fallback, then two/three-hop routing. Only after quote/commit/GrantGuard evidence is healthy should pumps be allowed to actuate.

### Healthy state
Planner commit generation advances only after a complete build; every active transfer has current endpoint reservations and a topology-bound one-shot grant. No route means pumps stay safe/off.

### Commissioning proof
`LG-PRESSURE-CORE`, `LG-PRESSURE-MULTIHOP`, `LG-PRESSURE-COST`.

### Common failures
No route: check medium/profile match, directory overflow, endpoint capacity and route class. Pump acts without current grant or continues after epoch change: stop deployment; that violates a core invariant.

### Reflash / replacement
Reflash planner/allocator/guard in a safe physical state. Old epochs must not reactivate; new actuation requires a fresh complete plan/commit.

### What can be removed
All grid services are conditional-resident while automatic routing is enabled. Cost/route services can be omitted only if the documented simpler topology does not call them.

### Technical references
`docs/PRESSURE_GRID_CONTROLLER.md`, `docs/PRESSURE_RESERVATION_MODEL.md`, `docs/PRESSURE_MULTI_HOP_ROUTING.md`, `docs/PRESSURE_ROUTE_COST_MODEL.md`

---

## Generic ResourceGrid Core
<!-- DEPLOYMENT_FAMILY:resource-grid-core -->

### Purpose
Use these domain-neutral contracts to expose typed resources, links and reservations to planners without teaching planners device-specific storage/topology behavior.

### Use this when
Use these domain-neutral contracts to expose typed resources, links and reservations to planners without teaching planners device-specific storage/topology behavior.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:resource-grid-core START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` | `conditional-resident` | Normalizes PressureDomain Inventory ABI2 into Generic Resource Endpoint ABI1. |
| `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` | `conditional-resident` | Projects a topology-bound PressureTransfer into Generic Resource Link ABI1. |
| `ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10` | `conditional-resident` | Publishes typed Resource Endpoint Adapter ABI2 candidates on its own stack. |
| `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` | `conditional-resident` | Publishes Resource Link Adapter ABI2 candidates on its own stack. |
| `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` | `conditional-resident` | Publishes Generic Resource Reservation mirrors as DirectorySchema.ResourceReservation snapshot candidates. |
| `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` | `conditional-resident` | Clears Generic Resource Reservation ownership only for an exact owner ReferenceId and plan epoch. |
| `ic10/resource-grid-core/resource_reservation_v1_0.ic10` | `conditional-resident` | Mirrors any Generic Resource Endpoint into a domain-neutral reservation surface. |
<!-- FAMILY_PROGRAMS:resource-grid-core END -->

### Prerequisites
A domain-specific Endpoint/Link provider (pressure, material, storage or power) and Generic Directory infrastructure when many providers must be discovered.

### Wiring and configuration
`ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` and `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` adapt pressure providers. `ic10/resource-grid-core/resource_reservation_v1_0.ic10` mirrors an Endpoint into a Reservation surface. The Resource Endpoint, Resource Link, and Resource Reservation directory adapters publish their schemas through the generic directory substrate. `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` releases only exact owner+epoch reservations.

### Deployment procedure
Bring up provider first, then generic adapter/reservation, then directory. Verify ResourceClass, ResourceType, Unit and provider ReferenceId match end to end before connecting a planner.

### Healthy state
Consumers see coherent typed capacity and exact generations; stale/mismatched provider identity fails closed.

### Commissioning proof
Exercised by `LG-PRESSURE-CORE`, `LG-MATERIAL`, `LG-ITEM-STORAGE`, and `LG-POWER` depending specialization.

### Common failures
Type/unit mismatch, stale generation, or duplicate directory record. Fix provider metadata; never make the core infer semantic equivalence.

### Reflash / replacement
Provider replacement changes identity/generation and must force re-resolution/re-reservation.

### What can be removed
Keep only the adapters/directories used by installed domains.

### Technical references
`docs/RESOURCE_GRID_CORE.md`, `docs/DIRECTORY_STANDARD.md`

---

## Generic Catalog Coordinator and Stores
<!-- DEPLOYMENT_FAMILY:catalog-control-plane -->

### Purpose
Use the shared static-catalog substrate for Input Profiles, Resource Profiles, transforms and printer recipes.

### Use this when
Use the shared static-catalog substrate for Input Profiles, Resource Profiles, transforms and printer recipes.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:catalog-control-plane START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` | `conditional-resident` | Coordinator Core ABI3; claims Stores, assigns runtime ordinals, and owns topology/capacity epochs. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` | `conditional-resident` | Publishes Generic Store membership as Directory Adapter ABI2 registry candidates. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` | `on-demand` | Aggregates Store lifecycle counts and used/free/capacity telemetry; marks missing nodes. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10` | `on-demand` | Selectable Store-directory view plus Coordinator aggregate health telemetry. |
| `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` | `on-demand` | Rebinds persisted Stores to a replacement Coordinator with a higher CoordinatorEpoch. |
| `ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` | `on-demand` | Generic Store ABI5 / Coordinator ABI3 inspector for node identity, item capacity, topology, and telemetry. |
| `ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` | `on-demand` | Plans whole-item compaction from DRAINING Stores into compatible live Store capacity. |
| `ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` | `on-demand` | Copies and commits one whole item to reserved destination capacity, then reclaims the source tail. |
| `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` | `on-demand` | Loader Router ABI3; places whole Loader ABI4 items into live unreserved Store capacity. |
| `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` | `on-demand` | Safely retires an empty Store and repairs neighboring topology. |
| `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` | `conditional-resident` | Generic Store ABI5 node with item directory + payload heap; imports runtime-routed relocatable items. |
<!-- FAMILY_PROGRAMS:catalog-control-plane END -->

### Prerequisites
One discoverable catalog network and enough IC housings running `151 Generic Store` for required capacity.

### Wiring and configuration
Resident control plane: the Catalog Coordinator Core, Catalog Store Directory Adapter, Generic Registry Directory Host, and active Generic Catalog Stores. Set each Store `S18 NodeId` to a unique 1..64 before startup. The Catalog Loader Router is on-demand during import. Catalog Inspector plus directory telemetry/view observe health; Catalog Coordinator Recovery recovers a replacement Coordinator; the migration planner/worker move whole items; the Store Retirement Manager retires an empty Store.

### Deployment procedure
1. Start Registry Host/Store Adapter/Coordinator. 2. Start one or more unclaimed Stores with unique NodeIds. 3. Run Loader Router and the desired one-shot loaders. 4. Wait until all items are durably imported and Store health/capacity is stable. 5. Power down loaders and Router. 6. Use migration/recovery only through documented lifecycle states.

### Healthy state
Coordinator owns assignments/topology epoch; Stores report ACTIVE with unique NodeIds and expected used/free capacity; no loader remains partially imported.

### Commissioning proof
Catalog behavior is exercised transitively by `LG-SHARED-INPUT`, `LG-MANUFACTURING`, `LG-MATERIAL`, and resource-profile domain suites.

### Common failures
Duplicate NodeId, incompatible schema/instance, insufficient capacity, DRAINING store with no migration target, or Router progress stalled. Do not manually copy partial catalog records.

### Reflash / replacement
Coordinator replacement uses `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` and a higher epoch. Store contents persist independently; consumers must tolerate temporary lookup unavailability.

### What can be removed
Keep Coordinator + membership directory + Stores resident. Reclaim one-shot loaders. Router and lifecycle/diagnostic services are on-demand.

### Technical references
`docs/CATALOG_COORDINATION.md`, `docs/CATALOG_STORAGE.md`

---

## Input Profile Catalog
<!-- DEPLOYMENT_FAMILY:input-profile-catalog -->

### Purpose
Use to store the logical field descriptions consumed by Shared Input and diagnostics.

### Use this when
Use to store the logical field descriptions consumed by Shared Input and diagnostics.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:input-profile-catalog START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_catalog_loader_01_v4_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` | `conditional-resident` | Selects one Input schema-v3 Store ABI5 catalog context and republishes Generic Input Profile ABI1. |
<!-- FAMILY_PROGRAMS:input-profile-catalog END -->

### Prerequisites
Healthy Catalog control plane and at least one Store with capacity.

### Wiring and configuration
Run the current `ic10/input-profile-catalog/input_profile_catalog_loader_*_v4_0.ic10` set on the catalog network; they need no Store screw. `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` selects a context using Controller/Profile hash fields and republishes Generic Input Profile ABI1.

### Deployment procedure
Run loaders once, verify durable import, reclaim them. For each active panel, configure `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` to the desired context and require positive status/generation before powering Resolver.

### Healthy state
View publishes expected profile identity, masks/descriptors, and positive generation; missing/duplicate context is not treated as a valid profile.

### Commissioning proof
`LG-SHARED-INPUT`.

### Common failures
No profile: check catalog health and selector hash/version. Wrong field geometry: regenerate catalog rather than patching stack cells.

### Reflash / replacement
View reflash simply re-resolves current catalog state; consumers must wait for fresh generation.

### What can be removed
Loaders are one-shot. Keep `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` only while a panel/consumer needs that selected profile.

### Technical references
`docs/SHARED_INPUT_SYSTEM.md`, `docs/CATALOG_SCHEMA.md`

---

## Resource Profile Catalog
<!-- DEPLOYMENT_FAMILY:resource-profile-catalog -->

### Purpose
Use for FLUID, ITEM, POWER, ENERGY and prepared-mixture semantic profiles shared across PressureGrid, MaterialGrid, storage and POWER.

### Use this when
Use for FLUID, ITEM, POWER, ENERGY and prepared-mixture semantic profiles shared across PressureGrid, MaterialGrid, storage and POWER.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:resource-profile-catalog START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10` | `one-shot` | One-shot relocatable ENERGY Resource Profile Loader ABI4 candidate. |
| `ic10/resource-profile-catalog/resource_profile_loader_fluid_00_v4_0.ic10` | `one-shot` | One-shot relocatable Resource Profile Loader ABI4 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_fluid_01_v4_0.ic10` | `one-shot` | One-shot relocatable Resource Profile Loader ABI4 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_00_v4_0.ic10` | `one-shot` | One-shot relocatable Resource Profile Loader ABI4 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_01_v4_0.ic10` | `one-shot` | One-shot relocatable Resource Profile Loader ABI4 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_02_v4_0.ic10` | `one-shot` | One-shot relocatable Resource Profile Loader ABI4 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10` | `one-shot` | One-shot relocatable POWER Resource Profile Loader ABI4 candidate. |
| `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` | `conditional-resident` | Resolves one Resource Profile across runtime-placed Store ABI5 items and republishes View ABI1. |
<!-- FAMILY_PROGRAMS:resource-profile-catalog END -->

### Prerequisites
Catalog control plane with enough Store capacity.

### Wiring and configuration
Run the generated `ic10/resource-profile-catalog/resource_profile_loader_*_v4_0.ic10` set. `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` selects one ResourceClass/ResourceType profile for a live consumer.

### Deployment procedure
Import all loaders, verify profile count/signature, reclaim loaders. Configure a dedicated `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` for each simultaneously required selected resource/medium. Require status=success and positive generation.

### Healthy state
View echoes exact selected class/type and current catalog generation; consumers reject kind/schema mismatch.

### Commissioning proof
Covered by `LG-PHASE-PRESSURE`, `LG-MATERIAL`, `LG-POWER`, and Item-11 cross-domain suites.

### Common failures
Missing profile or wrong semantic alias. Fix generated `data/resource_profiles.json`/catalog, not consumer code.

### Reflash / replacement
Reflash View and wait for re-resolution before resuming dependent actuation.

### What can be removed
Loaders are one-shot; Views are conditional-resident; generic Stores/control plane stay as required.

### Technical references
`docs/RESOURCE_PROFILES.md`, `docs/CATALOG_SCHEMA.md`

---

## Resource Transform Catalog
<!-- DEPLOYMENT_FAMILY:transform-catalog -->

### Purpose
Use to publish capability-based one-to-three-input resource transforms for Arc Furnace, Furnace and Advanced Furnace execution.

### Use this when
Use to publish capability-based one-to-three-input resource transforms for Arc Furnace, Furnace and Advanced Furnace execution.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:transform-catalog START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/transform-catalog/resource_transform_catalog_loader_00_v6_0.ic10` | `one-shot` | One-shot relocatable Transform Loader ABI4 candidate; each transform is a whole self-contained item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_01_v6_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_02_v6_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_03_v6_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_04_v6_0.ic10` | `one-shot` | One-shot relocatable Loader ABI4 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` | `conditional-resident` | Selects a Store ABI5 schema-v4 transform and publishes capability-based variable-input Transform Profile ABI4. |
<!-- FAMILY_PROGRAMS:transform-catalog END -->

### Prerequisites
Catalog control plane plus generated `data/resource_transforms.json` and current transform loaders.

### Wiring and configuration
Run the generated `ic10/transform-catalog/resource_transform_catalog_loader_*_v6_0.ic10` set. `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` selects a TransformType and republishes ABI4 including typed inputs/output, capability and P/T bounds.

### Deployment procedure
Import loaders once. Select representative one-input, two-input and advanced transform profiles and verify descriptors before connecting transform admission/scheduler.

### Healthy state
View returns exact TransformType, bounded input count, output semantics, capability and condition ranges with stable generation.

### Commissioning proof
`LG-MATERIAL` and `LG-MANUFACTURING`.

### Common failures
Profile missing/duplicate or wrong recipe bounds indicates generated catalog drift; regenerate from authoritative data.

### Reflash / replacement
Reflash View safely; current generation must be reacquired before admission.

### What can be removed
Loaders one-shot; View conditional-resident while transforms are used.

### Technical references
`docs/ORE_PROCESSING_TRANSFORMS.md`, `docs/CATALOG_SCHEMA.md`

---

## Printer Recipe Catalog
<!-- DEPLOYMENT_FAMILY:recipe-catalog -->

### Purpose
Use to resolve supported printer-family recipes and exact execution reagent metadata.

### Use this when
Use to resolve supported printer-family recipes and exact execution reagent metadata.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:recipe-catalog START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` | `conditional-resident` | Recipe Lookup v8 ABI3 across runtime-placed Recipe schema-v3 Store ABI5 printer-family partitions. |
| `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` | `conditional-resident` | Resolves exact RecipeHash execution metadata from Recipe schema-v3 stores, including bounded reagent requirements and stale-response echo. |
<!-- FAMILY_PROGRAMS:recipe-catalog END -->

### Prerequisites
Catalog control plane populated with generated Recipe schema-v3 items and live printer family identity where browsing by family.

### Wiring and configuration
`ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` performs family/ordinal Recipe lookup. `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` resolves exact RecipeHash execution metadata including reagent requirements for the scheduler. Recipe Stores are ordinary Generic Catalog Stores; printer discovery is separate.

### Deployment procedure
Import generated recipe data, verify family partitions/counts, then query at least one recipe per supported printer family. Confirm exact RecipeHash and reagent descriptors before enabling PRINT jobs.

### Healthy state
Lookup/profile responses are request-token fenced and family/hash coherent; unsupported recipe fails closed.

### Commissioning proof
`LG-MANUFACTURING`.

### Common failures
Wrong family partition, missing recipe after game update, or reagent alias unresolved. Regenerate Recipe Catalog from current GameData rather than inventing remote printer enumeration.

### Reflash / replacement
Reflash views/lookups and wait for exact response token/current catalog generation.

### What can be removed
Catalog Stores stay resident as static data; lookup/profile services only while consumers need them.

### Technical references
`docs/RECIPE_CATALOG.md`, `docs/CATALOG_SCHEMA.md`

---

## MaterialGrid Transport
<!-- DEPLOYMENT_FAMILY:material-grid -->

### Purpose
Use to move exact ITEM batches from storage/source devices through commissioned Vending/Stacker/Sorter/chute paths to processor import/export endpoints.

### Use this when
Use to move exact ITEM batches from storage/source devices through commissioned Vending/Stacker/Sorter/chute paths to processor import/export endpoints.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:material-grid START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10` | `conditional-resident` | Publishes one exact export slot, such as a Chute Export Bin, as a source-only ITEM Resource Endpoint. |
| `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` | `conditional-resident` | Publishes one processor import slot as a typed ITEM sink endpoint. |
| `ic10/material-grid/material_resource_link_v1_0.ic10` | `conditional-resident` | Publishes a Vending/Stacker/Sorter route as Generic Resource Link ABI1 with native topology identity. |
| `ic10/material-grid/material_transfer_executor_v1_0.ic10` | `conditional-resident` | Executes one Guard-authorized exact material batch and confirms destination import. |
| `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` | `conditional-resident` | Topology-binds committed material grants and consumes invalid epochs. |
| `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` | `conditional-resident` | Uses Vending + Stacker + Logic Sorter to prepare and release an exact routed item quantity. |
<!-- FAMILY_PROGRAMS:material-grid END -->

### Prerequisites
Resource Profile View for the ITEM, source Endpoint, sink Endpoint, Generic Resource Reservations, and commissioned physical route.

### Wiring and configuration
`ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` exposes processor import; `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10` exposes export/chute handoff. `ic10/material-grid/material_resource_link_v1_0.ic10` publishes the physical Material Link. `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` prepares exact Vending/Stacker batches. `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` guards committed topology; `ic10/material-grid/material_transfer_executor_v1_0.ic10` is final execution and confirms destination ImportCount.

### Deployment procedure
Commission source/sink endpoints first, then static route. Test one small exact batch. Verify reservation quote/commit, feeder ready, Guard authority, release, and destination evidence before scaling.

### Healthy state
Exactly requested quantity is prepared and destination evidence increases coherently; topology/resource changes before actuation cancel the move.

### Commissioning proof
`LG-MATERIAL`.

### Common failures
Wrong stack size, chute blockage, stale sorter route, or destination full. Do not report success merely because the feeder emitted an item.

### Reflash / replacement
Reflash feeder/executor with no item in an ambiguous intermediate state; restart must require current reservations/grant.

### What can be removed
Keep active endpoints/link/guard/executor/feeder resident only for automated routes.

### Technical references
`docs/MATERIAL_GRID_FOUNDATION.md`, `docs/MATERIAL_TRANSFER_SYSTEM.md`

---

## Furnace and Material Transform Execution
<!-- DEPLOYMENT_FAMILY:material-transform -->

### Purpose
Use for actual Arc Furnace/Furnace/Advanced Furnace resource transforms after inputs, output capacity and physical P/T conditions are ready.

### Use this when
Use for actual Arc Furnace/Furnace/Advanced Furnace resource transforms after inputs, output capacity and physical P/T conditions are ready.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:material-transform START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` | `conditional-resident` | Runs generic catalog-defined transforms and confirms coherent output growth. |
| `ic10/material-transform/material_transform_admission_v1_0.ic10` | `conditional-resident` | Generic 1..3-input capability-based transform admission: processor conditions and output capacity. |
| `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` | `conditional-resident` | Resolves typed Material Links for every transform input against the exact processor. |
| `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` | `conditional-resident` | Allocator ABI2 atomically commits one common epoch after every input is staged. |
| `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` | `conditional-resident` | Stages 1..3 input reservations and Guard payloads without publishing the commit epoch. |
<!-- FAMILY_PROGRAMS:material-transform END -->

### Prerequisites
Transform Profile View, MaterialGrid input routes/reservations, output Reservation, and compatible live processor.

### Wiring and configuration
`ic10/material-transform/material_transform_admission_v1_0.ic10` checks capability + all declared P/T bounds + output capacity. `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` resolves input links. `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` stages all reservations/guards. `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` commits one shared epoch last. `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` waits for all deliveries, activates the processor, and confirms coherent output growth.

### Deployment procedure
Start with a basic one-input smelt, then a two-input alloy, then an Advanced Furnace recipe. Never bypass Admission to “help” a difficult furnace. For automatic atmosphere preparation add the process-furnace family.

### Healthy state
No processor activation until all input deliveries are visible, output has reserved capacity, and current physical condition bounds pass. Completion requires output evidence.

### Commissioning proof
`LG-MATERIAL`; cross-domain P/T preparation uses `LG-XDOMAIN-FURNACE`.

### Common failures
WAIT/invalid condition means furnace state or capacity is not ready; wrong output evidence means processor/device semantics need investigation.

### Reflash / replacement
Reflash during execution must not reuse stale reservation epochs or infer success from old output state.

### What can be removed
Conditional-resident with manufacturing; can be omitted from installations that only transfer/store items.

### Technical references
`docs/ORE_PROCESSING_TRANSFORMS.md`, `docs/MATERIAL_GRID_FOUNDATION.md`

---

## Printer Discovery and Capacity
<!-- DEPLOYMENT_FAMILY:printer-directory -->

### Purpose
Use to discover supported printer families and overlay exact locally verified output-capacity state for scheduled printing.

### Use this when
Use to discover supported printer families and overlay exact locally verified output-capacity state for scheduled printing.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:printer-directory START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/printer-directory/printer_capacity_client_v2_0.ic10` | `conditional-resident` | Reserves/releases exact selected printers by ReferenceId and advertised execution-bank pin; fails closed on pin swaps. |
| `ic10/printer-directory/printer_directory_adapter_v1_0.ic10` | `conditional-resident` | Publishes six supported printer families as DirectorySchema.Printer v2 Adapter ABI2 candidates with common ProcessorSpec. |
| `ic10/printer-directory/printer_execution_bank_v2_0.ic10` | `conditional-resident` | Locally manages up to six pinned printers so output-slot occupancy can be read safely and Lock can guard one reservation. |
| `ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` | `conditional-resident` | Joins Item-4 Printer Directory metadata with local Execution Bank capacity and publishes exact-Printer PrinterExecution Adapter ABI2 records. |
<!-- FAMILY_PROGRAMS:printer-directory END -->

### Prerequisites
Generic Directory infrastructure, supported printer devices, Recipe Catalog, and output-capacity observation path.

### Wiring and configuration
`ic10/printer-directory/printer_directory_adapter_v1_0.ic10 -> ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10 -> dedicated ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` publishes `DirectorySchema.Printer` v2. For scheduled printing, `ic10/printer-directory/printer_execution_bank_v2_0.ic10` owns the local Printer Execution Bank; its directory adapter publishes `DirectorySchema.PrinterExecution` through the same bridge/host pattern, and `ic10/printer-directory/printer_capacity_client_v2_0.ic10` is the exact-ReferenceId capacity client.

### Deployment procedure
Bring up printer discovery, verify family hash/capability/busy/error fields, then add execution capacity overlay. Replace a printer once during commissioning and confirm exact ReferenceId invalidates old capacity reservation.

### Healthy state
Each candidate has current exact ReferenceId and family/capability; execution overlay reports only locally verified capacity.

### Commissioning proof
`LG-MANUFACTURING`.

### Common failures
Printer visible but unschedulable usually means capacity overlay/Recipe metadata mismatch. Never infer remote slot state from ReferenceId if game Logic cannot read it safely.

### Reflash / replacement
Printer replacement requires rediscovery and fresh capacity reservation; stale ExpectedPrinterRef fails closed.

### What can be removed
Keep discovery/capacity directory resident only while scheduler needs live printers.

### Technical references
`docs/PRINTER_DIRECTORY.md`, `docs/MANUFACTURING_SCHEDULER.md`

---

## Generic Job Store and Command Gateway
<!-- DEPLOYMENT_FAMILY:generic-jobs -->

### Purpose
Use when the installation accepts queued TRANSFORM, PRINT, dependency or POWER policy work.

### Use this when
Use when the installation accepts queued TRANSFORM, PRINT, dependency or POWER policy work.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:generic-jobs START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` | `conditional-resident` | Four-lane Job command arbiter for manufacturing lifecycle, dependency cancellation/creation, and POWER lifecycle requests. |
| `ic10/generic-jobs/generic_job_selector_v3_0.ic10` | `conditional-resident` | Read-only coherent Job Store selector: default TRANSFORM/PRINT mode or exact JobType mode, Priority descending, JobId cursor fairness. |
| `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` | `conditional-resident` | Sole Item-8 Job Store mailbox writer; atomically allocates child slots and checks parent JobId/generation/state. |
| `ic10/generic-jobs/generic_job_store_v1_0.ic10` | `conditional-resident` | BANKED_TRANSACTION SELECTOR_BANK store: 32 Generic Job ABI1 records with Store-owned JobIds, optimistic generation, ABI-gated recovery, and crash-safe publication. |
<!-- FAMILY_PROGRAMS:generic-jobs END -->

### Prerequisites
One Generic Job Store and the domain scheduler(s) that will consume it.

### Wiring and configuration
`ic10/generic-jobs/generic_job_store_v1_0.ic10` is the 32-slot durable Store. `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` is the sole production command-mailbox serializer/arbiter. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` executes Store mutations. `ic10/generic-jobs/generic_job_selector_v3_0.ic10` is the coherent selector used by manufacturing and POWER selection modes.

### Deployment procedure
Start Store, then Gateway/Executor, then selectors/schedulers. Publish a test job through the proper command lane; verify monotonic JobId, state generation, legal lifecycle edges, terminal immutability and reap.

### Healthy state
QueueSequence is coherent/even, stale ExpectedGeneration is rejected, terminal jobs never reopen, and no producer writes the Store mailbox outside the Gateway path.

### Commissioning proof
`LG-JOB-STORE`.

### Common failures
Stuck job: inspect lifecycle state/wait reason and Gateway lane. Duplicate mutation after reflash is a release blocker.

### Reflash / replacement
Store/Gateway recovery must replay deterministic request identity without applying a committed mutation twice.

### What can be removed
Keep only if queued jobs are used. Controller-only deployments do not need Generic Jobs.

### Technical references
`docs/GENERIC_JOB_ABI.md`, `docs/BANKED_TRANSACTION_STANDARD.md`

---

## Manufacturing Scheduler
<!-- DEPLOYMENT_FAMILY:manufacturing -->

### Purpose
Use to schedule queued TRANSFORM and PRINT jobs across live compatible processors while reusing existing material/reservation transactions.

### Use this when
Use to schedule queued TRANSFORM and PRINT jobs across live compatible processors while reusing existing material/reservation transactions.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:manufacturing START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/manufacturing/generic_print_runtime_v2_0.ic10` | `conditional-resident` | Runs a bounded printer batch through native ExecuteRecipe and verifies coherent ExportCount completion. |
| `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` | `conditional-resident` | Generic schema/version-qualified candidate selector for TransformLane or PrinterExecution snapshots; supports tier or bitmask capability matching. |
| `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` | `conditional-resident` | Normalizes TRANSFORM and PRINT domain drivers behind one scheduler-facing result ABI. |
| `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` | `conditional-resident` | Sole production Generic Job lifecycle writer; applies one legal generation-checked edge at a time. |
| `ic10/manufacturing/print_candidate_executor_v2_0.ic10` | `conditional-resident` | Evaluates one print candidate, reserves output capacity, resolves/material-allocates reagents, and launches the generic print runtime. |
| `ic10/manufacturing/print_job_driver_v2_0.ic10` | `conditional-resident` | Resolves Recipe execution shape, iterates PrinterExecution candidates, and normalizes print planning/execution progress for the scheduler. |
| `ic10/manufacturing/print_material_resolver_v1_0.ic10` | `conditional-resident` | Maps Recipe reagent semantics onto reachable MaterialGrid ResourceTypes and publishes transform-compatible multi-input records. |
| `ic10/manufacturing/transform_candidate_executor_v2_0.ic10` | `conditional-resident` | Evaluates and launches one transform candidate through the existing Admission/Resolver/Stager/Allocator/Runtime transaction. |
| `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` | `conditional-resident` | Fences Transform Profile/Admission/Link-Resolver completion to one exact transform candidate request before execution. |
| `ic10/manufacturing/transform_job_driver_v2_0.ic10` | `conditional-resident` | Iterates TransformLane candidates and normalizes transform planning/execution progress for the scheduler. |
| `ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` | `conditional-resident` | Publishes schema-qualified TransformLane Adapter ABI2 candidates with processor identity and common ProcessorSpec. |
<!-- FAMILY_PROGRAMS:manufacturing END -->

### Prerequisites
Generic Jobs, Transform/Recipe catalogs, Item/MaterialGrid, TransformLane and PrinterExecution directories. Add dependency-planning family if automatic deficits are enabled.

### Wiring and configuration
On `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10`, `d0` is Job Gateway, `d1` Generic Job Selector, and `d2` Dependency Gate. `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` routes to Transform and Print drivers. Each driver uses the manufacturing candidate selector plus its corresponding executor. PRINT additionally uses the print material resolver, generic print runtime, Recipe View, and printer-capacity services. `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` provides transform readiness.

### Deployment procedure
Commission direct transforms and printer execution first. Then queue one TRANSFORM and one PRINT job at low priority. Verify selection, WAIT handling, driver execution, VERIFYING and COMPLETE. Add multiple waiters to prove cursor fairness.

### Healthy state
Priority ordering is deterministic, WAIT jobs cannot permanently starve lower runnable work, resource/processor replacement returns to planning/fails closed, completion reflects physical evidence.

### Commissioning proof
`LG-MANUFACTURING`.

### Common failures
Repeated WAIT: inspect requirement/resource/candidate readiness rather than forcing state. Wrong processor means directory/schema/capability mismatch.

### Reflash / replacement
Reflash scheduler/driver with Job Store intact; job lifecycle must resume from durable state without repeating committed physical authority.

### What can be removed
Conditional-resident while automated manufacturing is enabled.

### Technical references
`docs/MANUFACTURING_SCHEDULER.md`

---

## Manufacturing Dependency Planner
<!-- DEPLOYMENT_FAMILY:dependency-planning -->

### Purpose
Use to create bounded child manufacturing work when a parent TRANSFORM/PRINT job has an exact ITEM deficit.

### Use this when
Use to create bounded child manufacturing work when a parent TRANSFORM/PRINT job has an exact ITEM deficit.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:dependency-planning START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10` | `conditional-resident` | Bounds dependency depth to two edges and rejects self/immediate-ancestor producer cycles. |
| `ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10` | `conditional-resident` | Detects terminal/reaped parents and requests reference-aware dependency cleanup through the Planner. |
| `ic10/dependency-planning/dependency_child_creator_v2_0.ic10` | `conditional-resident` | Builds one bounded child Job request after producer, ancestry, output, quantity, and parent-generation checks. |
| `ic10/dependency-planning/dependency_child_validity_v1_0.ic10` | `conditional-resident` | Validates one child Job against live Job Store state and current producer/catalog output semantics. |
| `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` | `conditional-resident` | Read-only active future-output claim view with per-parent claim aggregation and unclaimed-surplus accounting. |
| `ic10/dependency-planning/dependency_plan_builder_v2_0.ic10` | `conditional-resident` | Builds new dependency plans using coherent inventory, active future-output claims, and bounded child creation. |
| `ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10` | `conditional-resident` | Revalidates child identity/state and parent inventory; child completion alone never releases the parent. |
| `ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10` | `conditional-resident` | Read-only release advisor deciding whether a child is still shared/active and therefore cancellable. |
| `ic10/dependency-planning/dependency_plan_store_v2_0.ic10` | `conditional-resident` | Owns 32 committed eight-cell parent/child dependency plan records with ParentJobId commit markers. |
| `ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10` | `conditional-resident` | Existing-plan controller: evaluate, replan, clear-ready, or reference-aware cancel without owning Plan Store mutation. |
| `ic10/dependency-planning/generic_job_monitor_v1_0.ic10` | `conditional-resident` | Coherently resolves one exact JobId and its current state/generation from Generic Job Store. |
| `ic10/dependency-planning/item_producer_resolver_v1_0.ic10` | `conditional-resident` | Generated reverse producer index from ITEM output ResourceType to transform or print producer identity. |
| `ic10/dependency-planning/job_inventory_preflight_v1_0.ic10` | `conditional-resident` | Quotes current ITEM inventory across Resource Reservations and publishes exact/lower-bound deficit plus rolling quote fingerprints. |
| `ic10/dependency-planning/job_requirement_view_v1_0.ic10` | `conditional-resident` | Normalizes TRANSFORM and PRINT job requirements into one bounded ITEM requirement/output view. |
| `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` | `conditional-resident` | Dependency Gate ABI2; only dependency-ready jobs reach the existing Transform/Print Driver Router. |
| `ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10` | `conditional-resident` | Sole Dependency Plan Store mutation coordinator; applies plan upsert/clear and cancellation sequencing. |
| `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10` | `conditional-resident` | Resolves Recipe manufacturing-reagent aliases into canonical ITEM ResourceTypes for dependency planning. |
| `ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10` | `conditional-resident` | New-plan controller: orchestrates bounded plan construction and returns mutation intent to the sole Planner. |
<!-- FAMILY_PROGRAMS:dependency-planning END -->

### Prerequisites
Generic Jobs, ITEM storage/reservation discovery, Transform/Recipe producer metadata, Manufacturing Scheduler.

### Wiring and configuration
The Job Inventory Preflight checks inventory; Item Producer Resolver, Job Requirement View, and Manufacturing Reagent Resolver normalize producer/requirements; Dependency Plan Store persists plans; Manufacturing Dependency Planner is the sole plan-mutation coordinator; the child creator/build/new-plan controllers create new plans/children; plan evaluator/child-validity/existing-plan controller evaluate existing plans; the ancestry guard bounds depth/cycles; claim/release services handle shared claims; Manufacturing Dependency Gate gates parent execution; cleanup flows through Dependency Cancellation Guard and Job Gateway.

### Deployment procedure
Begin with one exact missing intermediate, then two parents sharing a child claim, then a root->child->grandchild chain. Confirm a third edge and cycles are rejected. Complete child output and verify parent does not release until ITEM inventory sees it.

### Healthy state
No second physical inventory ledger exists; FutureQty is logical only. Child COMPLETE alone never authorizes parent execution.

### Commissioning proof
Covered primarily by `LG-MANUFACTURING`, with physical inventory semantics in `LG-ITEM-STORAGE`.

### Common failures
Overproduction/duplicate children usually means claim visibility or inventory exact/lower-bound handling. Never convert lower-bound absence into a definite deficit.

### Reflash / replacement
Reflash Planner/Plan Store/Gateway must preserve or safely reconstruct plan identity; cancellation remains reference-aware.

### What can be removed
Conditional-resident only when automatic dependency expansion is enabled.

### Technical references
`docs/DEPENDENCY_PLANNING.md`

---

## Generic ITEM Reservation and Storage Brokerage
<!-- DEPLOYMENT_FAMILY:item-storage-common -->

### Purpose
Use for coherent split ITEM quotes, exact reservation commits and storage brokerage shared by Vending, LArRE, direct-slot and SDB providers.

### Use this when
Use for coherent split ITEM quotes, exact reservation commits and storage brokerage shared by Vending, LArRE, direct-slot and SDB providers.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:item-storage-common START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` | `conditional-resident` | Commits one coherent ITEM reservation quote with allocator identity, epoch, direction, and mirror-generation fencing. |
| `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` | `conditional-resident` | Read-only bounded ITEM reservation selector; aggregates up to six physical source/destination reservations without mutation. |
<!-- FAMILY_PROGRAMS:item-storage-common END -->

### Prerequisites
Resource Reservation Directory populated by one or more ITEM storage endpoints.

### Wiring and configuration
`ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` performs bounded read-only split quote. `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` exact-commits after semantic generation revalidation. Resource Reservation Directory comes from `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` through Generic Directory infrastructure; `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` releases exact owner+epoch when needed.

### Deployment procedure
Bring up storage endpoints and reservation directory. Quote a quantity spanning two locations, commit it, prove a second owner cannot double-reserve the same capacity, then release by exact owner/epoch.

### Healthy state
Quote reflects current exact/lower-bound semantics; commit rejects stale generation; foreign reservations remain untouched.

### Commissioning proof
`LG-ITEM-STORAGE`.

### Common failures
Short quote with lower-bound SDB provider is not proof of deficit. Commit failure after player mutation is expected and should cause replanning.

### Reflash / replacement
Reflash clients and reacquire current directory/reservation generations. Do not assume old quote remains valid.

### What can be removed
Keep common brokerage resident while automatic storage/manufacturing inventory uses it.

### Technical references
`docs/ITEM_STORAGE_SYSTEM.md`, `docs/RESOURCE_GRID_CORE.md`

---

## Vending ITEM Storage Provider
<!-- DEPLOYMENT_FAMILY:item-storage-vending -->

### Purpose
Use a Vending Machine as an exact ITEM source/provider.

### Use this when
Use a Vending Machine as an exact ITEM source/provider.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:item-storage-vending START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` | `conditional-resident` | Incrementally scans a Vending Machine for one ItemHash and publishes Generic Resource Endpoint ABI1. |
<!-- FAMILY_PROGRAMS:item-storage-vending END -->

### Prerequisites
Resource Profile View selecting the ItemHash; Vending device accessible to the endpoint and, for movement, a MaterialGrid feeder route.

### Wiring and configuration
`ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` incrementally scans the Vending Machine for one ItemHash and publishes Generic Resource Endpoint ABI1. Pair with `ic10/resource-grid-core/resource_reservation_v1_0.ic10` and storage brokerage. For exact export into a chute/processor use `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10`.

### Deployment procedure
Load known stacks, allow a full scan, verify published quantity, remove/add a stack and confirm generation/quantity update, then execute a small reserved withdrawal.

### Healthy state
Endpoint quantity matches the selected item and changes coherently after inventory mutation.

### Commissioning proof
`LG-ITEM-STORAGE` and `LG-MATERIAL`.

### Common failures
Wrong quantity often means scan not complete or wrong ItemHash/profile. Player mutation between quote and pickup must cause stale commit/action failure rather than wrong item movement.

### Reflash / replacement
Reflash endpoint and wait for a new complete scan before treating quantity as exact.

### What can be removed
Resident only while Vending inventory is part of automatic ResourceGrid.

### Technical references
`docs/ITEM_STORAGE_SYSTEM.md`, `docs/MATERIAL_GRID_FOUNDATION.md`

---

## LArRE Storage and Movement
<!-- DEPLOYMENT_FAMILY:item-storage-larre -->

### Purpose
Use LArRE as a first-class mechanism to inspect passive storage slots and physically move whole stacks between lockers/storage and chute import/export systems.

### Use this when
Use LArRE as a first-class mechanism to inspect passive storage slots and physically move whole stacks between lockers/storage and chute import/export systems.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:item-storage-larre START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` | `conditional-resident` | Serialized Cargo LArRE owner for proxy-slot SCAN and whole-stack MOVE_STACK operations. |
| `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` | `conditional-resident` | Publishes LArRE-accessible slot storage as Generic ITEM Resource Endpoint and serializes all LArRE movement requests. |
| `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` | `conditional-resident` | Validates paired source/destination reservations and drives serialized LArRE outbound, inbound, or held-item recovery movement. |
<!-- FAMILY_PROGRAMS:item-storage-larre END -->

### Prerequisites
Powered LArRE with reachable storage geometry, proxy/hand slot semantics verified in game, ITEM Resource Profile, source+destination reservation brokerage.

### Wiring and configuration
On `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`, `d0` is the LArRE device and the service supports SCAN/MOVE/RECOVER. `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` converts scan state into a Generic ITEM Endpoint. `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` is the reserved move client and will not pick up until matching source and destination reservations, owner/epoch, plan generation, and item identity are current.

### Deployment procedure
Commission SCAN first across known occupied/empty slots. Then reserve one source stack and destination capacity, execute one move, deliberately obstruct destination after pickup, and exercise RECOVER. Verify physical origin persistence across same-housing restart.

### Healthy state
Exact ItemHash/Quantity is revalidated immediately before pickup; failure while holding an item is explicit and recoverable; no unreserved move occurs.

### Commissioning proof
`LG-ITEM-STORAGE`.

### Common failures
Status `-6`/held-item state requires recovery, not a blind retry. Wrong proxy slot/TargetSlotIndex semantics must be resolved by live commissioning, never guessed.

### Reflash / replacement
If reflashing during held-item recovery, preserve/use the documented origin record and run RECOVER before accepting new movement requests.

### What can be removed
Keep service/endpoint/move client resident only for automated LArRE storage paths.

### Technical references
`docs/ITEM_STORAGE_SYSTEM.md`

---

## Direct-Slot ITEM Storage
<!-- DEPLOYMENT_FAMILY:item-storage-direct -->

### Purpose
Use for storage devices whose bounded slots are directly readable by IC10 without LArRE.

### Use this when
Use for storage devices whose bounded slots are directly readable by IC10 without LArRE.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:item-storage-direct START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` | `conditional-resident` | Publishes bounded directly readable slot storage as a policy-aware Generic ITEM Resource Endpoint. |
<!-- FAMILY_PROGRAMS:item-storage-direct END -->

### Prerequisites
Confirmed live-game slot semantics for the specific device and ITEM Resource Profile.

### Wiring and configuration
`ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` scans the configured bounded slot range and publishes Generic ITEM Endpoint state. Pair it with the common Resource Reservation, Reservation Directory, Item Reservation Selector, and Item Reservation Allocator infrastructure. Do not use direct `ReferenceId` as a substitute for slot access when the game only permits screw-bound slot reads.

### Deployment procedure
Populate known slots, verify item identity/quantity, mutate a slot, and confirm generation/quantity changes before enabling consumption.

### Healthy state
Only verified readable slots contribute exact quantity/capacity; invalid slot access fails closed.

### Commissioning proof
`LG-ITEM-STORAGE`.

### Common failures
Device has Logic but not slot access: this family is not applicable; use LArRE/Vending/SDB-specific integration instead.

### Reflash / replacement
Reflash requires a fresh bounded scan before exact inventory is trusted.

### What can be removed
Conditional-resident while that direct storage provider is used.

### Technical references
`docs/ITEM_STORAGE_SYSTEM.md`

---

## SDB Silo ITEM Storage
<!-- DEPLOYMENT_FAMILY:item-storage-sdb -->

### Purpose
Use for dedicated SDB Silos where native occupied-stack count cannot be treated as exact total item quantity.

### Use this when
Use for dedicated SDB Silos where native occupied-stack count cannot be treated as exact total item quantity.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:item-storage-sdb START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` | `conditional-resident` | Adapts a dedicated SDB Silo plus Stacker to Material Feeder ABI1 and meters exact requested quantities after FIFO stack export. |
| `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` | `conditional-resident` | Publishes a dedicated SDB Silo as conservative lower-bound ITEM availability/capacity without pretending stack count is exact quantity. |
<!-- FAMILY_PROGRAMS:item-storage-sdb END -->

### Prerequisites
SDB Silo plus export route through Stacker when exact quantity must be delivered.

### Wiring and configuration
`ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` publishes conservative lower-bound availability/capacity. `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` reuses Material Feeder ABI1 with a Stacker to export FIFO SDB stacks and meter the exact requested quantity.

### Deployment procedure
Load known stacks and confirm the endpoint deliberately reports lower-bound semantics. Then request an exact export through `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` and verify Stacker metering/destination evidence.

### Healthy state
Planner never interprets unobserved SDB contents as absent. Exact movement is established at feeder/Stacker execution, not from native Silo `Quantity` alone.

### Commissioning proof
`LG-ITEM-STORAGE`.

### Common failures
Apparent deficit from lower-bound inventory must produce PROBE/wait, not automatic duplicate manufacturing. Wrong FIFO/export semantics require live verification.

### Reflash / replacement
Reflash endpoint preserves no invented exact count; feeder restarts must reacquire current request/reservation state.

### What can be removed
Conditional-resident while SDB participates in automatic ITEM inventory.

### Technical references
`docs/ITEM_STORAGE_SYSTEM.md`

---

## POWER Endpoints, Dispatch, Batteries and Transformers
<!-- DEPLOYMENT_FAMILY:power-grid -->

### Purpose
Use to model POWER producers/consumers/batteries/links, build priority-aware dispatch, reserve exact flows, shed loads and safely actuate transformers/managed loads.

### Use this when
Use to model POWER producers/consumers/batteries/links, build priority-aware dispatch, reserve exact flows, shed loads and safely actuate transformers/managed loads.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:power-grid START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/power-grid/power_battery_endpoint_v1_0.ic10` | `conditional-resident` | Publishes bidirectional battery POWER capacity with reserve, target, rate, and policy-override semantics. |
| `ic10/power-grid/power_consumer_endpoint_v1_0.ic10` | `conditional-resident` | Publishes one managed POWER consumer demand and priority/shedding policy as a Generic Resource Endpoint. |
| `ic10/power-grid/power_dispatch_cycle_v1_0.ic10` | `conditional-resident` | Owns Power PlanStore BEGIN -> sweep -> COMMIT transaction boundaries. |
| `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` | `conditional-resident` | Owns one coherent bounded eight-flow power dispatch plan with odd/even publication fencing. |
| `ic10/power-grid/power_dispatch_sweep_v1_0.ic10` | `conditional-resident` | Sweeps priority-ordered sinks, stages flows, and records shed/critical-shortage state. |
| `ic10/power-grid/power_link_executor_v1_0.ic10` | `conditional-resident` | Sole transformer Setting/On actuator with exact plan, source/sink Reservation, epoch, and Link fencing. |
| `ic10/power-grid/power_link_selector_v1_0.ic10` | `conditional-resident` | Resolves a live source-to-sink POWER Resource Link and computes transformer source-side overhead. |
| `ic10/power-grid/power_load_executor_v1_0.ic10` | `conditional-resident` | Break-before-make actuator for managed consumer and battery On state under committed plan authority. |
| `ic10/power-grid/power_plan_validator_v1_0.ic10` | `conditional-resident` | Revalidates a complete power plan against exact Reservation and Link generations before mutation. |
| `ic10/power-grid/power_producer_endpoint_v1_0.ic10` | `conditional-resident` | Publishes one exact POWER producer/aggregate supply as a Generic Resource Endpoint. |
| `ic10/power-grid/power_reservation_allocator_v1_0.ic10` | `conditional-resident` | Validates, commits, cleans old/orphan epochs, and publishes the active power allocator authority. |
| `ic10/power-grid/power_reservation_committer_v1_0.ic10` | `conditional-resident` | Commits one common POWER reservation epoch with shared-source aggregation and foreign-owner protection. |
| `ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10` | `conditional-resident` | Publishes priority-ordered PowerReservation candidates through Generic Directory Adapter ABI2. |
| `ic10/power-grid/power_sink_flow_builder_v1_0.ic10` | `conditional-resident` | Builds one sink flow, retrying later sources until a compatible physical path is found. |
| `ic10/power-grid/power_sink_selector_v1_0.ic10` | `conditional-resident` | Selects managed POWER sinks in critical/sheddable/charge dispatch order. |
| `ic10/power-grid/power_source_selector_v1_0.ic10` | `conditional-resident` | Selects available POWER sources by preference while accounting for staged use and battery direction. |
| `ic10/power-grid/power_static_link_v1_0.ic10` | `conditional-resident` | Publishes a commissioned passive electrical path as a Generic POWER Resource Link. |
| `ic10/power-grid/power_transformer_link_v1_0.ic10` | `conditional-resident` | Publishes a transformer POWER Resource Link with safe delivered ceiling and source-side self-power overhead. |
<!-- FAMILY_PROGRAMS:power-grid END -->

### Prerequisites
Resource Profile catalog with POWER/ENERGY profiles, commissioned electrical topology, Generic Resource Reservation/Directory substrate.

### Wiring and configuration
Providers are `ic10/power-grid/power_producer_endpoint_v1_0.ic10`, `ic10/power-grid/power_consumer_endpoint_v1_0.ic10`, and `ic10/power-grid/power_battery_endpoint_v1_0.ic10`. Topology uses the static-link and transformer-link services. Discovery/planning is handled by the Power Reservation Directory Adapter, Plan Store, selectors/builders/sweep/cycle, and Plan Validator; reservation commit/allocation is handled by the Power Reservation Committer/Allocator; final physical actuation is split between `ic10/power-grid/power_load_executor_v1_0.ic10` and `ic10/power-grid/power_link_executor_v1_0.ic10`. The active allocator authority is `ACTIVE + PlanGeneration + Epoch` and executors re-fence it immediately before writes.

### Deployment procedure
Commission endpoints with executors disconnected/off. Verify aggregate supply/demand and battery reserve/target. Add links, build a no-shortage plan, then controlled deficit to observe priority/load shedding. Finally exercise transformer overhead and allocator reflash.

### Healthy state
No physical write occurs without current plan+reservation+allocator authority. Critical shortage and shed state are explicit. Battery capacity uses documented one-tick energy headroom semantics.

### Commissioning proof
`LG-POWER`.

### Common failures
Unexpected shedding: inspect endpoint policy/priority, source/link ceiling and transformer overhead. Actuation after allocator withdrawal is a release blocker.

### Reflash / replacement
Reflash allocator revokes ACTIVE, cleans/revalidates current plan into a fresh epoch, then executors may resume. Torn/odd Plan Store publication invalidates safely.

### What can be removed
Conditional-resident while automatic POWER dispatch is enabled.

### Technical references
`docs/POWER_MANAGEMENT.md`, `docs/RESOURCE_GRID_CORE.md`

---

## POWER Policy Jobs
<!-- DEPLOYMENT_FAMILY:power-jobs -->

### Purpose
Use Generic Jobs to apply finite POWER policy changes (for example managed watt cap/shedding policy) through the normal Job lifecycle.

### Use this when
Use Generic Jobs to apply finite POWER policy changes (for example managed watt cap/shedding policy) through the normal Job lifecycle.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:power-jobs START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/power-jobs/power_job_finalize_v1_0.ic10` | `conditional-resident` | Verifies applied POWER policy and advances RUNNING -> VERIFYING -> COMPLETE. |
| `ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10` | `conditional-resident` | Gateway-lane-D lifecycle client returning ExpectedGeneration+1 after successful SET_STATE. |
| `ic10/power-jobs/power_job_policy_apply_v1_0.ic10` | `conditional-resident` | Revalidates a READY POWER job and applies the endpoint policy override/watt cap. |
| `ic10/power-jobs/power_job_policy_verify_v1_0.ic10` | `conditional-resident` | Verifies Generic Resource Reservation coherently reflects the requested POWER policy semantics. |
| `ic10/power-jobs/power_job_prepare_v1_0.ic10` | `conditional-resident` | Prepares POWER jobs through READY, applies policy, and advances to RUNNING. |
| `ic10/power-jobs/power_job_scheduler_v1_0.ic10` | `conditional-resident` | Coordinates selection, prepare/apply, and verify/finalize for finite POWER policy jobs. |
| `ic10/power-jobs/power_policy_target_resolver_v1_0.ic10` | `conditional-resident` | Resolves one PolicyId to exactly one current managed POWER Reservation/Endpoint. |
<!-- FAMILY_PROGRAMS:power-jobs END -->

### Prerequisites
Generic Job family, healthy POWER endpoints/reservations and Power dispatcher.

### Wiring and configuration
The POWER policy target resolver resolves PolicyId to exactly one target; the apply/verify services revalidate Reservation semantics; the lifecycle client advances through Gateway; and the prepare/finalize/scheduler services coordinate execution. Generic selector `ic10/generic-jobs/generic_job_selector_v3_0.ic10` is configured for exact `JobType.POWER`.

### Deployment procedure
Queue one reversible low-risk POWER policy job. Verify READY -> RUNNING -> VERIFYING -> COMPLETE, then a missing target yields `WAIT_RESOURCE` and invalid/ambiguous target yields `FAULT` without starving other jobs.

### Healthy state
Policy Job cannot mutate a different endpoint after replacement; scheduler cursor prevents stuck work from monopolizing selection.

### Commissioning proof
`LG-POWER` and `LG-JOB-STORE`.

### Common failures
Permanent retry of one bad high-priority job indicates incorrect WAIT/FAULT mapping or selector cursor regression.

### Reflash / replacement
Reflash scheduler/client and resume from durable Job state; endpoint policy must be revalidated before further lifecycle advancement.

### What can be removed
Only needed when POWER policy is driven through queued jobs.

### Technical references
`docs/POWER_MANAGEMENT.md`, `docs/GENERIC_JOB_ABI.md`

---

## Prepared Gas Mixture and Thermal Conditioning
<!-- DEPLOYMENT_FAMILY:process-gas-preparation -->

### Purpose
Use to create a prepared two-component gas mixture and/or condition its temperature as a utility resource requested by another process.

### Use this when
Use to create a prepared two-component gas mixture and/or condition its temperature as a utility resource requested by another process.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:process-gas-preparation START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` | `conditional-resident` | Controls a Gas Mixer with temperature-corrected component ratios from a prepared-mixture Resource Profile. |
| `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` | `conditional-resident` | Validates a two-component prepared gas mixture through the existing PurityGuard ABI using Resource Profile kind 5. |
| `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` | `conditional-resident` | Controls a hot/cold Gas Mixer to satisfy a ProcessCondition temperature window without owning pressure-routing authority. |
<!-- FAMILY_PROGRAMS:process-gas-preparation END -->

### Prerequisites
Pure-gas source networks routed/reserved by PressureGrid, prepared-mixture Resource Profile (for example `Fuel.H2O2`), Gas Mixer(s), analyzers and ProcessCondition requester.

### Wiring and configuration
`ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` validates prepared composition using the Resource Profile. `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` controls a two-component Gas Mixer and temperature-corrects source ratios. `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` mixes hot/cold gas to satisfy a requested temperature window. These controllers produce/condition a ResourceType; they do **not** replace PressureGrid routing authority.

### Deployment procedure
Commission mixture ratio with small isolated volumes first. Verify composition at multiple unequal source temperatures. Then enable demand-driven pressure production and thermal conditioning. Confirm mixers shut off immediately when ProcessCondition generation/enable is withdrawn.

### Healthy state
Prepared network reaches requested composition, temperature window and sufficient supply pressure while all inputs remain current; stale condition/profile prevents writes.

### Commissioning proof
`LG-XDOMAIN-FURNACE`, `LG-XDOMAIN-GFG`, `LG-XDOMAIN-RESTART`.

### Common failures
Correct mixer setting but wrong output ratio usually means source temperature/composition assumptions are wrong. Do not hard-code 2:1 volume setting without current gas-state correction.

### Reflash / replacement
Reflash/condition-generation change must converge mixers to safe/off before current authority is reacquired.

### What can be removed
Conditional-resident only for installations that automatically prepare process gases.

### Technical references
`docs/PROCESS_UTILITY_ORCHESTRATION.md`, `docs/RESOURCE_PROFILES.md`

---

## Cross-Domain Furnace Utility Orchestration
<!-- DEPLOYMENT_FAMILY:process-furnace -->

### Purpose
Use to turn a selected Furnace/Advanced Furnace transform P/T requirement into ordinary process-utility demand that PressureGrid can satisfy.

### Use this when
Use to turn a selected Furnace/Advanced Furnace transform P/T requirement into ordinary process-utility demand that PressureGrid can satisfy.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:process-furnace START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` | `conditional-resident` | Projects an Advanced Furnace embedded inlet/outlet pump as ControllerPressureTransfer ABI2 and actuates only under PressureGrid GrantGuard authority. |
| `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` | `conditional-resident` | Publishes Transform-backed ProcessCondition ABI1 pressure/temperature demand for a selected Furnace or Advanced Furnace. |
| `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` | `conditional-resident` | Projects one active ProcessCondition target as standard ControllerPressureDomain ABI2 for ordinary PressureGrid planning. |
<!-- FAMILY_PROGRAMS:process-furnace END -->

### Prerequisites
Material Transform family, selected Transform Profile View, PressureDomain/Grid, prepared gas/thermal utilities as required.

### Wiring and configuration
On `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10`, `d0` is Transform View and `d1` the Furnace/Advanced Furnace; configure semantic medium in `S16`, enable `S17`, and strategy in `S18`. On `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10`, `d0` is ProcessCondition and `d1` the same furnace; it projects the chamber as a PressureDomain. `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` projects Advanced Furnace embedded inlet/outlet pump(s) as normal PressureTransfer and only actuates under GrantGuard.

### Deployment procedure
With material execution disabled, select one transform and observe `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` publish its P/T window. Verify `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` causes ordinary PressureGrid routing. Exercise inlet and outlet independently under GrantGuard. Then allow `ic10/material-transform/material_transform_admission_v1_0.ic10` to independently verify final physical P/T before material execution.

### Healthy state
Manufacturing never directly owns pump/mixer authority. Utility preparation can make the chamber ready, but Transform Admission remains the final independent condition gate.

### Commissioning proof
`LG-XDOMAIN-FURNACE` and `LG-XDOMAIN-RESTART`.

### Common failures
Furnace never becomes ready: inspect ProcessCondition window, medium, supply mixture/temperature, chamber domain inventory and route capacity. Never bypass `ic10/material-transform/material_transform_admission_v1_0.ic10` condition checks.

### Reflash / replacement
Withdrawing/replacing ProcessCondition or GrantGuard immediately before write must keep embedded pumps safe/off. Reflash requires fresh generations.

### What can be removed
Conditional-resident only when automatic furnace atmosphere preparation is desired.

### Technical references
`docs/PROCESS_UTILITY_ORCHESTRATION.md`, `docs/ORE_PROCESSING_TRANSFORMS.md`

---

## Gas Fuel Generator Utility Orchestration
<!-- DEPLOYMENT_FAMILY:process-gfg -->

### Purpose
Use a Gas Fuel Generator as a fuel-backed POWER source whose gas demand is coordinated with PressureGrid rather than manually maintained.

### Use this when
Use a Gas Fuel Generator as a fuel-backed POWER source whose gas demand is coordinated with PressureGrid rather than manually maintained.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:process-gfg START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` | `conditional-resident` | Converts coherent PowerPlan shortage into a fuel ProcessCondition/PressureDomain demand and safely starts/stops a Gas Fuel Generator after fuel and ambient verification. |
<!-- FAMILY_PROGRAMS:process-gfg END -->

### Prerequisites
PowerGrid active Plan Store, prepared fuel Resource Profile/network, PressureGrid path to GFG feed, mixture purity guard and ambient sensor.

### Wiring and configuration
For `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10`, `d0` is GFG, `d1` Power Plan Store, `d2` ambient sensor, and `d3` mixture guard. Configure semantic medium, fuel pressure envelope, shortage trigger, and enable cells documented in `docs/PROCESS_UTILITY_ORCHESTRATION.md`. It converts a coherent power shortage into ProcessCondition demand and starts the GFG only after fuel/ambient verification.

### Deployment procedure
Commission with generator initially disabled. Prove no shortage -> no fuel demand/off. Introduce controlled shortage, verify fuel condition/routing first, then generator start and delivered watts. Remove shortage and verify fuel demand plus generator stop. Record actual watts versus live fuel moles/temperature/mixture.

### Healthy state
Generator cannot start from stale PowerPlan or stale fuel condition; ambient/error/fuel failure shuts it down. No invented watt-to-pressure conversion is used.

### Commissioning proof
`LG-XDOMAIN-GFG` and `LG-XDOMAIN-RESTART`.

### Common failures
Generator fails to start despite shortage: inspect coherent Plan shortage, fuel mixture/purity/pressure and ambient constraints. Do not recursively start an Electrolyzer from the same deficit epoch.

### Reflash / replacement
PowerPlan or ProcessCondition generation change immediately before actuation must suppress start. Reflash converges to safe/off until current authority returns.

### What can be removed
Conditional-resident when fuel-backed automatic generation is enabled.

### Technical references
`docs/PROCESS_UTILITY_ORCHESTRATION.md`, `docs/POWER_MANAGEMENT.md`

---

## Live Commissioning Evidence Tools
<!-- DEPLOYMENT_FAMILY:live-commissioning -->

### Purpose
Use to capture release-bound, machine-readable physical observations for Item 12 without giving test code actuator authority.

### Use this when
Use to capture release-bound, machine-readable physical observations for Item 12 without giving test code actuator authority.

### Deployment class
This family contains the deployment classes shown in its generated program inventory; reclaim rules are summarized below.

### Programs
<!-- FAMILY_PROGRAMS:live-commissioning START -->
| Program | Deployment class | Purpose |
|---|---|---|
| `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` | `on-demand` | Read-only six-source live commissioning snapshot probe with optional stack-generation fencing. |
<!-- FAMILY_PROGRAMS:live-commissioning END -->

### Prerequisites
Current verified release, `data/live_commissioning_cases.json`, `live_commission.py`, and a real Stationeers installation under test.

### Wiring and configuration
`ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` is a read-only six-source snapshot probe. Each descriptor can read a dynamic LogicType or stack cell, with optional generation fencing for coherent stack capture. It must never sit in an actuator path.

### Deployment procedure
Create a session with `live_commission.py`, configure the probe only for cases that benefit from coherent capture, perform the physical action, record PASS/FAIL/BLOCKED plus notes/observations, and verify session fingerprint before accepting it.

### Healthy state
Every accepted observation is bound to exact framework fingerprint and case-catalog hash. Framework/case changes make old evidence stale rather than reusable.

### Commissioning proof
This family is the evidence mechanism for all `LG-*` suites; Item 12 closes only when all required current cases PASS.

### Common failures
Fingerprint mismatch, missing required case, ambiguous physical action or probe used as authority. Mark BLOCKED/FAIL; never edit evidence to manufacture PASS.

### Reflash / replacement
Reflash probe freely; it owns no actuation state. A new framework release requires a new/current session fingerprint.

### What can be removed
Always on-demand. Reclaim after the field session.

### Technical references
`docs/LIVE_COMMISSIONING.md`, `docs/FRAMEWORK_HARDENING_TESTS.md`

---

## Final deployment acceptance

A newly deployed installation is ready for unattended operation only when:

- every installed family above reaches its documented healthy state;
- all actuators remain safe when their final authority is withdrawn;
- no required Directory reports overflow;
- no required catalog lookup/profile is missing or ambiguous;
- persistent configuration survives reflash/power interruption;
- relevant Item-12 live suites are recorded against the exact current release fingerprint;
- any remaining BLOCKED live case is explicitly understood and accepted rather than silently treated as PASS.
