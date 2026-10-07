from __future__ import annotations

import json
from pathlib import Path

from skeleton.data.schema_evolution import (
    EvolutionPlan,
    SchemaEvolutionGuard,
    VersionWindow,
)


ROOT = Path(__file__).resolve().parents[2]


def _machine(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_compatibility_matrix_covers_exact_schema_registry() -> None:
    registry = _machine("machine/schema_registry.json")
    model = _machine("machine/compatibility_model.json")
    expected = {
        row["schema_id"]: row
        for row in registry["schemas"]
    }
    matrix = {
        row["schema_id"]: row
        for row in model["schema_matrix"]
    }

    assert set(matrix) == set(expected)
    assert len(matrix) == 40
    for schema_id, schema in expected.items():
        row = matrix[schema_id]
        assert row["current_version"] == schema["version"]
        assert row["supported_versions"] == [schema["version"]]
        assert row["reader_writer_mode"] == schema["compatibility_mode"]
        assert row["producer_plane"] == schema["producer_plane"]
        assert row["consumer_planes"] == schema["consumer_planes"]
        assert row["migration_required_for_breaking_change"] is True


def test_support_window_policy_is_explicit_and_executable() -> None:
    model = _machine("machine/compatibility_model.json")
    policy = model["support_window_policy"]

    assert policy["default_supported_versions"] == 2
    assert policy["rule"]
    assert policy["breaking_change_rule"]
    assert policy["rollback_rule"]
    assert model["sources"]["executable_guard"] == "skeleton/data/schema_evolution.py"


def test_additive_backward_change_qualifies_without_migration() -> None:
    guard = SchemaEvolutionGuard("backward")
    old = {
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": True,
    }
    new = {
        "properties": {
            "id": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["id"],
        "additionalProperties": True,
    }
    window = VersionWindow(current_version=2, supported_versions=(1, 2))
    decision = guard.qualify_transition(
        old,
        new,
        from_version=1,
        to_version=2,
        window=window,
    )
    assert decision["compatible"] is True
    assert decision["migration_required"] is False
    assert decision["rollback_required"] is False


def test_breaking_change_qualifies_only_with_reversible_exact_plan() -> None:
    guard = SchemaEvolutionGuard("full")
    old = {
        "properties": {"state": {"type": "string", "enum": ["a", "b"]}},
        "required": ["state"],
    }
    new = {
        "properties": {"state": {"type": "string", "enum": ["a"]}},
        "required": ["state"],
    }
    window = VersionWindow(current_version=2, supported_versions=(1, 2))
    plan = EvolutionPlan(
        from_version=1,
        to_version=2,
        migration_id="MIG-state-v2",
        rollback_id="RB-state-v1",
        reversible=True,
    )
    decision = guard.qualify_transition(
        old,
        new,
        from_version=1,
        to_version=2,
        window=window,
        plan=plan,
        mode="full",
    )
    assert decision["compatible"] is False
    assert decision["eligible_for_promotion"] is True
    assert decision["plan"]["rollback_id"] == "RB-state-v1"


def test_interface_matrix_still_requires_rollback_for_every_boundary() -> None:
    model = _machine("machine/compatibility_model.json")
    assert model["interface_matrix"]
    assert all(row["rollback_required"] is True for row in model["interface_matrix"])
    assert all(row["compatibility_semantics"] for row in model["interface_matrix"])
