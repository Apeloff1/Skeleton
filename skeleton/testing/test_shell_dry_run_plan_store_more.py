"""Dry-run, plan-store, and execution-context edge cases."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.admission import CommandAdmission
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.dry_run import ShellDryRun
from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.plan_store import PlanStore
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellCommand


def admission():
    definition = CommandDefinition(
        ExecutableSpec("python", sys.executable),
        ArgumentPolicy.allow_any(),
    )
    return CommandAdmission(CommandCatalog((definition,)))


def test_dry_run_command_allowed():
    report = ShellDryRun(admission()).command(
        ShellCommand("python", ("-c", "print(1)")),
        CapabilityGrant.execution_only(),
    )
    assert report.allowed
    assert report.denied == 0
    assert report.steps[0].command == "python"


def test_dry_run_unknown_command_denied():
    report = ShellDryRun(admission()).command(
        ShellCommand("git"),
        CapabilityGrant.execution_only(),
    )
    assert not report.allowed
    assert report.denied == 1


def test_dry_run_missing_capability_denied():
    report = ShellDryRun(admission()).command(
        ShellCommand("python"),
        CapabilityGrant.none(),
    )
    assert not report.allowed


def test_dry_run_plan_all_steps():
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python")),
            PlanStep("b", ShellCommand("git")),
        ),
    )
    report = ShellDryRun(admission()).plan(plan, CapabilityGrant.execution_only())
    assert len(report.steps) == 2
    assert report.steps[0].allowed
    assert not report.steps[1].allowed


def test_context_rejects_bad_principal():
    with pytest.raises(ValueError):
        ExecutionContext("c", principal="bad principal")


def test_context_rejects_bad_tag():
    with pytest.raises(ValueError):
        ExecutionContext("c", tags=frozenset({"bad tag"}))


def test_context_rejects_large_attribute():
    with pytest.raises(ValueError):
        ExecutionContext("c", attributes={"k": "x" * 513})


def test_context_child_can_add_attributes():
    parent = ExecutionContext("root", attributes={"a": "1"})
    child = parent.child("root:child", attributes={"a": "1", "b": "2"})
    assert child.attributes["b"] == "2"


def test_plan_store_capacity():
    store = PlanStore(max_versions=1)
    first = ExecutionPlan("a", (PlanStep("x", ShellCommand("python")),))
    second = ExecutionPlan("b", (PlanStep("x", ShellCommand("python")),))
    store.put(first)
    with pytest.raises(Exception):
        store.put(second)


def test_plan_store_history_empty():
    assert PlanStore().history("missing") == ()


def test_plan_step_shape_redacts_environment_values():
    step = PlanStep(
        "x",
        ShellCommand("python", env={"SECRET": "value"}, stdin=b"secret"),
    )
    shape = step.shape()
    assert shape["env_keys"] == ["SECRET"]
    assert "value" not in str(shape)
    assert shape["stdin_bytes"] == 6


def test_plan_fingerprint_does_not_embed_env_values_directly():
    plan = ExecutionPlan(
        "p",
        (PlanStep("x", ShellCommand("python", env={"SECRET": "value"})),),
    )
    assert "value" not in plan.fingerprint


@pytest.mark.parametrize("identifier", ["", "x" * 129])
def test_plan_rejects_bad_plan_id(identifier):
    with pytest.raises(ValueError):
        ExecutionPlan(identifier, (PlanStep("x", ShellCommand("python")),))


@pytest.mark.parametrize("identifier", ["", "x" * 129])
def test_plan_step_rejects_bad_step_id(identifier):
    with pytest.raises(ValueError):
        PlanStep(identifier, ShellCommand("python"))
