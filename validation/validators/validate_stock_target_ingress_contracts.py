#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from framework.validation import Validation

R = _PROJECT_ROOT
validation = Validation(R)


def need(path, *patterns):
    text = (R / path).read_text()
    for pattern in patterns:
        if pattern not in text:
            validation.fail(f"{path}: missing {pattern!r}")


need("ic10/manufacturing-ingress/stock_target_config_policy_v1_0.ic10",
     'HASH("CFG1|ManufacturingStockTarget|1|2|255|255|0|0")', "bge r4 r3 Bounds")
need("ic10/manufacturing-ingress/stock_target_inventory_view_v1_0.ic10",
     'HASH("ItemResourceReservationSelector.v1")', "and r12 r12 8", "get r13 db 22",
     "move r4 2")
need("ic10/manufacturing-ingress/stock_target_future_view_v1_0.ic10",
     'HASH("DependencyClaimView.v1")', 'HASH("DependencyPlanStore.v2")', "get r1 d1 27")
need("ic10/manufacturing-ingress/stock_target_demand_view_v1_0.ic10",
     "sub r0 r0 r9", "ble r0 r4 NoNeed", "slt r0 r12 sp")
need("ic10/manufacturing-ingress/stock_target_producer_view_v1_0.ic10",
     'HASH("ItemProducerResolver.v1")', 'HASH("JobRequirementView.v1")')
need("ic10/manufacturing-ingress/stock_target_job_evaluator_v1_0.ic10",
     'HASH("StockTargetDemandView.v1")', 'HASH("StockTargetJobIngress.v1")',
     "mul r13 r1 3", "put d3 31 r11", "put d3 32 r15")
need("ic10/manufacturing-ingress/stock_target_job_ingress_v1_0.ic10",
     'HASH("StockTargetProducerView.v1")', 'HASH("StockTargetDemandView.v1")',
     'HASH("GenericPersistentConfigHost.v1")', 'HASH("GenericJobCommandGateway.v5")',
     "get r0 d1 41", "bne r0 r11 Bad", "mul r14 r15 3", "get r0 d3 51",
     "put d0 80 r15")
need("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10",
     'HASH("GenericJobCommandGateway.v5")', "ble r7 96 Scan", "put d0 28 r0", "put d0 29 r0")
need("ic10/generic-jobs/generic_job_store_command_executor_v1_0.ic10",
     "beq r5 3 FindStart", "bne r5 5 Bad", "beq r5 5 Root", "bne r6 -1 Bad",
     'HASH("DependencyPlanStore.v2")', "get r2 db 28", "get r2 db 29")

for path in (R / "ic10/manufacturing-ingress").glob("*.ic10"):
    lines = len(path.read_text().splitlines())
    if lines > 120:
        validation.fail(f"{path.relative_to(R)}: {lines} lines > stock-ingress ceiling 120")

raise SystemExit(validation.finish("Stock-target ingress contracts", [
    "four Config Policy targets feed exact stock plus active unclaimed future-output decisions",
    "hysteresis suppresses boundary churn and root quantities refill the full deficit",
    "mutation-time demand, output-per-batch, config generation, and Store/Plan snapshots are revalidated",
    "only Gateway lane E can request a root; lane C remains child-only",
]))
