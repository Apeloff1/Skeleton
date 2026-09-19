"""Execution-plan storage and change-control regressions."""

from __future__ import annotations

import pytest

from skeleton.shells.change_control import ChangeControl, ChangeState
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.plan_store import PlanConflict, PlanStore
from skeleton.shells.runner import ShellCommand


def step(step_id, *, depends=(), command="python", args=()):
    return PlanStep(
        step_id,
        ShellCommand(command, tuple(args)),
        frozenset(depends),
    )


def plan(plan_id="p", *, second_arg="2"):
    return ExecutionPlan(
        plan_id,
        (
            step("a", args=("1",)),
            step("b", depends=("a",), args=(second_arg,)),
        ),
        {"owner": "test"},
    )


def test_plan_requires_steps():
    with pytest.raises(ValueError):
        ExecutionPlan("p", ())


def test_plan_rejects_duplicate_step_ids():
    with pytest.raises(ValueError):
        ExecutionPlan("p", (step("a"), step("a")))


def test_plan_rejects_unknown_dependency():
    with pytest.raises(ValueError):
        ExecutionPlan("p", (step("a", depends=("missing",)),))


def test_plan_rejects_self_dependency():
    with pytest.raises(ValueError):
        step("a", depends=("a",))


def test_plan_rejects_cycle():
    with pytest.raises(ValueError):
        ExecutionPlan(
            "p",
            (
                step("a", depends=("b",)),
                step("b", depends=("a",)),
            ),
        )


def test_plan_topological_order():
    item = ExecutionPlan(
        "p",
        (
            step("c", depends=("a", "b")),
            step("b", depends=("a",)),
            step("a"),
        ),
    )
    assert [value.step_id for value in item.topological_order()] == ["a", "b", "c"]


def test_plan_fingerprint_is_stable():
    assert plan().fingerprint == plan().fingerprint


def test_plan_fingerprint_changes_on_command_change():
    assert plan(second_arg="2").fingerprint != plan(second_arg="3").fingerprint


def test_plan_store_put_first_version():
    store = PlanStore()
    stored = store.put(plan())
    assert stored.version == 1
    assert not stored.superseded


def test_plan_store_same_fingerprint_is_idempotent():
    store = PlanStore()
    first = store.put(plan())
    second = store.put(plan())
    assert first == second
    assert len(store.history("p")) == 1


def test_plan_store_new_fingerprint_advances():
    store = PlanStore()
    first = store.put(plan())
    second = store.put(plan(second_arg="3"), expected_version=1)
    assert second.version == 2
    assert store.at("p", 1).superseded
    assert not store.at("p", 2).superseded


def test_plan_store_version_conflict():
    store = PlanStore()
    store.put(plan())
    with pytest.raises(PlanConflict):
        store.put(plan(second_arg="3"), expected_version=0)


def test_plan_store_current():
    store = PlanStore()
    store.put(plan())
    latest = store.put(plan(second_arg="3"))
    assert store.current("p") == latest


def test_plan_store_at_missing():
    store = PlanStore()
    store.put(plan())
    with pytest.raises(KeyError):
        store.at("p", 2)


def test_plan_store_remove():
    store = PlanStore()
    store.put(plan())
    assert store.remove("p")
    assert not store.remove("p")


def test_plan_store_ids_sorted():
    store = PlanStore()
    store.put(plan("b"))
    store.put(plan("a"))
    assert store.plan_ids() == ("a", "b")


def test_change_control_propose():
    control = ChangeControl()
    item = control.propose(
        kind="policy",
        target="shell",
        summary="narrow timeout",
        payload={"max_timeout": 10},
        proposed_by="alice",
    )
    assert item.state is ChangeState.PROPOSED
    assert item.payload_digest


def test_change_control_one_approval():
    control = ChangeControl(required_approvals=1)
    item = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    item = control.approve(item.change_id, "bob")
    assert item.state is ChangeState.APPROVED


def test_change_control_multiple_approvals():
    control = ChangeControl(required_approvals=2)
    item = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    item = control.approve(item.change_id, "bob")
    assert item.state is ChangeState.PROPOSED
    item = control.approve(item.change_id, "carol")
    assert item.state is ChangeState.APPROVED


def test_change_control_duplicate_approval_not_double_counted():
    control = ChangeControl(required_approvals=2)
    item = control.propose(
        kind="policy",
        target="shell",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    item = control.approve(item.change_id, "bob")
    item = control.approve(item.change_id, "bob")
    assert item.approvals == ("bob",)
    assert item.state is ChangeState.PROPOSED


def test_change_control_reject():
    control = ChangeControl()
    item = control.propose(
        kind="plan",
        target="p",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    assert control.reject(item.change_id).state is ChangeState.REJECTED


def test_change_control_applied_requires_approval():
    control = ChangeControl()
    item = control.propose(
        kind="plan",
        target="p",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    with pytest.raises(RuntimeError):
        control.applied(item.change_id)


def test_change_control_applied_after_approval():
    control = ChangeControl()
    item = control.propose(
        kind="plan",
        target="p",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    item = control.approve(item.change_id, "bob")
    assert control.applied(item.change_id).state is ChangeState.APPLIED


def test_change_control_rejected_cannot_approve():
    control = ChangeControl()
    item = control.propose(
        kind="plan",
        target="p",
        summary="x",
        payload={"x": 1},
        proposed_by="alice",
    )
    control.reject(item.change_id)
    with pytest.raises(RuntimeError):
        control.approve(item.change_id, "bob")


def test_change_control_payload_digest_stable_for_same_payload():
    control = ChangeControl()
    first = control.propose(
        kind="plan",
        target="p",
        summary="x",
        payload={"a": 1, "b": 2},
        proposed_by="alice",
    )
    second = control.propose(
        kind="plan",
        target="q",
        summary="x",
        payload={"b": 2, "a": 1},
        proposed_by="alice",
    )
    assert first.payload_digest == second.payload_digest
