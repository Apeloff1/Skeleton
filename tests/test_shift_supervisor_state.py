from datetime import datetime, timezone

import pytest

from core.shift_supervisor.__main__ import _read_state, _write_state
from core.shift_supervisor.models import PlanItem, PlanRevision, WorkerState
from core.shift_supervisor.plan_store import InMemoryPlanStore


def test_store_state_round_trip_preserves_open_plan_and_active_worker():
    now = datetime(2026, 9, 16, 17, 0, tzinfo=timezone.utc)
    store = InMemoryPlanStore()
    store.add_items(
        [
            PlanItem(
                id="task-1",
                title="Validate shared plan",
                description="Ensure both shifts consume the same durable plan.",
                priority=95,
                target_team="night",
                validation=["state survives the next scheduled run"],
                created_at=now,
                updated_at=now,
            )
        ]
    )
    store.upsert_worker(
        WorkerState(
            worker_id="idle-0042",
            team="idle",
            status="working",
            clocked_in_at=now,
            last_heartbeat_at=now,
            current_task_id="task-1",
            normal_shift_minutes=120,
        )
    )
    store.append_revision(
        PlanRevision(
            revision_id="rev-1",
            actor="shift-manager",
            created_at=now,
            added_item_ids=["task-1"],
            summary="shared plan refreshed",
            correlation_id="manager-test",
        )
    )

    restored = InMemoryPlanStore()
    restored.restore_state(store.export_state())

    items = restored.snapshot_items()
    workers = restored.snapshot_workers()
    revisions = restored.snapshot_revisions()
    assert [item.id for item in items] == ["task-1"]
    assert items[0].target_team == "night"
    assert workers[0].worker_id == "idle-0042"
    assert workers[0].current_task_id == "task-1"
    assert revisions[0].correlation_id == "manager-test"


def test_export_omits_uninteresting_offline_workers_but_keeps_daily_hours():
    store = InMemoryPlanStore()
    store.upsert_worker(WorkerState(worker_id="idle-0000", team="idle"))
    store.upsert_worker(
        WorkerState(
            worker_id="idle-0002",
            team="idle",
            status="offline",
            normal_shift_minutes=120,
            metadata={"daily_accounting_day": "2026-09-16", "daily_work_minutes": 120},
        )
    )
    store.upsert_worker(
        WorkerState(
            worker_id="night-0001",
            team="night",
            status="offline",
            overtime_minutes=15,
            overtime_task_ids=["task-ot"],
        )
    )

    state = store.export_state()
    assert [worker["worker_id"] for worker in state["workers"]] == [
        "night-0001",
        "idle-0002",
    ]


def test_compressed_state_file_round_trip(tmp_path):
    path = tmp_path / "state.txt"
    state = {
        "version": 1,
        "plan_items": [{"id": "x", "title": "t"}],
        "workers": [],
        "revisions": [],
    }

    _write_state(path, state)

    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("gz:v1:")
    assert _read_state(path) == state


def test_corrupt_compressed_state_is_rejected(tmp_path):
    path = tmp_path / "corrupt.txt"
    path.write_text("gz:v1:not-valid-base64%%%\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid compressed shift-supervisor state"):
        _read_state(path)


def test_malformed_plain_state_json_is_rejected(tmp_path):
    path = tmp_path / "malformed.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid shift-supervisor state JSON"):
        _read_state(path)


def test_restore_rejects_future_state_version():
    store = InMemoryPlanStore()
    with pytest.raises(ValueError, match="unsupported shift-supervisor state version"):
        store.restore_state({"version": 999})