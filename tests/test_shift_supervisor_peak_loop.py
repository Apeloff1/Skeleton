import json

from core.shift_supervisor.models import PlanRevision, utcnow
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.runtime import build_supervisor
from core.shift_supervisor.scheduler import SupervisorScheduler


class _Model:
    def __init__(self):
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return {"summary": "ok", "tasks": []}


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


def test_runtime_reuses_cycle_context_and_bounds_worker_prompt_surface():
    context_calls = 0
    research_generations = []

    def context_supplier():
        nonlocal context_calls
        context_calls += 1
        return {
            "generation": context_calls,
            "repository": "Apeloff1/Skeleton",
            "worker_snapshots": [
                {
                    "worker_id": "idle-prompt-guard",
                    "team": "idle",
                    "status": "idle",
                }
            ],
        }

    def research_source(context):
        research_generations.append(context["generation"])
        return [{"source": "same-cycle", "generation": context["generation"]}]

    model = _Model()
    scheduler = build_supervisor(
        project_context_supplier=context_supplier,
        research_sources={"test": research_source},
        model=model,
    )

    result = scheduler.run_once()

    assert result["actors"] == ["secretary", "manager"]
    assert context_calls == 1
    assert research_generations == [1]
    assert len(model.calls) == 2

    secretary_payload = json.loads(model.calls[0]["user_prompt"])
    manager_payload = json.loads(model.calls[1]["user_prompt"])
    for payload in (secretary_payload, manager_payload):
        planning_context = payload["project_context"]
        assert "worker_snapshots" not in planning_context
        assert planning_context["worker_snapshot_count"] == 1
        assert planning_context["generation"] == 1

    assert manager_payload["staffing"]["teams"]["idle"]["total"] == 1
    assert manager_payload["staffing"]["teams"]["night"]["total"] == 0
