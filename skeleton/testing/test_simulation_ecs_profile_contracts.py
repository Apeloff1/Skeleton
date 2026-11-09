"""Deterministic workload profile regression contracts."""
from __future__ import annotations

import pytest

from skeleton.simulation.ecs.errors import BoundsError, ValidationError
from skeleton.simulation.ecs.profiles import (
    WorkloadProfile,
    build_profile_store,
    compare_profile_builds,
    profile_matrix,
    profile_registry,
)
from skeleton.simulation.ecs.query import CompareOp, FieldPredicate, QueryEngine, QuerySpec
from skeleton.simulation.ecs.tables import ComponentTable


def test_profile_fingerprint_is_deterministic() -> None:
    left = WorkloadProfile("same", 10, zone_count=2)
    right = WorkloadProfile("same", 10, zone_count=2)
    assert left.fingerprint == right.fingerprint


def test_profile_name_changes_fingerprint() -> None:
    left = WorkloadProfile("left", 10)
    right = WorkloadProfile("right", 10)
    assert left.fingerprint != right.fingerprint


def test_profile_entity_count_changes_fingerprint() -> None:
    assert WorkloadProfile("x", 10).fingerprint != WorkloadProfile("x", 11).fingerprint


def test_profile_zone_count_changes_fingerprint() -> None:
    assert WorkloadProfile("x", 10, zone_count=2).fingerprint != WorkloadProfile("x", 10, zone_count=3).fingerprint


def test_profile_velocity_flag_changes_fingerprint() -> None:
    assert WorkloadProfile("x", 10, include_velocity=True).fingerprint != WorkloadProfile("x", 10, include_velocity=False).fingerprint


def test_profile_names_flag_changes_fingerprint() -> None:
    assert WorkloadProfile("x", 10, include_names=True).fingerprint != WorkloadProfile("x", 10, include_names=False).fingerprint


@pytest.mark.parametrize("entity_count", [-1, True, 100_001])
def test_profile_invalid_entity_count_fails(entity_count) -> None:
    with pytest.raises((BoundsError, ValidationError)):
        WorkloadProfile("x", entity_count)


@pytest.mark.parametrize("zone_count", [0, -1, True, 1025])
def test_profile_invalid_zone_count_fails(zone_count) -> None:
    with pytest.raises((BoundsError, ValidationError)):
        WorkloadProfile("x", 1, zone_count=zone_count)


@pytest.mark.parametrize("health_span", [0, -1, True])
def test_profile_invalid_health_span_fails(health_span) -> None:
    with pytest.raises(ValidationError):
        WorkloadProfile("x", 1, health_span=health_span)


def test_profile_registry_has_expected_schemas() -> None:
    registry = profile_registry()
    assert registry.has("profile.position")
    assert registry.has("profile.health")
    assert registry.has("profile.velocity")
    assert registry.has("profile.name")


def test_profile_registry_is_deterministic() -> None:
    assert profile_registry().fingerprint == profile_registry().fingerprint


def test_empty_profile_builds_empty_store() -> None:
    result = build_profile_store(WorkloadProfile("empty", 0))
    assert result.entities == 0
    assert result.components == 0
    assert result.store.entity_ids() == ()


def test_profile_build_entity_count_matches_request() -> None:
    result = build_profile_store(WorkloadProfile("ten", 10))
    assert result.entities == 10
    assert result.store.entity_count == 10


def test_profile_default_component_count_is_four_per_entity() -> None:
    result = build_profile_store(WorkloadProfile("ten", 10))
    assert result.components == 40
    assert result.store.component_count == 40


def test_profile_without_optional_components_has_two_per_entity() -> None:
    result = build_profile_store(
        WorkloadProfile(
            "minimal",
            10,
            include_velocity=False,
            include_names=False,
        )
    )
    assert result.components == 20


def test_profile_entity_ids_are_stable() -> None:
    result = build_profile_store(WorkloadProfile("ids", 3))
    assert result.store.entity_ids() == (
        "profile:00000000",
        "profile:00000001",
        "profile:00000002",
    )


def test_profile_position_is_repeatable() -> None:
    left = build_profile_store(WorkloadProfile("position", 8, zone_count=2))
    right = build_profile_store(WorkloadProfile("position", 8, zone_count=2))
    for entity_id in left.store.entity_ids():
        assert left.store.get_component(entity_id, "profile.position") == right.store.get_component(entity_id, "profile.position")


def test_profile_health_is_repeatable() -> None:
    left = build_profile_store(WorkloadProfile("health", 20, health_span=7))
    right = build_profile_store(WorkloadProfile("health", 20, health_span=7))
    for entity_id in left.store.entity_ids():
        assert left.store.get_component(entity_id, "profile.health") == right.store.get_component(entity_id, "profile.health")


def test_profile_velocity_is_repeatable() -> None:
    left = build_profile_store(WorkloadProfile("velocity", 20))
    right = build_profile_store(WorkloadProfile("velocity", 20))
    for entity_id in left.store.entity_ids():
        assert left.store.get_component(entity_id, "profile.velocity") == right.store.get_component(entity_id, "profile.velocity")


def test_profile_names_are_stable() -> None:
    result = build_profile_store(WorkloadProfile("names", 2))
    assert result.store.get_component("profile:00000000", "profile.name").data["value"] == "entity-00000000"
    assert result.store.get_component("profile:00000001", "profile.name").data["value"] == "entity-00000001"


def test_profile_zone_assignment_cycles() -> None:
    result = build_profile_store(WorkloadProfile("zones", 6, zone_count=2))
    zones = [
        result.store.get_component(entity_id, "profile.position").data["zone"]
        for entity_id in result.store.entity_ids()
    ]
    assert zones == [0, 1, 0, 1, 0, 1]


def test_profile_state_digest_is_repeatable() -> None:
    profile = WorkloadProfile("repeat", 64, zone_count=4)
    left = build_profile_store(profile)
    right = build_profile_store(profile)
    assert left.state_digest == right.state_digest
    assert left.build_digest == right.build_digest


def test_profile_different_entity_count_changes_state_digest() -> None:
    left = build_profile_store(WorkloadProfile("left", 8))
    right = build_profile_store(WorkloadProfile("right", 9))
    assert left.state_digest != right.state_digest


def test_profile_different_zone_count_changes_state_digest() -> None:
    left = build_profile_store(WorkloadProfile("x", 16, zone_count=2))
    right = build_profile_store(WorkloadProfile("x", 16, zone_count=4))
    assert left.state_digest != right.state_digest


def test_profile_different_health_span_changes_state_digest() -> None:
    left = build_profile_store(WorkloadProfile("x", 16, health_span=10))
    right = build_profile_store(WorkloadProfile("x", 16, health_span=11))
    assert left.state_digest != right.state_digest


def test_profile_build_does_not_create_resources() -> None:
    result = build_profile_store(WorkloadProfile("resources", 8))
    assert result.store.resource_ids() == ()


def test_profile_build_has_no_tombstones() -> None:
    result = build_profile_store(WorkloadProfile("tombstones", 8))
    assert result.store.tombstone_ids() == ()


def test_profile_store_invariants_pass() -> None:
    result = build_profile_store(WorkloadProfile("invariants", 64))
    result.store.assert_invariants()


def test_profile_query_position_count_matches_entities() -> None:
    result = build_profile_store(WorkloadProfile("query", 64))
    engine = QueryEngine(result.store)
    assert engine.count(QuerySpec(all_of=("profile.position",))) == 64


def test_profile_query_optional_velocity_respects_flag() -> None:
    with_velocity = build_profile_store(WorkloadProfile("with", 16, include_velocity=True))
    without_velocity = build_profile_store(WorkloadProfile("without", 16, include_velocity=False))
    assert QueryEngine(with_velocity.store).count(QuerySpec(all_of=("profile.velocity",))) == 16
    assert QueryEngine(without_velocity.store).count(QuerySpec(all_of=("profile.velocity",))) == 0


def test_profile_query_zone_predicate() -> None:
    result = build_profile_store(WorkloadProfile("zones", 20, zone_count=4))
    spec = QuerySpec(
        all_of=("profile.position",),
        predicates=(FieldPredicate("profile.position", "zone", CompareOp.EQ, 2),),
    )
    ids = QueryEngine(result.store).ids(spec)
    assert len(ids) == 5
    assert ids[0] == "profile:00000002"


def test_profile_health_predicate_is_deterministic() -> None:
    result = build_profile_store(WorkloadProfile("health", 30, health_span=10))
    spec = QuerySpec(
        all_of=("profile.health",),
        predicates=(FieldPredicate("profile.health", "current", CompareOp.LT, 5),),
    )
    first = QueryEngine(result.store).ids(spec)
    second = QueryEngine(result.store).ids(spec)
    assert first == second


def test_profile_component_table_contains_all_positions() -> None:
    result = build_profile_store(WorkloadProfile("table", 32))
    table = ComponentTable(result.store, "profile.position")
    assert len(table.rows(result.store)) == 32


def test_profile_component_table_field_projection_is_stable() -> None:
    result = build_profile_store(WorkloadProfile("table", 8, zone_count=2))
    table = ComponentTable(result.store, "profile.position")
    first = table.field(result.store, "zone")
    second = table.field(result.store, "zone")
    assert first == second


def test_compare_equal_profile_builds_reports_equal() -> None:
    profile = WorkloadProfile("same", 32)
    comparison = compare_profile_builds(build_profile_store(profile), build_profile_store(profile))
    assert comparison.equal
    assert comparison.left_digest == comparison.right_digest


def test_compare_different_profile_builds_reports_not_equal() -> None:
    left = build_profile_store(WorkloadProfile("left", 16))
    right = build_profile_store(WorkloadProfile("right", 17))
    comparison = compare_profile_builds(left, right)
    assert not comparison.equal
    assert comparison.left_digest != comparison.right_digest


def test_comparison_digest_is_repeatable() -> None:
    profile = WorkloadProfile("same", 16)
    left_a = build_profile_store(profile)
    right_a = build_profile_store(profile)
    left_b = build_profile_store(profile)
    right_b = build_profile_store(profile)
    assert compare_profile_builds(left_a, right_a).comparison_digest == compare_profile_builds(left_b, right_b).comparison_digest


def test_profile_matrix_has_unique_names() -> None:
    matrix = profile_matrix()
    names = [profile.name for profile in matrix]
    assert len(names) == len(set(names))


def test_profile_matrix_includes_empty_case() -> None:
    matrix = profile_matrix()
    assert any(profile.entity_count == 0 for profile in matrix)


def test_profile_matrix_includes_minimal_component_case() -> None:
    matrix = profile_matrix()
    assert any(not profile.include_velocity and not profile.include_names for profile in matrix)


@pytest.mark.parametrize("profile", profile_matrix(), ids=lambda profile: profile.name)
def test_profile_matrix_builds_are_self_consistent(profile) -> None:
    result = build_profile_store(profile)
    assert result.entities == profile.entity_count
    assert result.state_digest == result.store.state_digest
    assert result.registry_fingerprint == result.store.registry.fingerprint
    result.store.assert_invariants()


@pytest.mark.parametrize("profile", profile_matrix(), ids=lambda profile: profile.name)
def test_profile_matrix_rebuilds_identically(profile) -> None:
    left = build_profile_store(profile)
    right = build_profile_store(profile)
    assert compare_profile_builds(left, right).equal
