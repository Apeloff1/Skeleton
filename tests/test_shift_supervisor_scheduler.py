from core.shift_supervisor.models import PlanRevision, utcnow
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.scheduler import SupervisorScheduler


class _Store:
    def snapshot_items(self):
        return []

    def snapshot_workers(self):
        return []


class _Secretary:
    def __init__(self):
        self.calls = []

    def enrich_plan(self, context):
        self.calls.append(context)
        return PlanRevision("secretary-rev", "secretary", utcnow())


class _Manager:
    def __init__(self, store=None):
        self.calls = []
        self.store = store or _Store()
        self.normal_shift_minutes = 480

    def refresh_plan(self, *, project_context, research):
        self.calls.append((project_context, research))
        return PlanRevision("manager-rev", "shift-manager", utcnow())


def test_scheduler_advance_skips_missed_ticks_without_bursting():
    assert SupervisorScheduler._advance(100.0, 900, 100.0) == 1000.0
    assert SupervisorScheduler._advance(100.0, 900, 2800.0) == 3700.0


def test_scheduler_rejects_non_positive_interval():
    try:
        SupervisorScheduler._advance(100.0, 0, 100.0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_once_executes_both_actors_and_returns_machine_plan():
    secretary = _Secretary()
    manager = _Manager()
    context = {"repository": "Apeloff1/Skeleton"}
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: context,
        research_supplier=lambda: [{"source": "repo"}],
    )

    result = scheduler.run_once()

    assert result["actors"] == ["secretary", "manager"]
    assert result["plan_items"] == []
    assert result["workers"] == []
    assert secretary.calls == [context]
    assert manager.calls == [(context, [{"source": "repo"}])]


def test_run_once_ingests_latest_worker_snapshot_before_manager_call():
    secretary = _Secretary()
    store = InMemoryPlanStore()
    manager = _Manager(store)
    context = {
        "worker_snapshots": [
            {
                "worker_id": "idle-0042",
                "team": "idle",
                "status": "offline",
                "clocked_in_at": "2026-09-16T10:00:00+00:00",
                "clocked_out_at": "2026-09-16T10:07:00+00:00",
                "last_heartbeat_at": "2026-09-16T10:07:00+00:00",
                "normal_shift_minutes": 7,
                "overtime_minutes": 0,
                "metadata": {"last_task_id": "issue:42", "worked_on": ["issue:42"]},
            }
        ]
    }
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: context,
    )

    result = scheduler.run_once(run_secretary=False, run_manager=True)

    assert result["workers"][0]["worker_id"] == "idle-0042"
    assert result["workers"][0]["normal_shift_minutes"] == 7
    assert result["workers"][0]["metadata"]["last_task_id"] == "issue:42"
    assert manager.calls[0][0] is context


def test_run_once_can_execute_secretary_without_manager():
    secretary = _Secretary()
    manager = _Manager()
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: {},
    )

    result = scheduler.run_once(run_secretary=True, run_manager=False)

    assert result["actors"] == ["secretary"]
    assert len(secretary.calls) == 1
    assert manager.calls == []


def test_run_once_requires_at_least_one_actor():
    scheduler = SupervisorScheduler(
        manager=_Manager(),
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )
    try:
        scheduler.run_once(run_secretary=False, run_manager=False)
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def _snapshot(*, key, minutes, started_at, ended_at, task):
    return {
        "worker_id": "idle-0042",
        "team": "idle",
        "status": "offline",
        "clocked_in_at": started_at,
        "clocked_out_at": ended_at,
        "last_heartbeat_at": ended_at,
        "normal_shift_minutes": min(minutes, 480),
        "overtime_minutes": max(0, minutes - 480),
        "overtime_task_ids": [],
        "metadata": {
            "shift_key": key,
            "shift_minutes": minutes,
            "worked_on": [task],
            "last_task_id": task,
        },
    }


def test_worker_snapshots_accumulate_daily_overtime_without_double_counting(monkeypatch):
    monkeypatch.setenv("SHIFT_ACCOUNTING_TIMEZONE", "UTC")
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    first = _snapshot(
        key="idle-0042:first",
        minutes=300,
        started_at="2026-09-16T05:00:00+00:00",
        ended_at="2026-09-16T10:00:00+00:00",
        task="issue:1",
    )
    second = _snapshot(
        key="idle-0042:second",
        minutes=240,
        started_at="2026-09-16T12:00:00+00:00",
        ended_at="2026-09-16T16:00:00+00:00",
        task="issue:2",
    )

    scheduler._ingest_worker_snapshots([first])
    scheduler._ingest_worker_snapshots([second])
    scheduler._ingest_worker_snapshots([second])

    worker = manager.store.snapshot_workers()[0]
    assert worker.normal_shift_minutes == 480
    assert worker.overtime_minutes == 60
    assert worker.overtime_task_ids == ["issue:2"]
    assert worker.metadata["daily_work_minutes"] == 540
    assert worker.metadata["applied_shift_keys"] == [
        "idle-0042:first",
        "idle-0042:second",
    ]


def test_new_accounting_day_archives_previous_overtime(monkeypatch):
    monkeypatch.setenv("SHIFT_ACCOUNTING_TIMEZONE", "UTC")
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            _snapshot(
                key="idle-day-one",
                minutes=600,
                started_at="2026-09-15T10:00:00+00:00",
                ended_at="2026-09-15T20:00:00+00:00",
                task="task-overtime",
            )
        ]
    )
    scheduler._ingest_worker_snapshots(
        [
            _snapshot(
                key="idle-day-two",
                minutes=60,
                started_at="2026-09-16T07:00:00+00:00",
                ended_at="2026-09-16T08:00:00+00:00",
                task="task-new-day",
            )
        ]
    )

    worker = manager.store.snapshot_workers()[0]
    assert worker.normal_shift_minutes == 60
    assert worker.overtime_minutes == 0
    assert worker.metadata["daily_accounting_day"] == "2026-09-16"
    assert worker.metadata["overtime_history"] == [
        {
            "day": "2026-09-15",
            "work_minutes": 600,
            "overtime_minutes": 120,
            "task_ids": ["task-overtime"],
        }
    ]