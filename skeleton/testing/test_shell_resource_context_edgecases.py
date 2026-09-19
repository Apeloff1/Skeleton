"""Resource estimator and execution-context edge cases."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.execution_context import ExecutionContext
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.resource_estimator import ResourceEstimate, ShellResourceEstimator
from skeleton.shells.runner import ShellCommand, ShellPolicy


def policy(tmp_path):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return ShellPolicy(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        default_timeout=3,
        max_timeout=10,
        max_output_bytes=100,
        max_input_bytes=100,
        max_env_bytes=100,
        max_args=10,
        max_arg_bytes=100,
    )


@pytest.mark.parametrize(
    "values",
    [
        (-1, 0, 0, 0, 0, 0, 0),
        (0, -1, 0, 0, 0, 0, 0),
        (0, 0, -1, 0, 0, 0, 0),
        (0, 0, 0, -1, 0, 0, 0),
        (0, 0, 0, 0, -1, 0, 0),
        (0, 0, 0, 0, 0, -1, 0),
        (0, 0, 0, 0, 0, 0, -1),
    ],
)
def test_resource_estimate_rejects_negative(values):
    with pytest.raises(ValueError):
        ResourceEstimate(*values)


def test_resource_estimate_environment_bytes_include_key_value_overhead(tmp_path):
    command = ShellCommand("python", env={"A": "B"})
    estimate = ShellResourceEstimator().command(command, policy(tmp_path))
    assert estimate.environment_bytes == 4


def test_resource_estimate_argument_utf8_bytes(tmp_path):
    command = ShellCommand("python", ("é",))
    estimate = ShellResourceEstimator().command(command, policy(tmp_path))
    assert estimate.argument_bytes == len("é".encode("utf-8"))


def test_resource_estimate_stdin_attempt_multiplier(tmp_path):
    command = ShellCommand("python", stdin=b"abc")
    estimate = ShellResourceEstimator().command(command, policy(tmp_path), attempts=3)
    assert estimate.input_bytes == 9


def test_plan_estimate_empty_impossible_but_aggregation_correct(tmp_path):
    plan = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python")),
            PlanStep("b", ShellCommand("python")),
            PlanStep("c", ShellCommand("python")),
        ),
    )
    estimate = ShellResourceEstimator().plan(plan, policy(tmp_path))
    assert estimate.commands == 3
    assert estimate.attempts == 3


def test_context_attributes_are_defensively_copied():
    attrs = {"x": "1"}
    context = ExecutionContext("c", attributes=attrs)
    attrs["x"] = "2"
    assert context.attributes["x"] == "1"


def test_context_tags_are_frozen():
    tags = {"a"}
    context = ExecutionContext("c", tags=tags)
    tags.add("b")
    assert context.tags == frozenset({"a"})


def test_context_child_replaces_parent_link():
    root = ExecutionContext("root")
    child = root.child("child")
    grandchild = child.child("grand")
    assert child.parent_correlation_id == "root"
    assert grandchild.parent_correlation_id == "child"


def test_context_different_attribute_changes_fingerprint():
    a = ExecutionContext("c", attributes={"x": "1"})
    b = ExecutionContext("c", attributes={"x": "2"})
    assert a.fingerprint != b.fingerprint
