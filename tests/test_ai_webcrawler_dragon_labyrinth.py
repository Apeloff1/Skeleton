"""Labyrinth experiment DAG and fail-closed worker lease tests."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_labyrinth import (
    DragonLabyrinth, WorkKind, WorkSpec, WorkStatus, plan_labyrinth,
)


def graph():
    nodes = (
        WorkSpec("capture", WorkKind.CAPTURE_REVIEW),
        WorkSpec("vision", WorkKind.TEMPORAL_ANALYSIS, ("capture",)),
        WorkSpec("taste", WorkKind.TASTE_CONFIRMATION, ("vision",), True),
        WorkSpec("build", WorkKind.PROTOTYPE_BUILD, ("taste",)),
        WorkSpec("gate", WorkKind.REGRESSION_GATE, ("build",)),
    )
    plan = plan_labyrinth("alice", nodes, authorized=True)
    engine = DragonLabyrinth(sqlite3.connect(":memory:"))
    engine.install(plan, authorized=True)
    return engine, plan


def test_initial_work_only_has_root():
    engine, plan = graph()
    assert [x.key for x in engine.ready(
        "alice", plan.plan_id, authorized=True,
    )] == ["capture"]


def test_dependency_unlocks_after_completion():
    engine, plan = graph()
    token = engine.lease(
        "alice", plan.plan_id, "capture",
        worker="worker-1", authorized=True,
    )
    assert engine.resolve(
        "alice", plan.plan_id, "capture", token=token,
        output_digest="a" * 64, success=True, authorized=True,
    ) is WorkStatus.COMPLETED
    assert [x.key for x in engine.ready(
        "alice", plan.plan_id, authorized=True,
    )] == ["vision"]


def test_human_gate_cannot_be_bypassed():
    engine, plan = graph()
    for key in ("capture", "vision"):
        token = engine.lease(
            "alice", plan.plan_id, key,
            worker="worker-1", authorized=True,
        )
        engine.resolve(
            "alice", plan.plan_id, key, token=token,
            output_digest="b" * 64, success=True, authorized=True,
        )
    with pytest.raises(PermissionError):
        engine.lease(
            "alice", plan.plan_id, "taste",
            worker="worker-1", authorized=True,
        )
    assert len(engine.lease(
        "alice", plan.plan_id, "taste", worker="worker-1",
        authorized=True, approval=True,
    )) == 64


def test_stale_lease_rejected():
    engine, plan = graph()
    token = engine.lease(
        "alice", plan.plan_id, "capture",
        worker="worker-1", authorized=True,
    )
    with pytest.raises(PermissionError):
        engine.resolve(
            "alice", plan.plan_id, "capture",
            token="0" * 64, output_digest="a" * 64,
            success=True, authorized=True,
        )
    engine.resolve(
        "alice", plan.plan_id, "capture", token=token,
        output_digest="a" * 64, success=True, authorized=True,
    )
    with pytest.raises(PermissionError):
        engine.resolve(
            "alice", plan.plan_id, "capture", token=token,
            output_digest="a" * 64, success=True, authorized=True,
        )


def test_failure_retries_until_budget_exhaustion():
    engine, plan = graph()
    for attempt in range(3):
        token = engine.lease(
            "alice", plan.plan_id, "capture",
            worker="worker-1", authorized=True,
        )
        result = engine.resolve(
            "alice", plan.plan_id, "capture", token=token,
            output_digest="a" * 64, success=False, authorized=True,
        )
        assert result is (
            WorkStatus.FAILED if attempt == 2 else WorkStatus.PENDING
        )
    assert not engine.ready("alice", plan.plan_id, authorized=True)


def test_cycle_rejected():
    with pytest.raises(ValueError, match="cyclic"):
        plan_labyrinth("alice", (
            WorkSpec("a", WorkKind.FRAME_EXTRACTION, ("b",)),
            WorkSpec("b", WorkKind.FRAME_EXTRACTION, ("a",)),
        ), authorized=True)


def test_missing_dependency_rejected():
    with pytest.raises(ValueError, match="missing"):
        plan_labyrinth("alice", (
            WorkSpec("a", WorkKind.FRAME_EXTRACTION, ("unknown",)),
        ), authorized=True)


def test_cost_budget_enforced():
    with pytest.raises(ValueError, match="cost"):
        plan_labyrinth("alice", (
            WorkSpec("expensive", WorkKind.PLAYTEST,
                     cost_units=100, max_attempts=3),
        ), authorized=True, max_cost=200)


def test_owner_isolation_and_erasure():
    engine, plan = graph()
    assert engine.status("bob", plan.plan_id, authorized=True) == ()
    assert engine.erase("alice", authorized=True) == 5
    assert engine.status("alice", plan.plan_id, authorized=True) == ()


def test_install_is_idempotent():
    engine, plan = graph()
    engine.install(plan, authorized=True)
    assert len(engine.status("alice", plan.plan_id, authorized=True)) == 5


def test_authorization_required():
    engine, plan = graph()
    with pytest.raises(PermissionError):
        engine.ready("alice", plan.plan_id, authorized=False)
    with pytest.raises(PermissionError):
        engine.lease("alice", plan.plan_id, "capture",
                     worker="x", authorized=False)
