#!/usr/bin/env python3
"""Validate and record contract-driven in-world wiring commissioning."""
from __future__ import annotations
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

from pathlib import Path
import argparse
import json

from framework.commissioning import apply_evidence, build_plan, load_wiring, overall_status
import tools.live_commission as live

ROOT = _PROJECT_ROOT


def render(plan):
    lines = [
        f"Commissioning plan: {plan['binding']['plan_id']}",
        f"Consumer: {plan['binding']['consumer_contract']['source']}",
        f"Overall: {overall_status(plan)}",
    ]
    for item in plan["results"]:
        lines.append(f"{item['status']:10} {item['id']}: {item['message']}")
    if plan["observations"]:
        lines.append("Runtime observations:")
        for observation in plan["observations"]:
            lines.append(f"- {observation['id']} [{observation['tool']}]: {observation['summary']}")
            for cell in observation.get("cells", []):
                expected = cell.get("expected", cell.get("expected_any_of"))
                relation = "expected" if "expected" in cell else "expected one of"
                lines.append(f"  S{cell['address']} {relation} {expected!r}")
            capabilities = observation.get("capabilities")
            if capabilities:
                lines.append(
                    "  Capabilities: "
                    f"read={capabilities['reads']}, write={capabilities['writes']}, "
                    f"slot-read={capabilities['slot_reads']}, slot-write={capabilities['slot_writes']}"
                )
            for fence in observation.get("fences", []):
                lines.append(
                    f"  Snapshot Probe FenceStackCell=S{fence['address']} ({fence['kind']}): "
                    f"{fence['description']}"
                )
            lines.append(f"  Fencing: {observation['fencing']}")
    return "\n".join(lines) + "\n"


def _current_plan(path, session_path=None):
    wiring = load_wiring(path, ROOT)
    plan = build_plan(wiring, ROOT)
    if session_path:
        session = live.read_session(session_path)
        if not live.session_fresh(session):
            raise ValueError("STALE SESSION: framework or commissioning catalog changed")
        plan = apply_evidence(plan, session)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="cmd", required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--map", required=True)
    validate_parser.add_argument("--session")
    validate_parser.add_argument("--json", action="store_true")
    record_parser = commands.add_parser("record")
    record_parser.add_argument("--map", required=True)
    record_parser.add_argument("--session", required=True)
    record_parser.add_argument("--obligation", required=True)
    record_parser.add_argument("--status", choices=sorted(live.VALID), required=True)
    record_parser.add_argument("--observed", required=True)
    record_parser.add_argument("--refs", default="")
    record_parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    try:
        plan = _current_plan(args.map)
        if args.cmd == "validate":
            if args.session:
                plan = _current_plan(args.map, args.session)
            print(json.dumps(plan, indent=2, sort_keys=True) if args.json else render(plan), end="" if not args.json else "\n")
            return 0 if overall_status(plan) == "PASS" else 1

        session = live.read_session(args.session)
        if not live.session_fresh(session):
            print("STALE SESSION: framework or commissioning catalog changed", file=_project_sys.stderr)
            return 2
        runtime_ids = {item["id"] for item in plan["results"] if item["category"] == "runtime"}
        if args.obligation not in runtime_ids:
            print("unknown or non-runtime obligation", file=_project_sys.stderr)
            return 2
        plan_id = plan["binding"]["plan_id"]
        entry = session.setdefault("wiring_results", {}).setdefault(plan_id, {
            "binding": plan["binding"], "runs": {},
        })
        if entry.get("binding") != plan["binding"]:
            print("wiring evidence binding mismatch", file=_project_sys.stderr)
            return 2
        run = {
            "status": args.status,
            "recorded_at": live.now(),
            "observed": args.observed,
            "reference_ids": [value.strip() for value in args.refs.split(",") if value.strip()],
            "notes": args.notes,
        }
        entry["runs"].setdefault(args.obligation, []).append(run)
        live.write_session(args.session, session)
        print(f"Recorded {args.obligation}: {args.status} ({plan_id})")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=_project_sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
