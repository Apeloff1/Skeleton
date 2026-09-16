from datetime import datetime, timedelta, timezone

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
    model = FakeModel([{"summary": "balanced", "tasks": [], "delegation": []}])
    manager = SMBShiftManager(store=store, model=model, normal_shift_minutes=60)
    start = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)

    manager.clock_in("night-1", "night", at=start)
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


def test_manager_rejects_cross_team_delegation():
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
            "summary": "bad delegation is ignored",
            "tasks": [],
            "delegation": [
                {"task_id_or_title": item.id, "worker_id": "idle-1", "reason": "wrong team"}
            ],
        }
    ])
    manager = SMBShiftManager(store=store, model=manager_model)
    manager.clock_in("idle-1", "idle")
    revision = manager.refresh_plan(project_context={}, research=[])

    assert revision.updated_item_ids == []
    assert store.snapshot_items()[0].owner is None
