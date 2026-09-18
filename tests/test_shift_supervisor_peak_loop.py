from core.shift_supervisor.models import PlanRevision, utcnow
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.scheduler import SupervisorScheduler


class _Secretary:
    def __init__(self, events):
        self.events = events

    def enrich_plan(self, context):
        self.events.append(("secretary", context["generation"]))
        return PlanRevision("secretary-rev", "secretary", utcnow())


class _Manager:
    def __init__(self, store, events):
        self.store = store
        self.events = events
        self.normal_shift_minutes = 480

    def refresh_plan(self, *, project_context, research):
        self.events.append(("manager", project_context["generation"]))
        return PlanRevision("manager-rev", "shift-manager", utcnow())


class _OneLoopStop:
    def __init__(self):
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, _delay):
        self.stopped = True
        return True


def test_run_forever_coalesces_coincident_secretary_and_manager_tick(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    events = []
    context_calls = 0

    def context_supplier():
        nonlocal context_calls
        context_calls += 1
        events.append(("context", context_calls))
        return {"generation": context_calls, "worker_snapshots": []}

    def research_supplier():
        events.append(("research", context_calls))
        return [{"source": "test"}]

    store = InMemoryPlanStore()
    scheduler = SupervisorScheduler(
        manager=_Manager(store, events),
        secretary=_Secretary(events),
        project_context_supplier=context_supplier,
        research_supplier=research_supplier,
    )
    scheduler._stop = _OneLoopStop()
    monkeypatch.setattr("core.shift_supervisor.scheduler.time.monotonic", lambda: 100.0)

    scheduler.run_forever()

    assert context_calls == 1
    assert events == [
        ("context", 1),
        ("secretary", 1),
        ("research", 1),
        ("manager", 1),
    ]