"""Migration, compatibility, and resource-estimate regressions."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.compatibility import (
    ShellCompatibility,
    ShellCompatibilityRequirement,
)
from skeleton.shells.execution_plan import ExecutionPlan, PlanStep
from skeleton.shells.migration import MigrationRisk, ShellMigrationPlanner
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.resource_estimator import ResourceEstimate, ShellResourceEstimator
from skeleton.shells.runner import ShellCommand, ShellPolicy


def policy(tmp_path, **changes):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    values = dict(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        allowed_env=frozenset({"X"}),
        inherited_env=frozenset(),
        default_timeout=5.0,
        max_timeout=10.0,
        max_output_bytes=1024,
        max_input_bytes=1024,
        max_env_bytes=1024,
        max_args=16,
        max_arg_bytes=1024,
    )
    values.update(changes)
    return ShellPolicy(**values)


def catalog(*names):
    return CommandCatalog(
        CommandDefinition(
            ExecutableSpec(name, sys.executable),
            ArgumentPolicy.allow_any(),
        )
        for name in names
    )


def test_compatibility_default_schema(tmp_path):
    result = ShellCompatibility().check(policy(tmp_path), catalog("python"))
    assert result.compatible


def test_compatibility_schema_mismatch(tmp_path):
    requirement = ShellCompatibilityRequirement(min_schema_version=2, max_schema_version=3)
    result = ShellCompatibility().check(
        policy(tmp_path),
        catalog("python"),
        requirement,
        schema_version=1,
    )
    assert not result.compatible


def test_compatibility_required_command(tmp_path):
    requirement = ShellCompatibilityRequirement(required_commands=frozenset({"python"}))
    assert ShellCompatibility().check(policy(tmp_path), catalog("python"), requirement).compatible


def test_compatibility_missing_command(tmp_path):
    requirement = ShellCompatibilityRequirement(required_commands=frozenset({"git"}))
    result = ShellCompatibility().check(policy(tmp_path), catalog("python"), requirement)
    assert not result.compatible


def test_compatibility_required_environment(tmp_path):
    requirement = ShellCompatibilityRequirement(required_environment_keys=frozenset({"X"}))
    assert ShellCompatibility().check(policy(tmp_path), catalog("python"), requirement).compatible


def test_compatibility_missing_environment(tmp_path):
    requirement = ShellCompatibilityRequirement(required_environment_keys=frozenset({"Y"}))
    result = ShellCompatibility().check(policy(tmp_path), catalog("python"), requirement)
    assert not result.compatible


def test_compatibility_forbids_inherited_environment(tmp_path):
    requirement = ShellCompatibilityRequirement(require_no_inherited_environment=True)
    result = ShellCompatibility().check(
        policy(tmp_path, inherited_env=frozenset({"X"})),
        catalog("python"),
        requirement,
    )
    assert not result.compatible


def test_migration_executable_add_is_safe(tmp_path):
    old = policy(tmp_path)
    new = policy(tmp_path, executables={"python": sys.executable, "py2": sys.executable})
    plan = ShellMigrationPlanner().compare_policy(old, new)
    match = [item for item in plan.changes if item.code == "executable_added"]
    assert match and match[0].risk is MigrationRisk.SAFE


def test_migration_executable_remove_is_breaking(tmp_path):
    old = policy(tmp_path, executables={"python": sys.executable, "py2": sys.executable})
    new = policy(tmp_path)
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "executable_removed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_migration_timeout_widen_requires_review(tmp_path):
    old = policy(tmp_path, max_timeout=10)
    new = policy(tmp_path, max_timeout=20)
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "timeout_widened" for item in plan.changes)
    assert plan.requires_review


def test_migration_timeout_narrow_is_safe(tmp_path):
    old = policy(tmp_path, max_timeout=10)
    new = policy(tmp_path, max_timeout=5)
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "timeout_narrowed" and item.risk is MigrationRisk.SAFE for item in plan.changes)


def test_migration_environment_add_requires_review(tmp_path):
    old = policy(tmp_path, allowed_env=frozenset({"X"}))
    new = policy(tmp_path, allowed_env=frozenset({"X", "Y"}))
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "environment_added" and item.risk is MigrationRisk.REVIEW for item in plan.changes)


def test_migration_environment_remove_breaking(tmp_path):
    old = policy(tmp_path, allowed_env=frozenset({"X", "Y"}))
    new = policy(tmp_path, allowed_env=frozenset({"X"}))
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "environment_removed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_migration_inheritance_widen_review(tmp_path):
    old = policy(tmp_path, inherited_env=frozenset())
    new = policy(tmp_path, inherited_env=frozenset({"X"}))
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "inheritance_widened" for item in plan.changes)


def test_catalog_migration_add_safe():
    plan = ShellMigrationPlanner().compare_catalog(catalog("python"), catalog("python", "git"))
    assert any(item.code == "command_added" and item.risk is MigrationRisk.SAFE for item in plan.changes)


def test_catalog_migration_remove_breaking():
    plan = ShellMigrationPlanner().compare_catalog(catalog("python", "git"), catalog("python"))
    assert any(item.code == "command_removed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_resource_estimate_command(tmp_path):
    estimator = ShellResourceEstimator()
    command = ShellCommand(
        "python",
        ("-c", "print(1)"),
        env={"X": "Y"},
        stdin=b"abc",
        timeout=2,
    )
    estimate = estimator.command(command, policy(tmp_path), attempts=2)
    assert estimate.commands == 1
    assert estimate.attempts == 2
    assert estimate.timeout_seconds == 4
    assert estimate.input_bytes == 6
    assert estimate.max_output_bytes == 2048
    assert estimate.environment_bytes > 0
    assert estimate.argument_bytes > 0


def test_resource_estimate_uses_policy_default_timeout(tmp_path):
    estimate = ShellResourceEstimator().command(
        ShellCommand("python"),
        policy(tmp_path, default_timeout=7),
    )
    assert estimate.timeout_seconds == 7


def test_resource_estimate_attempts_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        ShellResourceEstimator().command(ShellCommand("python"), policy(tmp_path), attempts=0)


def test_resource_estimate_addition():
    a = ResourceEstimate(1, 1, 1, 1, 1, 1, 1)
    b = ResourceEstimate(2, 2, 2, 2, 2, 2, 2)
    total = a + b
    assert total.commands == 3
    assert total.attempts == 3
    assert total.timeout_seconds == 3


def test_resource_estimate_plan(tmp_path):
    item = ExecutionPlan(
        "p",
        (
            PlanStep("a", ShellCommand("python", timeout=2)),
            PlanStep("b", ShellCommand("python", timeout=3), frozenset({"a"})),
        ),
    )
    estimate = ShellResourceEstimator().plan(item, policy(tmp_path), attempts_per_step=2)
    assert estimate.commands == 2
    assert estimate.attempts == 4
    assert estimate.timeout_seconds == 10
