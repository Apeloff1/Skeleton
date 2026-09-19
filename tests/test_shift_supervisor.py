from datetime import datetime, timedelta, timezone

import pytest

from core.shift_supervisor.models import PlanItem
from core.shift_supervisor.plan_api import PlanQueueAPI
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.secretary import SecretaryBot
from core.shift_supervisor.shift_manager import SMBShiftManager


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_secretary_calls_model_and_deduplicates_open_work():
    store = InMemoryPlanStore()
    model = FakeModel([
        {
            "summary": "add validation",
            "tasks": [
                {
                    "title": "Add queue validation",
                    "description": "Verify queue state before dispatch",
                    "priority": 80,
                    "target_team": "idle",
                    "rationale": "prevents duplicate dispatch",
                    "research_refs": ["internal:queue"],
                    "expected_output": "regression tests",
                    "validation": ["pytest"],
                    "dependencies": [],
                },
                {
                    "title": "Add queue validation",
                    "description": "Verify queue state before dispatch",
                    "priority": 80,
                    "target_team": "idle",
                    "rationale": "duplicate proposal",
                    "research_refs": [],
                    "expected_output": "duplicate",
                    "validation": [],
                    "dependencies": [],
                },
            ],
        }
    ])
    secretary = SecretaryBot(store=store, model=model)

    revision = secretary.enrich_plan({"repo": "Skeleton"})

    assert len(model.calls) == 1
    assert len(revision.added_item_ids) == 1
    assert len(store.snapshot_items()) == 1
    assert model.calls[0]["correlation_id"].startswith("secretary-")


def test_manager_tracks_overtime_task_context_and_calls_model():
    store = InMemoryPlanStore()
    model = FakeModel([{"summary": "balanced", "tasks": []}])
    manager = SMBShiftManager(store=store, model=model, normal_shift_minutes=60)
    start = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    manager.clock_in("night-1", "night", at=start)
    store.add_items(
        [
            PlanItem(
                id="task-42",
                title="bounded work",
                description="claimed from canonical queue",
                priority=90,
                target_team="night",
            )
        ]
    )
    assert PlanQueueAPI(store).claim_next("night-1")["id"] == "task-42"
    worker = manager.heartbeat(
        "night-1",
        status="working",
        task_id="task-42",
        at=start + timedelta(minutes=95),
    )
    revision = manager.refresh_plan(project_context={"repo": "Skeleton"}, research=[])

    assert worker.normal_shift_minutes == 60
    assert worker.overtime_minutes == 35
    assert worker.overtime_task_ids == ["task-42"]
    assert len(model.calls) == 1
    assert revision.actor == "shift-manager"



def test_worker_events_are_monotonic_and_cannot_rewind_status():
    store = InMemoryPlanStore()
    manager = SMBShiftManager(store=store, model=FakeModel([]))
    start = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
    manager.clock_in("night-1", "night", at=start)
    manager.heartbeat(
        "night-1",
        status="idle",
        at=start + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="precedes canonical"):
        manager.heartbeat(
            "night-1",
            status="idle",
            at=start + timedelta(minutes=5),
        )
    with pytest.raises(ValueError, match="precedes canonical"):
        manager.clock_out(
            "night-1",
            at=start + timedelta(minutes=5),
        )

    worker = store.snapshot_workers()[0]
    assert worker.status == "idle"
    assert worker.last_heartbeat_at == start + timedelta(minutes=10)


def test_manager_policy_minutes_reject_bool_and_coercible_values():
    store = InMemoryPlanStore()
    with pytest.raises(ValueError):
        SMBShiftManager(store=store, model=FakeModel([]), normal_shift_minutes=True)
    with pytest.raises(ValueError):
        SMBShiftManager(
            store=store,
            model=FakeModel([]),
            overtime_soft_limit_minutes=1.5,
        )


def test_manager_ignores_direct_delegation_even_for_matching_worker():
    store = InMemoryPlanStore()
    secretary_model = FakeModel([
        {
            "summary": "seed",
            "tasks": [
                {
                    "title": "Night task",
                    "description": "night only",
                    "priority": 90,
                    "target_team": "night",
                    "rationale": "",
                    "research_refs": [],
                    "expected_output": "",
                    "validation": [],
                    "dependencies": [],
                }
            ],
        }
    ])
    SecretaryBot(store=store, model=secretary_model).enrich_plan({})
    item = store.snapshot_items()[0]

    manager_model = FakeModel([
        {
            "summary": "model attempted direct dispatch",
            "tasks": [],
            "delegation": [
                {"task_id_or_title": item.id, "worker_id": "night-1", "reason": "direct assignment"}
            ],
        }
    ])
    manager = SMBShiftManager(store=store, model=manager_model)
    manager.clock_in("night-1", "night")
    revision = manager.refresh_plan(project_context={}, research=[])

    assert revision.updated_item_ids == []
    assert store.snapshot_items()[0].owner is None
    assert "do not emit worker IDs" in manager_model.calls[0]["system_prompt"]


def test_manager_model_receives_aggregate_staffing_not_full_fleet():
    store = InMemoryPlanStore()
    model = FakeModel([{"summary": "capacity aware", "tasks": []}])
    manager = SMBShiftManager(store=store, model=model)
    for index in range(100):
        manager.clock_in(f"idle-{index}", "idle")

    manager.refresh_plan(project_context={}, research=[])

    prompt = model.calls[0]["user_prompt"]
    assert '"total": 100' in prompt
    assert '"attention_workers": []' in prompt
