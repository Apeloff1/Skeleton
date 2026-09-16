from core.shift_supervisor.models import PlanRevision, utcnow
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
    def __init__(self):
        self.calls = []
        self.store = _Store()

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
