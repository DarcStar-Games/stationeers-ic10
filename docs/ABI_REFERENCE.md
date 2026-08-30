# ABI Reference — Current Deployment Baseline

Most controller/configuration services remain on **ABI 1**, while hardened transaction services use higher service-local ABIs where their contracts require them. Live directories now share canonical Generic Snapshot Directory ABI1 or Generic Registry Directory ABI3 and are distinguished by `DirectorySchemaId`/version rather than domain-specific magic values. The unified Resource Profile Catalog/View owns phase/material metadata; PressureDomain Inventory and the safety-critical controller telemetry families use ABI2 for coherent publication; the Pressure Reservation Allocator uses ABI3 for quote/exact-commit operation. Consumers require the exact ABI of each dependency; implementation filenames are revisions, not ABI numbers.

`contracts/index.json`, `contracts/protocol_registry.json`, and `contracts/protocols/*.protocol.json` provide the generated machine-readable inventory and typed access schemas behind this human reference. See `docs/SCRIPT_CONTRACTS.md` for regeneration, authority, and compatibility rules.

## Magic values

| Service | Magic | Version cell | ABI |
|---|---:|---:|---:|
| Generic telemetry | `27182818` | `S97` | 1 or 2 by controller family |
| Generic Config Host | `31415928` | `S1` | 1 |
| Generic Input Profile | `31415929` | `S1` | 1 |
| Generic Input Scanner | `31415930` | `S1` | 1 |
| Generic Input Resolver | `31415931` | `S1` | 1 |
| Generic Snapshot Directory Host | `31415981` | `S1` | 1 |
| Generic Registry Directory Host | `31415982` | `S1` | 3 |
| Directory Adapter | `31415983` | `S1` | 3 |
| Generic Job Store | `31415984` | `S1` | 1 |
| PhasePressure Request Arbiter | `31415933` | `S1` | 1 |
| PressureDomain Inventory | `31415935` | `S1` | 2 |
| PressureInventory Reservation | `31415936` | `S1` | 1 |
| Grid Reservation Planner | `31415937` | `S1` | 2 |
| Pressure Reservation Allocator | `31415938` | `S1` | 3 |
| Grid Path Enumerator | `31415940` | `S1` | 2 |
| Grid Path Allocator | `31415941` | `S1` | 1 |
| Grid Single-Hop Builder | `31415942` | `S1` | 1 |
| Grid Plan Builder | `31415943` | `S1` | 1 |
| Grid Route Selector | `31415944` | `S1` | 2 |
| Grid Cost Profile | `31415945` | `S1` | 1 |
| Grid Route Ranker | `31415946` | `S1` | 2 |
| Pressure Medium Purity Guard | `31415947` | `S1` | 1 |
| Pressure Transfer Grant Guard | `31415948` | `S1` | 1 |
| Generic Resource Endpoint | `31415949` | `S1` | 1 |
| Generic Resource Reservation | `31415950` | `S1` | 1 |
| Resource Transform Profile | `31415952` | `S1` | 4 |
| Catalog Store (all static catalogs) | `31415968` | `S1` | 6 |
| Catalog Loader metadata | `31415969` | `S1` | 5 |
| Catalog Coordinator Core | `31415970` | `S1` | 4 |
| Catalog Loader Router | `31415971` | `S1` | 3 |
| Catalog Inspector | `31415972` | `S1` | 4 |
| Catalog Coordinator Directory View | `31415975` | `S1` | 2 |
| Catalog Coordinator Recovery | `31415976` | `S1` | 2 |
| Generic Resource Link | `31415953` | `S1` | 1 |
| Material Reservation Allocator | `31415954` | `S1` | 2 |
| Material Transfer Executor | `31415958` | `S1` | 1 |
| Material Transform Admission | `31415977` | `S1` | 1 |
| Material Transform Link Resolver | `31415978` | `S1` | 1 |
| Multi Reservation Stager | `31415979` | `S1` | 1 |
| Generic Material Transform Runtime | `31415980` | `S1` | 2 |
| Material Transfer Grant Guard | `31415960` | `S1` | 1 |
| Material Vending/Stacker Feeder | `31415961` | `S1` | 1 |
| Resource Profile View | `31415963` | `S1` | 1 |
| Recipe Catalog Lookup | `31415967` | `S1` | 3 |
| Console Registry | `14142136` | `S1` | 1 |
| Controller Selector | `17320508` | `S1` | 2 |
| Console Selector | `17320509` | `S1` | 1 |
| Diagnostic Mapping Editor | `17320510` | `S1` | 1 |
| Diagnostic Input Bridge | `17320511` | `S1` | 1 |
| Diagnostic Selector Bridge | `17320512` | `S1` | 1 |
| Diagnostic Renderer | `16180339` | `S1` | 1 |
| Hash Console Mode | `17320513` | `S1` | 1 |
| Generic Config Editor | `22360680` | `S1` | 1 |
| Config Input Bridge | `22360681` | `S1` | 1 |
| Stack Cell Monitor | `31416052` | `S1` | 1 |
| Stack Header Reader | `31416067` | `S1` | 1 |
| Catalog Directory Telemetry | `31416068` | `S1` | 1 |
| Catalog Item Migration Planner | `31416069` | `S1` | 1 |
| Catalog Store Retirement Manager | `31416070` | `S1` | 1 |
| Catalog Item Migration Worker | `31416071` | `S1` | 1 |
| Controller PhasePressure Runtime | `31416060` | `S1` | 1 |
| Controller PI Runtime | `31416061` | `S1` | 1 |
| Controller Sequencer Runtime | `31416062` | `S1` | 1 |
| Controller PressureDomain Runtime | `31416063` | `S1` | 1 |
| Controller PressureTransfer Runtime | `31416064` | `S1` | 1 |
| Embedded PressureTransfer Runtime | `31416065` | `S1` | 1 |
| Process PressureDomain Runtime | `31416066` | `S1` | 1 |
| Stack header extension | `31416054` | `E+1` | 1 |

## Every published header

The table above names the service contracts consumers code against. This block is
generated from `data/script_protocol_headers.json` by
`tools/generate/update_magic_registry.py` and lists **every** header any deployable
program publishes, so a magic cannot exist without being registered here. A program
appears twice when it publishes both a service header at `S0` and a Generic
Telemetry block at `S96`; a magic appears on several rows when one service contract
has several implementations, which is the generic-instance pattern and requires them
all to publish the same ABI. Eight programs publish no header at all — the config
policies, the config committer and loader, and the directory adapter bridge — and so
appear nowhere below.

<!-- PUBLISHED_HEADERS START -->
| Magic | ABI | Cell | Program | Purpose |
|---:|---:|---:|---|---|
| `14142136` | 1 | `S0` | `ic10/diagnostics/console_registry_v1_1.ic10` | Discovers diagnostic consoles and mirror sinks and publishes stable identities. |
| `16180339` | 1 | `S0` | `ic10/diagnostics/diagnostic_renderer_v1_1.ic10` | Renders generic telemetry into committed displays; accepts compatible telemetry ABI revisions. |
| `17320508` | 2 | `S0` | `ic10/controller-discovery/controller_selector_v3_0.ic10` | Directly derives type/member groups from the sorted Generic Controller Directory and resolves one ReferenceId; rejects overflowed discovery. |
| `17320509` | 1 | `S0` | `ic10/diagnostics/console_selector_v1_1.ic10` | Resolves console ordinals and post-commit advance. |
| `17320510` | 1 | `S0` | `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` | Commits resolved display/controller/channel mappings. |
| `17320511` | 1 | `S0` | `ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10` | Owns diagnostic desired-state/change generations. |
| `17320512` | 1 | `S0` | `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10` | Publishes atomic desired controller/console selection. |
| `17320513` | 1 | `S0` | `ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10` | Sets Console circuitboard Mode (HashType) from IC through logic slot set. |
| `22360680` | 1 | `S0` | `ic10/controller-config/generic_config_editor_v1_0.ic10` | Owns staged config image and Save/Reload/Apply UI state. |
| `22360681` | 1 | `S0` | `ic10/controller-config/config_input_bridge_v1_0.ic10` | Maps Resolver active ordinal/value into Editor physical slots. |
| `27182818` | 2 | `S96` | `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10` | Derives pressure requirements from a coherently committed medium profile; telemetry ABI2. |
| `27182818` | 1 | `S96` | `ic10/controller-pi/controller_pi_runtime_v1_1.ic10` | Continuous PI controller consuming Generic Host effective config. |
| `27182818` | 1 | `S96` | `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` | Fill/settle/drain discrete state-machine controller. |
| `27182818` | 2 | `S96` | `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` | Owns LOW/HIGH target or passive STORAGE envelope; telemetry ABI2. |
| `27182818` | 2 | `S96` | `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` | One physical pump edge; publishes coherent candidate topology and executes only Guard-authorized leases. |
| `27182818` | 2 | `S96` | `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` | Projects an Advanced Furnace embedded inlet/outlet pump as ControllerPressureTransfer ABI2 and actuates only under PressureGrid GrantGuard authority. |
| `27182818` | 2 | `S96` | `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` | Projects one active ProcessCondition target as standard ControllerPressureDomain ABI2 for ordinary PressureGrid planning. |
| `31415928` | 1 | `S0` | `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` | BANKED_TRANSACTION REVISION_BANK host: owns candidate/effective config, A/B persistence, recovery, and post-commit replay acknowledgement. |
| `31415929` | 1 | `S0` | `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` | Selects one Input schema-v3 Store ABI6 catalog context and republishes Generic Input Profile ABI1. |
| `31415930` | 1 | `S0` | `ic10/shared-input/generic_input_scanner_v1_1.ic10` | Discovers/classifies physical commissioning controls. |
| `31415931` | 1 | `S0` | `ic10/shared-input/generic_input_resolver_v1_0.ic10` | Resolves logical commissioning controls from Scanner + Profile metadata. |
| `31415933` | 1 | `S0` | `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10` | Reduces coherent PhasePressure ABI2 requests for one LOW/HIGH domain; rejects directory overflow. |
| `31415935` | 2 | `S0` | `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10` | Purity-gated gas inventory; converts P/T/V/n into molar export/import capacity. |
| `31415936` | 1 | `S0` | `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` | Mirrors one Inventory ABI2 and owns mutable per-build endpoint reservation counters. |
| `31415937` | 2 | `S0` | `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` | Medium-specific commit authority; publishes plan epoch only after successful construction. |
| `31415938` | 3 | `S0` | `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` | Allocator ABI3: non-mutating quote, exact commit, topology-bound staged grants. |
| `31415940` | 2 | `S0` | `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` | Incrementally enumerates available 2/3-hop LOW-to-HIGH candidates through STORAGE. |
| `31415941` | 1 | `S0` | `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` | Quotes every selected path hop, then exact-commits one common mol/tick rate. |
| `31415942` | 1 | `S0` | `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` | Stages direct reuse or storage fallback while preserving fallback anti-circulation. |
| `31415943` | 1 | `S0` | `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` | Orchestrates direct reuse -> ranked routed reuse -> fallback before Planner commit. |
| `31415944` | 2 | `S0` | `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` | Route Selector ABI2: bounded reservation-aware candidate comparison. |
| `31415945` | 1 | `S0` | `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` | Publishes dimensionless route-ranking weights and candidate budget. |
| `31415946` | 2 | `S0` | `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` | Route Ranker ABI2: scores using remaining endpoint capacity, lift, hops, storage and throughput. |
| `31415947` | 1 | `S0` | `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` | Verifies actual analyzer gas ratio against the selected medium profile purity threshold. |
| `31415947` | 1 | `S0` | `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` | Validates a two-component prepared gas mixture through the existing PurityGuard ABI using Resource Profile kind 5. |
| `31415948` | 1 | `S0` | `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` | Topology-binds staged grants to Planner commit and consumes each committed epoch at most once. |
| `31415949` | 1 | `S0` | `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` | Publishes bounded directly readable slot storage as a policy-aware Generic ITEM Resource Endpoint. |
| `31415949` | 1 | `S0` | `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` | Publishes LArRE-accessible slot storage as Generic ITEM Resource Endpoint and serializes all LArRE movement requests. |
| `31415949` | 1 | `S0` | `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` | Publishes a dedicated SDB Silo as conservative lower-bound ITEM availability/capacity without pretending stack count is exact quantity. |
| `31415949` | 1 | `S0` | `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` | Incrementally scans a Vending Machine for one ItemHash and publishes Generic Resource Endpoint ABI1. |
| `31415949` | 1 | `S0` | `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10` | Publishes one exact export slot, such as a Chute Export Bin, as a source-only ITEM Resource Endpoint. |
| `31415949` | 1 | `S0` | `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` | Publishes one processor import slot as a typed ITEM sink endpoint. |
| `31415949` | 1 | `S0` | `ic10/power-grid/power_battery_endpoint_v1_0.ic10` | Publishes bidirectional battery POWER capacity with reserve, target, rate, and policy-override semantics. |
| `31415949` | 1 | `S0` | `ic10/power-grid/power_consumer_endpoint_v1_0.ic10` | Publishes one managed POWER consumer demand and priority/shedding policy as a Generic Resource Endpoint. |
| `31415949` | 1 | `S0` | `ic10/power-grid/power_producer_endpoint_v1_0.ic10` | Publishes one exact POWER producer/aggregate supply as a Generic Resource Endpoint. |
| `31415949` | 1 | `S0` | `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` | Normalizes PressureDomain Inventory ABI2 into Generic Resource Endpoint ABI1. |
| `31415950` | 1 | `S0` | `ic10/resource-grid-core/resource_reservation_v1_0.ic10` | Mirrors any Generic Resource Endpoint into a domain-neutral reservation surface. |
| `31415952` | 4 | `S0` | `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` | Selects a Store ABI6 schema-v4 transform and publishes capability-based variable-input Transform Profile ABI4. |
| `31415953` | 1 | `S0` | `ic10/material-grid/material_resource_link_v1_0.ic10` | Publishes a Vending/Stacker/Sorter route as Generic Resource Link ABI1 with native topology identity. |
| `31415953` | 1 | `S0` | `ic10/power-grid/power_static_link_v1_0.ic10` | Publishes a commissioned passive electrical path as a Generic POWER Resource Link. |
| `31415953` | 1 | `S0` | `ic10/power-grid/power_transformer_link_v1_0.ic10` | Publishes a transformer POWER Resource Link with safe delivered ceiling and source-side self-power overhead. |
| `31415953` | 1 | `S0` | `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` | Projects a topology-bound PressureTransfer into Generic Resource Link ABI1. |
| `31415954` | 2 | `S0` | `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` | Allocator ABI2 atomically commits one common epoch after every input is staged. |
| `31415958` | 1 | `S0` | `ic10/material-grid/material_transfer_executor_v1_0.ic10` | Executes one Guard-authorized exact material batch and confirms destination import. |
| `31415960` | 1 | `S0` | `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` | Topology-binds committed material grants and consumes invalid epochs. |
| `31415961` | 1 | `S0` | `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` | Adapts a dedicated SDB Silo plus Stacker to Material Feeder ABI1 and meters exact requested quantities after FIFO stack export. |
| `31415961` | 1 | `S0` | `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` | Uses Vending + Stacker + Logic Sorter to prepare and release an exact routed item quantity. |
| `31415963` | 1 | `S0` | `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` | Resolves one Resource Profile across runtime-placed Store ABI6 items and republishes View ABI1. |
| `31415967` | 3 | `S0` | `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` | Recipe Lookup v8 ABI3 across runtime-placed Recipe schema-v3 Store ABI6 printer-family partitions. |
| `31415968` | 6 | `S0` | `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` | Generic Store ABI6 node with item directory + payload heap; imports runtime-routed relocatable items. |
| `31415969` | 5 | `S0` | `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `31415969` | 5 | `S0` | `ic10/input-profile-catalog/input_profile_catalog_loader_01_v4_0.ic10` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `31415969` | 5 | `S0` | `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10` | One-shot relocatable ENERGY Resource Profile Loader ABI5 candidate. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_fluid_00_v4_0.ic10` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_fluid_01_v4_0.ic10` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_item_00_v4_0.ic10` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_item_01_v4_0.ic10` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_item_02_v4_0.ic10` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `31415969` | 5 | `S0` | `ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10` | One-shot relocatable POWER Resource Profile Loader ABI5 candidate. |
| `31415969` | 5 | `S0` | `ic10/transform-catalog/resource_transform_catalog_loader_00_v6_0.ic10` | One-shot relocatable Transform Loader ABI5 candidate; each transform is a whole self-contained item. |
| `31415969` | 5 | `S0` | `ic10/transform-catalog/resource_transform_catalog_loader_01_v6_0.ic10` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `31415969` | 5 | `S0` | `ic10/transform-catalog/resource_transform_catalog_loader_02_v6_0.ic10` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `31415969` | 5 | `S0` | `ic10/transform-catalog/resource_transform_catalog_loader_03_v6_0.ic10` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `31415969` | 5 | `S0` | `ic10/transform-catalog/resource_transform_catalog_loader_04_v6_0.ic10` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `31415970` | 4 | `S0` | `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` | Coordinator Core ABI3; claims Stores, assigns runtime ordinals, and owns topology/capacity epochs. |
| `31415971` | 3 | `S0` | `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` | Loader Router ABI3; places whole Loader ABI5 items into live unreserved Store capacity. |
| `31415972` | 4 | `S0` | `ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` | Generic Store ABI6 / Coordinator ABI4 inspector for node identity, item capacity, topology, and telemetry. |
| `31415975` | 2 | `S0` | `ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10` | Selectable Store-directory view plus Coordinator aggregate health telemetry. |
| `31415976` | 2 | `S0` | `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` | Rebinds persisted Stores to a replacement Coordinator with a higher CoordinatorEpoch. |
| `31415977` | 1 | `S0` | `ic10/material-transform/material_transform_admission_v1_0.ic10` | Generic 1..3-input capability-based transform admission: processor conditions and output capacity. |
| `31415978` | 1 | `S0` | `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` | Resolves typed Material Links for every transform input against the exact processor. |
| `31415979` | 1 | `S0` | `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` | Stages 1..3 input reservations and Guard payloads without publishing the commit epoch. |
| `31415980` | 2 | `S0` | `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` | Runs generic catalog-defined transforms and confirms coherent output growth. |
| `31415981` | 1 | `S0` | `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` | Generic sorted A/B Snapshot Directory Host: width 1..3, capacity 64, dedupe/overflow/generation. |
| `31415982` | 3 | `S0` | `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` | Generic Registry Directory Host ABI3; consumes Adapter ABI2 and persists NodeId-indexed membership. |
| `31415983` | 3 | `S0` | `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` | Publishes Generic Store membership as Directory Adapter ABI3 registry candidates. |
| `31415983` | 3 | `S0` | `ic10/controller-discovery/controller_directory_adapter_v4_0.ic10` | Publishes Controller Directory Adapter ABI3 candidates; Generic Adapter Bridge + Snapshot Host own publication. |
| `31415983` | 3 | `S0` | `ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` | Publishes schema-qualified TransformLane Adapter ABI2 candidates with processor identity and common ProcessorSpec. |
| `31415983` | 3 | `S0` | `ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10` | Publishes priority-ordered PowerReservation candidates through Generic Directory Adapter ABI3. |
| `31415983` | 3 | `S0` | `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` | Publishes coherent Pressure Link Adapter ABI2 candidates from the schema-qualified Generic Snapshot Controller directory and Transfer telemetry. |
| `31415983` | 3 | `S0` | `ic10/printer-directory/printer_directory_adapter_v1_0.ic10` | Publishes six supported printer families as DirectorySchema.Printer v2 Adapter ABI2 candidates with common ProcessorSpec. |
| `31415983` | 3 | `S0` | `ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` | Joins Item-4 Printer Directory metadata with local Execution Bank capacity and publishes exact-Printer PrinterExecution Adapter ABI2 records. |
| `31415983` | 3 | `S0` | `ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10` | Publishes typed Resource Endpoint Adapter ABI2 candidates on its own stack. |
| `31415983` | 3 | `S0` | `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` | Publishes Resource Link Adapter ABI2 candidates on its own stack. |
| `31415983` | 3 | `S0` | `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` | Publishes Generic Resource Reservation mirrors as DirectorySchema.ResourceReservation snapshot candidates. |
| `31415984` | 1 | `S0` | `ic10/generic-jobs/generic_job_store_v1_0.ic10` | BANKED_TRANSACTION SELECTOR_BANK store: 32 Generic Job ABI1 records with Store-owned JobIds, optimistic generation, ABI-gated recovery, and crash-safe publication. |
| `31415985` | 1 | `S0` | `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` | Resolves exact RecipeHash execution metadata from Recipe schema-v3 stores, including bounded reagent requirements and stale-response echo. |
| `31415986` | 1 | `S0` | `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` | Serialized Cargo LArRE owner for proxy-slot SCAN and whole-stack MOVE_STACK operations. |
| `31415987` | 1 | `S0` | `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` | Read-only bounded ITEM reservation selector; aggregates up to six physical source/destination reservations without mutation. |
| `31415988` | 1 | `S0` | `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` | Commits one coherent ITEM reservation quote with allocator identity, epoch, direction, and mirror-generation fencing. |
| `31415989` | 1 | `S0` | `ic10/manufacturing/print_material_resolver_v1_0.ic10` | Maps Recipe reagent semantics onto reachable MaterialGrid ResourceTypes and publishes transform-compatible multi-input records. |
| `31415990` | 1 | `S0` | `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` | Clears Generic Resource Reservation ownership only for an exact owner ReferenceId and plan epoch. |
| `31415991` | 1 | `S0` | `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` | Validates paired source/destination reservations and drives serialized LArRE outbound, inbound, or held-item recovery movement. |
| `31415992` | 2 | `S0` | `ic10/manufacturing/print_job_driver_v2_0.ic10` | Resolves Recipe execution shape, iterates PrinterExecution candidates, and normalizes print planning/execution progress for the scheduler. |
| `31415993` | 3 | `S0` | `ic10/generic-jobs/generic_job_selector_v3_0.ic10` | Read-only coherent Job Store selector: default TRANSFORM/PRINT mode or exact JobType mode, Priority descending, JobId cursor fairness. |
| `31415994` | 2 | `S0` | `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` | Normalizes TRANSFORM and PRINT domain drivers behind one scheduler-facing result ABI. |
| `31415995` | 1 | `S0` | `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` | Sole production Generic Job lifecycle writer; applies one legal generation-checked edge at a time. |
| `31415996` | 2 | `S0` | `ic10/printer-directory/printer_execution_bank_v2_0.ic10` | Locally manages up to six pinned printers so output-slot occupancy can be read safely and Lock can guard one reservation. |
| `31415997` | 2 | `S0` | `ic10/printer-directory/printer_capacity_client_v2_0.ic10` | Reserves/releases exact selected printers by ReferenceId and advertised execution-bank pin; fails closed on pin swaps. |
| `31415998` | 1 | `S0` | `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` | Fences Transform Profile/Admission/Link-Resolver completion to one exact transform candidate request before execution. |
| `31416001` | 3 | `S0` | `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` | Four-lane Job command arbiter for manufacturing lifecycle, dependency cancellation/creation, and POWER lifecycle requests. |
| `31416002` | 1 | `S0` | `ic10/dependency-planning/job_requirement_view_v1_0.ic10` | Normalizes TRANSFORM and PRINT job requirements into one bounded ITEM requirement/output view. |
| `31416003` | 1 | `S0` | `ic10/dependency-planning/item_producer_resolver_v1_0.ic10` | Generated reverse producer index from ITEM output ResourceType to transform or print producer identity. |
| `31416004` | 1 | `S0` | `ic10/dependency-planning/generic_job_monitor_v1_0.ic10` | Coherently resolves one exact JobId and its current state/generation from Generic Job Store. |
| `31416005` | 1 | `S0` | `ic10/dependency-planning/job_inventory_preflight_v1_0.ic10` | Quotes current ITEM inventory across Resource Reservations and publishes exact/lower-bound deficit plus rolling quote fingerprints. |
| `31416006` | 2 | `S0` | `ic10/dependency-planning/dependency_child_creator_v2_0.ic10` | Builds one bounded child Job request after producer, ancestry, output, quantity, and parent-generation checks. |
| `31416007` | 2 | `S0` | `ic10/dependency-planning/dependency_plan_store_v2_0.ic10` | Owns 32 committed eight-cell parent/child dependency plan records with ParentJobId commit markers. |
| `31416008` | 2 | `S0` | `ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10` | Revalidates child identity/state and parent inventory; child completion alone never releases the parent. |
| `31416009` | 1 | `S0` | `ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10` | Bounds dependency depth to two edges and rejects self/immediate-ancestor producer cycles. |
| `31416010` | 1 | `S0` | `ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10` | Sole Dependency Plan Store mutation coordinator; applies plan upsert/clear and cancellation sequencing. |
| `31416011` | 2 | `S0` | `ic10/dependency-planning/dependency_plan_builder_v2_0.ic10` | Builds new dependency plans using coherent inventory, active future-output claims, and bounded child creation. |
| `31416012` | 2 | `S0` | `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` | Dependency Gate ABI2; only dependency-ready jobs reach the existing Transform/Print Driver Router. |
| `31416013` | 1 | `S0` | `ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10` | Detects terminal/reaped parents and requests reference-aware dependency cleanup through the Planner. |
| `31416014` | 1 | `S0` | `ic10/dependency-planning/dependency_child_validity_v1_0.ic10` | Validates one child Job against live Job Store state and current producer/catalog output semantics. |
| `31416015` | 1 | `S0` | `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` | Sole Item-8 Job Store mailbox writer; atomically allocates child slots and checks parent JobId/generation/state. |
| `31416016` | 1 | `S0` | `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` | Read-only active future-output claim view with per-parent claim aggregation and unclaimed-surplus accounting. |
| `31416017` | 1 | `S0` | `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10` | Resolves Recipe manufacturing-reagent aliases into canonical ITEM ResourceTypes for dependency planning. |
| `31416018` | 1 | `S0` | `ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10` | Read-only release advisor deciding whether a child is still shared/active and therefore cancellable. |
| `31416019` | 1 | `S0` | `ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10` | Existing-plan controller: evaluate, replan, clear-ready, or reference-aware cancel without owning Plan Store mutation. |
| `31416020` | 1 | `S0` | `ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10` | New-plan controller: orchestrates bounded plan construction and returns mutation intent to the sole Planner. |
| `31416028` | 1 | `S0` | `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` | Owns one coherent bounded eight-flow power dispatch plan with odd/even publication fencing. |
| `31416029` | 1 | `S0` | `ic10/power-grid/power_source_selector_v1_0.ic10` | Selects available POWER sources by preference while accounting for staged use and battery direction. |
| `31416030` | 1 | `S0` | `ic10/power-grid/power_link_selector_v1_0.ic10` | Resolves a live source-to-sink POWER Resource Link and computes transformer source-side overhead. |
| `31416031` | 1 | `S0` | `ic10/power-grid/power_sink_selector_v1_0.ic10` | Selects managed POWER sinks in critical/sheddable/charge dispatch order. |
| `31416032` | 1 | `S0` | `ic10/power-grid/power_sink_flow_builder_v1_0.ic10` | Builds one sink flow, retrying later sources until a compatible physical path is found. |
| `31416033` | 1 | `S0` | `ic10/power-grid/power_dispatch_sweep_v1_0.ic10` | Sweeps priority-ordered sinks, stages flows, and records shed/critical-shortage state. |
| `31416034` | 1 | `S0` | `ic10/power-grid/power_dispatch_cycle_v1_0.ic10` | Owns Power PlanStore BEGIN -> sweep -> COMMIT transaction boundaries. |
| `31416035` | 1 | `S0` | `ic10/power-grid/power_plan_validator_v1_0.ic10` | Revalidates a complete power plan against exact Reservation and Link generations before mutation. |
| `31416036` | 1 | `S0` | `ic10/power-grid/power_reservation_committer_v1_0.ic10` | Commits one common POWER reservation epoch with shared-source aggregation and foreign-owner protection. |
| `31416037` | 1 | `S0` | `ic10/power-grid/power_reservation_allocator_v1_0.ic10` | Validates, commits, cleans old/orphan epochs, and publishes the active power allocator authority. |
| `31416038` | 1 | `S0` | `ic10/power-grid/power_load_executor_v1_0.ic10` | Break-before-make actuator for managed consumer and battery On state under committed plan authority. |
| `31416039` | 1 | `S0` | `ic10/power-grid/power_link_executor_v1_0.ic10` | Sole transformer Setting/On actuator with exact plan, source/sink Reservation, epoch, and Link fencing. |
| `31416041` | 1 | `S0` | `ic10/power-jobs/power_policy_target_resolver_v1_0.ic10` | Resolves one PolicyId to exactly one current managed POWER Reservation/Endpoint. |
| `31416042` | 1 | `S0` | `ic10/power-jobs/power_job_policy_apply_v1_0.ic10` | Revalidates a READY POWER job and applies the endpoint policy override/watt cap. |
| `31416043` | 1 | `S0` | `ic10/power-jobs/power_job_policy_verify_v1_0.ic10` | Verifies Generic Resource Reservation coherently reflects the requested POWER policy semantics. |
| `31416044` | 1 | `S0` | `ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10` | Gateway-lane-D lifecycle client returning ExpectedGeneration+1 after successful SET_STATE. |
| `31416045` | 1 | `S0` | `ic10/power-jobs/power_job_prepare_v1_0.ic10` | Prepares POWER jobs through READY, applies policy, and advances to RUNNING. |
| `31416046` | 1 | `S0` | `ic10/power-jobs/power_job_finalize_v1_0.ic10` | Verifies applied POWER policy and advances RUNNING -> VERIFYING -> COMPLETE. |
| `31416047` | 1 | `S0` | `ic10/power-jobs/power_job_scheduler_v1_0.ic10` | Coordinates selection, prepare/apply, and verify/finalize for finite POWER policy jobs. |
| `31416048` | 1 | `S0` | `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` | Publishes Transform-backed ProcessCondition ABI1 pressure/temperature demand for a selected Furnace or Advanced Furnace. |
| `31416048` | 1 | `S0` | `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` | Converts coherent PowerPlan shortage into a fuel ProcessCondition/PressureDomain demand and safely starts/stops a Gas Fuel Generator after fuel and ambient verification. |
| `31416049` | 1 | `S0` | `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` | Controls a Gas Mixer with temperature-corrected component ratios from a prepared-mixture Resource Profile. |
| `31416050` | 1 | `S0` | `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` | Controls a hot/cold Gas Mixer to satisfy a ProcessCondition temperature window without owning pressure-routing authority. |
| `31416051` | 1 | `S0` | `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` | Read-only six-source live commissioning snapshot probe with optional stack-generation fencing. |
| `31416052` | 1 | `S0` | `ic10/live-commissioning/stack_cell_monitor_v1_0.ic10` | Read-only target IC stack-cell probe with a Logic Memory address selector and visible value mirror. |
| `31416060` | 1 | `S0` | `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10` | Derives pressure requirements from a coherently committed medium profile; telemetry ABI2. |
| `31416061` | 1 | `S0` | `ic10/controller-pi/controller_pi_runtime_v1_1.ic10` | Continuous PI controller consuming Generic Host effective config. |
| `31416062` | 1 | `S0` | `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` | Fill/settle/drain discrete state-machine controller. |
| `31416063` | 1 | `S0` | `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` | Owns LOW/HIGH target or passive STORAGE envelope; telemetry ABI2. |
| `31416064` | 1 | `S0` | `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` | One physical pump edge; publishes coherent candidate topology and executes only Guard-authorized leases. |
| `31416065` | 1 | `S0` | `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` | Projects an Advanced Furnace embedded inlet/outlet pump as ControllerPressureTransfer ABI2 and actuates only under PressureGrid GrantGuard authority. |
| `31416066` | 1 | `S0` | `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` | Projects one active ProcessCondition target as standard ControllerPressureDomain ABI2 for ordinary PressureGrid planning. |
| `31416067` | 1 | `S0` | `ic10/live-commissioning/stack_header_reader_v1_0.ic10` | Read-only common stack header reader: reports a target's identity, ABI, capabilities, and declared fields. |
| `31416068` | 1 | `S0` | `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` | Aggregates Store lifecycle counts and used/free/capacity telemetry; marks missing nodes. |
| `31416069` | 1 | `S0` | `ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` | Plans whole-item compaction from DRAINING Stores into compatible live Store capacity. |
| `31416070` | 1 | `S0` | `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` | Safely retires an empty Store and repairs neighboring topology. |
| `31416071` | 1 | `S0` | `ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` | Copies and commits one whole item to reserved destination capacity, then reclaims the source tail. |
| `31416072` | 2 | `S0` | `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` | Generic schema/version-qualified candidate selector for TransformLane or PrinterExecution snapshots; supports tier or bitmask capability matching. |
| `31416073` | 2 | `S0` | `ic10/manufacturing/transform_candidate_executor_v2_0.ic10` | Evaluates and launches one transform candidate through the existing Admission/Resolver/Stager/Allocator/Runtime transaction. |
| `31416074` | 2 | `S0` | `ic10/manufacturing/print_candidate_executor_v2_0.ic10` | Evaluates one print candidate, reserves output capacity, resolves/material-allocates reagents, and launches the generic print runtime. |
| `31416075` | 2 | `S0` | `ic10/manufacturing/generic_print_runtime_v2_0.ic10` | Runs a bounded printer batch through native ExecuteRecipe and verifies coherent ExportCount completion. |
| `31416076` | 2 | `S0` | `ic10/manufacturing/transform_job_driver_v2_0.ic10` | Iterates TransformLane candidates and normalizes transform planning/execution progress for the scheduler. |
<!-- PUBLISHED_HEADERS END -->

## Catalog Store ABI v6

Magic `31415968`, ABI `6`. It publishes the common header at `S0..S3`: the coordinator assigns the folded `SchemaId` at `S3`, and the instance, coordinator identity, and store-chain pointers moved to `S13`, `S14`, `S21` and `S24`. `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` is the only physical Store program. Human commissioning sets only `S18 NodeId` (1..64); Coordinator ABI4 assigns schema/version/instance, partition, StoreOrdinal, topology, Coordinator identity, and AssignmentEpoch.

Store ABI6 uses a generic item heap rather than schema-specific fixed regions:

```text
S9   LocalItemCount
S16  StoreState
S17  data seqlock; odd mutating, even stable
S19  next item-directory cell
S20  payload heap top
S22  used cells
S23  PartitionKey
S27  in-flight capacity reservation
S29  unreserved free cells
S32.. item directory [ItemBase, ItemCellCount]
...   payload heap grows downward from S511
```

Each item consumes its payload size plus two directory cells. See `docs/CATALOG_STORAGE.md`.

## Catalog Loader metadata ABI v5

Magic `31415969`, ABI `5`. A generated Loader is one-shot, self-clearing, sparse, and **relocatable**. It publishes the common header at `S0..S3` — `CapabilityMask` `1` and `SchemaId` `HASH("<schema>.v<version>")` — then its payload from `S8`:

```text
S8/S9   schema id and version, unfolded for Store ABI6 matching (transitional)
S10     instance      S14 item count        S18 Ready, written LAST
S11     partition     S15 header cells      S19 TargetStoreRef, begins zero
S12     LoaderId      S16 total payload     S20 AssignmentToken, begins zero
S13     kind          S17 signature         S21 next imported item index
S24..   item directory
```

The Router writes `S19`/`S20` after runtime placement. `S8`/`S9` disappear when Store ABI6 folds its own schema slots.

## Catalog Coordinator ABI v4

`ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` publishes magic `31415970`, ABI4 with an empty capability mask at `S2`. Its identity and fencing cells moved out of the header: `S14` CoordinatorId, `S15` Epoch, `S16` publication generation, `S21` AssignmentEpoch, and `S22` the topology seqlock that every catalog view fences on. It owns CoordinatorId/Epoch, Store claims, AssignmentEpoch, topology seqlock, and runtime capacity requests. `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` publishes magic `31415971`, ABI3 and places each pending Loader ABI5 item into compatible ACTIVE Store capacity or asks Core to claim another Generic Store.

The Store registry is `ic10/directory-core/generic_registry_directory_host_v2_0.ic10`, generic magic `31415982`, Host ABI3, publishing `DirectorySchema.CatalogStoreNode` schema version 1. Directory View `31415975` is ABI2 and Recovery `31415976` is ABI2.

Coordinator ABI4 supports 64 NodeIds, missing/duplicate health, higher-epoch recovery, runtime Store placement, item-level drain/compaction, and empty Store retirement. See `docs/CATALOG_COORDINATION.md`.

## Catalog Inspector

`ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` publishes magic `31415972`, ABI4. It accepts any Generic Store on `d0` and exposes NodeId/state/capacity/assignment, local catalog topology and Loader progress, plus Coordinator aggregate Store/capacity/topology telemetry.

## Controller discovery through Generic Snapshot Directory ABI v1

The shared discovery path supports **64 telemetry controllers**. `ic10/controller-discovery/controller_directory_adapter_v4_0.ic10` publishes `DIRECTORY_ADAPTER_ABI_V3` candidates with schema `DirectorySchema.Controller`; `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` commits them into `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10`.

```text
Controller Directory (Generic Snapshot Host)
S0      magic = 31415981
S1      ABI = 1
S2      active bank: 0=A, 1=B
S3/S4   generation A/B
S5/S6   provider count A/B, 0..64
S7/S8   overflow flag A/B; 1 means candidate 65+ existed
S9      DirectorySchemaId = HASH("DirectorySchema.Controller")
S10     DirectorySchemaVersion = 1
S11     entry width = 2
S12     capacity = 64
S32..159   bank A: 64 x [ControllerType, ReferenceId]
S160..287  bank B: 64 x [ControllerType, ReferenceId]
```

A snapshot with overflow set is **known incomplete**. Controller Selector reports `-3`; PhasePressure Arbiter and the Pressure Grid Link Adapter refuse to treat it as authoritative. Consumers validate generic directory magic/ABI plus Controller schema ID/version before reading the bank. Controller Selector ABI2 consumes the Generic Controller Directory directly. Editor and diagnostic selection consumers validate Selector ABI2; no Type Catalog compatibility path remains.

## Printer Directory schema v2

`ic10/printer-directory/printer_directory_adapter_v1_0.ic10` publishes Adapter ABI3 candidates for `DirectorySchema.Printer` v2. Generic Bridge/Host publish:

```text
[ReferenceId, FamilyHash, ProcessorSpec]

ProcessorSpec bits 0..7 = capability tier
              bit 8     = Power
              bit 9     = Busy/Active
              bit 10    = Error
              bit 11    = On
              bit 12    = Lock
```

Width is 3, capacity 64. FamilyHash equals Recipe Catalog PartitionKey. Fabricator is excluded. Scheduled printing consumes the `DirectorySchema.PrinterExecution` v1 overlay described below rather than attempting remote slot reads. See `docs/PRINTER_DIRECTORY.md`.

## Generic Job Store ABI v1

Persistence profile: `BANKED_TRANSACTION_V1 / SELECTOR_BANK`. Recovery requires `S0=31415984` **and** `S1=1` before existing slot geometry is interpreted.


`ic10/generic-jobs/generic_job_store_v1_0.ic10` publishes magic `31415984`, ABI1 and implements the physical store for `GENERIC_JOB_ABI_V1`. The logical job record is eleven fields:

```text
[JobId, JobType, RequiredCapability, Identity,
 InputCount, OutputCount, RequestedQuantity, Priority,
 State, Generation, ErrorStatus]
```

JobType values are `1 TRANSFORM`, `2 PRINT`, `3 TRANSFER`, `4 POWER`. State values are `1 QUEUED`, `2 PLANNING`, `3 RESERVING`, `4 READY`, `5 RUNNING`, `6 VERIFYING`, `7 COMPLETE`, `8 WAIT_RESOURCE`, `9 WAIT_PROCESSOR`, `10 WAIT_CAPACITY`, `11 FAULT`, `12 CANCELLED`.

Store header/control cells:

```text
S0   magic = 31415984
S1   ABI = 1
S2   QueueSequence; odd mutating, even stable
S3   QueueGeneration
S5   capacity = 32
S7   request generation
S8   response generation
S9   response status; 1 success, <0 rejected
S10  allocated JobId for PUBLISH_NEW
S11  command: 1 PUBLISH_NEW, 2 SET_STATE, 3 REAP
S12  slot ordinal 0..31
S13  expected JobGeneration for SET_STATE/REAP
S14  desired State for SET_STATE
S15  desired ErrorStatus for SET_STATE
S23  next JobId
S24  applied-request/replay marker
S25  in-flight slot state-base journal
S26  in-flight old active state bank
```

Physical geometry:

```text
S32..287   32 x 8 immutable intent slots
             [JobId,JobType,RequiredCapability,Identity,
              InputCount,OutputCount,RequestedQuantity,Priority]

S288..511  32 x 7 mutable state slots
             [activeBank,
              A.State,A.Generation,A.ErrorStatus,
              B.State,B.Generation,B.ErrorStatus]
```

A free slot has active `State=0`. `PUBLISH_NEW` assigns a fresh JobId and atomically publishes `QUEUED/Generation=1/ErrorStatus=0`. `SET_STATE` requires the exact current JobGeneration and refuses to reopen terminal jobs. `REAP` requires exact generation and accepts only COMPLETE/FAULT/CANCELLED.

Lifecycle-edge legality is the required writer contract in `docs/GENERIC_JOB_ABI.md`, `data/generic_job_schema.json`, and `framework/job_abi.py`. Queue readers capture even `S2`, read intent plus the active state bank, then require unchanged even `S2` before accepting the record. Same-service odd-sequence recovery distinguishes pre-flip rollback from post-flip commit using S25/S26.

## Generic telemetry ABI v1 and v2

All controller runtimes share the same magic/header region. ABI 1 is sufficient when channels are consumed independently (PI, Test, Sequencer). ABI 2 is required when another service combines multiple live fields as one invariant-bearing snapshot (PhasePressure, PressureDomain, PressureTransfer).

```text
S96    magic = 27182818
S97    ABI = 1 or 2, exact per controller family
S98    capability bitmask
S99    ControllerType hash
S100.. telemetry channels
S115   ABI2 only: telemetry publication generation; payload precedes generation
S116   paired Generic Config Host ReferenceId
```

ABI2 publishers clear `S115` before mutating related telemetry, write the payload, then write a new positive generation to `S115` last. Transactional consumers capture `S115`, read all required fields, and accept only if the same positive generation remains afterward.

## Generic Config Host ABI v1

Block width is fixed at 8. Masks are authoritative schema geometry.

```text
S0       magic = 31415928
S1       ABI = 1
S2       ControllerType hash
S3       reserved
S4       controller config schema
S5       effective generation
S6       request generation
S7       response generation
S8       operational status; >0 ready
S9       effective config revision
S10      block count 1..4
S11      transaction result associated with S7
S12      Policy persistence schema signature
S13      Policy generation; metadata/defaults precede increment
S16..19  validity masks for physical blocks 0..3
S20      Policy response generation
S21      Policy validation result
S96..127 effective physical image
S128..159 candidate physical image
S160..191 durable bank A image
S192..223 durable bank B image
S224..226 bank A footer: signature, config revision, bank revision
S227..229 bank B footer: signature, config revision, bank revision
```

A set mask bit means the physical slot participates in the schema. Loader derives active-control count and active ordinal -> physical-slot mapping from the masks. Committer transports only set bits.

## Generic Input Profile ABI v1

The Profile ABI is domain-neutral. Configuration Profiles use ControllerType/schema as their context identity; diagnostics uses `HASH("DiagnosticMapping")`/schema 1.

```text
S0       magic = 31415929
S1       ABI = 1
S2       ContextType hash
S3       context schema
S4       logical control count
S5       profile generation; written last
S32..    four-value control descriptors
```

Descriptor N begins at `S32 + 4*(N-1)`:

```text
+0 InputKind
+1 min / switch OFF / enum table base
+2 max / switch ON / enum entry count
+3 Dial step count / auxiliary
```

Input kinds: `0 LOGIC_MEMORY`, `1 DIAL_LINEAR`, `2 DIAL_INTEGER`, `3 SWITCH`, `4 ENUM`.

For Dial kinds, `+3` must provide the intended Dial Mode/step count (`1..999`). The Resolver intentionally does not invent domain-specific ranges.

### Input Profile Catalog Store / View

Input Profiles use Store ABI6 with `CatalogSchemaId=HASH("CatalogSchema.InputProfile")`, **CatalogSchemaVersion=3**, and stable `CatalogInstanceId=HASH("Catalog.InputProfiles.Schema3")`. Six self-contained variable-length production/diagnostic profiles fit one Store at runtime and are supplied by the generated `ic10/input-profile-catalog/input_profile_catalog_loader_*_v4_0.ic10` candidates.

Each schema-v3 item is:

```text
[ProfileType, schema, FieldCount, EnumPairCount,
 FieldCount x 4-cell descriptors,
 EnumPairCount x 2-cell enum pairs,
 zero padding to 4-cell alignment]
```

No absolute descriptor/enum pool pointers exist. `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` scans runtime Store item directories and republishes the unchanged Generic Input Profile ABI1.

## Generic Input Scanner ABI v1

The Scanner owns all physical commissioning screws and knows nothing about configuration or diagnostics.

```text
S0   magic = 31415930
S1   ABI = 1
S2   capability mask = 0
S8   populated/assigned-screw bitmask
S9   requested logical control count 1..32
S10  selected logical control ordinal 1..N; 0 unavailable
S11  discovered Generic Input Profile ReferenceId; 0 absent
S12  hardware snapshot generation; written last
S13  Field Dial ReferenceId
S14  Value Dial ReferenceId
S15  Logic-Memory-like ReferenceId
S16  Switch-like ReferenceId
S17  capability bitmask
```

`S17`: bit0 Field Dial, bit1 Value Dial, bit2 Memory, bit3 Switch, bit4 Profile. First Dial by screw order is Field Dial; second is Value Dial. `S9` is supplied by the paired Resolver. Scanner sets Field Dial Mode to `S9-1`, reads its exact integer Setting, and publishes a 1-based ordinal at S10.

## Generic Input Resolver ABI v1

One Resolver instance is paired with one active commissioning input context. It interprets the Scanner's physical inputs through an optional Profile.

```text
S0   magic = 31415931
S1   ABI = 1
S2   capability mask = 0
S8   Generic Input Scanner RefId
S9   logical control count 1..32
S10  validated/context-appropriate Profile RefId; 0 => Memory descriptors
S11  status; 1 ready, <0 invalid/unavailable
S12  resolved snapshot generation; written last
S13  selected logical control ordinal 1..N
S14  resolved value
S15  resolved InputKind
```

The Resolver implements Dial scaling with `lerp`, integer quantization only for `DIAL_INTEGER`, Switch min/max mapping, enum lookup, and preferred-device -> Memory fallback. It rechecks Scanner and Profile generations before publishing.

## Generic Config Editor ABI v1

```text
S0       magic = 22360680
S1       ABI = 1
S2       Controller Selector RefId
S5       Apply generation
S6..8    Save/Reload/Apply previous states
S10      loaded controller RefId
S11      staging revision
S12      desired controller RefId
S13      Apply-captured staging revision
S14      Apply-captured controller RefId
S15      staging ready
S16      editor status
S17      active field count
S18      loaded Config Host RefId
S19      controller config schema
S20      Config Bridge-selected physical image slot 0..31
S21      Config Bridge-resolved value
S22      Config Bridge input kind
S25      Config Bridge publication valid
S26      Config Bridge Host snapshot
S27      Loader-validated Profile RefId
S28      validated Profile ABI (=1)
S29      validated Profile generation
S30      loaded block count
S32..63  staged physical config image
S64..95  active UI ordinal -> physical image slot map
S96..99  loaded Host block-mask snapshot
```

## Config Input Bridge ABI v1

```text
S0   magic = 22360681
S1   ABI = 1
S2   Generic Config Editor RefId
S3   Generic Input Resolver RefId
```

The Bridge configures Resolver count/Profile from the Loader-validated Editor state, then converts Resolver logical ordinal through Editor `S64..95` and publishes Editor `S20/S21/S22/S26`, with Editor `S25` written last.

## Unified Resource Profile Catalog / View

Resource Profiles use Store ABI6, `CatalogSchemaId=HASH("CatalogSchema.ResourceProfile")`, **schema version 2**, and instance `HASH("Catalog.ResourceProfiles.Schema2")`. Every profile is a fixed 16-cell item: 14 semantic cells plus two zero padding cells (`SchemaCellMask=0x3fff`). PartitionKey is ResourceClass.

With the 2-cell Store item-directory overhead, a Store holds 26 such items. The current 39 records derive at runtime as one FLUID Store (10), two ITEM Stores (26+1), one POWER Store (1), and one ENERGY Store (1). Seven Loader ABI5 candidates provide the records; none contains a Store ordinal or physical target.

`ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` accepts any Store in the catalog, follows runtime topology under a stable Coordinator sequence, scans `[ItemBase,ItemCellCount]` entries, and republishes Resource Profile View ABI1 with its existing S8..S21 semantic surface.

## Recipe Catalog / Lookup ABI v3

Recipes use `CatalogSchema.Recipe`, **schema version 3**, through Store ABI6. Each recipe is one variable-width 4-cell-aligned item:

```text
[RecipeHash, FamilyHash, RequiredCapability, FamilyOrdinal, InputCount,
 Input0ReagentHash, Input0Quantity, ...]
```

The generator permits up to 16 material inputs. Store capacity is computed from whole item widths plus each 2-cell Store directory entry; it is not a fixed recipes-per-Store value. The 780-recipe stress case derives 18 Stores (`48+48+34` per family).

`ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` publishes magic `31415967`, ABI3 and retains the compact `[FamilyHash, capability, FamilyOrdinal] -> RecipeHash` browse surface while requiring Recipe schema v3.

`ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` publishes magic `31415985`, ABI1 for exact RecipeHash execution planning:

```text
S2  requested RecipeHash
S3  FamilyHash
S4  RequiredCapability
S5  InputCount
S6  Store publication generation
S7  status: 1 ready, -2 invalid catalog, -3 missing
S8..S39 [ManufacturingReagentHash, Quantity] pairs
S40 Coordinator topology generation
S41 resolved RecipeHash echo
```

Consumers require S41 to equal the current request before accepting S7=1.

## Manufacturing Scheduler ABIs — current

Roadmap item 6 plus its hardening pass uses ordinals 172..187. Services whose request-token or reservation semantics changed are ABI2; unchanged helper contracts remain ABI1. Full wiring and lifecycle semantics are in `docs/MANUFACTURING_SCHEDULER.md` and asynchronous publication rules are in `docs/ASYNC_REQUEST_STANDARD.md`.

### DirectorySchema.TransformLane v1

```text
[RuntimeReferenceId, ProcessorReferenceId, ProcessorSpec]
```

`ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` publishes Adapter ABI3 candidates and accepts Transform Runtime ABI2. ProcessorSpec bits 0..7 are the capability mask; bits 8/9/10 are Power/Busy/Error.

### Manufacturing Candidate Selector ABI2

Magic `31416072`. `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` accepts a **dynamic Snapshot Directory ReferenceId in S16**. Request cells are S17 schema ID, S18 optional key/FamilyHash, S19 capability, S20 comparison mode (`1 mask`, `2 tier`), S21 start ordinal, S22 request generation, and S15 expected schema version, its request mailbox having moved above the common S0..S7 header. It captures active bank + generation, scans, then requires the same active bank + generation before publishing status S9, candidate S10..S12, next ordinal S13, directory generation S14, and response token S8. One physical selector can therefore serve Transform and Print serially.

### Transform Candidate Readiness ABI1

Magic `31415998`. `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` owns generation-qualified Transform planning. It requires Transform Profile View ABI4 `S68 == requested TransformType` and `S69 == 1`, then waits for new Admission and Resolver publication generations. It reports `1 ready`, `-2 processor`, `-3 resource`, `-4 capacity`, `-1 invalid` in S9 and publishes response token S10. There is no fixed planning tick timeout.

### Transform Candidate Executor ABI2

Magic `31416073`. `ic10/manufacturing/transform_candidate_executor_v2_0.ic10` delegates planning to Readiness on d0, launches the exact Runtime only after readiness succeeds, and consumes Runtime state only when Runtime ABI2 current request token S21 matches its request. It writes the TransformType to Runtime S8 and the request token to Runtime S16 last, and reads Runtime status at S20 -- the cells the material-transform migration moved those fields to. S11 is target Job state, S12 ErrorStatus, S10 current request token.

### Print Candidate Executor ABI2

Magic `31416074`. `ic10/manufacturing/print_candidate_executor_v2_0.ic10` binds one exact PrinterRef to Recipe Execution View, Capacity Client ABI2, Print Material Resolver, and Generic Print Runtime ABI2. It publishes current request token S10 before exposing request-specific state, waits for exact runtime token matches, and waits for acknowledged capacity release before publishing terminal/wait/fault completion.

### Transform Job Driver ABI2

Magic `31416076`. `ic10/manufacturing/transform_job_driver_v2_0.ic10` iterates TransformLane candidates for the Driver Router. It requests candidates from the shared Candidate Selector on d0, writing the directory ReferenceId to S16 and the request to S17..S22, and mirrors the selected candidate to Transform Candidate Executor S21..S26 on d1. Its own request mailbox is S12..S17, written by the Router.

### Print Material Resolver ABI1

Magic `31415989`. `ic10/manufacturing/print_material_resolver_v1_0.ic10` consumes Recipe Execution View on d0 and ResourceLink Snapshot Directory on d1. Its request mailbox is S16 target printer ReferenceId, S17 requested output quantity, and S18 request generation. It publishes S8 printer binding echo, S9 InputCount, S11 generation, S12 status, S13 response token, and S20.. four-cell `[LinkRef, QuantityPerOutput, ResourceType, Unit]` records compatible with Multi Reservation Stager/Allocator.

### Generic Print Runtime ABI2

Magic `31416075`. `ic10/manufacturing/generic_print_runtime_v2_0.ic10` consumes Print Material Resolver d0 and Multi Material Allocator ABI2 d1. S10 PrinterRef, S11 RecipeHash, S12 RequestedQuantity, S13 JobId, S14 request token; S15 is the **current accepted request token**, S8 target Job state, S9 ErrorStatus. It publishes initial request state/error before S15, issues native printer stack instructions only after material commit, and verifies ExportCount.

### Manufacturing drivers/router/scheduler

```text
179 Transform Job Driver magic 31415991 ABI2
180 Print Job Driver     magic 31415992 ABI2
181 Job Selector         magic 31415993 ABI2
182 Driver Router        magic 31415994 ABI2
183 Scheduler            magic 31415995 ABI1
```

Generic Job Selector ABI3 uses S2 as a JobId cursor and skips every eligible JobId `<= cursor`, guaranteeing progress before wrap. S18=0 selects the manufacturing TRANSFORM/PRINT state policy; S18>0 selects that exact JobType and its nonterminal lifecycle states. Manufacturing and POWER schedulers own domain lifecycle policy, while all physical Job Store mutation is serialized through Gateway ABI3 and `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10`.

### Printer Execution Bank ABI2

Magic `31415996`. `ic10/printer-directory/printer_execution_bank_v2_0.ic10` locally pins up to six printers on d0..d5. Per pin: S16 current PrinterRef, S24 capacity/status, S32 ExpectedPrinterRef, S40 RequestToken (positive reserve / negative release), S48 ResponseStatus, S56 ResponseToken, S64 OwnerPrinterRef, S72 OwnerToken. Response status is written before ResponseToken. Failed requests do not create ownership. Fresh/reset initialization never clears unknown external Lock state; release clears Lock only when the currently attached printer still equals persisted OwnerPrinterRef.

### DirectorySchema.PrinterExecution v1

`ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` joins Printer Directory v2 with live Execution Banks ABI2 and publishes Adapter ABI3 records:

```text
[PrinterReferenceId, FamilyHash, ProcessorSpec]
```

ProcessorSpec retains Printer v2 bits and adds bit13 output occupied, bit14 output-capacity-known, and bits16..18 Execution Bank pin index.

### Printer Capacity Client ABI2

Magic `31415997`. Request S2 exact PrinterReferenceId, S3 ProcessorSpec, S4 command (`1 reserve`, `2 release`), S5 request token. Response S6 token, S7 status, S8 resolved PrinterRef. S9/S10/S11 retain owning Bank/pin/reservation token. The client reasserts ExpectedPrinterRef + RequestToken while waiting, so Bank reboot cannot lose the operation; reserve success is post-validated against current pin identity plus OwnerPrinterRef/OwnerToken; release is acknowledged before local ownership state is cleared.

## ControllerPhasePressure telemetry ABI v2

The controller publishes `HASH("ControllerPhasePressure")` at `S99`; capability mask `254` advertises channels 1..7.

```text
S100 / channel 1  actual pressure, kPa
S101 / channel 2  actual temperature, K
S102 / channel 3  phase-boundary pressure, kPa
S103 / channel 4  requested pressure, kPa
S104 / channel 5  mode: 0 HOLD, 1 EVAPORATE, 2 CONDENSE
S105 / channel 6  runtime status
S106 / channel 7  MediumType hash
S115              telemetry generation; written LAST
S116              paired Generic Config Host ReferenceId
```

The request channel remains useful with `DirectWrite=0`; higher-level services treat the request/mode/status/medium tuple as valid only from one coherent positive `S115` snapshot.

## PhasePressure Request Arbiter ABI v1

The Arbiter is an internal pressure-grid service, not generic controller telemetry. One instance is paired with one active PressureDomain context.

```text
S0   magic = 31415933
S1   ABI = 1
S2   capability mask = 0
S8   raw aggregate requested pressure
S9   contributing request count
S10  result status: 0 none, 1 LOW, 2 HIGH, -3 Directory invalid, -9 context invalid
S11  Controller Directory generation used by completed pass
S12  result generation; payload is written before this value
S13  handled Host effective generation
S14  handled MediumType hash
S15  context Enabled
S16  context Role: 1 LOW/EVAP, 2 HIGH/CONDENSE
S17  context MediumType hash
S18  context Host effective generation
```

The Arbiter scans one Controller Directory provider per tick. It restarts the pass if context, active Directory bank, or source generation changes. LOW reduces with `min(RequestedPressure)` over valid matching EVAPORATE producers; HIGH reduces with `max(RequestedPressure)` over matching CONDENSE producers.

## ControllerPressureDomain telemetry ABI v2

`ControllerPressureDomain` publishes `HASH("ControllerPressureDomain")` at `S99` and a transactional telemetry generation at `S115`.

```text
S100 / channel 1  actual pressure, kPa (NaN when unavailable)
S101 / channel 2  LOW/HIGH: target pressure; STORAGE: minimum/export floor
S102 / channel 3  LOW/HIGH: contributing request count; STORAGE: maximum/import ceiling
S103 / channel 4  role: 1 LOW, 2 HIGH, 3 STORAGE
S104 / channel 5  MediumType hash
S105 / channel 6  runtime status
S115              telemetry generation; written LAST
S116              paired Generic Config Host ReferenceId
```

`Role=3` deliberately overlays channels 2/3 with STORAGE pressure bounds. Inventory captures/rechecks `S115` before calculating capacity. Runtime statuses are documented in `docs/PRESSURE_DOMAIN_CONTROLLER.md`.

## PressureDomain Inventory ABI v2

One Inventory service is paired with one PressureDomain, one Pipe Analyzer, and one Pressure Medium Purity Guard. It translates a coherent pressure-policy snapshot plus verified gas-network state into molar export/import capacity.

```text
S0   magic = 31415935
S1   ABI = 2
S2   PressureDomain ReferenceId
S3   role: 1 LOW, 2 HIGH, 3 STORAGE
S4   MediumType hash
S5   ExportableMoles
S6   ImportCapacityMoles
S7   MolesPerKPa = Volume / (8.3144 * Temperature)
S8   MolesPerLiter = Pressure / (8.3144 * Temperature)
S9   TotalMoles
S10  Pressure, kPa
S11  status: 1 ready; negative fault
S12  publication generation; written LAST
```

Inventory rejects liquid-bearing buses, invalid numerics, torn PressureDomain telemetry, and failed/mismatched purity. See `docs/PRESSURE_INVENTORY_MODEL.md`.

## PressureInventory Reservation ABI v1

One Reservation service wraps one PressureDomain Inventory and provides the mutable shared-endpoint ledger used by parallel planning.

```text
S0   magic = 31415936
S1   ABI = 1
S2   underlying Inventory ReferenceId
S3   PressureDomain ReferenceId
S4   role: 1 LOW, 2 HIGH, 3 STORAGE
S5   MediumType hash
S6   ExportableMoles
S7   ImportCapacityMoles
S8   MolesPerKPa
S9   MolesPerLiter
S10  mirrored Inventory status
S11  mirror publication generation
S12  ReservedExportMoles          # Allocator-owned
S13  ReservedImportMoles          # Allocator-owned
S14  reservation build epoch      # Allocator-owned
S15  owning Planner ReferenceId   # Allocator-owned
```

The Reservation IC writes `S0..S11`; the paired Pressure Reservation Allocator is the only intended writer of `S12..S15`.

## Pressure Reservation Allocator ABI v3

`ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` serializes endpoint reservation mutation and stages one physical Transfer hop. It is screwless. ABI3 adds non-mutating QUOTE plus exact COMMIT and stages topology identity with the grant.

```text
S0   magic = 31415938
S1   ABI = 3

Request:
S2   Planner ReferenceId
S3   build/reservation epoch
S4   MediumType
S5   ControllerPressureTransfer ReferenceId
S6   request generation; written LAST
S10  mode: 1 fallback, 2 direct, 3 path hop
S11  maximum requested mol/tick
S16  operation: 1 QUOTE, 0 COMMIT

Response:
S7   committed lease moles; 0 for QUOTE
S8   result: 1 admissible/granted, 0 no grant, -1 rejected
S9   response generation; written LAST
S12  admissible/committed mol/tick
```

QUOTE calculates remaining endpoint capacity without mutation. COMMIT reserves exactly the accepted rate for the full Planner lease and stages `S117 source Reservation`, `S118 sink Reservation`, `S119 MediumType`, `S120 RouteKind`, then writes staged epoch `S109` last. Mode 3 admits route classes 1..4; modes 1/2 deliberately exclude free-standing STORAGE->STORAGE movement.

## Pressure Grid Link directory through Generic Snapshot Directory ABI v1

`ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` derives a transfer-only candidate set from a schema-qualified Controller directory and commits it through the generic bridge/host.

```text
S0   magic = 31415981
S1   ABI = 1
S2   active bank
S3/S4 generation A/B
S5/S6 link count A/B, 0..64
S7/S8 overflow A/B
S9   DirectorySchemaId = HASH("DirectorySchema.PressureGridLink")
S10  DirectorySchemaVersion = 1
S11  entry width = 3
S12  capacity = 64

A = S32..223
B = S224..415
record = [TransferRef, SourceReservationRef, SinkReservationRef]
```

Consumers reject overflow and validate the generic Host header plus schema identity before treating the graph as authoritative. Unchanged candidate sets do not force a new committed generation.

## Grid Path Enumerator ABI v2

`ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` enumerates usable routed reuse candidates with two or three physical links. `SearchId` separates one bounded ranking search from the next while `build epoch` remains the reservation/staging identity.

```text
S0   magic = 31415940
S1   ABI = 2

Request:
S2   Planner ReferenceId
S3   build epoch
S4   MediumType
S5   SearchId
S6   request generation; written last

Response:
S7   path length: 2 or 3; 0 when enumeration is exhausted
S8   path bottleneck mol/tick
S9   status: 1 candidate, 0 none, -1 fault
S10  response generation; written last
S16  hop 1 Transfer ReferenceId
S17  hop 2 Transfer ReferenceId
S18  hop 3 Transfer ReferenceId when used
```

Repeated requests with the same `SearchId` resume the same bounded-depth DFS. A new `SearchId` restarts traversal. Current routed forms remain `LOW->STORAGE->HIGH` and `LOW->STORAGE->STORAGE->HIGH`.

## Grid Route Selector ABI v2

`ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` enumerates/ranks up to the Cost Profile candidate budget and returns the lowest-cost candidate examined. ABI2 passes the current Planner lease length into reservation-aware ranking.

```text
S0   magic = 31415944
S1   ABI = 2
S2   Planner ReferenceId
S3   build epoch
S4   MediumType
S5   LeaseTicks
S6   request generation; written LAST
S7   selected path length
S8   selected admissible bottleneck mol/tick
S9   status: 1 route, 0 none, -1 fault
S10  response generation; written LAST
S11  selected route cost
S12  persistent search-id counter
S16..18 selected Transfer ReferenceIds
```

The selector restarts enumeration for each new search while preserving the current build epoch and already committed endpoint reservations.

## Grid Cost Profile ABI v1

`ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` publishes route-ranking policy:

```text
S0 magic = 31415945
S1 ABI = 1
S2 HopWeight = 100
S3 StorageWeight = 25
S4 LiftWeightPerKPa = 0.01
S5 FlowScarcityWeight = 100
S6 CandidateBudget = 32
```

Weights must be non-negative; HopWeight must be positive. The score is dimensionless.

## Grid Route Ranker ABI v2

`ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` scores candidates and retains the best route per SearchId. It clamps candidate throughput by **remaining** reservation-ledger capacity using the supplied lease length before applying the route-cost function.

```text
S0 magic = 31415946
S1 ABI = 2

Request:
S2  SearchId
S3  PathLength
S4  raw candidate BottleneckMolesPerTick
S5..S7 Transfer ReferenceIds
S8  RequestToken
S11 LeaseTicks

Response/state:
S9   status: 1 accepted, -1 invalid
S10  ResponseToken
S16..S18 best Transfer ReferenceIds
S19  BestPathLength
S20  BestAdmissibleBottleneckMolesPerTick
S21  BestCost
S22  ActiveSearchId
S23  CandidatesEvaluated
S24  CandidateBudget
S25  scratch accumulated positive lift (not a public contract)
```

The Ranker rejects NaN or invalid policy values and removes routes whose remaining export/import reservation capacity is exhausted.

## Grid Path Allocator ABI v1

`ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` requests one ranked route from Route Selector ABI2, then uses Allocator ABI3 in two phases.

```text
S0   magic = 31415941
S1   ABI = 1

Request:
S2   Planner ReferenceId
S3   build epoch
S4   MediumType
S5   LeaseTicks
S6   request generation; written LAST

Response:
S7   end-to-end reserved moles at the exact path rate
S8   result: 1 path staged, 0 no path/admission, -1 dependency fault
S9   response generation; written LAST
S10  staged path link count
S11  exact common path mol/tick
```

Path Allocator QUOTEs every hop first, takes the minimum admissible rate, then COMMITs every hop at exactly that common rate. The current endpoint ledgers therefore do not intentionally over-reserve earlier hops during later-hop normalization.

## Grid Single-Hop Builder ABI v1

`ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` stages a complete direct or fallback sweep.

```text
S0   magic = 31415942
S1   ABI = 1

Request:
S2   Planner ReferenceId
S3   build epoch
S4   MediumType
S6   mode: 2 direct, 1 fallback
S7   request generation; written last

Response:
S8   granted link count
S9   total hop-reserved moles
S10  status: 1 grants, 0 none, negative fault
S11  response generation; written last
```

Fallback mode preserves the STORAGE anti-circulation direction check and never admits route class 4.

## Grid Plan Builder ABI v1

`ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` sequences direct reuse, repeated routed reuse, and fallback. It cannot commit the plan.

```text
S0   magic = 31415943
S1   ABI = 1

Request:
S2   Planner ReferenceId
S3   build epoch
S4   MediumType
S5   LeaseTicks
S6   request generation; written last

Response:
S7   staged physical-link count
S8   staged plan reserved-moles summary
S9   status
S10  response generation; written last
```

## Grid Reservation Planner ABI v2

`ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` is the medium-specific commit authority. It is wired to one Grid Link Directory, one PHASE_MEDIUM Resource Profile View, and one Grid Plan Builder.

```text
S0   magic = 31415937
S1   ABI = 2
S7   LeaseTicks = max(64, 4 * linkCount + 16)
S8   staged physical-link count in committed plan
S9   reserved-moles summary in committed plan
S10  status: 1 grants, 0 no grants, negative dependency/build fault
S12  MediumType hash
S13  persistent build-generation counter
S14  committed reservation epoch; written LAST on successful build only
S15  persistent Plan-Builder request generation
```

A failed build does not write `S14`; partial staged state therefore remains inert.

## ControllerPressureTransfer telemetry ABI v2

`ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` publishes `HASH("ControllerPressureTransfer")` at `S99`, transactional ABI2 telemetry, and owns one physical Volume/Turbo Volume Pump edge.

```text
S100 / channel 1  current PlannedMolesPerTick rate ceiling; meaningful when S103=1
S101 / channel 2  RouteKind: 1 LOW->HIGH, 2 LOW->STORAGE,
                  3 STORAGE->HIGH, 4 STORAGE->STORAGE
S102 / channel 3  MediumType hash
S103 / channel 4  candidate status: 1 valid, 0 inactive, -1 fault
S115              telemetry generation; written LAST
S116              paired Generic Config Host ReferenceId
```

Topology/staged-grant surface used by discovery, Allocator, and Grant Guard:

```text
S106 source PressureInventory Reservation ReferenceId
S107 sink PressureInventory Reservation ReferenceId
S108 staged GrantMolesPerTick
S109 staged GrantEpoch; written after staged payload
S110 staged Planner ReferenceId
S111 staged LeaseTicks
S117 staged source Reservation ReferenceId
S118 staged sink Reservation ReferenceId
S119 staged MediumType
S120 staged RouteKind
```

The Transfer runtime does **not** activate a staged grant directly. Its `d3` points to the Pressure Transfer Grant Guard and it executes only a coherent active rate from that Guard, capped again by current physical capacity.

## Pressure Medium Purity Guard ABI v1

`ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` verifies that the gas physically observed by a Pipe Analyzer matches the attached `PHASE_MEDIUM` Resource Profile View.

```text
S0  magic = 31415947
S1  ABI = 1
S2  MediumType
S3  observed gas ratio
S4  required purity threshold
S5  status: 1 good, -1 profile, -2 sensor/property, -3 numeric, -4 contaminated
S6  Resource Profile View generation used
S7  publication generation; written LAST
```

For a nonempty gas bus, `S3 >= S4` is required. Empty buses are accepted because there is no contaminating inventory.

## Pressure Transfer Grant Guard ABI v1

`ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` is the activation barrier between staged reservation state and physical pump execution.

```text
S0  magic = 31415948
S1  ABI = 1
S2  active GrantMolesPerTick
S3  remaining active lease ticks
S4  status: 1 active, 0 off, -1 fault
S5  last consumed/accepted committed Planner epoch
S6  Transfer ReferenceId
S7  publication generation; written LAST
S10..S13 active source/sink/medium/route identity snapshot
```

It requires a coherent current Transfer ABI2 snapshot, matching staged source/sink/medium/route identity, matching Planner ReferenceId, and `staged epoch == Planner S14`. A topology mismatch **consumes** that committed epoch rather than merely pausing it, so restoring old wiring cannot reactivate a previously invalidated lease. Each committed epoch can activate at most once per Transfer; expiration does not cause repeated reactivation while Planner `S14` remains unchanged.

## Controller Selector ABI v2

Controller Selector is screwless and scans the sorted Generic Controller Directory directly. It derives type/member groups on demand and revalidates the active bank/generation before publication.

```text
S8       status; 1 valid
S9       source generation
S10      requested type ordinal
S11      requested member ordinal
S12      request generation; values precede generation
S13      handled request generation; TERMINAL_RESPONSE token written after the result/status
S14      Generic Snapshot Controller Directory RefId
S15      selected type ordinal
S16      selected member ordinal
S17      controller ReferenceId
S18      absolute provider index0
S19      ControllerType hash
```

Consumers may use S17/S19/S8/S9 only after `S13` equals the exact expected request generation. A stale valid status from the prior request is not evidence that a newer desired Type/Member has resolved.

## Console Selector ABI v1

Console Selector is screwless and has two independent request streams so automatic advance cannot be undone by stale UI state.

```text
S2       Console Registry RefId
S3       selected console ordinal
S4       display ReferenceId
S5       status; 1 valid
S6       blink state
S7       source generation
S8       previous display ReferenceId
S10      advance request generation
S11      handled advance generation
S12      requested console ordinal
S13      desired-selection request generation
S14      handled desired-selection generation
```

Both `S14` and `S11` are `TERMINAL_RESPONSE` tokens: resolved ordinal/ReferenceId/source generation/status are published before either handled token. A consumer of the current resolved console requires the desired stream settled (`S14 == expected S13`) and the automatic-advance stream settled (`S11 == S10`). A new desired request is applied once. A later increment of `S10` advances from the current selection even if `S12` still contains an older desired value.

## Diagnostic Input Bridge ABI v1

```text
S0       magic = 17320511
S1       ABI = 1
S2       Generic Input Resolver RefId
S3       Diagnostic Input Profile RefId
S7       status; 1 ready
S16      desired Controller Type ordinal
S17      desired Controller Member ordinal
S18      desired Console ordinal
S19      telemetry channel
S20      LED Mode
S21      LED Color
S22      current Commit switch state
S23      Commit request generation (rising edges)
S24      Controller Selector request generation
S25      Console Selector desired-request generation
```

## Diagnostic Selector Bridge ABI v1

```text
S0   magic = 17320512
S1   ABI = 1
S2   Diagnostic Input Bridge RefId
S3   Controller Selector RefId
S4   Console Selector RefId
S5   last observed console-request generation
```

It writes desired selector values before their request generation, preserving atomic selector requests.

## Diagnostic Mapping Editor ABI v1

```text
S0   magic = 17320510
S1   ABI = 1
S2   Console Selector RefId
S3   Controller Selector RefId
S4   Diagnostic Renderer RefId
S5   handled Commit generation
S6   status: 1 ready, 2 committed, negative fault
S7   Diagnostic Input Bridge RefId
```

The Mapping Editor owns no physical screws. Before interpreting selector status or ReferenceIds it fences Controller Selector `S13` against Diagnostic Input `S24`, Console desired response `S14` against Diagnostic Input `S25`, and Console advance response `S11` against request `S10`. On a new Commit generation it then snapshots Diagnostic Input Bridge `S19..S21`, commits `[display,controller,channel,Mode,Color]`, requests Console Selector advance through `S10`, then marks the Commit generation handled.

## PI config schema 1

PI uses two blocks with masks `255` and `63`.

| Active field | Physical slot | Meaning |
|---:|---:|---|
| 1 | 0 | Setpoint |
| 2 | 1 | Kp |
| 3 | 2 | Ki |
| 4 | 3 | Output minimum |
| 5 | 4 | Output maximum |
| 6 | 5 | Integral minimum |
| 7 | 6 | Integral maximum |
| 8 | 7 | Bias |
| 9 | 8 | Deadband |
| 10 | 9 | Mode |
| 11 | 10 | Manual output |
| 12 | 11 | Input LogicType |
| 13 | 12 | Output LogicType |
| 14 | 13 | Direction |

PI transaction results: `-5` malformed, `-51` output range, `-52` integral range, `-53` non-integral LogicType, `5` applied.

## PI telemetry channels

Channels 1..10 are process value, actual output, integral state, saturation delta, status, setpoint, raw error, adjusted error, mode, and requested/pre-limit output respectively.


## ControllerSequencer config schema 1

ControllerSequencer uses two blocks with masks `255` and `1`.

| Active field | Physical slot | Meaning |
|---:|---:|---|
| 1 | 0 | Enabled |
| 2 | 1 | Input LogicType |
| 3 | 2 | LowThreshold |
| 4 | 3 | HighThreshold |
| 5 | 4 | Fill LogicType |
| 6 | 5 | Drain LogicType |
| 7 | 6 | SettleTicks |
| 8 | 7 | TimeoutTicks |
| 9 | 8 | Repeat |

Persistence signature: `CFG1|ControllerSequencer|1|2|255|1|0|0`.

Sequencer Policy results: `-5` malformed/NaN, `-71` threshold ordering, `-72` non-integral discrete field, `-73` timer range, `5` applied.

## ControllerSequencer telemetry channels

Channels 1..5 are process value, state, ticks in current state, completed cycle count, and status.

State values: `0` fill, `1` settle, `2` drain, `3` complete, `4` timeout, `5` numeric fault.

Status values: `0` healthy, `-1` input unavailable, `-4` config/Host incompatibility, `-5` numeric fault, `-6` phase timeout.

## ControllerPressureDomain config schema 1

ControllerPressureDomain uses one block with mask `255`.

| Active field | Physical slot | Meaning |
|---:|---:|---|
| 1 | 0 | Enabled |
| 2 | 1 | Role: 1 LOW/EVAP, 2 HIGH/CONDENSE |
| 3 | 2 | MinimumPressure |
| 4 | 3 | MaximumPressure |
| 5 | 4 | StandbyPressure |
| 6 | 5 | PressurizeLogicType |
| 7 | 6 | DepressurizeLogicType |
| 8 | 7 | DirectWrite |

Persistence signature: `CFG1|ControllerPressureDomain|1|1|255|0|0|0`.

Policy results: `-5` malformed candidate, `-91` invalid Role, `-92` invalid pressure bounds/standby, `5` applied.

## How to read this ABI reference

This file is the exact stack contract; higher-level documents explain intent. A few conventions apply across almost every service:

- `S0` is usually the service magic and `S1` the ABI version for discoverable public services.
- A **ReferenceId** identifies one concrete game object; a **type hash** identifies a family/category.
- A **generation** is a transaction/snapshot marker, not a semantic version.
- Multi-cell payloads are written first and their generation/request marker is written **last**.
- Status values `>0` generally mean ready/successful state for long-running services; negative values are faults/results whose exact meaning is service-specific.
- Reserved cells must not be repurposed casually; future ABI evolution depends on consumers being able to trust the documented layout.

When wiring by hand, first verify magic/ABI, then dependency ReferenceIds, then readiness/status, then the generation associated with the data you are reading.

## Common publication patterns

### Snapshot publication

Used by Scanner, Resolver, discovery directories, and similar services:

```text
capture/update payload
write payload cells
write snapshot generation LAST
```

A consumer should use the corresponding generation to avoid combining cells from different snapshots.

### Request/response publication

Used by selectors and configuration transactions:

```text
producer writes request payload
producer writes request generation LAST
consumer processes request
consumer writes result/payload
consumer writes handled/response generation LAST
```

The generation tells both sides which request a result belongs to. Do not infer request completion from a payload cell changing by itself.

### Durable publication

Generic Config Host uses the same idea for persistence, with the bank revision acting as the final commit token. A bank with zero/non-positive revision is intentionally incomplete even if some image/footer cells already contain new data.

## Address notation

- `S17` means stack cell 17 on the current device/service.
- `S32..S63` means an inclusive contiguous range.
- `S99+N` means a computed telemetry slot offset from stack cell 99.
- `d0`, `d1`, etc. are device screws on the IC running the script, not stack cells.

Do not confuse a dependency stored as a ReferenceId in `S2` with an IC screw wired as `d0`; both are used in this framework for different reasons.

## ControllerPhasePressure Policy result codes

In addition to generic success `5` and malformed candidate `-5`:

```text
-81  invalid evaporation/condensation factor
-82  invalid pressure bounds or StandbyPressure outside bounds
-83  invalid discrete Mode or OutputLogicType
```



## Generic Resource Core ABI v1

The Resource Core is an additive normalization layer above domain-specific implementations. PressureGrid remains the hardened production specialization; material and future power services use the same normalized contracts where the semantics genuinely match. See `docs/RESOURCE_GRID_CORE.md` and `docs/MATERIAL_GRID_FOUNDATION.md`.

### Generic Resource Endpoint

```text
S0   magic = 31415949
S1   ABI = 1
S2   ResourceClass
S3   ResourceType
S4   role/capability bits: export=1, import=2, storage=4
S5   ExportAvailable
S6   ImportCapacity
S7   MaxRate; 0 means unknown at the endpoint layer
S8   status
S9   NativeProvider ReferenceId
S10  NativeGeneration
S11  PublicationGeneration; payload first, generation LAST
S12  Unit: mole=1, item quantity=2, reagent=3, watt=4, joule=5
S13  precision flags: exact export=1, exact import=2, exact rate=4
```

`ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` maps PressureDomain Inventory ABI2 into this contract. `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` publishes the same ABI directly for one ItemHash in a 100-slot vending warehouse.

### Generic Resource Reservation

```text
S0   magic = 31415950
S1   ABI = 1
S2   Generic Resource Endpoint ReferenceId
S3   ResourceClass
S4   ResourceType
S5   role/capability bits
S6   ExportAvailable
S7   ImportCapacity
S8   MaxRate
S9   endpoint status
S10  Unit
S11  precision flags
S12  mirror generation; payload first, generation LAST
S13  build/transaction epoch; allocator-owned
S14  ReservedExport
S15  ReservedImport
S16  direction lock
```

The current `ic10/resource-grid-core/resource_reservation_v1_0.ic10` is intentionally domain-neutral. PressureGrid retains its specialized molar Reservation/Allocator ABI3, while MaterialGrid uses S13-S16 through Multi Material Allocator ABI2 for one-to-three-route exact-quantity ITEM transactions. A single cross-domain allocator has not yet been promoted.

### Resource Profile View for ITEM resources

Material item metadata is not a separate public profile ABI. A material consumer receives the same Resource Profile View ABI described above and requires:

```text
S8   ResourceClass = 2 ITEM
S9   ResourceType = ItemHash
S10  Unit = 2 ITEM_QUANTITY
S11  ProfileKind = 2 ITEM_STACK
S12  ProfileSchema = 1
S13  maximum stack quantity
S14  expected SlotClass
S15..S21 reserved
```

The 27 current ITEM records (10 ores, 7 basic ingots, 5 alloys, and 5 superalloys) are generated into the ResourceClass-partitioned shared catalog from `data/resource_profiles.json`.

### Resource Transform Catalog Store / Profile View

Resource Transforms use Store ABI6 with `CatalogSchemaId=HASH("CatalogSchema.ResourceTransform")`, **payload schema version 4**. All 17 current transforms fit one Store at 466/512 cells including Store header and item-directory overhead; five generated `ic10/transform-catalog/resource_transform_catalog_loader_*_v6_0.ic10` candidates exist only because of IC10 source limits.

Every transform is one self-contained item:

```text
12-cell header:
  TransformType, RequiredCapabilityMask, InputCount, OutputCount,
  Min/MaxPressure, Min/MaxTemperature, Flags, reserved x3
then InputCount x [ResourceClass, ResourceType, Unit, Quantity]
then OutputCount x [ResourceClass, ResourceType, Unit, Quantity]
then zero padding to 4-cell alignment
```

Capability bits are `SMELT_BASIC=1`, `FURNACE_ALLOY=2`, `ADVANCED_ALLOY=4`. Arc Furnace advertises 1, Furnace 3, Advanced Furnace 7. Compatibility is `(ActualCapabilities & RequiredCapabilityMask) == RequiredCapabilityMask`.

`ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` republishes Transform Profile ABI4: S3 capability mask, S4/S5 input/output counts, S8..S31 inputs, S32..S63 outputs, S64..S67 condition bounds. The **only current execution path** is the semantic pipeline under `ic10/material-transform/`, which handles one to three inputs atomically under Material Allocator ABI2.

### Generic Directory Hosts

The reusable live-directory infrastructure is defined in `docs/DIRECTORY_STANDARD.md` and `data/directory_schemas.json`.

`DIRECTORY_ADAPTER_ABI_V3` uses magic `31415983`, ABI2. Candidate adapters publish:

```text
S2 schema id             S3 schema version
S4 entry width           S5 capacity
S6 candidate count       S7 candidate generation
S8 odd/even sequence     S9 overflow
S10 mode: 1 snapshot, 2 registry
S11 freeze request token; 0 releases
S12 freeze acknowledgement token
S16.. packed candidate records
```

There are no consumer-facing domain magic/ABI fields in the Adapter contract.

`ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` consumes Snapshot-mode adapters and drives `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` (magic `31415981`, ABI1). The Host owns sorting, exact dedupe, overflow, A/B publication, stable generation, and publishes schema ID/version/width/capacity in S9..S12.

`ic10/directory-core/generic_registry_directory_host_v2_0.ic10` (magic `31415982`, ABI3) consumes Registry-mode Adapter ABI3 directly. It accepts only `DirectorySchema.CatalogStoreNode` v1 with width 6/capacity 64, publishes schema ID at S2, schema version at S19, width at S20, capacity at S21, and an odd/even publication sequence at S23. It freezes the Adapter during a rebuild; readers require S23 even and unchanged around registry reads.

Consumers identify a directory by **generic Host magic + Host ABI + DirectorySchemaId + DirectorySchemaVersion**. This is the canonical current directory contract; domain-specific compatibility facades are not retained.

### Resource discovery directories

The generic Resource Core has its own schemas on the shared Snapshot Host rather than forcing resource services into Controller discovery.

```text
Resource Endpoint Directory
S0/S1   31415981 / ABI1
S9/S10  HASH("DirectorySchema.ResourceEndpoint") / 1
S11/S12 width 3 / capacity 64
S2      active bank
S3/S4   generations A/B
S5/S6   endpoint counts A/B
S7/S8   overflow A/B
S32..223   bank A: 64 x [ResourceClass, ResourceType, EndpointRef]
S224..415  bank B: 64 x [ResourceClass, ResourceType, EndpointRef]

Resource Link Directory
S0/S1   31415981 / ABI1
S9/S10  HASH("DirectorySchema.ResourceLink") / 1
S11/S12 width 1 / capacity 64
S2      active bank
S3/S4   generations A/B
S5/S6   link counts A/B
S7/S8   overflow A/B
S32..95   bank A: 64 x [GenericResourceLinkRef]
S96..159  bank B: 64 x [GenericResourceLinkRef]
```

Both schemas inspect only coherently published Generic Resource services and publish explicit overflow rather than silently pretending a truncated snapshot is complete.

### Generic Resource Link

```text
S0   magic = 31415953
S1   ABI = 1
S2   source Generic Resource Reservation ReferenceId
S3   sink Generic Resource Reservation ReferenceId
S4   ResourceClass
S5   ResourceType
S6   native route/link class
S7   maximum transferable resource units/tick
S8   normalized cost hint; 0 when unavailable
S9   status
S10  NativeLink ReferenceId
S11  NativeLink generation
S12  PublicationGeneration; written LAST
S13  link flags
```

`ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` validates that the generic source/sink endpoints ultimately reference the same PressureDomain Inventories as the native PressureTransfer reservations before publishing the generalized link.

`ic10/material-grid/material_resource_link_v1_0.ic10` publishes the same Generic Link ABI for a discrete ITEM route. Its S2/S3 are the **source/sink Generic Resource Reservation ReferenceIds**; native material topology is carried separately in extension cells so generic planners do not confuse an Endpoint with its mutable Reservation surface.

For the Material Link, S13 currently uses flags value `7`: directed physical route + discrete/batch transport + observed-rate semantics. Generic consumers should treat flags as capabilities and should not infer pressure-flow behavior from them.


## MaterialGrid execution ABIs

The following ABIs specialize Generic Resource contracts for exact discrete ITEM movement and the first active Transform runtime. See `docs/MATERIAL_TRANSFER_SYSTEM.md` and `docs/ORE_PROCESSING_TRANSFORMS.md` for transaction narratives and wiring diagrams.

### Material Import-Slot Endpoint

`ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` publishes normal Generic Resource Endpoint ABI1 (`31415949`). It has no new public magic.

For the selected ITEM_STACK Resource Profile View:

```text
ResourceClass = ITEM
role/capability = import
Unit = ITEM_QUANTITY
ExportAvailable = 0
ImportCapacity = profile.MaxStack when device slot 0 is empty, else 0
NativeProvider = the processor/import device ReferenceId
NativeGeneration = ImportCount + ExportCount
```

Machine-specific readiness is deliberately not inferred here; Transform Admission owns processor readiness.

### Material Resource Link extensions

`ic10/material-grid/material_resource_link_v1_0.ic10` uses Generic Resource Link ABI1 in S0-S13 and adds:

```text
S14  Material Grant Guard ReferenceId
S15  Material Transfer Executor ReferenceId
S16  Material Feeder ReferenceId
S17  current Feeder buffer quantity
S18  current Feeder buffer ResourceType
S19  source Vending ReferenceId
S20  Stacker ReferenceId
S21  Logic Sorter ReferenceId
S22  sink native provider ReferenceId
S23  Executor completed epoch
S24  Executor status
S25  observed achieved ITEM_QUANTITY/tick
S26  Executor elapsed ticks
```

The Link snapshots source/sink Reservations and Feeder publication coherently and refuses publication if Guard or Executor ABI/publication surfaces are unavailable.

### Material Transfer Grant Guard ABI v1

Magic: `31415960`.

Public output:

```text
S0   magic
S1   ABI = 1
S2   capability mask = 0
S8   last consumed epoch
S9   active/granted exact quantity
S10  active/committed epoch
S11  status: 1 active, 0 no active grant, -1 invalid/consumed
S12  Material Link ReferenceId
S13  publication generation
```

Allocator-staged fields:

```text
S16  exact quantity
S17  staged epoch; written after staged identity payload
S18  Allocator ReferenceId
S19  source Resource Reservation ReferenceId
S20  sink Resource Reservation ReferenceId
S21  ResourceType
S22  Feeder ReferenceId
S23  Logic Sorter ReferenceId
S24  sink native provider ReferenceId
S25  Material Link ReferenceId
S26  Executor ReferenceId
```

The Guard activates only when the staged epoch equals Allocator S14 commit epoch and all current Link/Reservation/topology identities still match. Invalid epochs are consumed rather than becoming eligible again if wiring is later restored.

### Material Vending/Stacker Feeder ABI v1

Magic: `31415961`.

Wiring:

```text
d0 Vending Machine
d1 Stacker
d2 Logic Sorter
```

Observed/public state:

```text
S0   magic
S1   ABI = 1
S2   source Vending ReferenceId
S3   Stacker ReferenceId
S4   current Stacker buffer quantity
S5   current Stacker buffer ResourceType
S6   status: 0 idle, 1 exact batch ready, 2 emitted, -1 fault
S7   active/request epoch
S8   ready epoch
S9   emitted epoch
S10  publication generation
S11  Logic Sorter ReferenceId
```

Executor request surface:

```text
S16  ResourceType ItemHash
S17  exact desired quantity
S18  request epoch
S19  release-command epoch; Executor writes only after sink counter snapshot
```

Internal persistent state uses S20-S23. `S0` magic is also the reflash marker: when the same ABI image is reflashed, an in-flight prepared batch is retained instead of being cleared.

The request surface follows `ASYNC_REQUEST_V1 / LIVE_CURRENT`. Executor writes S16/S17 and resets S19 before publishing request epoch S18 **last**. Feeder resets request-specific S6 to idle and initializes its internal/hardware state before publishing matching current token S7 **last**. Immediate device-unavailable faults publish S6=-1 before S7, so a caller is never stranded behind an identity the Feeder will never expose. S8/S9 remain ready/emitted evidence, but consumers must first require S7 to equal the expected request epoch.

### Material Transfer Executor ABI v1

Magic: `31415958`.

Wiring:

```text
d0 Material Resource Link
d1 Material Feeder
d2 Material Grant Guard
```

```text
S0   magic
S1   ABI = 1
S2   capability mask = 0
S8   granted exact quantity
S14  active/last accepted epoch
S15  completed epoch
S16  execution status: 1 completed, 0 active/idle, -1 failed
S17  observed delivered ITEM_QUANTITY/tick
S18  elapsed ticks for completed/failed batch
S19  publication generation
S9   internal state: 0 idle, 1 wait-ready, 2 wait-emitted, 3 wait-sink
S10  elapsed internal ticks
S11  ResourceType
S12  sink native provider ReferenceId
S13  destination ImportCount snapshot taken BEFORE batch release
```

The pre-release S13 snapshot is a correctness requirement: it prevents a fast chute path from delivering the item before Executor begins observing destination completion. In WAIT_READY and WAIT_EMITTED the Executor first requires Feeder S7 to equal its active S2 epoch, then interprets Feeder S6 state; a stale failure/success from the previous batch therefore cannot terminate or advance the current transfer.

### Generic Material Transform Admission ABI v1

Magic `31415977`. `ic10/material-transform/material_transform_admission_v1_0.ic10` consumes Transform View ABI4, a live processor, and one output Resource Reservation. It accepts `InputCount=1..3`, requires exactly one output, derives the processor capability mask from the live processor PrefabHash, requires the transform capability subset, validates Power/Error, applies every declared pressure/temperature bound independently of processor class, validates descriptor units/quantities, and checks output Reservation identity/capacity. It publishes TransformType S2, processor Ref S3, input count S4, output quantity S5, output Reservation Ref S6, stable Transform Profile generation S7, status S8, publication generation S9, output ResourceType/Unit S10/S11, and the live processor capability mask S12.

### Material Transform Link Resolver ABI v1

Magic `31415978`. `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` consumes Admission, Transform View, and Resource Link Directory. It resolves each required input to a healthy Material Link whose ResourceType matches the descriptor and whose native sink is the exact admitted processor. S8 is TransformType, S9 InputCount, S10 processor Ref, S11 stable profile generation, S12 status, S13 publication generation, and S20..S31 contain up to three `[LinkRef, QuantityPerJob, ResourceType, ResourceClass]` records.

### Multi Reservation Stager ABI v1

Magic `31415979`. `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` is deliberately not commit authority. Allocator commands S9 (`1` stage, `2` cleanup), S10 epoch, S11 batch count and S12 request token. The Stager validates all 1..3 resolved links, provisionally reserves source/sink Resource Reservations, prepares each existing Grant Guard, records staged link/source/sink triples at S32..S40, and publishes S13 status/S14 acknowledged request token. Any failure enters cleanup and removes all partial reservations before returning failure.

### Material Reservation Allocator ABI v2

Magic `31415954`, ABI2 in `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10`. Request surface uses S8 BatchCount, S20 RuntimeRef and S21 RequestGeneration. The allocator asks the Stager to prepare every input first. Only after successful staging does it publish the common active epoch at **S14 last**. S22 is state/status, S13 is next epoch, S15 completed epoch, S16 consumed request generation, and S17..S19 coordinate Stager commands/results. On successful staging it publishes S22 before S16, satisfying the `ASYNC_REQUEST_V1` LIVE_CURRENT ordering while keeping S14 as the separate transaction commit authority. `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` requires Material Allocator **ABI2 exactly**. No Guard can activate from merely staged state because S14 remains zero until the atomic commit point.

### Generic Material Transform Runtime ABI v2

Magic `31415980`. `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` wires `d0` processor, `d1` Admission, `d2` Resolver, `d3` Allocator ABI2 and `d4` output Reservation. S2 is requested batch count, S3 request generation, S4 internal state, S5 status, S6 current accepted request token, S7 committed material epoch, S9/S10 bind Admission/Resolver generations, S11/S12 snapshot output quantity/generation, and S13 is output-wait ticks. It resets S5 before publishing S6 and binds even immediately-invalid accepted requests to S6 before reporting fault, so callers cannot wait forever on an identity that is never published. It activates the processor only after every input Link reports completion of the common epoch and completes only after a newer coherent output Reservation snapshot grows by the declared output quantity.


## Item Storage / Reservation extensions (Item 7)

Item Storage keeps Generic Resource Endpoint ABI1 and Generic Resource Reservation ABI1 base cells unchanged. It uses previously unused extension cells rather than introducing a parallel warehouse ABI.

### Material ITEM Endpoint storage extension

`S14` remains the existing Resource Profile View ReferenceId consumed by Material Link. Storage metadata is:

```text
S35 AccessKind
S36 PolicyFlags
S37 ReserveFloor
S38 FirstSourceSlot
S39 FirstSourceQuantity
S40 FirstEmptySlot
```

Current providers are the Vending, LArRE storage, direct-slot storage, dedicated SDB lower-bound storage, and exact export-slot Endpoint services under their semantic `ic10/item-storage-*` families.

Endpoint precision adds bit 3 = conservative ExportAvailable lower bound and bit 4 = conservative ImportCapacity lower bound. SDB uses `S13=24`; it never labels native occupied-stack count as exact total item quantity.

### Generic Resource Reservation Item-7 ownership extension

```text
S17 OwnerReferenceId
S18 OwnerPlanEpoch
S19 committed semantic Reservation mirror generation
S20 Endpoint PublicationGeneration represented by the current semantic mirror
S21 opaque Endpoint AccessKind mirror
S22 opaque action hint 0 / FirstSourceSlot
S23 opaque action hint 1 / FirstSourceQuantity
S24 opaque action hint 2 / FirstEmptySlot
S25 committed action source slot
S26 committed action quantity
S27 committed action destination slot
```

`S12` remains the Reservation mirror's generation-last publication token. Physical consumers require current Reservation `S12 == committed S19`; the Reservation advances S12 only when reservation-relevant endpoint state or action hints change. LArRE still revalidates the actual slot ItemHash/Quantity before pickup.

### Resource Reservation Directory v1

Schema: `DirectorySchema.ResourceReservation`, width 3, capacity 64:

```text
[ResourceClass, ResourceType, ReservationReferenceId]
```

Adapter: `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10`.

### ITEM reservation services

- `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10`, magic `31415987`: read-only up-to-six-leg export/import quote; request is S11 type, S12 quantity, S13 direction, S14 required capabilities, S15 request generation; response token S16 last.
- `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10`, magic `31415988`: coherent quote commit; request is S11 expected Selector token, S12 request generation; response token S13 last; publishes owner ReferenceId/epoch and captured Endpoint generation into each Reservation.
- `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10`, magic `31415990`: clears only exact owner ReferenceId + epoch; response token S4 last.
- `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10`, magic `31415991`: requires paired source/destination ownership and current semantic Reservation-generation equality before outbound/inbound movement; response token S8 last.

### Cargo LArRE Storage Service ABI1

`ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10`, magic `31415986`, supports operation 1 SCAN, 2 MOVE, and 3 RECOVER. Request token is S8; response token S14 is written last. MOVE uses S15 ExpectedQuantity and validates exact ItemHash/Quantity immediately before pickup. Status `-6` means failure with the hand still occupied and requires RECOVER.

### LArRE ITEM Storage Endpoint raw movement extension

`ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` remains Generic Resource Endpoint ABI1. Its configuration is S20 StorageStation, S21 FirstSlot, S22 SlotCount; policy S36 and ReserveFloor S37. The serialized raw movement surface is S24 operation, S25/S26 source, S27/S28 destination, S30 expected quantity, S31 request token last; S32 status, S33 moved quantity, S34 response token last.

### SDB / Stacker Feeder

`ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` deliberately reuses Material Feeder magic `31415961`/ABI1. The SDB source therefore plugs into the existing Material Link / Grant Guard / Executor transaction rather than creating a new processor-delivery protocol.

## Process Utility ABIs — current

### ProcessCondition ABI1

Magic `31416048`, ABI1. `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` and `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` publish the common surface:

```text
S2 Target ReferenceId
S3 semantic FLUID ResourceType
S4/S5 minimum/maximum pressure kPa
S6/S7 minimum/maximum temperature K
S8 unmet-condition bitmask
S9 process identity
S10 Active
S11 PublicationGeneration LAST
S12 Status
S13 Strategy
S14/S15 pressure/temperature target hints
```

`ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` projects this demand as PressureDomain ABI2; `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` projects an Advanced Furnace embedded pump as PressureTransfer ABI2 under the ordinary GrantGuard; `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` reuses PurityGuard ABI1 for two-component mixtures; the gas-mixer and thermal-mixer utility controllers own composition/thermal Gas Mixer writes. ProcessCondition has no owner/epoch fields and never authorizes resource movement. See `docs/PROCESS_UTILITY_ORCHESTRATION.md`.

## Power Management ABIs — current

Item 9 uses the existing Generic Resource Endpoint, Reservation, Link, Directory, and Job ABIs. `DirectorySchema.PowerReservation` v1 records `[DispatchKey,PolicyId,ReservationReferenceId]`. For Generic Resource Reservation ABI1, `S6` mirrors Endpoint `ExportAvailable` and `S7` mirrors Endpoint `ImportCapacity`; `S5` remains the role bitmap.

`ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` is Job Command Gateway ABI3 with four independent producer lanes A manufacturing, B dependency cancellation, C dependency child creation, and D POWER lifecycle. `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` remains the sole physical Job Store command writer. `ic10/power-grid/` implements power Endpoint/Link/discovery/dispatch/reservation/actuation; the shared generic Job selector plus `ic10/power-jobs/` implement finite `JobType.POWER` policy transactions. See `docs/POWER_MANAGEMENT.md`.

## Live Commission Snapshot Probe ABI1

`ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` is a read-only on-demand Item-12 field tool. Magic `31416051`, ABI1. `S2 RequestToken` is caller-published last and `S3 ResponseToken` is probe-published last. `S6 DescriptorGeneration` fences the six descriptors at `S32..S49`; `S7` echoes the captured descriptor generation. `S4` reports complete/error state, `S5` is the number of successful observations, and `S9` identifies the first failed ordinal.

Each descriptor is `[Mode, FieldOrStackCell, FenceStackCell]`: mode 0 disabled, mode 1 dynamic LogicType read, mode 2 stack-cell read with optional positive before/after generation fence. Results at `S64..S93` are six `[ReferenceId, Mode, Status, Value, FenceGeneration]` records. The probe contains no external `s/sd/put/putd` mutation instruction; it is evidence collection only. See `docs/LIVE_COMMISSIONING.md`.

## Stack Cell Monitor ABI1

`ic10/live-commissioning/stack_cell_monitor_v1_0.ic10` is an on-demand,
human-visible probe for one stack cell on a standard or compact IC housing.
Magic `31416052`, ABI1, and it publishes the common header with `HAS_STATE` and
`HAS_GENERATION`. `d0` is the target IC housing, `d1` is a Logic Memory whose
`Setting` selects address `0..511`, and optional `d2` mirrors the sampled value.
It never writes the target or selector.

```text
S5  own state: 1 booting, 4 target/selector missing, 2 ready
S7  own sample generation, published last
S8  status: 1 finite value, 2 captured NaN, -1 target missing,
            -2 target is not an IC housing, -3 selector missing/unsupported,
            -4 address is NaN, fractional, negative, or above 511
S9  selected address
S10 sampled value; 0 for pre-capture errors
S11 target ReferenceId
```

## Stack Header Reader ABI1

`ic10/live-commissioning/stack_header_reader_v1_0.ic10` is the generic reader for
the common header. Magic `31416067`, ABI1. `d0` is the target IC housing and
optional `d1` mirrors the discovered magic to a `Setting` device. It reads only
`S0..S7` of the target, validates the shape, and republishes every field the
target's mask declares. Undeclared fields publish `0`.

```text
S5  own state: 1 booting, 4 target missing or not a housing, 2 ready
S7  own sample generation, published last
S8  status: 3 valid header, -1 target missing,
            -2 target is not an IC housing,
            -5 S0 holds no usable magic,
            -6 header fields or extension bounds are invalid
S9  discovered ServiceMagic      S13 discovered ExtensionBase
S10 discovered ServiceABI        S14 discovered State
S11 discovered CapabilityMask    S15 discovered TelemetryBase
S12 discovered SchemaId          S16 discovered Generation
S17 target ReferenceId
```

## Controller runtime identities

The seven Generic Telemetry runtimes each publish their own service magic in the
common header at `S0`, and point `S7` at the telemetry block that stays at `S96`.
The telemetry magic `27182818` continues to identify that block, not the service:
its consumers read `S96` exactly as before.

## Common Stack Header v1

Every service identifies itself in the first five cells:

```text
S0 ServiceMagic — the registered magic below; identity   (always)
S1 ServiceABI                                            (always)
S2 CapabilityMask — bits 0..4, 5+ reserved zero          (always)
S3 SchemaId — HASH("<schema>.v<version>")      (mask bit 0)
S4 ExtensionBase                               (mask bit 1)
S5 State: bits 0..3 field (0 unreported,1 boot,2 ready,3 working,
          4 blocked,5 fault), bits 4..7 reserved zero,
          bits 8..52 service-specific                 (mask bit 2)
S6 TelemetryBase                               (mask bit 3)
S7 Generation — initialized 0, advanced, published last (mask bit 4)
```

A cell is read only when its mask bit is set. `S5` and `S7` are the header cells a
service may change after publication. A stack cell is a double, so its exact
integer width is 53 bits; the game caps `ext`/`ins` bit fields at the same 53. Extensions use magic `31416054`, version 1,
an inclusive length in `4..192`, begin at `S8` or later, and must end inside
`S0..S511`. Family payload begins
after the header. See `docs/STACK_ABI_ENVELOPE.md` for identity, zero/unknown,
compatibility, upgrade, inventory, and migration rules.
