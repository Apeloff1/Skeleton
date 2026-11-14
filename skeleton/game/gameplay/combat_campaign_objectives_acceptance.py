"""End-to-end acceptance evidence for authored combat objective campaigns.

This gate actually plays every canonical encounter, verifies each intermediate
checkpoint and portable package, and reports incomplete objectives explicitly.
It never converts a skipped or failed gameplay objective into release success.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_objectives import (
    _encoded, advance_objectives, new_objectives, normalize_objectives,
    objective_summary, original_objectives, package_objectives,
    verify_objectives, verify_objectives_package,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _object, _parse_json,
)

SCHEMA = "skeleton.combat_objectives_acceptance.v1"


def accept_objectives(source: Any) -> dict[str, Any]:
    spec = normalize_objectives(source)
    current = new_objectives(spec)
    lineage = [{
        "index": 0, "state_digest": current["state_digest"],
        "save_digest": dig(current["save"]),
        "phase": current["state"]["phase"],
        "earned": current["state"]["score"],
    }]
    while current["state"]["phase"] == "active":
        current = advance_objectives(current)
        verified = verify_objectives(current)
        if verified != current:
            raise CombatSessionError("objective acceptance checkpoint replay mismatch")
        lineage.append({
            "index": len(current["state"]["journal"]),
            "state_digest": current["state_digest"],
            "save_digest": dig(current["save"]),
            "phase": current["state"]["phase"],
            "earned": current["state"]["score"],
        })
    summary = objective_summary(current)
    total = len(summary["objectives"])
    completed = sum(item["status"] == "completed" for item in summary["objectives"])
    issues = [{
        "objective_id": item["objective_id"], "status": item["status"],
        "reason": (
            "unreached_encounter" if item["status"] == "unreachable" else
            "unmet_prerequisite" if item["status"] == "blocked" else
            "canonical_condition_failed"
        ),
    } for item in summary["objectives"] if item["status"] != "completed"]
    accepted = current["state"]["phase"] == "won" and completed == total
    if current["state"]["phase"] != "won":
        issues.append({
            "objective_id": None, "status": current["state"]["phase"],
            "reason": "canonical_campaign_not_won",
        })
    package = package_objectives(current)
    if verify_objectives_package(package) != package:
        raise CombatSessionError("objective acceptance portable replay mismatch")
    result = {
        "schema_version": SCHEMA,
        "source": spec, "source_digest": dig(spec),
        "accepted": accepted, "claim": "offline_gameplay_acceptance_only",
        "completed": completed, "total": total,
        "earned_score": current["state"]["score"],
        "maximum_score": sum(item["points"] for item in spec["objectives"]),
        "issues": issues, "lineage": lineage,
        "terminal_summary": summary, "terminal_package": package,
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_objectives_acceptance(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "accepted", "claim",
        "completed", "total", "earned_score", "maximum_score", "issues",
        "lineage", "terminal_summary", "terminal_package", "receipt",
    }, "objectives acceptance report")
    if (obj["schema_version"] != SCHEMA
            or obj["claim"] != "offline_gameplay_acceptance_only"):
        raise CombatSessionError("unsupported objectives acceptance schema")
    _encoded(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("objectives acceptance receipt mismatch")
    expected = accept_objectives(obj["source"])
    if expected != obj:
        raise CombatSessionError("objectives acceptance replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-objectives-accept")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    audit = sub.add_parser("audit")
    audit.add_argument("--source-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = accept_objectives(original_objectives())
        elif args.command == "audit":
            result = accept_objectives(_parse_json(args.source_json, "objective source"))
        else:
            result = verify_objectives_acceptance(
                _parse_json(args.report_json, "objective acceptance"),
            )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
