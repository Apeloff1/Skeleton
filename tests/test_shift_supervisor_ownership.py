from datetime import datetime, timezone

import pytest

from core.shift_supervisor.models import PlanItem, PlanRevision, WorkerState
from core.shift_supervisor.ownership import (
    SupervisorStateTypeError,
    clone_plan_item,
    clone_plan_revision,
    clone_worker_state,
    require_exact_schema_version,
    strict_nonnegative_int,
)


def test_plan_item_clone_owns_nested_mutable_state():
    item = PlanItem(
        id="task",
        title="task",
        description="desc",
        priority=50,
        target_team="night",
        dependencies=["dep"],
        research_refs=["ref"],
        validation=["pytest"],
        metadata={"nested": {"paths": ["a.py"]}},
    )
    cloned = clone_plan_item(item)

    cloned.dependencies.append("other")
    cloned.research_refs.append("other")
    cloned.validation.append("ruff")
    cloned.metadata["nested"]["paths"].append("b.py")

    assert item.dependencies == ["dep"]
    assert item.research_refs == ["ref"]
    assert item.validation == ["pytest"]
    assert item.metadata == {"nested": {"paths": ["a.py"]}}


def test_worker_clone_owns_nested_mutable_state():
    worker = WorkerState(
        worker_id="night-1",
        team="night",
        overtime_task_ids=["task-a"],
        metadata={"history": [{"task": "task-a"}]},
    )
    cloned = clone_worker_state(worker)
    cloned.overtime_task_ids.append("task-b")
    cloned.metadata["history"][0]["task"] = "mutated"

    assert worker.overtime_task_ids == ["task-a"]
    assert worker.metadata == {"history": [{"task": "task-a"}]}


def test_revision_clone_owns_identity_lists():
    revision = PlanRevision(
        revision_id="rev-1",
        actor="supervisor",
        created_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
        added_item_ids=["a"],
        updated_item_ids=["b"],
    )
    cloned = clone_plan_revision(revision)
    cloned.added_item_ids.append("x")
    cloned.updated_item_ids.append("y")
    assert revision.added_item_ids == ["a"]
    assert revision.updated_item_ids == ["b"]


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_schema_version_rejects_bool_and_coercible_values(value):
    with pytest.raises(ValueError):
        require_exact_schema_version(value, 1)


def test_schema_version_accepts_exact_integer_only():
    assert require_exact_schema_version(1, 1) == 1


@pytest.mark.parametrize("value", [True, False, 1.0, "1", -1])
def test_strict_nonnegative_int_rejects_coercion_and_negative_values(value):
    with pytest.raises(ValueError):
        strict_nonnegative_int(value, field="minutes")


def test_strict_nonnegative_int_accepts_exact_bounded_integer():
    assert strict_nonnegative_int(7, field="minutes", maximum=10) == 7
    with pytest.raises(ValueError, match="maximum"):
        strict_nonnegative_int(11, field="minutes", maximum=10)


def test_clone_rejects_unknown_mutable_object():
    item = PlanItem(
        id="task",
        title="task",
        description="desc",
        priority=50,
        target_team="night",
        metadata={"opaque": object()},
    )
    with pytest.raises(SupervisorStateTypeError):
        clone_plan_item(item)
