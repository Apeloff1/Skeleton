#!/usr/bin/env python3
"""Build and validate a fail-closed repository maintenance plan.

The planner reads ownership policy, tasks and observations as data. It never
deletes repository resources. A mutation-capable caller must still pass the
exact receipt through the runtime execution boundary immediately before acting.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

from skeleton.repo_machine.maintenance import (
    MaintenanceAction,
    MaintenanceRegistry,
    MaintenanceRisk,
    MaintenanceTask,
    MaintenanceVerdict,
    OwnershipClass,
    RepositoryOwnership,
    ResourceEvidence,
    ResourceKind,
    plan_summary,
)


def _time(value: str | None):
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_ownership(item: dict) -> RepositoryOwnership:
    return RepositoryOwnership(
        resource_id=item["resource_id"],
        kind=ResourceKind(item["kind"]),
        ownership=OwnershipClass(item["ownership"]),
        owner=item["owner"],
        retention_reason=item["retention_reason"],
        mutation_authority_refs=tuple(item["mutation_authority_refs"]),
        repository_path=item.get("repository_path"),
        retention_until=_time(item.get("retention_until")),
        active_refs=tuple(item.get("active_refs", ())),
        preservation_refs=tuple(item.get("preservation_refs", ())),
        generation_source_refs=tuple(item.get("generation_source_refs", ())),
    )


def build_task(item: dict) -> MaintenanceTask:
    return MaintenanceTask(
        task_id=item["task_id"],
        resource_id=item["resource_id"],
        action=MaintenanceAction(item["action"]),
        risk=MaintenanceRisk(item["risk"]),
        expected_digest=item["expected_digest"],
        authority_ref=item["authority_ref"],
        mutation_limit=item["mutation_limit"],
        evidence_ttl_seconds=item["evidence_ttl_seconds"],
        stale_after_seconds=item["stale_after_seconds"],
    )


def build_evidence(item: dict) -> ResourceEvidence:
    return ResourceEvidence(
        evidence_id=item["evidence_id"],
        resource_id=item["resource_id"],
        observed_digest=item["observed_digest"],
        observed_at=_time(item["observed_at"]),
        last_activity_at=_time(item["last_activity_at"]),
        reachable=item["reachable"],
        active_migration=item["active_migration"],
        release_bound=item["release_bound"],
        evidence_bound=item["evidence_bound"],
        regeneration_receipt_digest=item.get("regeneration_receipt_digest"),
        regeneration_source_refs=tuple(
            item.get("regeneration_source_refs", ())
        ),
        provenance_refs=tuple(item["provenance_refs"]),
    )


def build_plan(spec: dict):
    registry = MaintenanceRegistry(
        tuple(build_ownership(item) for item in spec["ownership"])
    )
    tasks = tuple(build_task(item) for item in spec.get("tasks", ()))
    evidence = tuple(
        build_evidence(item) for item in spec.get("evidence", ())
    )
    return registry.plan(
        tasks,
        evidence,
        at=_time(spec["assessed_at"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument(
        "--require-all-allowed",
        action="store_true",
        help="Exit nonzero when any planned maintenance task is blocked.",
    )
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    plan = build_plan(spec)
    summary = plan_summary(plan)
    print(
        json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        end="",
    )

    if args.require_all_allowed and any(
        item.decision is MaintenanceVerdict.BLOCK
        for item in plan.receipts
    ):
        raise SystemExit("maintenance plan contains blocked tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
