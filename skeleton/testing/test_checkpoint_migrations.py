"""Contract tests for versioned checkpoint-state migrations."""

from __future__ import annotations

import pytest

from skeleton.state import (
    CheckpointMigrator,
    MigrationError,
    MigrationPathError,
    MigrationValidationError,
)


def test_contiguous_migrations_upgrade_to_current_version_without_mutating_input():
    migrator = CheckpointMigrator(3)

    @migrator.migration(1)
    def add_phase(state):
        state["phase"] = "planned"
        return state

    @migrator.migration(2)
    def normalize_tasks(state):
        state["tasks"] = [{"name": task} for task in state.pop("task_names")]
        return state

    original = {"task_names": ["compile", "test"]}
    result = migrator.migrate(original, 1)

    assert original == {"task_names": ["compile", "test"]}
    assert result.from_version == 1
    assert result.to_version == 3
    assert result.applied_versions == (2, 3)
    assert result.state == {
        "phase": "planned",
        "tasks": [{"name": "compile"}, {"name": "test"}],
    }


def test_partial_target_runs_only_required_prefix():
    migrator = CheckpointMigrator(4)
    migrator.register(1, lambda state: {**state, "v2": True})
    migrator.register(2, lambda state: {**state, "v3": True})
    migrator.register(3, lambda state: {**state, "v4": True})

    result = migrator.migrate({}, 1, to_version=3)

    assert result.to_version == 3
    assert result.applied_versions == (2, 3)
    assert result.state == {"v2": True, "v3": True}


def test_current_version_is_validated_and_detached_without_running_migration():
    migrator = CheckpointMigrator(2)
    migrator.register(1, lambda state: state)
    original = {"nested": [1, 2]}

    result = migrator.migrate(original, 2)
    result.state["nested"].append(3)

    assert result.applied_versions == ()
    assert original == {"nested": [1, 2]}


def test_missing_migration_path_fails_before_any_function_runs():
    called = []
    migrator = CheckpointMigrator(4)
    migrator.register(1, lambda state: called.append(1) or state)
    migrator.register(3, lambda state: called.append(3) or state)

    assert migrator.missing_versions(1) == (2,)
    with pytest.raises(MigrationPathError, match="missing source versions: 2"):
        migrator.migrate({}, 1)

    assert called == []


def test_duplicate_registration_is_rejected():
    migrator = CheckpointMigrator(2)
    migrator.register(1, lambda state: state)

    with pytest.raises(MigrationPathError, match="already registered"):
        migrator.register(1, lambda state: state)


def test_registration_cannot_start_at_or_above_current_version():
    migrator = CheckpointMigrator(2)

    with pytest.raises(ValueError, match="below current_version"):
        migrator.register(2, lambda state: state)
    with pytest.raises(ValueError, match="below current_version"):
        migrator.register(3, lambda state: state)


def test_newer_checkpoint_and_downgrade_fail_closed():
    migrator = CheckpointMigrator(3)
    migrator.register(1, lambda state: state)
    migrator.register(2, lambda state: state)

    with pytest.raises(MigrationPathError, match="newer than supported"):
        migrator.migrate({}, 4)
    with pytest.raises(MigrationPathError, match="do not support downgrade"):
        migrator.migrate({}, 3, to_version=2)


def test_target_newer_than_supported_fails_closed():
    migrator = CheckpointMigrator(2)
    migrator.register(1, lambda state: state)

    with pytest.raises(MigrationPathError, match="target version 3"):
        migrator.migrate({}, 1, to_version=3)


def test_migration_exception_is_wrapped_with_version_boundary():
    migrator = CheckpointMigrator(2)

    def explode(_state):
        raise RuntimeError("provider-specific secret details")

    migrator.register(1, explode)

    with pytest.raises(MigrationError, match="1->2") as caught:
        migrator.migrate({}, 1)

    assert "provider-specific secret details" not in str(caught.value)


@pytest.mark.parametrize("bad", [{"x": float("nan")}, {"x": float("inf")}, {1, 2}])
def test_invalid_source_state_is_rejected_before_migration(bad):
    called = []
    migrator = CheckpointMigrator(2)
    migrator.register(1, lambda state: called.append(True) or state)

    with pytest.raises(MigrationValidationError, match="finite JSON"):
        migrator.migrate(bad, 1)

    assert called == []


@pytest.mark.parametrize("bad", [{"x": float("nan")}, object()])
def test_invalid_migration_output_is_rejected(bad):
    migrator = CheckpointMigrator(2)
    migrator.register(1, lambda _state: bad)

    with pytest.raises(MigrationValidationError, match="finite JSON"):
        migrator.migrate({}, 1)


def test_oversized_source_and_migration_output_are_rejected():
    migrator = CheckpointMigrator(2, max_payload_bytes=32)
    migrator.register(1, lambda _state: {"blob": "x" * 100})

    with pytest.raises(MigrationValidationError, match="exceeds 32"):
        migrator.migrate({"blob": "x" * 100}, 1)

    with pytest.raises(MigrationValidationError, match="exceeds 32"):
        migrator.migrate({}, 1)


def test_migration_step_budget_prevents_pathological_upgrade_chain():
    migrator = CheckpointMigrator(5, max_steps=2)
    for version in range(1, 5):
        migrator.register(version, lambda state: state)

    with pytest.raises(MigrationPathError, match="requires 4 steps"):
        migrator.migrate({}, 1)


def test_migration_outputs_are_canonical_plain_json_data():
    migrator = CheckpointMigrator(2)
    source_key = ("tuple", "becomes invalid")
    migrator.register(1, lambda _state: {"values": (1, 2, 3)})

    result = migrator.migrate({"key": list(source_key)}, 1)

    assert result.state == {"values": [1, 2, 3]}
    assert isinstance(result.state["values"], list)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"current_version": 0},
        {"current_version": True},
        {"current_version": 1, "max_payload_bytes": 0},
        {"current_version": 1, "max_payload_bytes": True},
        {"current_version": 1, "max_steps": 0},
        {"current_version": 1, "max_steps": True},
    ],
)
def test_invalid_migrator_configuration_fails_fast(kwargs):
    with pytest.raises(ValueError):
        CheckpointMigrator(**kwargs)
