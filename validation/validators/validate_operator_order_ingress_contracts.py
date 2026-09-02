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


need("ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10",
     'HASH("GenericInputResolver.v1")', 'HASH("OperatorOrderJobIngress.v1")',
     "blez r0 Resolve", "blez r1 Commit", "poke 30 r15", "poke 28 1",
     "put d1 19 r15", "bne r0 r15 Loop")
need("ic10/manufacturing-ingress/operator_order_recipe_view_v1_0.ic10",
     'HASH("RecipeCatalogLookup.v3")', 'HASH("RecipeExecutionProfileView.v1")',
     "put d0 13 255", "bne r0 r3 ProfileBad", "bne r0 r8 ProfileBad",
     "poke 24 r9", "poke 20 r15")
need("ic10/manufacturing-ingress/operator_order_job_ingress_v1_0.ic10",
     'HASH("OperatorOrderRecipeView.v1")', 'HASH("GenericJobCommandGateway.v5")',
     'HASH("GenericJobStore.v1")', 'HASH("DependencyPlanStore.v2")',
     "put d0 96 r14", "put d0 101 r10", "put d0 102 r11",
     "put d0 103 2", "put d0 108 r5", "put d0 109 r6")
need("ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10",
     'HASH("GenericJobCommandGateway.v5")', "ble r7 96 Scan",
     "add r8 r7 7", "get r7 db 26", "mul r0 r0 6")

editor = "ic10/manufacturing-ingress/operator_order_editor_v1_0.ic10"
editor_text = (R / editor).read_text()
if editor_text.index("poke 30 r15") > editor_text.index("poke 28 1"):
    validation.fail(f"{editor}: commit edge is consumed before pending identity is durable")
replay_guard = ('Wait:\nget r0 d1 0\n'
                'bne r0 HASH("OperatorOrderJobIngress.v1") Loop\n'
                'poke 28 1\nput d1 19 r15')
if replay_guard not in editor_text:
    validation.fail(f"{editor}: pending replay is not guarded by exact ingress identity")

need("docs/OPERATOR_ORDER_INGRESS.md",
     "dedicated Recipe Catalog Lookup", "dedicated Recipe Execution Profile View",
     "ABI4-to-ABI5")
need("docs/DEPLOYMENT.md", "lane F Operator Order Ingress")

for path in [
    R / "ic10/generic-jobs/generic_job_command_gateway_v5_0.ic10",
    *sorted((R / "ic10/manufacturing-ingress").glob("operator_order_*.ic10")),
]:
    lines = len(path.read_text().splitlines())
    if lines > 120:
        validation.fail(f"{path.relative_to(R)}: {lines} lines > operator-order ceiling 120")

raise SystemExit(validation.finish("Operator-order ingress contracts", [
    "shared-input values stage independently and only a rising commit edge submits an order",
    "family/ordinal selection resolves through Recipe Lookup and exact execution metadata is revalidated",
    "Gateway lane F preserves quantity and priority while the sole Store executor publishes one PRINT root",
    "all Item-13.2 IC10 programs and the six-lane Gateway remain within 120 lines",
]))
