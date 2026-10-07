import json

import pytest

from core.shift_supervisor.models import PlanItem, WorkerState
from core.shift_supervisor.plan_store import InMemoryPlanStore
from core.shift_supervisor.secretary import SecretaryBot
from core.shift_supervisor.shift_manager import SMBShiftManager
from core.shift_supervisor.squads import SQUAD_ROLES, SQUAD_SIZE, SquadCoordinator


class RecordingModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def call_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _task(task_key: str, *, dependencies=None, domain="gameplay"):
    return {
        "task_key": task_key,
        "title": task_key,
        "description": f"Implement {task_key}",
        "priority": 80,
        "target_team": "night",
        "task_type": "engineering",
        "rationale": "unblocks frontier work",
        "research_refs": ["internal:test"],
        "expected_output": "validated change",
        "acceptance_criteria": ["focused regression passes"],
        "validation": ["pytest focused"],
        "dependencies": dependencies or [],
        "conflict_domain": domain,
        "relevant_paths": [f"skeleton/{domain}/core.py"],
        "security_considerations": "preserve trust boundaries",
        "performance_considerations": "measure if hot path changes",
    }


def _squad_item(task_id: str = "task-a") -> PlanItem:
    return PlanItem(
        id=task_id,
        title=task_id,
        description=f"Implement {task_id}",
        priority=100,
        target_team="night",
        metadata={
            "squad_size": SQUAD_SIZE,
            "relevant_paths": ["skeleton/runtime/core.py"],
            "conflict_domain": "runtime",
        },
    )


def test_manager_maps_local_dependency_keys_to_canonical_ids_and_marks_squad_contract() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "dependency aware",
            "tasks": [
                _task("foundation", domain="runtime"),
                _task("integration", dependencies=["foundation"], domain="integration"),
            ],
        }
    )
    manager = SMBShiftManager(store=store, model=model)

    revision = manager.refresh_plan(project_context={"repo": "Skeleton"}, research=[])
    items = {item.metadata["task_key"]: item for item in store.snapshot_items()}

    assert len(revision.added_item_ids) == 2
    assert items["integration"].dependencies == [items["foundation"].id]
    for item in items.values():
        assert item.metadata["squad_size"] == SQUAD_SIZE
        assert item.metadata["squad_roles"] == list(SQUAD_ROLES)
        assert item.metadata["acceptance_criteria"] == ["focused regression passes"]
        assert item.metadata["conflict_domain"]


def test_manager_drops_task_with_unresolvable_dependency_instead_of_executing_out_of_order() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel({"summary": "bad dep", "tasks": [_task("child", dependencies=["missing-parent"])]})
    manager = SMBShiftManager(store=store, model=model)

    revision = manager.refresh_plan(project_context={}, research=[])

    assert revision.added_item_ids == []
    assert store.snapshot_items() == []


def test_manager_rejects_entire_batch_when_invalid_parent_has_dependents() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "bad dependency chain",
            "tasks": [
                _task("parent", dependencies=["missing-external"], domain="runtime"),
                _task("child", dependencies=["parent"], domain="integration"),
            ],
        }
    )
    manager = SMBShiftManager(store=store, model=model)

    revision = manager.refresh_plan(project_context={}, research=[])

    assert revision.added_item_ids == []
    assert store.snapshot_items() == []


def test_manager_rejects_duplicate_task_keys_as_ambiguous() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "ambiguous keys",
            "tasks": [
                _task("same", domain="runtime"),
                _task("same", domain="integration"),
            ],
        }
    )
    manager = SMBShiftManager(store=store, model=model)

    revision = manager.refresh_plan(project_context={}, research=[])

    assert revision.added_item_ids == []
    assert store.snapshot_items() == []


def test_manager_rejects_entire_cyclic_batch() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "cycle",
            "tasks": [
                _task("a", dependencies=["b"], domain="a"),
                _task("b", dependencies=["a"], domain="b"),
            ],
        }
    )
    manager = SMBShiftManager(store=store, model=model)

    with pytest.raises(ValueError, match="cyclic plan dependencies rejected"):
        manager.refresh_plan(project_context={}, research=[])
    assert store.snapshot_items() == []


def test_manager_exposes_safe_four_worker_capacity_to_planner() -> None:
    store = InMemoryPlanStore()
    for index in range(9):
        store.upsert_worker(WorkerState(worker_id=f"night-{index}", team="night", status="idle"))
    model = RecordingModel({"summary": "capacity", "tasks": []})
    manager = SMBShiftManager(store=store, model=model)

    manager.refresh_plan(project_context={}, research=[])

    payload = json.loads(model.calls[0]["user_prompt"])
    assert payload["staffing"]["teams"]["night"]["safe_squad_capacity"] == 2
    assert payload["policies"]["squad_size"] == 4
    assert payload["policies"]["safe_squad_capacity"]["night"] == 2
    assert "one task, one active squad" in payload["policies"]["anti_swarm"]
    assert "acyclic DAG" in payload["policies"]["dependency_policy"]


def test_manager_worker_state_updates_cannot_bypass_live_squad_ownership() -> None:
    store = InMemoryPlanStore()
    manager = SMBShiftManager(store=store, model=RecordingModel({"summary": "", "tasks": []}))
    for index in range(4):
        manager.clock_in(f"night-{index}", "night")
    store.add_items([_squad_item()])
    lease = SquadCoordinator(store).claim_next("night", plan_generation="rev-1")
    assert lease is not None
    worker_id = lease.members["lead"]

    with pytest.raises(PermissionError, match="replace or clear"):
        manager.heartbeat(worker_id, status="working", task_id=None)
    with pytest.raises(PermissionError, match="replace or clear"):
        manager.heartbeat(worker_id, status="working", task_id="other-task")
    with pytest.raises(PermissionError, match="mark a worker idle"):
        manager.heartbeat(worker_id, status="idle", task_id=lease.task_id)
    with pytest.raises(PermissionError, match="clock out"):
        manager.clock_out(worker_id)
    with pytest.raises(PermissionError, match="clock in or reset"):
        manager.clock_in(worker_id, "night")

    heartbeat = manager.heartbeat(worker_id, status="working", task_id=lease.task_id)
    assert heartbeat.current_task_id == lease.task_id
    assert heartbeat.status == "working"


def test_manager_heartbeat_cannot_self_assign_idle_worker() -> None:
    store = InMemoryPlanStore()
    manager = SMBShiftManager(store=store, model=RecordingModel({"summary": "", "tasks": []}))
    manager.clock_in("night-0", "night")

    with pytest.raises(PermissionError, match="cannot self-assign"):
        manager.heartbeat("night-0", status="working", task_id="made-up-task")

    worker = store.snapshot_workers()[0]
    assert worker.status == "idle"
    assert worker.current_task_id is None


def test_secretary_additions_are_squad_ready_and_dependency_resolved() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "add missing validation",
            "tasks": [
                _task("test-foundation", domain="tests"),
                _task("test-integration", dependencies=["test-foundation"], domain="integration-tests"),
            ],
        }
    )
    secretary = SecretaryBot(store=store, model=model)

    revision = secretary.enrich_plan({"repo": "Skeleton"})
    items = {item.metadata["task_key"]: item for item in store.snapshot_items()}

    assert len(revision.added_item_ids) == 2
    assert items["test-integration"].dependencies == [items["test-foundation"].id]
    assert all(item.metadata["squad_size"] == 4 for item in items.values())
    assert "never dispatch workers" in SecretaryBot.SYSTEM_PROMPT.lower()


def test_secretary_rejects_entire_batch_when_invalid_parent_has_dependents() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "bad dependency chain",
            "tasks": [
                _task("research", dependencies=["missing-external"], domain="research"),
                _task("verify", dependencies=["research"], domain="verify"),
            ],
        }
    )
    secretary = SecretaryBot(store=store, model=model)

    revision = secretary.enrich_plan({})

    assert revision.added_item_ids == []
    assert store.snapshot_items() == []


def test_secretary_rejects_duplicate_task_keys_as_ambiguous() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "ambiguous keys",
            "tasks": [
                _task("same", domain="research"),
                _task("same", domain="verify"),
            ],
        }
    )
    secretary = SecretaryBot(store=store, model=model)

    revision = secretary.enrich_plan({})

    assert revision.added_item_ids == []
    assert store.snapshot_items() == []


def test_secretary_rejects_entire_cyclic_batch() -> None:
    store = InMemoryPlanStore()
    model = RecordingModel(
        {
            "summary": "cycle",
            "tasks": [
                _task("research", dependencies=["verify"], domain="research"),
                _task("verify", dependencies=["research"], domain="verify"),
            ],
        }
    )
    secretary = SecretaryBot(store=store, model=model)

    with pytest.raises(ValueError, match="cyclic plan dependencies rejected"):
        secretary.enrich_plan({})
    assert store.snapshot_items() == []

def test_manager_parser_preserves_council_and_epistemic_evidence_with_squad_contract() -> None:
    task = _task("reviewed-runtime", domain="runtime")
    task["_planning_council"] = {
        "version": 2,
        "decision": "accept",
        "confidence": 97,
        "roles": {"researcher": {}, "lead": {}, "reviewer": {}, "verifier": {}},
        "failure_modes": ["runtime contract regression"],
        "success_metrics": ["focused suite passes"],
    }
    task["_epistemic_gate"] = {
        "status": "ready",
        "checks": {"confidence": True},
    }

    items = SMBShiftManager._parse_tasks(
        [task],
        "manager-reviewed",
        existing_ids=set(),
    )

    assert len(items) == 1
    item = items[0]
    assert item.metadata["squad_size"] == SQUAD_SIZE
    assert item.metadata["squad_roles"] == list(SQUAD_ROLES)
    assert item.metadata["planning_council"]["confidence"] == 97
    assert item.metadata["epistemic_gate"]["status"] == "ready"
    assert item.metadata["task_key"] == "reviewed-runtime"
    assert item.metadata["conflict_domain"] == "runtime"


def test_secretary_parser_preserves_council_and_epistemic_evidence_with_squad_contract() -> None:
    task = _task("reviewed-test", domain="tests")
    task["_planning_council"] = {
        "version": 2,
        "decision": "revise",
        "confidence": 91,
        "roles": {"researcher": {}, "lead": {}, "reviewer": {}, "verifier": {}},
        "failure_modes": ["coverage gap"],
        "success_metrics": ["focused regression passes"],
    }
    task["_epistemic_gate"] = {
        "status": "ready",
        "checks": {"validation": True},
    }

    items = SecretaryBot._parse_tasks(
        [task],
        "secretary-reviewed",
        existing_ids=set(),
    )

    assert len(items) == 1
    item = items[0]
    assert item.metadata["squad_size"] == SQUAD_SIZE
    assert item.metadata["squad_roles"] == list(SQUAD_ROLES)
    assert item.metadata["planning_council"]["decision"] == "revise"
    assert item.metadata["epistemic_gate"]["status"] == "ready"
    assert item.metadata["task_key"] == "reviewed-test"
    assert item.metadata["conflict_domain"] == "tests"
