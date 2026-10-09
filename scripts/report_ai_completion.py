#!/usr/bin/env python3
"""Evidence-based AI delivery report; distinct from masterplan sign-off totals.

This report never signs volumes, rewrites P1 task status, or promotes deferred
P3/enterprise claims. An unmeasured end-to-end release gets no fabricated %.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]


class DeliveryAuditError(ValueError):
    """Canonical delivery evidence is unreadable or inconsistent."""


def _load(root: Path, relative: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = (root / relative).read_bytes()
        result = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeliveryAuditError("cannot parse canonical source: " + relative) from exc
    if not isinstance(result, dict):
        raise DeliveryAuditError("canonical source must be an object: " + relative)
    return raw, result


def _blob_identity(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()


def audit_ai_delivery(root: Path = ROOT) -> dict[str, Any]:
    plan_raw, plan = _load(root, "machine/ai_master_plan.json")
    ledger_raw, _ledger = _load(root, "machine/ai_build_accountability.json")
    _, index = _load(root, "machine/ai_masterplan_parse_index.json")
    _, p1 = _load(root, "machine/ai_p1_task_backlog.json")
    _, p3 = _load(root, "machine/ai_p3_learning_closure.json")
    _, training = _load(root, "machine/ai_p3_training_closure.json")

    volumes = plan.get("volumes")
    tasks = p1.get("tasks")
    if not isinstance(volumes, list) or not isinstance(tasks, list):
        raise DeliveryAuditError("canonical volume/task inventory unavailable")
    if any(not isinstance(v, dict) for v in volumes) or any(
        not isinstance(t, dict) for t in tasks
    ):
        raise DeliveryAuditError("invalid masterplan/P1 record")

    source_hashes = {
        "machine/ai_master_plan.json": _blob_identity(plan_raw),
        "machine/ai_build_accountability.json": _blob_identity(ledger_raw),
    }
    sources = index.get("sources")
    freshness = isinstance(sources, dict) and all(
        isinstance(sources.get(name), dict)
        and sources[name].get("git_blob_sha") == digest
        for name, digest in source_hashes.items()
    )

    signed = sum(v.get("completion_checkbox") is True for v in volumes)
    enterprise_qualified = sum(
        v.get("enterprise_grade_state") == "enterprise_qualified" for v in volumes
    )
    done = sum(t.get("status") == "done" for t in tasks)
    blocked = sum(t.get("status") == "blocked" for t in tasks)
    ledger_execution_disagreements = sorted(
        str(t.get("task_id", "unknown")) for t in tasks
        if t.get("completion_checkbox") is True and t.get("status") != "done"
    )

    if not isinstance(p3.get("frontier"), dict):
        raise DeliveryAuditError("P3 frontier is missing")
    deferred = p3["frontier"].get("queued_volume_count")
    if type(deferred) is not int or deferred < 0:
        raise DeliveryAuditError("P3 deferred count is malformed")

    errors = []
    if not freshness:
        errors.append("masterplan parse index source identity mismatch")
    if ledger_execution_disagreements:
        errors.append(
            f"{len(ledger_execution_disagreements)} signed P1 tasks have unfinished execution status"
        )
    if blocked:
        errors.append(f"{blocked} P1 tasks remain blocked")
    if deferred:
        errors.append(f"{deferred} P3 volume identities remain deferred")
    if enterprise_qualified != len(volumes):
        errors.append(f"{len(volumes) - enterprise_qualified} volumes lack enterprise qualification")
    if training.get("status") != "closed":
        errors.append("native training frontier lacks closed, independently qualified release status")
    if p3.get("status") != "closed":
        errors.append("learning/multimodal frontier remains active")

    return {
        "schema": "skeleton.ai.delivery.audit.v1",
        "source_blobs": source_hashes,
        "index_fresh": bool(freshness),
        "masterplan": {
            "volumes_total": len(volumes),
            "signed": signed,
            "signed_percent": round(100 * signed / len(volumes), 2) if volumes else 0.0,
            "enterprise_qualified": enterprise_qualified,
            "enterprise_qualified_percent": round(100 * enterprise_qualified / len(volumes), 2) if volumes else 0.0,
        },
        "p1": {
            "tasks_total": len(tasks),
            "done": done,
            "done_percent": round(100 * done / len(tasks), 2) if tasks else 0.0,
            "blocked": blocked,
            "signed_but_not_done": ledger_execution_disagreements,
        },
        "p3": {
            "deferred_volumes": deferred,
            "learning_status": p3.get("status"),
            "native_training_status": training.get("status"),
        },
        "standalone_release": {
            "independently_verified": False,
            "note": "No end-to-end shipped installer, trained model quality, and operation acceptance is proven by the volume signing ledger.",
        },
        "whole_project_completion_percent": None,
        "ready_for_full_completion": not errors and False,
        "open_obligations": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="fail unless every independent delivery claim is qualified")
    args = parser.parse_args(argv)
    try:
        report = audit_ai_delivery()
    except DeliveryAuditError as exc:
        print("AI completion audit invalid: " + str(exc))
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Masterplan signed: {report['masterplan']['signed_percent']}%")
        print(f"P1 tasks done: {report['p1']['done_percent']}%")
        print(f"Enterprise volume grade qualified: {report['masterplan']['enterprise_qualified_percent']}%")
        print("Whole-project percent: unverified")
        for issue in report["open_obligations"]:
            print(" - " + issue)
    return 1 if args.strict and not report["ready_for_full_completion"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
