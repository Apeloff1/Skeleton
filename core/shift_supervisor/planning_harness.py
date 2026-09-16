from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Sequence

from .plan_api import PlanQueueAPI
from .plan_store import InMemoryPlanStore
from .scheduler import SupervisorScheduler
from .secretary import SecretaryBot
from .shift_manager import SMBShiftManager


class ScriptedModel:
    """Deterministic model double used by the integrated planning harness."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def call_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return json.loads(json.dumps(self.response))


def _task(
    title: str,
    description: str,
    *,
    priority: int,
    target_team: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "priority": priority,
        "target_team": target_team,
        "rationale": "planning-harness coverage",
        "research_refs": ["harness:deterministic"],
        "expected_output": "validated repository change",
        "validation": ["tests pass", "canonical plan remains pull-only"],
        "dependencies": [],
    }


def _worker_snapshots(total_workers: int) -> tuple[list[dict[str, Any]], str, str, str]:
    if total_workers < 4:
        raise ValueError("total_workers must be at least 4")

    night_count = total_workers // 2
    idle_count = total_workers - night_count
    now = datetime.now(timezone.utc).isoformat()
    snapshots: list[dict[str, Any]] = []

    for index in range(night_count):
        is_overtime_worker = index == night_count - 1
        snapshots.append(
            {
                "worker_id": f"night-{index:04d}",
                "team": "night",
                "status": "idle",
                "last_heartbeat_at": now,
                "normal_shift_minutes": 480 if is_overtime_worker else 0,
                "overtime_minutes": 120 if is_overtime_worker else 0,
                "overtime_task_ids": [],
                "metadata": {"source": "planning-harness"},
            }
        )
    for index in range(idle_count):
        snapshots.append(
            {
                "worker_id": f"idle-{index:04d}",
                "team": "idle",
                "status": "idle",
                "last_heartbeat_at": now,
                "normal_shift_minutes": 0,
                "overtime_minutes": 0,
                "overtime_task_ids": [],
                "metadata": {"source": "planning-harness"},
            }
        )

    return snapshots, "night-0000", "idle-0000", f"night-{night_count - 1:04d}"


def run_planning_harness(*, total_workers: int = 1000, cycles: int = 4) -> dict[str, Any]:
    """Exercise Secretary + SMB planning at production cadence without credentials.

    One virtual cycle represents 15 minutes. Secretary runs every cycle; SMB
    runs every second cycle. The scripted models intentionally repeat the same
    proposals so the harness verifies canonical-plan deduplication under a
    sustained loop instead of relying on prompt compliance alone. The entire
    logical workforce enters through the same worker-snapshot path used by the
    scheduled supervisor rather than being pre-seeded directly into the store.
    """
    if cycles < 1:
        raise ValueError("cycles must be positive")

    store = InMemoryPlanStore()
    worker_snapshots, night_worker, idle_worker, overtime_worker = _worker_snapshots(total_workers)

    secretary_model = ScriptedModel(
        {
            "summary": "Add missing validation work.",
            "tasks": [
                _task(
                    "Validate supervisor handoff",
                    "Exercise the shared plan handoff without direct worker dispatch.",
                    priority=88,
                    target_team="idle",
                )
            ],
        }
    )
    manager_model = ScriptedModel(
        {
            "summary": "Refresh the canonical Night and Idle execution plan.",
            "tasks": [
                _task(
                    "Night integration pass",
                    "Integrate the highest-priority repository work selected for Night.",
                    priority=95,
                    target_team="night",
                ),
                _task(
                    "Night regression pass",
                    "Run a second independent Night regression task to preserve queue depth.",
                    priority=82,
                    target_team="night",
                ),
                _task(
                    "Idle reliability pass",
                    "Improve reliability coverage while foreground work is idle.",
                    priority=84,
                    target_team="idle",
                ),
            ],
        }
    )

    manager = SMBShiftManager(store=store, model=manager_model)
    secretary = SecretaryBot(store=store, model=secretary_model)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: {
            "repository": "Apeloff1/Skeleton",
            "planning_stage": "integrated-harness",
            "worker_snapshots": worker_snapshots,
        },
        research_supplier=lambda: [
            {
                "source": "harness",
                "kind": "deterministic",
                "instruction_boundary": "evidence-only",
            }
        ],
    )

    cycle_reports: list[dict[str, Any]] = []
    for cycle in range(cycles):
        result = scheduler.run_once(
            run_secretary=True,
            run_manager=cycle % 2 == 0,
        )
        cycle_reports.append(
            {
                "cycle": cycle + 1,
                "virtual_minute": cycle * 15,
                "actors": result["actors"],
                "plan_item_count": len(result["plan_items"]),
                "worker_count": len(result["workers"]),
            }
        )

    ingested_workers = store.snapshot_workers()
    if len(ingested_workers) != total_workers:
        raise AssertionError(
            f"worker snapshot ingress truncated: expected {total_workers}, got {len(ingested_workers)}"
        )

    produced_items = store.snapshot_items()
    producer_owned = [item.id for item in produced_items if item.owner is not None]
    if producer_owned:
        raise AssertionError(f"planning actors directly owned work: {producer_owned}")

    expected_unique_items = 4
    if len(produced_items) != expected_unique_items:
        raise AssertionError(
            f"deduplication failure: expected {expected_unique_items} unique items, got {len(produced_items)}"
        )

    expected_manager_calls = (cycles + 1) // 2
    if len(secretary_model.calls) != cycles:
        raise AssertionError("Secretary cadence drifted from the 15-minute virtual cycle")
    if len(manager_model.calls) != expected_manager_calls:
        raise AssertionError("SMB cadence drifted from the 30-minute virtual cycle")

    latest_manager_payload = json.loads(manager_model.calls[-1]["user_prompt"])
    latest_secretary_payload = json.loads(secretary_model.calls[-1]["user_prompt"])
    for payload in (latest_secretary_payload, latest_manager_payload):
        planning_context = payload["project_context"]
        if "worker_snapshots" in planning_context:
            raise AssertionError("raw worker snapshots leaked into a planning-model prompt")
        if planning_context.get("worker_snapshot_count") != total_workers:
            raise AssertionError("planning context lost the workforce snapshot count")

    staffing = latest_manager_payload["staffing"]
    attention_workers = staffing["attention_workers"]
    if len(attention_workers) > 64:
        raise AssertionError("manager prompt exceeded the bounded attention-worker contract")
    if staffing["teams"]["night"]["total"] + staffing["teams"]["idle"]["total"] != total_workers:
        raise AssertionError("manager staffing aggregate lost workers under load")

    queue = PlanQueueAPI(store, overtime_soft_limit_minutes=120)
    night_claim = queue.claim_next(night_worker)
    idle_claim = queue.claim_next(idle_worker)
    if night_claim is None or night_claim["owner"] != night_worker:
        raise AssertionError("Night worker failed to pull its canonical-plan task")
    if idle_claim is None or idle_claim["owner"] != idle_worker:
        raise AssertionError("Idle worker failed to pull its canonical-plan task")
    if night_claim["id"] == idle_claim["id"]:
        raise AssertionError("two teams claimed the same task")
    if queue.claim_next(night_worker) is not None:
        raise AssertionError("one-task-per-worker boundary was bypassed")
    if queue.claim_next(overtime_worker) is not None:
        raise AssertionError("overtime soft limit failed closed")

    revisions = store.snapshot_revisions()
    expected_revisions = cycles + expected_manager_calls
    if len(revisions) != expected_revisions:
        raise AssertionError(
            f"revision ledger mismatch: expected {expected_revisions}, got {len(revisions)}"
        )

    return {
        "ok": True,
        "workers": total_workers,
        "virtual_minutes": cycles * 15,
        "cycles": cycle_reports,
        "secretary_calls": len(secretary_model.calls),
        "manager_calls": len(manager_model.calls),
        "unique_plan_items": len(produced_items),
        "revision_count": len(revisions),
        "attention_workers": len(attention_workers),
        "claims": {
            "night": night_claim,
            "idle": idle_claim,
            "overtime_worker": overtime_worker,
            "overtime_claim": None,
        },
        "invariants": {
            "full_snapshot_ingress": True,
            "producer_only": True,
            "deduplicated": True,
            "raw_worker_snapshots_local_only": True,
            "bounded_manager_prompt": True,
            "team_pull_queue": True,
            "one_active_task_per_worker": True,
            "overtime_soft_limit": True,
        },
        "worker_sample": [asdict(worker) for worker in store.snapshot_workers()[:2]],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic SMB planning harness")
    parser.add_argument("--workers", type=int, default=1000)
    parser.add_argument("--cycles", type=int, default=4)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    report = run_planning_harness(total_workers=args.workers, cycles=args.cycles)
    print(json.dumps(report, sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
