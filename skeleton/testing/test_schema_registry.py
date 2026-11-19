from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.data.schema_evolution import (
    EvolutionPlan,
    SchemaEvolutionError,
    SchemaEvolutionGuard,
    VersionWindow,
)


ROOT = Path(__file__).resolve().parents[2]


def _machine(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_schema_registry_covers_runtime_catalog_exactly() -> None:
    runtime = _machine("machine/ai_runtime_schemas.json")
    registry = _machine("machine/schema_registry.json")
    records = runtime["records"]
    schemas = registry["schemas"]

    assert len(records) == len(schemas) == 40
    assert [row["record_name"] for row in schemas] == list(records)
    assert len({row["schema_id"] for row in schemas}) == len(schemas)
    assert all(row["schema_id"] == f"SCHEMA-{row['record_name']}" for row in schemas)
    assert all(row["migration_required_for_breaking_change"] is True for row in schemas)


def test_protocol_and_consistency_contracts_are_registered() -> None:
    registry = _machine("machine/schema_registry.json")
    by_name = {row["record_name"]: row for row in registry["schemas"]}

    assert {"ProtocolEnvelope", "ProtocolExecutionEnvelope", "ProtocolReceipt", "ConsistencyProfile"} <= set(by_name)
    assert by_name["ProtocolEnvelope"]["owner_plane"] == "foundation"
    assert by_name["ProtocolExecutionEnvelope"]["owner_plane"] == "orchestration"
    assert by_name["ProtocolReceipt"]["owner_plane"] == "observability"
    assert by_name["ConsistencyProfile"]["owner_plane"] == "data-persistence"


def test_schema_conformance_inventory_covers_every_registered_contract() -> None:
    runtime = _machine("machine/ai_runtime_schemas.json")
    conformance = _machine("machine/contract_conformance.json")
    entries = {row["contract"]: row for row in conformance["entries"]}

    assert set(entries) == set(runtime["records"])
    for name, record in runtime["records"].items():
        assert entries[name]["schema_version"] == record["schema_version"]
        assert entries[name]["producer_plane"] == record["owner_plane"]
        assert entries[name]["consumer_planes"]


def test_invalid_compatibility_mode_fails_closed() -> None:
    with pytest.raises(SchemaEvolutionError, match="unsupported compatibility mode"):
        SchemaEvolutionGuard("guess")


def test_backward_mode_rejects_removed_field_and_tightened_requiredness() -> None:
    guard = SchemaEvolutionGuard("backward")
    old = {
        "properties": {"id": {"type": "string"}, "note": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": False,
    }
    new = {
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": False,
    }

    result = guard.check(old, new)
    assert result["compatible"] is False
    assert any(row["kind"] == "removed_field" for row in result["issues"])


def test_full_mode_rejects_enum_narrowing_and_widening() -> None:
    guard = SchemaEvolutionGuard("full")
    old = {
        "properties": {"state": {"type": "string", "enum": ["a", "b"]}},
        "required": ["state"],
    }
    narrowed = {
        "properties": {"state": {"type": "string", "enum": ["a"]}},
        "required": ["state"],
    }
    widened = {
        "properties": {"state": {"type": "string", "enum": ["a", "b", "c"]}},
        "required": ["state"],
    }

    assert guard.check(old, narrowed)["compatible"] is False
    assert guard.check(old, widened)["compatible"] is False


def test_backward_mode_rejects_constraint_tightening() -> None:
    guard = SchemaEvolutionGuard("backward")
    old = {
        "properties": {"name": {"type": "string", "maxLength": 100}},
        "required": ["name"],
    }
    new = {
        "properties": {"name": {"type": "string", "maxLength": 20}},
        "required": ["name"],
    }

    result = guard.check(old, new)
    assert result["compatible"] is False
    assert any(row["kind"] == "constraint_tightened" for row in result["issues"])


def test_forward_mode_rejects_optional_addition_for_closed_old_reader() -> None:
    guard = SchemaEvolutionGuard("forward")
    old = {
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": False,
    }
    new = {
        "properties": {
            "id": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["id"],
        "additionalProperties": False,
    }
    result = guard.check(old, new)
    assert result["compatible"] is False
    assert any(
        row["kind"] == "new_optional_with_closed_old_reader"
        for row in result["issues"]
    )


def test_breaking_transition_requires_migration_rollback_and_old_version_window() -> None:
    guard = SchemaEvolutionGuard("backward")
    old = {
        "properties": {"id": {"type": "string"}, "legacy": {"type": "string"}},
        "required": ["id"],
    }
    new = {
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }
    window = VersionWindow(current_version=2, supported_versions=(1, 2))

    decision = guard.check_transition(
        old,
        new,
        from_version=1,
        to_version=2,
        window=window,
    )
    assert decision["compatible"] is False
    assert decision["migration_required"] is True
    assert decision["rollback_required"] is True
    assert decision["eligible_for_promotion"] is False

    plan = EvolutionPlan(
        from_version=1,
        to_version=2,
        migration_id="MIG-schema-1-2",
        rollback_id="RB-schema-2-1",
        reversible=True,
    )
    qualified = guard.qualify_transition(
        old,
        new,
        from_version=1,
        to_version=2,
        window=window,
        plan=plan,
    )
    assert qualified["eligible_for_promotion"] is True
    assert len(qualified["decision_digest"]) == 64


def test_breaking_transition_cannot_drop_old_version_before_migration_window() -> None:
    guard = SchemaEvolutionGuard("backward")
    old = {
        "properties": {"id": {"type": "string"}, "legacy": {"type": "string"}},
        "required": ["id"],
    }
    new = {
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }
    plan = EvolutionPlan(
        from_version=1,
        to_version=2,
        migration_id="MIG-schema-1-2",
        rollback_id="RB-schema-2-1",
    )
    window = VersionWindow(current_version=2, supported_versions=(2,))

    decision = guard.check_transition(
        old,
        new,
        from_version=1,
        to_version=2,
        window=window,
        plan=plan,
    )
    assert decision["eligible_for_promotion"] is False


def test_schema_evolution_ai_mirror_is_byte_identical() -> None:
    canonical = ROOT / "skeleton/data/schema_evolution.py"
    mirror = ROOT / "skeleton/ai/runtime/data/schema_evolution.py"
    assert canonical.read_bytes() == mirror.read_bytes()
