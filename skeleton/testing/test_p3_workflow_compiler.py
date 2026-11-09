from __future__ import annotations

import copy

import pytest

from skeleton.ai.runtime.autonomous_engineering.workflow import (
    WorkflowCompileError,
    WorkflowCompiler,
    critical_path,
    simulate_schedule,
)


def _source():
    return {
        "workflow_id": "p3.fixture",
        "version": "v1",
        "tasks": [
            {
                "task_id": "inspect",
                "kind": "analysis",
                "objective": "Inspect the repository model.",
                "estimated_effort": 2,
                "required_capabilities": ["repo.read"],
            },
            {
                "task_id": "plan",
                "kind": "analysis",
                "objective": "Build a bounded safe-change plan.",
                "depends_on": ["inspect"],
                "estimated_effort": 4,
                "required_capabilities": ["repo.plan"],
            },
            {
                "task_id": "test",
                "kind": "test",
                "objective": "Run focused verification.",
                "depends_on": ["inspect"],
                "estimated_effort": 3,
                "conflict_keys": ["repo"],
                "required_capabilities": ["test.run"],
            },
            {
                "task_id": "edit",
                "kind": "code",
                "objective": "Apply an approved transactional edit.",
                "depends_on": ["plan"],
                "estimated_effort": 5,
                "effect_class": "write",
                "approval_required": True,
                "conflict_keys": ["repo"],
                "required_capabilities": ["repo.write"],
            },
            {
                "task_id": "verify",
                "kind": "verify",
                "objective": "Independently verify the resulting repository state.",
                "depends_on": ["edit", "test"],
                "estimated_effort": 2,
                "required_capabilities": ["repo.verify"],
            },
        ],
    }


def test_compile_is_deterministic_and_source_bound() -> None:
    compiler = WorkflowCompiler()
    first = compiler.compile(_source())
    second_source = _source()
    second_source["tasks"] = list(reversed(second_source["tasks"]))
    second = compiler.compile(second_source)

    # Source identity records declaration order, while canonical IR ordering is
    # deterministic. This prevents silently rewriting source provenance.
    assert first.source_digest != second.source_digest
    assert [task.task_id for task in first.tasks] == sorted(
        task.task_id for task in first.tasks
    )
    assert first.topological_order == ("inspect", "plan", "edit", "test", "verify")
    assert first.ir_digest != second.ir_digest


def test_identical_source_has_identical_ir() -> None:
    compiler = WorkflowCompiler()
    first = compiler.compile(_source())
    second = compiler.compile(copy.deepcopy(_source()))
    assert first.as_dict() == second.as_dict()


def test_rejects_unknown_dependency() -> None:
    source = _source()
    source["tasks"][0]["depends_on"] = ["missing"]
    with pytest.raises(WorkflowCompileError, match="unknown task"):
        WorkflowCompiler().compile(source)


def test_rejects_cycle() -> None:
    source = _source()
    source["tasks"][0]["depends_on"] = ["verify"]
    with pytest.raises(WorkflowCompileError, match="dependency cycle"):
        WorkflowCompiler().compile(source)


def test_rejects_effectful_task_without_approval() -> None:
    source = _source()
    edit = next(task for task in source["tasks"] if task["task_id"] == "edit")
    edit["approval_required"] = False
    with pytest.raises(WorkflowCompileError, match="requires explicit approval"):
        WorkflowCompiler().compile(source)


def test_critical_path_is_weighted_and_deterministic() -> None:
    workflow = WorkflowCompiler().compile(_source())
    assert critical_path(workflow) == ("inspect", "plan", "edit", "verify")


def test_scheduler_respects_dependencies_and_conflicts() -> None:
    workflow = WorkflowCompiler().compile(_source())
    simulation = simulate_schedule(workflow, max_concurrency=3)
    assert simulation.waves[0].task_ids == ("inspect",)
    # plan and test are both ready after inspect. They can share a wave because
    # only test holds the repo conflict key.
    assert set(simulation.waves[1].task_ids) == {"plan", "test"}
    assert simulation.waves[2].task_ids == ("edit",)
    assert simulation.waves[3].task_ids == ("verify",)
    assert simulation.completed_order[-1] == "verify"


def test_scheduler_serializes_conflicting_ready_tasks() -> None:
    source = {
        "workflow_id": "p3.conflicts",
        "version": "v1",
        "tasks": [
            {
                "task_id": "a",
                "kind": "code",
                "objective": "First edit.",
                "effect_class": "write",
                "approval_required": True,
                "conflict_keys": ["repo"],
            },
            {
                "task_id": "b",
                "kind": "code",
                "objective": "Second edit.",
                "effect_class": "write",
                "approval_required": True,
                "conflict_keys": ["repo"],
            },
        ],
    }
    simulation = simulate_schedule(
        WorkflowCompiler().compile(source),
        max_concurrency=2,
    )
    assert [wave.task_ids for wave in simulation.waves] == [("a",), ("b",)]


def test_bounds_are_fail_closed() -> None:
    compiler = WorkflowCompiler(max_tasks=2)
    with pytest.raises(WorkflowCompileError, match="exceeds max_tasks"):
        compiler.compile(_source())
