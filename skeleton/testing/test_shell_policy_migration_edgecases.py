"""Policy migration and compatibility edge cases."""

from __future__ import annotations

import sys

import pytest

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.compatibility import ShellCompatibility, ShellCompatibilityRequirement
from skeleton.shells.migration import MigrationRisk, ShellMigrationPlanner
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy


def make_policy(tmp_path, **changes):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    values = dict(
        executables={"python": sys.executable},
        cwd_roots=(root,),
        allowed_env=frozenset({"A", "B"}),
        inherited_env=frozenset(),
        default_timeout=2,
        max_timeout=10,
        max_output_bytes=100,
        max_input_bytes=100,
        max_env_bytes=100,
        max_args=10,
        max_arg_bytes=100,
    )
    values.update(changes)
    return ShellPolicy(**values)


def make_catalog(*definitions):
    return CommandCatalog(definitions)


def definition(name="python", **changes):
    values = dict(
        spec=ExecutableSpec(name, sys.executable),
        arguments=ArgumentPolicy.allow_any(),
        allow_stdin=False,
        allow_nonzero_success=False,
    )
    values.update(changes)
    return CommandDefinition(**values)


def test_compatibility_requirement_rejects_inverted_schema():
    with pytest.raises(ValueError):
        ShellCompatibilityRequirement(min_schema_version=2, max_schema_version=1)


def test_compatibility_multiple_missing_reasons(tmp_path):
    requirement = ShellCompatibilityRequirement(
        min_schema_version=2,
        max_schema_version=2,
        required_commands=frozenset({"git"}),
        required_environment_keys=frozenset({"Z"}),
        require_no_inherited_environment=True,
    )
    result = ShellCompatibility().check(
        make_policy(tmp_path, inherited_env=frozenset({"A"})),
        make_catalog(definition("python")),
        requirement,
        schema_version=1,
    )
    assert not result.compatible
    assert len(result.reasons) == 4


def test_migration_output_widen_review(tmp_path):
    plan = ShellMigrationPlanner().compare_policy(
        make_policy(tmp_path, max_output_bytes=100),
        make_policy(tmp_path, max_output_bytes=200),
    )
    assert any(item.code == "output_widened" and item.risk is MigrationRisk.REVIEW for item in plan.changes)


def test_migration_output_narrow_safe(tmp_path):
    plan = ShellMigrationPlanner().compare_policy(
        make_policy(tmp_path, max_output_bytes=200),
        make_policy(tmp_path, max_output_bytes=100),
    )
    assert any(item.code == "output_narrowed" and item.risk is MigrationRisk.SAFE for item in plan.changes)


def test_migration_cwd_add_review(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    old = make_policy(tmp_path)
    new = make_policy(tmp_path, cwd_roots=old.cwd_roots + (extra,))
    plan = ShellMigrationPlanner().compare_policy(old, new)
    assert any(item.code == "workspace_widened" for item in plan.changes)


def test_migration_cwd_remove_breaking(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    wide = make_policy(tmp_path)
    wide = make_policy(tmp_path, cwd_roots=wide.cwd_roots + (extra,))
    narrow = make_policy(tmp_path)
    plan = ShellMigrationPlanner().compare_policy(wide, narrow)
    assert any(item.code == "workspace_narrowed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_catalog_change_stdin_disable_breaking():
    old = make_catalog(definition(allow_stdin=True))
    new = make_catalog(definition(allow_stdin=False))
    plan = ShellMigrationPlanner().compare_catalog(old, new)
    assert any(item.code == "command_changed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_catalog_change_nonzero_disable_breaking():
    old = make_catalog(definition(allow_nonzero_success=True))
    new = make_catalog(definition(allow_nonzero_success=False))
    plan = ShellMigrationPlanner().compare_catalog(old, new)
    assert any(item.code == "command_changed" and item.risk is MigrationRisk.BREAKING for item in plan.changes)


def test_catalog_description_change_requires_review():
    old = make_catalog(definition(description="old"))
    new = make_catalog(definition(description="new"))
    plan = ShellMigrationPlanner().compare_catalog(old, new)
    assert any(item.code == "command_changed" and item.risk is MigrationRisk.REVIEW for item in plan.changes)


def test_empty_policy_migration_has_no_changes(tmp_path):
    item = make_policy(tmp_path)
    plan = ShellMigrationPlanner().compare_policy(item, item)
    assert plan.changes == ()
    assert not plan.requires_review
