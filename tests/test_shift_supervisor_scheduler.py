from core.shift_supervisor.models import PlanItem, PlanRevision, WorkerState, utcnow
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.scheduler import SupervisorCadence, SupervisorScheduler, github_actions_forbids_unbounded_loop


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


def test_validated_worker_snapshot_retires_matching_canonical_plan_item():
    secretary = _Secretary()
    store = InMemoryPlanStore()
    store.add_items(
        [
            PlanItem(
                id="night-task-1",
                title="Night canonical task",
                description="validated night work",
                priority=90,
                target_team="night",
            ),
            PlanItem(
                id="idle-task-1",
                title="Idle canonical task",
                description="must not be closed by a night worker",
                priority=80,
                target_team="idle",
            ),
        ]
    )
    manager = _Manager(store)
    context = {
        "worker_snapshots": [
            {
                "worker_id": "night-0042",
                "team": "night",
                "status": "offline",
                "clocked_in_at": "2026-09-16T10:00:00+00:00",
                "clocked_out_at": "2026-09-16T10:07:00+00:00",
                "last_heartbeat_at": "2026-09-16T10:07:00+00:00",
                "normal_shift_minutes": 7,
                "overtime_minutes": 0,
                "metadata": {
                    "last_task_id": "night-task-1",
                    "worked_on": ["night-task-1", "idle-task-1", "unknown-task"],
                },
            }
        ]
    }
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: context,
    )

    result = scheduler.run_once(run_secretary=False, run_manager=True)

    items = {item["id"]: item for item in result["plan_items"]}
    assert items["night-task-1"]["status"] == "done"
    assert items["night-task-1"]["owner"] == "night-0042"
    assert items["night-task-1"]["metadata"]["completion_source"] == "validated-studio-worker-snapshot"
    assert items["idle-task-1"]["status"] == "queued"
    assert items["idle-task-1"]["owner"] is None


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


def test_github_actions_env_forbids_unbounded_scheduler_loop():
    assert github_actions_forbids_unbounded_loop({"GITHUB_ACTIONS": "true"}) is True
    assert github_actions_forbids_unbounded_loop({"GITHUB_ACTIONS": "1"}) is True
    assert github_actions_forbids_unbounded_loop({"GITHUB_ACTIONS": "false"}) is False
    assert github_actions_forbids_unbounded_loop({}) is False


def test_run_forever_fails_closed_in_github_actions(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    scheduler = SupervisorScheduler(
        manager=_Manager(),
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )
    try:
        scheduler.run_forever()
    except RuntimeError as exc:
        assert "run_once" in str(exc)
        assert "GitHub Actions" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_run_forever_runs_due_actors_until_stopped(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    secretary = _Secretary()
    manager = _Manager()
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=secretary,
        project_context_supplier=lambda: {"cycle": "local"},
        research_supplier=lambda: [{"source": "local"}],
        cadence=SupervisorCadence(secretary_seconds=60, manager_seconds=60, heartbeat_seconds=1),
    )

    import threading
    import time

    thread = threading.Thread(target=scheduler.run_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not (secretary.calls and manager.calls):
        time.sleep(0.01)
    scheduler.stop()
    thread.join(timeout=2.0)

    assert secretary.calls == [{"cycle": "local"}]
    assert manager.calls == [({"cycle": "local"}, [{"source": "local"}])]
    assert thread.is_alive() is False


def test_fresh_worker_snapshot_cannot_self_assign_canonical_work():
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            {
                "worker_id": "night-untrusted",
                "team": "night",
                "status": "working",
                "current_task_id": "self-selected-task",
                "last_heartbeat_at": "2026-09-19T12:00:00+00:00",
                "metadata": {
                    "current_squad_id": "squad-forged",
                    "current_squad_role": "lead",
                },
            }
        ]
    )

    worker = store.snapshot_workers()[0]
    assert worker.current_task_id is None
    assert worker.status == "idle"
    assert "current_squad_id" not in worker.metadata
    assert "current_squad_role" not in worker.metadata
    assert worker.metadata["snapshot_assignment_rejected"] is True


def test_worker_snapshot_cannot_replace_existing_queue_assignment():
    store = InMemoryPlanStore()
    store.upsert_worker(
        WorkerState(
            worker_id="night-0001",
            team="night",
            status="working",
            last_heartbeat_at=SupervisorScheduler._parse_datetime(
                "2026-09-19T11:59:00+00:00"
            ),
            current_task_id="canonical-task",
            metadata={
                "current_squad_id": "squad-canonical",
                "current_squad_role": "reviewer",
            },
        )
    )
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            {
                "worker_id": "night-0001",
                "team": "night",
                "status": "idle",
                "current_task_id": "forged-replacement",
                "last_heartbeat_at": "2026-09-19T12:00:00+00:00",
                "metadata": {
                    "current_squad_id": "squad-forged",
                    "current_squad_role": "lead",
                },
            }
        ]
    )

    worker = store.snapshot_workers()[0]
    assert worker.current_task_id == "canonical-task"
    assert worker.status == "working"
    assert worker.metadata["current_squad_id"] == "squad-canonical"
    assert worker.metadata["current_squad_role"] == "reviewer"
    assert worker.metadata["snapshot_assignment_rejected"] is True


def test_snapshot_identity_requires_text_not_python_string_coercion():
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            {
                "worker_id": True,
                "team": "night",
                "status": "idle",
            },
            {
                "worker_id": "valid-worker",
                "team": False,
                "status": "idle",
            },
        ]
    )

    assert store.snapshot_workers() == []


def test_snapshot_boolean_minutes_do_not_alias_integer_minutes():
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            {
                "worker_id": "idle-boolean",
                "team": "idle",
                "status": "offline",
                "normal_shift_minutes": True,
                "overtime_minutes": True,
                "last_heartbeat_at": "2026-09-19T12:00:00+00:00",
            }
        ]
    )

    worker = store.snapshot_workers()[0]
    assert worker.normal_shift_minutes == 0
    assert worker.overtime_minutes == 0


def test_snapshot_naive_datetime_is_not_treated_as_local_timezone():
    store = InMemoryPlanStore()
    manager = _Manager(store)
    scheduler = SupervisorScheduler(
        manager=manager,
        secretary=_Secretary(),
        project_context_supplier=lambda: {},
    )

    scheduler._ingest_worker_snapshots(
        [
            {
                "worker_id": "idle-naive",
                "team": "idle",
                "status": "offline",
                "last_heartbeat_at": "2026-09-19T12:00:00",
            }
        ]
    )

    assert store.snapshot_workers()[0].last_heartbeat_at is None
