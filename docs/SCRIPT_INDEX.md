# IC10 Script Index

Generated from the deployable `ic10/` inventory. Semantic paths plus version suffixes are the executable source identity; historical numeric source ordinals are intentionally not part of filenames. Deployment family/class metadata is resolved from `data/source_manifest.json`.

Production IC10 programs: 174

## Script index

| Current file | Lines | Layer | Deployment family | Class | Human purpose |
|---|---:|---|---|---|---|
| `ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10` | 114 | Catalog control plane | `catalog-control-plane` | `conditional-resident` | Coordinator Core ABI3; claims Stores, assigns runtime ordinals, and owns topology/capacity epochs. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10` | 89 | Catalog control plane | `catalog-control-plane` | `conditional-resident` | Publishes Generic Store membership as Directory Adapter ABI3 registry candidates. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10` | 99 | Catalog telemetry | `catalog-control-plane` | `on-demand` | Aggregates Store lifecycle counts and used/free/capacity telemetry; marks missing nodes. |
| `ic10/catalog-control-plane/catalog_coordinator_directory_view_v2_0.ic10` | 45 | Catalog diagnostics | `catalog-control-plane` | `on-demand` | Selectable Store-directory view plus Coordinator aggregate health telemetry. |
| `ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10` | 54 | Catalog recovery | `catalog-control-plane` | `on-demand` | Rebinds persisted Stores to a replacement Coordinator with a higher CoordinatorEpoch. |
| `ic10/catalog-control-plane/catalog_inspector_v4_0.ic10` | 114 | Catalog diagnostics | `catalog-control-plane` | `on-demand` | Generic Store ABI6 / Coordinator ABI4 inspector for node identity, item capacity, topology, and telemetry. |
| `ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10` | 108 | Catalog migration | `catalog-control-plane` | `on-demand` | Plans whole-item compaction from DRAINING Stores into compatible live Store capacity. |
| `ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10` | 89 | Catalog migration | `catalog-control-plane` | `on-demand` | Copies and commits one whole item to reserved destination capacity, then reclaims the source tail. |
| `ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10` | 108 | Catalog control plane | `catalog-control-plane` | `on-demand` | Loader Router ABI3; places whole Loader ABI5 items into live unreserved Store capacity. |
| `ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10` | 55 | Catalog lifecycle | `catalog-control-plane` | `on-demand` | Safely retires an empty Store and repairs neighboring topology. |
| `ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10` | 118 | Catalog storage | `catalog-control-plane` | `conditional-resident` | Generic Store ABI6 node with item directory + payload heap; imports runtime-routed relocatable items. |
| `ic10/controller-config/config_input_bridge_v1_0.ic10` | 61 | Configuration adapter | `controller-config` | `commissioning` | Maps Resolver active ordinal/value into Editor physical slots. |
| `ic10/controller-config/generic_config_committer_v1_1.ic10` | 97 | Configuration UI | `controller-config` | `commissioning` | Copies staged values into Host candidate config and starts apply. |
| `ic10/controller-config/generic_config_editor_v1_0.ic10` | 109 | Configuration UI | `controller-config` | `commissioning` | Owns staged config image and Save/Reload/Apply UI state. |
| `ic10/controller-config/generic_config_loader_v1_2.ic10` | 119 | Configuration UI | `controller-config` | `commissioning` | Loads selected Host/Profile state and builds active-ordinal mapping. |
| `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` | 120 | Persistence | `controller-config` | `resident` | BANKED_TRANSACTION REVISION_BANK host: owns candidate/effective config, A/B persistence, recovery, and post-commit replay acknowledgement. |
| `ic10/controller-discovery/controller_directory_adapter_v4_0.ic10` | 58 | Discovery adapter | `controller-discovery` | `commissioning` | Publishes Controller Directory Adapter ABI3 candidates; Generic Adapter Bridge + Snapshot Host own publication. |
| `ic10/controller-discovery/controller_selector_v3_0.ic10` | 109 | Selection | `controller-discovery` | `commissioning` | Directly derives type/member groups from the sorted Generic Controller Directory and resolves one ReferenceId; rejects overflowed discovery. |
| `ic10/controller-phase-pressure/controller_phase_pressure_runtime_v1_1.ic10` | 124 | Runtime | `controller-phase-pressure` | `resident` | Derives pressure requirements from a coherently committed medium profile; telemetry ABI2. |
| `ic10/controller-phase-pressure/phase_pressure_config_policy_v1_0.ic10` | 94 | Family semantics | `controller-phase-pressure` | `resident` | PhasePressure bounds/factors/mode validation and signature. |
| `ic10/controller-pi/controller_pi_runtime_v1_1.ic10` | 119 | Runtime | `controller-pi` | `resident` | Continuous PI controller consuming Generic Host effective config. |
| `ic10/controller-pi/pi_config_policy_v1_0.ic10` | 86 | Family semantics | `controller-pi` | `resident` | PI defaults, masks, validation, normalization, signature. |
| `ic10/controller-sequencer/controller_sequencer_runtime_v1_0.ic10` | 123 | Runtime | `controller-sequencer` | `resident` | Fill/settle/drain discrete state-machine controller. |
| `ic10/controller-sequencer/sequencer_config_policy_v1_0.ic10` | 97 | Family semantics | `controller-sequencer` | `resident` | Sequencer defaults, timing/threshold validation, signature. |
| `ic10/dependency-planning/dependency_ancestry_guard_v1_0.ic10` | 80 | Dependency safety | `dependency-planning` | `conditional-resident` | Bounds dependency depth to two edges and rejects self/immediate-ancestor producer cycles. |
| `ic10/dependency-planning/dependency_cancellation_guard_v1_0.ic10` | 52 | Dependency cleanup | `dependency-planning` | `conditional-resident` | Detects terminal/reaped parents and requests reference-aware dependency cleanup through the Planner. |
| `ic10/dependency-planning/dependency_child_creator_v2_0.ic10` | 106 | Dependency creation | `dependency-planning` | `conditional-resident` | Builds one bounded child Job request after producer, ancestry, output, quantity, and parent-generation checks. |
| `ic10/dependency-planning/dependency_child_validity_v1_0.ic10` | 59 | Dependency validation | `dependency-planning` | `conditional-resident` | Validates one child Job against live Job Store state and current producer/catalog output semantics. |
| `ic10/dependency-planning/dependency_claim_view_v1_0.ic10` | 120 | Dependency sharing | `dependency-planning` | `conditional-resident` | Read-only active future-output claim view with per-parent claim aggregation and unclaimed-surplus accounting. |
| `ic10/dependency-planning/dependency_plan_builder_v2_0.ic10` | 74 | Dependency planning | `dependency-planning` | `conditional-resident` | Builds new dependency plans using coherent inventory, active future-output claims, and bounded child creation. |
| `ic10/dependency-planning/dependency_plan_evaluator_v2_0.ic10` | 86 | Dependency evaluation | `dependency-planning` | `conditional-resident` | Revalidates child identity/state and parent inventory; child completion alone never releases the parent. |
| `ic10/dependency-planning/dependency_plan_release_advisor_v1_0.ic10` | 59 | Dependency cleanup | `dependency-planning` | `conditional-resident` | Read-only release advisor deciding whether a child is still shared/active and therefore cancellable. |
| `ic10/dependency-planning/dependency_plan_store_v2_0.ic10` | 115 | Dependency persistence | `dependency-planning` | `conditional-resident` | Owns 32 committed eight-cell parent/child dependency plan records with ParentJobId commit markers. |
| `ic10/dependency-planning/existing_dependency_plan_controller_v1_0.ic10` | 112 | Dependency control | `dependency-planning` | `conditional-resident` | Existing-plan controller: evaluate, replan, clear-ready, or reference-aware cancel without owning Plan Store mutation. |
| `ic10/dependency-planning/generic_job_monitor_v1_0.ic10` | 67 | Dependency observation | `dependency-planning` | `conditional-resident` | Coherently resolves one exact JobId and its current state/generation from Generic Job Store. |
| `ic10/dependency-planning/item_producer_resolver_v1_0.ic10` | 78 | Dependency metadata | `dependency-planning` | `conditional-resident` | Generated reverse producer index from ITEM output ResourceType to transform or print producer identity. |
| `ic10/dependency-planning/job_inventory_preflight_v1_0.ic10` | 111 | Dependency planning | `dependency-planning` | `conditional-resident` | Quotes current ITEM inventory across Resource Reservations and publishes exact/lower-bound deficit plus rolling quote fingerprints. |
| `ic10/dependency-planning/job_requirement_view_v1_0.ic10` | 97 | Dependency planning | `dependency-planning` | `conditional-resident` | Normalizes TRANSFORM and PRINT job requirements into one bounded ITEM requirement/output view. |
| `ic10/dependency-planning/manufacturing_dependency_gate_v2_0.ic10` | 96 | Manufacturing scheduling | `dependency-planning` | `conditional-resident` | Dependency Gate ABI2; only dependency-ready jobs reach the existing Transform/Print Driver Router. |
| `ic10/dependency-planning/manufacturing_dependency_planner_v1_0.ic10` | 120 | Dependency control | `dependency-planning` | `conditional-resident` | Sole Dependency Plan Store mutation coordinator; applies plan upsert/clear and cancellation sequencing. |
| `ic10/dependency-planning/manufacturing_reagent_resolver_v1_0.ic10` | 115 | Manufacturing metadata | `dependency-planning` | `conditional-resident` | Resolves Recipe manufacturing-reagent aliases into canonical ITEM ResourceTypes for dependency planning. |
| `ic10/dependency-planning/new_dependency_plan_controller_v1_0.ic10` | 91 | Dependency control | `dependency-planning` | `conditional-resident` | New-plan controller: orchestrates bounded plan construction and returns mutation intent to the sole Planner. |
| `ic10/diagnostics/console_registry_v1_1.ic10` | 85 | Discovery | `diagnostics` | `commissioning` | Discovers diagnostic consoles and mirror sinks and publishes stable identities. |
| `ic10/diagnostics/console_selector_v1_1.ic10` | 93 | Selection | `diagnostics` | `commissioning` | Resolves console ordinals and post-commit advance. |
| `ic10/diagnostics/diagnostic_hash_console_mode_v1_0.ic10` | 47 | Diagnostics | `diagnostics` | `commissioning` | Sets Console circuitboard Mode (HashType) from IC through logic slot set. |
| `ic10/diagnostics/diagnostic_input_bridge_v1_0.ic10` | 114 | Diagnostics adapter | `diagnostics` | `commissioning` | Owns diagnostic desired-state/change generations. |
| `ic10/diagnostics/diagnostic_mapping_editor_v1_2.ic10` | 121 | Diagnostics | `diagnostics` | `commissioning` | Commits resolved display/controller/channel mappings. |
| `ic10/diagnostics/diagnostic_renderer_v1_1.ic10` | 67 | Diagnostics | `diagnostics` | `commissioning` | Renders generic telemetry into committed displays; accepts compatible telemetry ABI revisions. |
| `ic10/diagnostics/diagnostic_selector_bridge_v1_0.ic10` | 47 | Diagnostics adapter | `diagnostics` | `commissioning` | Publishes atomic desired controller/console selection. |
| `ic10/directory-core/generic_directory_adapter_bridge_v1_0.ic10` | 107 | Directory infrastructure | `directory-core` | `conditional-resident` | Consumes frozen Adapter ABI2 snapshots and drives Generic Snapshot Host BEGIN/ADD/COMMIT. |
| `ic10/directory-core/generic_registry_directory_host_v2_0.ic10` | 116 | Directory infrastructure | `directory-core` | `conditional-resident` | Generic Registry Directory Host ABI3; consumes Adapter ABI2 and persists NodeId-indexed membership. |
| `ic10/directory-core/generic_snapshot_directory_host_v1_0.ic10` | 120 | Directory infrastructure | `directory-core` | `conditional-resident` | Generic sorted A/B Snapshot Directory Host: width 1..3, capacity 64, dedupe/overflow/generation. |
| `ic10/generic-jobs/generic_job_command_gateway_v3_0.ic10` | 120 | Generic job control | `generic-jobs` | `conditional-resident` | Four-lane Job command arbiter for manufacturing lifecycle, dependency cancellation/creation, and POWER lifecycle requests. |
| `ic10/generic-jobs/generic_job_selector_v3_0.ic10` | 120 | Generic job scheduling | `generic-jobs` | `conditional-resident` | Read-only coherent Job Store selector: default TRANSFORM/PRINT mode or exact JobType mode, Priority descending, JobId cursor fairness. |
| `ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10` | 119 | Generic job mutation | `generic-jobs` | `conditional-resident` | Sole Item-8 Job Store mailbox writer; atomically allocates child slots and checks parent JobId/generation/state. |
| `ic10/generic-jobs/generic_job_store_v1_0.ic10` | 120 | Generic job substrate | `generic-jobs` | `conditional-resident` | BANKED_TRANSACTION SELECTOR_BANK store: 32 Generic Job ABI1 records with Store-owned JobIds, optimistic generation, ABI-gated recovery, and crash-safe publication. |
| `ic10/input-profile-catalog/input_profile_catalog_loader_00_v4_0.ic10` | 109 | Input metadata | `input-profile-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_catalog_loader_01_v4_0.ic10` | 82 | Input metadata | `input-profile-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_catalog_loader_02_v4_0.ic10` | 112 | Input metadata | `input-profile-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate containing whole self-contained Input Profile items. |
| `ic10/input-profile-catalog/input_profile_view_v5_0.ic10` | 111 | Input metadata | `input-profile-catalog` | `conditional-resident` | Selects one Input schema-v3 Store ABI6 catalog context and republishes Generic Input Profile ABI1. |
| `ic10/item-storage-common/item_resource_reservation_allocator_v1_0.ic10` | 101 | Item storage allocation | `item-storage-common` | `conditional-resident` | Commits one coherent ITEM reservation quote with allocator identity, epoch, direction, and mirror-generation fencing. |
| `ic10/item-storage-common/item_resource_reservation_selector_v1_0.ic10` | 115 | Item storage planning | `item-storage-common` | `conditional-resident` | Read-only bounded ITEM reservation selector; aggregates up to six physical source/destination reservations without mutation. |
| `ic10/item-storage-direct/direct_item_storage_endpoint_v1_0.ic10` | 90 | Item storage | `item-storage-direct` | `conditional-resident` | Publishes bounded directly readable slot storage as a policy-aware Generic ITEM Resource Endpoint. |
| `ic10/item-storage-larre/larre_cargo_storage_service_v1_0.ic10` | 119 | Item storage | `item-storage-larre` | `conditional-resident` | Serialized Cargo LArRE owner for proxy-slot SCAN and whole-stack MOVE_STACK operations. |
| `ic10/item-storage-larre/larre_item_storage_endpoint_v1_0.ic10` | 120 | Item storage | `item-storage-larre` | `conditional-resident` | Publishes LArRE-accessible slot storage as Generic ITEM Resource Endpoint and serializes all LArRE movement requests. |
| `ic10/item-storage-larre/larre_storage_reserved_move_client_v1_0.ic10` | 115 | Item storage movement | `item-storage-larre` | `conditional-resident` | Validates paired source/destination reservations and drives serialized LArRE outbound, inbound, or held-item recovery movement. |
| `ic10/item-storage-sdb/material_sdb_stacker_feeder_v1_0.ic10` | 120 | Material feeder | `item-storage-sdb` | `conditional-resident` | Adapts a dedicated SDB Silo plus Stacker to Material Feeder ABI1 and meters exact requested quantities after FIFO stack export. |
| `ic10/item-storage-sdb/sdb_silo_item_endpoint_v1_0.ic10` | 82 | Item storage | `item-storage-sdb` | `conditional-resident` | Publishes a dedicated SDB Silo as conservative lower-bound ITEM availability/capacity without pretending stack count is exact quantity. |
| `ic10/item-storage-vending/material_vending_inventory_v1_0.ic10` | 112 | Material inventory | `item-storage-vending` | `conditional-resident` | Incrementally scans a Vending Machine for one ItemHash and publishes Generic Resource Endpoint ABI1. |
| `ic10/live-commissioning/live_commission_snapshot_probe_v1_0.ic10` | 108 | On-demand commissioning | `live-commissioning` | `on-demand` | Read-only six-source live commissioning snapshot probe with optional stack-generation fencing. |
| `ic10/live-commissioning/stack_cell_monitor_v1_0.ic10` | 46 | On-demand commissioning | `live-commissioning` | `on-demand` | Read-only target IC stack-cell probe with a Logic Memory address selector and visible value mirror. |
| `ic10/live-commissioning/stack_header_reader_v1_0.ic10` | 118 | On-demand commissioning | `live-commissioning` | `on-demand` | Read-only common stack header reader: reports a target's identity, ABI, capabilities, and declared fields. |
| `ic10/manufacturing/generic_print_runtime_v2_0.ic10` | 113 | Manufacturing runtime | `manufacturing` | `conditional-resident` | Runs a bounded printer batch through native ExecuteRecipe and verifies coherent ExportCount completion. |
| `ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10` | 106 | Manufacturing selection | `manufacturing` | `conditional-resident` | Generic schema/version-qualified candidate selector for TransformLane or PrinterExecution snapshots; supports tier or bitmask capability matching. |
| `ic10/manufacturing/manufacturing_driver_router_v2_0.ic10` | 76 | Manufacturing scheduling | `manufacturing` | `conditional-resident` | Normalizes TRANSFORM and PRINT domain drivers behind one scheduler-facing result ABI. |
| `ic10/manufacturing/manufacturing_scheduler_v1_0.ic10` | 120 | Manufacturing scheduling | `manufacturing` | `conditional-resident` | Sole production Generic Job lifecycle writer; applies one legal generation-checked edge at a time. |
| `ic10/manufacturing/print_candidate_executor_v2_0.ic10` | 121 | Manufacturing execution | `manufacturing` | `conditional-resident` | Evaluates one print candidate, reserves output capacity, resolves/material-allocates reagents, and launches the generic print runtime. |
| `ic10/manufacturing/print_job_driver_v2_0.ic10` | 120 | Manufacturing driver | `manufacturing` | `conditional-resident` | Resolves Recipe execution shape, iterates PrinterExecution candidates, and normalizes print planning/execution progress for the scheduler. |
| `ic10/manufacturing/print_material_resolver_v1_0.ic10` | 119 | Manufacturing planning | `manufacturing` | `conditional-resident` | Maps Recipe reagent semantics onto reachable MaterialGrid ResourceTypes and publishes transform-compatible multi-input records. |
| `ic10/manufacturing/transform_candidate_executor_v2_0.ic10` | 81 | Manufacturing execution | `manufacturing` | `conditional-resident` | Evaluates and launches one transform candidate through the existing Admission/Resolver/Stager/Allocator/Runtime transaction. |
| `ic10/manufacturing/transform_candidate_readiness_v1_0.ic10` | 109 | Manufacturing readiness | `manufacturing` | `conditional-resident` | Fences Transform Profile/Admission/Link-Resolver completion to one exact transform candidate request before execution. |
| `ic10/manufacturing/transform_job_driver_v2_0.ic10` | 114 | Manufacturing driver | `manufacturing` | `conditional-resident` | Iterates TransformLane candidates and normalizes transform planning/execution progress for the scheduler. |
| `ic10/manufacturing/transform_lane_directory_adapter_v1_0.ic10` | 78 | Manufacturing discovery | `manufacturing` | `conditional-resident` | Publishes schema-qualified TransformLane Adapter ABI2 candidates with processor identity and common ProcessorSpec. |
| `ic10/material-grid/material_export_slot_endpoint_v1_0.ic10` | 52 | Material endpoint | `material-grid` | `conditional-resident` | Publishes one exact export slot, such as a Chute Export Bin, as a source-only ITEM Resource Endpoint. |
| `ic10/material-grid/material_import_slot_endpoint_v1_0.ic10` | 62 | Material endpoint | `material-grid` | `conditional-resident` | Publishes one processor import slot as a typed ITEM sink endpoint. |
| `ic10/material-grid/material_resource_link_v1_0.ic10` | 117 | Material link | `material-grid` | `conditional-resident` | Publishes a Vending/Stacker/Sorter route as Generic Resource Link ABI1 with native topology identity. |
| `ic10/material-grid/material_transfer_executor_v1_0.ic10` | 119 | Material execution | `material-grid` | `conditional-resident` | Executes one Guard-authorized exact material batch and confirms destination import. |
| `ic10/material-grid/material_transfer_grant_guard_v1_0.ic10` | 119 | Material safety | `material-grid` | `conditional-resident` | Topology-binds committed material grants and consumes invalid epochs. |
| `ic10/material-grid/material_vending_stacker_feeder_v1_0.ic10` | 120 | Material feeder | `material-grid` | `conditional-resident` | Uses Vending + Stacker + Logic Sorter to prepare and release an exact routed item quantity. |
| `ic10/material-transform/generic_material_transform_runtime_v2_0.ic10` | 120 | Transform runtime | `material-transform` | `conditional-resident` | Runs generic catalog-defined transforms and confirms coherent output growth. |
| `ic10/material-transform/material_transform_admission_v1_0.ic10` | 123 | Transform admission | `material-transform` | `conditional-resident` | Generic 1..3-input capability-based transform admission: processor conditions and output capacity. |
| `ic10/material-transform/material_transform_link_resolver_v1_0.ic10` | 123 | Transform planning | `material-transform` | `conditional-resident` | Resolves typed Material Links for every transform input against the exact processor. |
| `ic10/material-transform/multi_material_reservation_allocator_v2_0.ic10` | 115 | Material allocation | `material-transform` | `conditional-resident` | Allocator ABI2 atomically commits one common epoch after every input is staged. |
| `ic10/material-transform/multi_material_reservation_stager_v1_0.ic10` | 119 | Material allocation | `material-transform` | `conditional-resident` | Stages 1..3 input reservations and Guard payloads without publishing the commit epoch. |
| `ic10/power-grid/power_battery_endpoint_v1_0.ic10` | 113 | Power resource | `power-grid` | `conditional-resident` | Publishes bidirectional battery POWER capacity with reserve, target, rate, and policy-override semantics. |
| `ic10/power-grid/power_consumer_endpoint_v1_0.ic10` | 59 | Power resource | `power-grid` | `conditional-resident` | Publishes one managed POWER consumer demand and priority/shedding policy as a Generic Resource Endpoint. |
| `ic10/power-grid/power_dispatch_cycle_v1_0.ic10` | 53 | Power planning | `power-grid` | `conditional-resident` | Owns Power PlanStore BEGIN -> sweep -> COMMIT transaction boundaries. |
| `ic10/power-grid/power_dispatch_plan_store_v1_0.ic10` | 87 | Power planning | `power-grid` | `conditional-resident` | Owns one coherent bounded eight-flow power dispatch plan with odd/even publication fencing. |
| `ic10/power-grid/power_dispatch_sweep_v1_0.ic10` | 80 | Power planning | `power-grid` | `conditional-resident` | Sweeps priority-ordered sinks, stages flows, and records shed/critical-shortage state. |
| `ic10/power-grid/power_link_executor_v1_0.ic10` | 94 | Power execution | `power-grid` | `conditional-resident` | Sole transformer Setting/On actuator with exact plan, source/sink Reservation, epoch, and Link fencing. |
| `ic10/power-grid/power_link_selector_v1_0.ic10` | 74 | Power planning | `power-grid` | `conditional-resident` | Resolves a live source-to-sink POWER Resource Link and computes transformer source-side overhead. |
| `ic10/power-grid/power_load_executor_v1_0.ic10` | 90 | Power execution | `power-grid` | `conditional-resident` | Break-before-make actuator for managed consumer and battery On state under committed plan authority. |
| `ic10/power-grid/power_plan_validator_v1_0.ic10` | 103 | Power safety | `power-grid` | `conditional-resident` | Revalidates a complete power plan against exact Reservation and Link generations before mutation. |
| `ic10/power-grid/power_producer_endpoint_v1_0.ic10` | 63 | Power resource | `power-grid` | `conditional-resident` | Publishes one exact POWER producer/aggregate supply as a Generic Resource Endpoint. |
| `ic10/power-grid/power_reservation_allocator_v1_0.ic10` | 84 | Power allocation | `power-grid` | `conditional-resident` | Validates, commits, cleans old/orphan epochs, and publishes the active power allocator authority. |
| `ic10/power-grid/power_reservation_committer_v1_0.ic10` | 97 | Power allocation | `power-grid` | `conditional-resident` | Commits one common POWER reservation epoch with shared-source aggregation and foreign-owner protection. |
| `ic10/power-grid/power_reservation_directory_adapter_v1_0.ic10` | 103 | Power discovery | `power-grid` | `conditional-resident` | Publishes priority-ordered PowerReservation candidates through Generic Directory Adapter ABI3. |
| `ic10/power-grid/power_sink_flow_builder_v1_0.ic10` | 97 | Power planning | `power-grid` | `conditional-resident` | Builds one sink flow, retrying later sources until a compatible physical path is found. |
| `ic10/power-grid/power_sink_selector_v1_0.ic10` | 68 | Power planning | `power-grid` | `conditional-resident` | Selects managed POWER sinks in critical/sheddable/charge dispatch order. |
| `ic10/power-grid/power_source_selector_v1_0.ic10` | 91 | Power planning | `power-grid` | `conditional-resident` | Selects available POWER sources by preference while accounting for staged use and battery direction. |
| `ic10/power-grid/power_static_link_v1_0.ic10` | 51 | Power topology | `power-grid` | `conditional-resident` | Publishes a commissioned passive electrical path as a Generic POWER Resource Link. |
| `ic10/power-grid/power_transformer_link_v1_0.ic10` | 68 | Power topology | `power-grid` | `conditional-resident` | Publishes a transformer POWER Resource Link with safe delivered ceiling and source-side self-power overhead. |
| `ic10/power-jobs/power_job_finalize_v1_0.ic10` | 91 | Power jobs | `power-jobs` | `conditional-resident` | Verifies applied POWER policy and advances RUNNING -> VERIFYING -> COMPLETE. |
| `ic10/power-jobs/power_job_lifecycle_client_v1_0.ic10` | 37 | Power jobs | `power-jobs` | `conditional-resident` | Gateway-lane-D lifecycle client returning ExpectedGeneration+1 after successful SET_STATE. |
| `ic10/power-jobs/power_job_policy_apply_v1_0.ic10` | 80 | Power jobs | `power-jobs` | `conditional-resident` | Revalidates a READY POWER job and applies the endpoint policy override/watt cap. |
| `ic10/power-jobs/power_job_policy_verify_v1_0.ic10` | 62 | Power jobs | `power-jobs` | `conditional-resident` | Verifies Generic Resource Reservation coherently reflects the requested POWER policy semantics. |
| `ic10/power-jobs/power_job_prepare_v1_0.ic10` | 105 | Power jobs | `power-jobs` | `conditional-resident` | Prepares POWER jobs through READY, applies policy, and advances to RUNNING. |
| `ic10/power-jobs/power_job_scheduler_v1_0.ic10` | 75 | Power jobs | `power-jobs` | `conditional-resident` | Coordinates selection, prepare/apply, and verify/finalize for finite POWER policy jobs. |
| `ic10/power-jobs/power_policy_target_resolver_v1_0.ic10` | 73 | Power jobs | `power-jobs` | `conditional-resident` | Resolves one PolicyId to exactly one current managed POWER Reservation/Endpoint. |
| `ic10/pressure-domain/controller_pressure_domain_runtime_v1_2.ic10` | 124 | Runtime / pressure grid | `pressure-domain` | `resident` | Owns LOW/HIGH target or passive STORAGE envelope; telemetry ABI2. |
| `ic10/pressure-domain/phase_pressure_request_arbiter_v1_2.ic10` | 118 | Pressure-grid service | `pressure-domain` | `conditional-resident` | Reduces coherent PhasePressure ABI2 requests for one LOW/HIGH domain; rejects directory overflow. |
| `ic10/pressure-domain/pressure_domain_config_policy_v1_1.ic10` | 78 | Family semantics | `pressure-domain` | `resident` | PressureDomain role/bounds validation and signature. |
| `ic10/pressure-grid/controller_pressure_transfer_runtime_v2_0.ic10` | 124 | Runtime / pressure grid | `pressure-grid` | `conditional-resident` | One physical pump edge; publishes coherent candidate topology and executes only Guard-authorized leases. |
| `ic10/pressure-grid/pressure_domain_inventory_v1_1.ic10` | 120 | Pressure-grid resource model | `pressure-grid` | `conditional-resident` | Purity-gated gas inventory; converts P/T/V/n into molar export/import capacity. |
| `ic10/pressure-grid/pressure_grid_cost_profile_v1_0.ic10` | 11 | Pressure-grid policy | `pressure-grid` | `conditional-resident` | Publishes dimensionless route-ranking weights and candidate budget. |
| `ic10/pressure-grid/pressure_grid_link_directory_adapter_v3_0.ic10` | 86 | Pressure-grid discovery adapter | `pressure-grid` | `conditional-resident` | Publishes coherent Pressure Link Adapter ABI2 candidates from the schema-qualified Generic Snapshot Controller directory and Transfer telemetry. |
| `ic10/pressure-grid/pressure_grid_path_allocator_v1_2.ic10` | 118 | Pressure-grid routing | `pressure-grid` | `conditional-resident` | Quotes every selected path hop, then exact-commits one common mol/tick rate. |
| `ic10/pressure-grid/pressure_grid_path_enumerator_v2_0.ic10` | 118 | Pressure-grid routing | `pressure-grid` | `conditional-resident` | Incrementally enumerates available 2/3-hop LOW-to-HIGH candidates through STORAGE. |
| `ic10/pressure-grid/pressure_grid_plan_builder_v1_0.ic10` | 120 | Pressure-grid planning | `pressure-grid` | `conditional-resident` | Orchestrates direct reuse -> ranked routed reuse -> fallback before Planner commit. |
| `ic10/pressure-grid/pressure_grid_reservation_planner_v2_1.ic10` | 87 | Pressure-grid commit | `pressure-grid` | `conditional-resident` | Medium-specific commit authority; publishes plan epoch only after successful construction. |
| `ic10/pressure-grid/pressure_grid_route_ranker_v2_0.ic10` | 120 | Pressure-grid routing | `pressure-grid` | `conditional-resident` | Route Ranker ABI2: scores using remaining endpoint capacity, lift, hops, storage and throughput. |
| `ic10/pressure-grid/pressure_grid_route_selector_v2_0.ic10` | 117 | Pressure-grid routing | `pressure-grid` | `conditional-resident` | Route Selector ABI2: bounded reservation-aware candidate comparison. |
| `ic10/pressure-grid/pressure_grid_singlehop_builder_v1_1.ic10` | 118 | Pressure-grid planning | `pressure-grid` | `conditional-resident` | Stages direct reuse or storage fallback while preserving fallback anti-circulation. |
| `ic10/pressure-grid/pressure_inventory_reservation_v1_1.ic10` | 51 | Pressure-grid ledger | `pressure-grid` | `conditional-resident` | Mirrors one Inventory ABI2 and owns mutable per-build endpoint reservation counters. |
| `ic10/pressure-grid/pressure_medium_purity_guard_v1_0.ic10` | 66 | Pressure-grid safety | `pressure-grid` | `conditional-resident` | Verifies actual analyzer gas ratio against the selected medium profile purity threshold. |
| `ic10/pressure-grid/pressure_reservation_allocator_v3_0.ic10` | 120 | Pressure-grid allocator | `pressure-grid` | `conditional-resident` | Allocator ABI3: non-mutating quote, exact commit, topology-bound staged grants. |
| `ic10/pressure-grid/pressure_transfer_config_policy_v1_0.ic10` | 69 | Family semantics | `pressure-grid` | `conditional-resident` | Validates the four-field PressureTransfer schema. |
| `ic10/pressure-grid/pressure_transfer_grant_guard_v1_0.ic10` | 112 | Pressure-grid safety | `pressure-grid` | `conditional-resident` | Topology-binds staged grants to Planner commit and consumes each committed epoch at most once. |
| `ic10/printer-directory/printer_capacity_client_v2_0.ic10` | 120 | Printer execution capacity | `printer-directory` | `conditional-resident` | Reserves/releases exact selected printers by ReferenceId and advertised execution-bank pin; fails closed on pin swaps. |
| `ic10/printer-directory/printer_directory_adapter_v1_0.ic10` | 117 | Manufacturing discovery | `printer-directory` | `conditional-resident` | Publishes six supported printer families as DirectorySchema.Printer v2 Adapter ABI2 candidates with common ProcessorSpec. |
| `ic10/printer-directory/printer_execution_bank_v2_0.ic10` | 120 | Printer execution capacity | `printer-directory` | `conditional-resident` | Locally manages up to six pinned printers so output-slot occupancy can be read safely and Lock can guard one reservation. |
| `ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10` | 118 | Manufacturing discovery | `printer-directory` | `conditional-resident` | Joins Item-4 Printer Directory metadata with local Execution Bank capacity and publishes exact-Printer PrinterExecution Adapter ABI2 records. |
| `ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10` | 123 | Pressure execution | `process-furnace` | `conditional-resident` | Projects an Advanced Furnace embedded inlet/outlet pump as ControllerPressureTransfer ABI2 and actuates only under PressureGrid GrantGuard authority. |
| `ic10/process-furnace/furnace_process_condition_request_v1_0.ic10` | 99 | Process utilities | `process-furnace` | `conditional-resident` | Publishes Transform-backed ProcessCondition ABI1 pressure/temperature demand for a selected Furnace or Advanced Furnace. |
| `ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10` | 65 | Process/pressure bridge | `process-furnace` | `conditional-resident` | Projects one active ProcessCondition target as standard ControllerPressureDomain ABI2 for ordinary PressureGrid planning. |
| `ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10` | 111 | Process utilities | `process-gas-preparation` | `conditional-resident` | Controls a Gas Mixer with temperature-corrected component ratios from a prepared-mixture Resource Profile. |
| `ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10` | 76 | Process utilities | `process-gas-preparation` | `conditional-resident` | Validates a two-component prepared gas mixture through the existing PurityGuard ABI using Resource Profile kind 5. |
| `ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10` | 82 | Process utilities | `process-gas-preparation` | `conditional-resident` | Controls a hot/cold Gas Mixer to satisfy a ProcessCondition temperature window without owning pressure-routing authority. |
| `ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10` | 114 | Power/process bridge | `process-gfg` | `conditional-resident` | Converts coherent PowerPlan shortage into a fuel ProcessCondition/PressureDomain demand and safely starts/stops a Gas Fuel Generator after fuel and ambient verification. |
| `ic10/recipe-catalog/recipe_catalog_lookup_v8_0.ic10` | 105 | Recipe metadata | `recipe-catalog` | `conditional-resident` | Recipe Lookup v8 ABI3 across runtime-placed Recipe schema-v3 Store ABI6 printer-family partitions. |
| `ic10/recipe-catalog/recipe_execution_profile_view_v1_0.ic10` | 116 | Manufacturing metadata | `recipe-catalog` | `conditional-resident` | Resolves exact RecipeHash execution metadata from Recipe schema-v3 stores, including bounded reagent requirements and stale-response echo. |
| `ic10/resource-grid-core/pressure_resource_endpoint_adapter_v1_0.ic10` | 63 | Resource-grid adapter | `resource-grid-core` | `conditional-resident` | Normalizes PressureDomain Inventory ABI2 into Generic Resource Endpoint ABI1. |
| `ic10/resource-grid-core/pressure_resource_link_adapter_v1_0.ic10` | 82 | Resource-grid adapter | `resource-grid-core` | `conditional-resident` | Projects a topology-bound PressureTransfer into Generic Resource Link ABI1. |
| `ic10/resource-grid-core/resource_endpoint_directory_adapter_v3_0.ic10` | 64 | Resource-grid discovery adapter | `resource-grid-core` | `conditional-resident` | Publishes typed Resource Endpoint Adapter ABI2 candidates on its own stack. |
| `ic10/resource-grid-core/resource_link_directory_adapter_v3_0.ic10` | 57 | Resource-grid discovery adapter | `resource-grid-core` | `conditional-resident` | Publishes Resource Link Adapter ABI2 candidates on its own stack. |
| `ic10/resource-grid-core/resource_reservation_directory_adapter_v1_0.ic10` | 64 | Resource-grid discovery adapter | `resource-grid-core` | `conditional-resident` | Publishes Generic Resource Reservation mirrors as DirectorySchema.ResourceReservation snapshot candidates. |
| `ic10/resource-grid-core/resource_reservation_releaser_v1_0.ic10` | 46 | Resource-grid release | `resource-grid-core` | `conditional-resident` | Clears Generic Resource Reservation ownership only for an exact owner ReferenceId and plan epoch. |
| `ic10/resource-grid-core/resource_reservation_v1_0.ic10` | 117 | Resource-grid core | `resource-grid-core` | `conditional-resident` | Mirrors any Generic Resource Endpoint into a domain-neutral reservation surface. |
| `ic10/resource-profile-catalog/resource_profile_loader_energy_00_v4_0.ic10` | 22 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable ENERGY Resource Profile Loader ABI5 candidate. |
| `ic10/resource-profile-catalog/resource_profile_loader_fluid_00_v4_0.ic10` | 111 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_fluid_01_v4_0.ic10` | 79 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_00_v4_0.ic10` | 115 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_01_v4_0.ic10` | 115 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_item_02_v4_0.ic10` | 75 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable Resource Profile Loader ABI5 candidate; whole records only, own-stack zero-init. |
| `ic10/resource-profile-catalog/resource_profile_loader_power_00_v4_0.ic10` | 22 | Resource metadata | `resource-profile-catalog` | `one-shot` | One-shot relocatable POWER Resource Profile Loader ABI5 candidate. |
| `ic10/resource-profile-catalog/resource_profile_view_v4_0.ic10` | 93 | Resource metadata | `resource-profile-catalog` | `conditional-resident` | Resolves one Resource Profile across runtime-placed Store ABI6 items and republishes View ABI1. |
| `ic10/shared-input/generic_input_resolver_v1_0.ic10` | 113 | Shared input | `shared-input` | `commissioning` | Resolves logical commissioning controls from Scanner + Profile metadata. |
| `ic10/shared-input/generic_input_scanner_v1_1.ic10` | 84 | Shared input | `shared-input` | `commissioning` | Discovers/classifies physical commissioning controls. |
| `ic10/transform-catalog/resource_transform_catalog_loader_00_v6_0.ic10` | 109 | Transformation metadata | `transform-catalog` | `one-shot` | One-shot relocatable Transform Loader ABI5 candidate; each transform is a whole self-contained item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_01_v6_0.ic10` | 98 | Transformation metadata | `transform-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_02_v6_0.ic10` | 110 | Transformation metadata | `transform-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_03_v6_0.ic10` | 95 | Transformation metadata | `transform-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_catalog_loader_04_v6_0.ic10` | 41 | Transformation metadata | `transform-catalog` | `one-shot` | One-shot relocatable Loader ABI5 candidate; each Transform and all descriptors remain one atomic item. |
| `ic10/transform-catalog/resource_transform_profile_view_v8_0.ic10` | 118 | Transformation metadata | `transform-catalog` | `conditional-resident` | Selects a Store ABI6 schema-v4 transform and publishes capability-based variable-input Transform Profile ABI4. |

## Pressure-grid dependency map

```text
Generic Snapshot Controller Directory ABI1 + DirectorySchema.Controller
        |
        +--> PhasePressure Request Arbiter --> PressureDomain telemetry ABI2
        |                                      |
        |                               Purity Guard <--- Resource Profile View
        |                                      |
        |                                 Inventory ABI2
        |                                      |
        |                              Reservation ledger ABI1
        |                                      |
        +--> PressureGridLink Snapshot Directory +
                 |                              |
                 +--> Path Enumerator --> Route Selector ABI2 --> Path Allocator --+
                 |                         ^                         |               |
                 +--> Single-Hop Builder --|-------------------------+               |
                                           |                                         v
                    Cost Profile --> Route Ranker ABI2        Allocator ABI3 (quote/commit)
                                                                  |
                                                             staged topology grant
                                                                  |
                 Plan Builder --> Planner ABI2 commit LAST --> Grant Guard --> Transfer ABI2 --> pump
```

Route classes are `1 LOW->HIGH`, `2 LOW->STORAGE`, `3 STORAGE->HIGH`, and `4 STORAGE->STORAGE`. Route class 4 is path-only. Automatic routed reuse is currently bounded to two or three physical hops.

## Resource-grid generalization map

```text
Pressure Inventory -> Pressure Endpoint Adapter --+ 
                                                  +-> Generic Resource Endpoint -> Generic Resource Reservation
Vending + ITEM Resource Profile View -> Material Inventory -+ 
Cargo LArRE -> Storage Service -> LArRE ITEM Endpoint --------+ 

PressureTransfer + matching generic reservations -> Generic Resource Link

Vending -> Stacker -> Logic Sorter -> Material Link -> processor/import endpoint
                        |                 ^
                        +-> Grant Guard <-+-> Multi Material Allocator ABI2

Material Link + Transform Profile + output Reservation -> Admission -> Link Resolver
                                                         -> Multi Stager -> Multi Allocator -> Generic Runtime

Generic Job Store -> Generic Job Selector -> Manufacturing Scheduler -> TRANSFORM / PRINT drivers
                         |                                      |
                         |                         +------------+------------+
                         |                         |                         |
                         |                 TransformLane             PrinterExecution
                         |                         |                         |
                         +-------------------------+--> existing Multi Reservation / Allocation substrates
```

## Deployment ownership

Every deployable program resolves to exactly one `deployment_family` and one deployment class in `data/source_manifest.json` (directly or through a generated-file rule). See `USER_DEPLOYMENT_GUIDE.md` for operator procedures, prerequisites, wiring, health checks, commissioning proof, restart behavior, and reclaim guidance.

## Source of truth

The deployable programs under `ic10/<deployment-family>/` are canonical. Use this index for navigation and line-pressure review; inspect the source file directly for exact code.

