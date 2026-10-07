"""Regression contracts for the deterministic ECS foundation.

These tests deliberately exercise public module-level contracts rather than
implementation details.  The suite is intentionally verbose: each assertion
locks a separate determinism, validation, rollback, or ordering guarantee that
future game-building layers are expected to rely on.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.simulation.ecs.canonical import (
    canonical_bytes,
    canonical_json,
    canonical_node,
    chained_digest,
    digest,
    digest_many,
)
from skeleton.simulation.ecs.errors import (
    ComponentExistsError,
    ComponentNotFoundError,
    EntityExistsError,
    EntityNotFoundError,
    EntityTombstonedError,
    IdentifierError,
    QueryError,
    ResourceNotFoundError,
    SchemaConflictError,
    SchemaError,
    SchemaNotFoundError,
    SchemaVersionError,
    ValidationError,
)
from skeleton.simulation.ecs.identity import EntityAllocator, EntityId
from skeleton.simulation.ecs.index import ComponentIndex
from skeleton.simulation.ecs.query import CompareOp, FieldPredicate, QueryEngine, QuerySpec
from skeleton.simulation.ecs.schema import (
    ComponentSchema,
    FieldKind,
    FieldSpec,
    MigrationRegistry,
    MigrationStep,
    SchemaRegistry,
    make_schema,
)
from skeleton.simulation.ecs.store import EntityStore


def _registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    registry.register(
        make_schema(
            "position",
            1,
            (
                FieldSpec("x", FieldKind.FLOAT),
                FieldSpec("y", FieldKind.FLOAT),
                FieldSpec("zone", FieldKind.TEXT, required=False, default="world"),
            ),
            description="Stable world position.",
        )
    )
    registry.register(
        make_schema(
            "health",
            1,
            (
                FieldSpec("current", FieldKind.INT, minimum=0, maximum=1000),
                FieldSpec("maximum", FieldKind.INT, minimum=1, maximum=1000),
                FieldSpec("alive", FieldKind.BOOL, default=True),
            ),
            description="Bounded health state.",
        )
    )
    registry.register(
        make_schema(
            "name",
            1,
            (FieldSpec("value", FieldKind.TEXT),),
        )
    )
    registry.register(
        make_schema(
            "inventory",
            1,
            (FieldSpec("items", FieldKind.JSON, default=[]),),
        )
    )
    return registry


def _populated_store() -> EntityStore:
    store = EntityStore(_registry(), allocator=EntityAllocator("test", seed="fixture"))
    store.create_entity("entity:a")
    store.create_entity("entity:b")
    store.create_entity("entity:c")
    store.set_component("entity:a", "position", {"x": 1, "y": 2})
    store.set_component("entity:a", "health", {"current": 100, "maximum": 100})
    store.set_component("entity:a", "name", {"value": "alpha"})
    store.set_component("entity:b", "position", {"x": 5, "y": 8, "zone": "cave"})
    store.set_component("entity:b", "health", {"current": 40, "maximum": 80})
    store.set_component("entity:c", "name", {"value": "charlie"})
    store.set_resource("weather", {"kind": "rain", "intensity": 0.5})
    return store


@dataclass(frozen=True)
class _Point:
    x: int
    y: int


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (1, 1.0),
        (1, True),
        (1, "1"),
        (0, False),
        (b"1", "1"),
        ([1, 2], (1, 2)),
        ({1, 2}, frozenset({1, 2})),
        (None, "None"),
        ({"a": 1}, [("a", 1)]),
        ("", b""),
    ],
)
def test_canonical_hash_is_type_separated(left, right) -> None:
    assert digest(left) != digest(right)


def test_canonical_mapping_order_does_not_change_digest() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_canonical_set_order_does_not_change_digest() -> None:
    assert digest({"alpha", "beta", "gamma"}) == digest({"gamma", "alpha", "beta"})


def test_canonical_list_order_changes_digest() -> None:
    assert digest([1, 2, 3]) != digest([3, 2, 1])


def test_canonical_dataclass_is_supported() -> None:
    point = _Point(3, 7)
    node = canonical_node(point)
    assert node[0] == "dataclass"
    assert digest(point) == digest(_Point(3, 7))


def test_canonical_bytes_are_repeatable() -> None:
    value = {"nested": [1, True, 2.5, "value", b"bytes"]}
    assert canonical_bytes(value) == canonical_bytes(value)
    assert canonical_json(value) == canonical_json(value)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_float_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        digest(value)


def test_non_string_mapping_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        canonical_node({1: "not allowed"})


def test_unsupported_object_is_rejected() -> None:
    with pytest.raises(ValidationError):
        canonical_node(object())


def test_digest_many_preserves_element_boundaries() -> None:
    assert digest_many(["ab", "c"]) != digest_many(["a", "bc"])


def test_chained_digest_changes_with_previous_digest() -> None:
    zero = "0" * 64
    one = "1" * 64
    assert chained_digest(zero, {"x": 1}) != chained_digest(one, {"x": 1})


def test_chained_digest_rejects_non_sha_previous_value() -> None:
    with pytest.raises(ValidationError):
        chained_digest("not-a-digest", {"x": 1})


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        " has-space",
        "contains space",
        "*wildcard",
        "\nnewline",
    ],
)
def test_entity_id_rejects_invalid_text(invalid: str) -> None:
    with pytest.raises(IdentifierError):
        EntityId(invalid)


def test_entity_id_accepts_namespaced_identifier() -> None:
    assert str(EntityId("npc:guard-01")) == "npc:guard-01"


def test_allocator_is_deterministic_for_same_state() -> None:
    a = EntityAllocator("npc", seed="same")
    b = EntityAllocator("npc", seed="same")
    assert [a.allocate("guard").value for _ in range(5)] == [
        b.allocate("guard").value for _ in range(5)
    ]


def test_allocator_seed_changes_identity_sequence() -> None:
    a = EntityAllocator("npc", seed="a")
    b = EntityAllocator("npc", seed="b")
    assert a.allocate("guard").value != b.allocate("guard").value


def test_allocator_namespace_changes_identity_sequence() -> None:
    a = EntityAllocator("npc", seed="same")
    b = EntityAllocator("item", seed="same")
    assert a.allocate("guard").value != b.allocate("guard").value


def test_allocator_counter_advances_monotonically() -> None:
    allocator = EntityAllocator("npc", seed="counter")
    allocator.allocate()
    allocator.allocate()
    assert allocator.counter == 2


def test_allocator_snapshot_round_trip_preserves_next_id() -> None:
    allocator = EntityAllocator("npc", seed="snapshot")
    allocator.allocate("one")
    allocator.allocate("two")
    restored = EntityAllocator.restore(allocator.snapshot())
    assert restored.allocate("three") == allocator.allocate("three")


def test_allocator_restore_rejects_unexpected_fields() -> None:
    with pytest.raises(IdentifierError):
        EntityAllocator.restore(
            {"namespace": "npc", "seed": "x", "counter": 0, "extra": True}
        )


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (FieldKind.BOOL, True),
        (FieldKind.INT, 7),
        (FieldKind.FLOAT, 7),
        (FieldKind.FLOAT, 7.5),
        (FieldKind.TEXT, "hello"),
        (FieldKind.BYTES, b"hello"),
        (FieldKind.JSON, {"a": [1, 2, 3]}),
    ],
)
def test_field_kinds_accept_valid_values(kind: FieldKind, value) -> None:
    schema = make_schema("value", 1, (FieldSpec("v", kind),))
    validated = schema.validate({"v": value})
    assert "v" in validated


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (FieldKind.BOOL, 1),
        (FieldKind.INT, True),
        (FieldKind.INT, 1.0),
        (FieldKind.FLOAT, True),
        (FieldKind.FLOAT, "1.0"),
        (FieldKind.TEXT, 1),
        (FieldKind.BYTES, "bytes"),
        (FieldKind.JSON, object()),
    ],
)
def test_field_kinds_reject_wrong_types(kind: FieldKind, value) -> None:
    schema = make_schema("value", 1, (FieldSpec("v", kind),))
    with pytest.raises(SchemaError):
        schema.validate({"v": value})


def test_field_minimum_is_enforced() -> None:
    schema = make_schema("score", 1, (FieldSpec("v", FieldKind.INT, minimum=5),))
    with pytest.raises(SchemaError):
        schema.validate({"v": 4})


def test_field_maximum_is_enforced() -> None:
    schema = make_schema("score", 1, (FieldSpec("v", FieldKind.INT, maximum=5),))
    with pytest.raises(SchemaError):
        schema.validate({"v": 6})


def test_field_choices_are_enforced() -> None:
    schema = make_schema(
        "stance",
        1,
        (FieldSpec("v", FieldKind.TEXT, choices=("idle", "attack", "flee")),),
    )
    assert schema.validate({"v": "attack"}) == {"v": "attack"}
    with pytest.raises(SchemaError):
        schema.validate({"v": "sleep"})


def test_required_field_is_enforced() -> None:
    schema = make_schema("required", 1, (FieldSpec("v", FieldKind.INT),))
    with pytest.raises(SchemaError):
        schema.validate({})


def test_default_value_is_materialized() -> None:
    schema = make_schema(
        "defaults",
        1,
        (FieldSpec("v", FieldKind.INT, required=False, default=4),),
    )
    assert schema.validate({}) == {"v": 4}


def test_unknown_component_fields_are_rejected_by_default() -> None:
    schema = make_schema("known", 1, (FieldSpec("v", FieldKind.INT),))
    with pytest.raises(SchemaError):
        schema.validate({"v": 1, "unknown": 2})


def test_unknown_component_fields_can_be_explicitly_retained() -> None:
    schema = make_schema("known", 1, (FieldSpec("v", FieldKind.INT),))
    assert schema.validate({"v": 1, "unknown": 2}, allow_extra=True) == {
        "unknown": 2,
        "v": 1,
    }


def test_schema_field_order_is_canonicalized() -> None:
    schema = make_schema(
        "ordered",
        1,
        (
            FieldSpec("z", FieldKind.INT),
            FieldSpec("a", FieldKind.INT),
            FieldSpec("m", FieldKind.INT),
        ),
    )
    assert tuple(field.name for field in schema.fields) == ("a", "m", "z")


def test_duplicate_schema_fields_are_rejected() -> None:
    with pytest.raises(SchemaError):
        ComponentSchema(
            "duplicate",
            1,
            (FieldSpec("v", FieldKind.INT), FieldSpec("v", FieldKind.INT)),
        )


def test_schema_registry_registration_is_idempotent() -> None:
    registry = SchemaRegistry()
    schema = make_schema("position", 1, (FieldSpec("x", FieldKind.FLOAT),))
    assert registry.register(schema) is schema
    assert registry.register(schema) is schema


def test_schema_registry_rejects_same_key_with_different_definition() -> None:
    registry = SchemaRegistry()
    registry.register(make_schema("position", 1, (FieldSpec("x", FieldKind.FLOAT),)))
    with pytest.raises(SchemaConflictError):
        registry.register(make_schema("position", 1, (FieldSpec("x", FieldKind.INT),)))


def test_schema_registry_latest_version_is_default_lookup() -> None:
    registry = SchemaRegistry()
    registry.register(make_schema("position", 1, (FieldSpec("x", FieldKind.FLOAT),)))
    registry.register(
        make_schema(
            "position",
            2,
            (FieldSpec("x", FieldKind.FLOAT), FieldSpec("y", FieldKind.FLOAT, default=0.0)),
        )
    )
    assert registry.get("position").version == 2
    assert registry.versions("position") == (1, 2)


def test_schema_registry_unknown_lookup_fails_closed() -> None:
    with pytest.raises(SchemaNotFoundError):
        SchemaRegistry().get("missing")


def test_schema_registry_fingerprint_is_registration_order_independent() -> None:
    first = SchemaRegistry()
    second = SchemaRegistry()
    a = make_schema("a", 1, (FieldSpec("v", FieldKind.INT),))
    b = make_schema("b", 1, (FieldSpec("v", FieldKind.TEXT),))
    first.register(a)
    first.register(b)
    second.register(b)
    second.register(a)
    assert first.fingerprint == second.fingerprint


def test_migration_registry_applies_each_version_step() -> None:
    schemas = SchemaRegistry()
    schemas.register(make_schema("actor", 1, (FieldSpec("hp", FieldKind.INT),)))
    schemas.register(
        make_schema(
            "actor",
            2,
            (
                FieldSpec("current", FieldKind.INT),
                FieldSpec("maximum", FieldKind.INT),
            ),
        )
    )
    schemas.register(
        make_schema(
            "actor",
            3,
            (
                FieldSpec("current", FieldKind.INT),
                FieldSpec("maximum", FieldKind.INT),
                FieldSpec("alive", FieldKind.BOOL, default=True),
            ),
        )
    )
    migrations = MigrationRegistry(schemas)
    migrations.register(
        MigrationStep("actor", 1, 2, "split_hp"),
        lambda value: {"current": value["hp"], "maximum": value["hp"]},
    )
    migrations.register(
        MigrationStep("actor", 2, 3, "add_alive"),
        lambda value: {**value, "alive": value["current"] > 0},
    )
    value, evidence = migrations.migrate("actor", 1, 3, {"hp": 50})
    assert value == {"alive": True, "current": 50, "maximum": 50}
    assert evidence.steps == ("split_hp", "add_alive")
    assert evidence.before_digest != evidence.after_digest


def test_migration_registry_rejects_downgrade() -> None:
    schemas = SchemaRegistry()
    schemas.register(make_schema("actor", 1, (FieldSpec("hp", FieldKind.INT),)))
    schemas.register(make_schema("actor", 2, (FieldSpec("hp", FieldKind.INT),)))
    migrations = MigrationRegistry(schemas)
    with pytest.raises(SchemaVersionError):
        migrations.migrate("actor", 2, 1, {"hp": 1})


def test_migration_registry_rejects_incomplete_path() -> None:
    schemas = SchemaRegistry()
    schemas.register(make_schema("actor", 1, (FieldSpec("hp", FieldKind.INT),)))
    schemas.register(make_schema("actor", 2, (FieldSpec("hp", FieldKind.INT),)))
    migrations = MigrationRegistry(schemas)
    with pytest.raises(SchemaVersionError):
        migrations.migrate("actor", 1, 2, {"hp": 1})


def test_store_entity_ids_are_stably_sorted() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:z")
    store.create_entity("entity:a")
    store.create_entity("entity:m")
    assert store.entity_ids() == ("entity:a", "entity:m", "entity:z")


def test_store_rejects_duplicate_entity() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    with pytest.raises(EntityExistsError):
        store.create_entity("entity:a")


def test_store_unknown_entity_lookup_fails_closed() -> None:
    with pytest.raises(EntityNotFoundError):
        EntityStore(_registry()).get_entity("entity:missing")


def test_store_tombstone_blocks_identity_reuse() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    tombstone = store.delete_entity("entity:a")
    assert tombstone.entity_id == "entity:a"
    assert store.is_tombstoned("entity:a")
    with pytest.raises(EntityTombstonedError):
        store.create_entity("entity:a")


def test_store_component_round_trip() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    value = store.set_component("entity:a", "position", {"x": 1, "y": 2})
    assert value.schema_id == "position"
    assert value.schema_version == 1
    assert value.data == {"x": 1.0, "y": 2.0, "zone": "world"}
    assert store.get_component("entity:a", "position") == value


def test_store_set_component_replace_false_rejects_duplicate() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    store.set_component("entity:a", "name", {"value": "first"})
    with pytest.raises(ComponentExistsError):
        store.set_component(
            "entity:a", "name", {"value": "second"}, replace=False
        )


def test_store_patch_component_revalidates_schema() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    store.set_component("entity:a", "health", {"current": 100, "maximum": 100})
    patched = store.patch_component("entity:a", "health", {"current": 75})
    assert patched.data["current"] == 75
    assert patched.data["maximum"] == 100


def test_store_patch_component_rejects_invalid_result() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    store.set_component("entity:a", "health", {"current": 100, "maximum": 100})
    with pytest.raises(SchemaError):
        store.patch_component("entity:a", "health", {"current": -1})


def test_store_remove_component_returns_previous_value() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    store.set_component("entity:a", "name", {"value": "alpha"})
    removed = store.remove_component("entity:a", "name")
    assert removed.data == {"value": "alpha"}
    assert not store.has_component("entity:a", "name")


def test_store_remove_missing_component_fails_closed() -> None:
    store = EntityStore(_registry())
    store.create_entity("entity:a")
    with pytest.raises(ComponentNotFoundError):
        store.remove_component("entity:a", "name")


def test_store_resource_round_trip() -> None:
    store = EntityStore(_registry())
    resource = store.set_resource("world.time", {"hour": 12})
    assert resource.value == {"hour": 12}
    assert store.get_resource("world.time").value == {"hour": 12}


def test_store_remove_resource_returns_previous_value() -> None:
    store = EntityStore(_registry())
    store.set_resource("world.time", {"hour": 12})
    removed = store.remove_resource("world.time")
    assert removed.resource_id == "world.time"
    with pytest.raises(ResourceNotFoundError):
        store.get_resource("world.time")


def test_store_state_digest_changes_after_mutation() -> None:
    store = EntityStore(_registry())
    before = store.state_digest
    store.create_entity("entity:a")
    after = store.state_digest
    assert before != after


def test_store_clone_has_same_digest_but_is_independent() -> None:
    store = _populated_store()
    clone = store.clone()
    assert clone.state_digest == store.state_digest
    clone.patch_component("entity:a", "health", {"current": 1})
    assert clone.state_digest != store.state_digest
    assert store.get_component("entity:a", "health").data["current"] == 100


def test_store_replace_from_copies_complete_state() -> None:
    source = _populated_store()
    target = EntityStore()
    target.replace_from(source)
    assert target.state_digest == source.state_digest
    assert target.to_record() == source.to_record()


def test_store_transaction_rolls_back_failure() -> None:
    store = _populated_store()
    before = store.state_digest
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.patch_component("entity:a", "health", {"current": 1})
            store.set_resource("temporary", {"v": 1})
            raise RuntimeError("abort")
    assert store.state_digest == before
    assert store.get_component("entity:a", "health").data["current"] == 100
    with pytest.raises(ResourceNotFoundError):
        store.get_resource("temporary")


def test_store_transaction_commits_success() -> None:
    store = _populated_store()
    before = store.state_digest
    with store.transaction():
        store.patch_component("entity:a", "health", {"current": 50})
    assert store.state_digest != before
    assert store.get_component("entity:a", "health").data["current"] == 50


def test_store_tick_is_monotonic() -> None:
    store = EntityStore(_registry())
    store.advance_tick(5)
    assert store.tick == 5
    with pytest.raises(ValidationError):
        store.advance_tick(4)


def test_store_same_tick_is_noop() -> None:
    store = EntityStore(_registry())
    store.advance_tick(5)
    revision = store.revision
    store.advance_tick(5)
    assert store.revision == revision


def test_store_assert_invariants_accepts_valid_store() -> None:
    store = _populated_store()
    store.assert_invariants()


def test_component_index_matches_store_presence() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    assert index.entities_with("position") == ("entity:a", "entity:b")
    assert index.entities_with("health") == ("entity:a", "entity:b")
    assert index.entities_with("name") == ("entity:a", "entity:c")


def test_component_index_all_candidates_are_intersection() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    assert index.candidates_all(["health", "name"]) == ("entity:a",)


def test_component_index_any_candidates_are_union() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    assert index.candidates_any(["health", "name"]) == (
        "entity:a",
        "entity:b",
        "entity:c",
    )


def test_component_index_none_candidates_exclude_presence() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    assert index.candidates_none(["position"]) == ("entity:c",)


def test_component_index_detects_stale_state() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    store.patch_component("entity:a", "health", {"current": 99})
    assert not index.is_current(store)
    with pytest.raises(QueryError):
        index.require_current(store)


def test_component_index_refresh_restores_current_state() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    store.set_component("entity:c", "position", {"x": 9, "y": 9})
    index.refresh(store)
    assert index.is_current(store)
    assert index.entities_with("position") == ("entity:a", "entity:b", "entity:c")


@pytest.mark.parametrize(
    ("op", "actual", "expected", "matches"),
    [
        (CompareOp.EQ, 5, 5, True),
        (CompareOp.NE, 5, 4, True),
        (CompareOp.LT, 4, 5, True),
        (CompareOp.LE, 5, 5, True),
        (CompareOp.GT, 6, 5, True),
        (CompareOp.GE, 5, 5, True),
        (CompareOp.IN, "a", ("a", "b"), True),
        (CompareOp.CONTAINS, ("a", "b"), "a", True),
        (CompareOp.EQ, 5, 4, False),
        (CompareOp.LT, 5, 4, False),
    ],
)
def test_field_predicate_operations(op, actual, expected, matches) -> None:
    predicate = FieldPredicate("value", "v", op, expected)
    assert predicate.matches(actual) is matches


def test_query_all_of_requires_every_component() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    assert engine.ids(QuerySpec(all_of=("position", "health", "name"))) == (
        "entity:a",
    )


def test_query_any_of_requires_at_least_one_component() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    assert engine.ids(QuerySpec(any_of=("health", "name"))) == (
        "entity:a",
        "entity:b",
        "entity:c",
    )


def test_query_none_of_excludes_matching_components() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    assert engine.ids(QuerySpec(none_of=("position",))) == ("entity:c",)


def test_query_predicate_filters_component_field() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    spec = QuerySpec(
        all_of=("health",),
        predicates=(FieldPredicate("health", "current", CompareOp.GT, 50),),
    )
    assert engine.ids(spec) == ("entity:a",)


def test_query_multiple_predicates_are_anded() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    spec = QuerySpec(
        all_of=("position", "health"),
        predicates=(
            FieldPredicate("position", "zone", CompareOp.EQ, "cave"),
            FieldPredicate("health", "current", CompareOp.LE, 40),
        ),
    )
    assert engine.ids(spec) == ("entity:b",)


def test_query_offset_and_limit_are_applied_after_stable_sort() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    assert engine.ids(QuerySpec(offset=1, limit=1)) == ("entity:b",)


def test_query_count_matches_execute_length() -> None:
    store = _populated_store()
    engine = QueryEngine(store)
    spec = QuerySpec(any_of=("position",))
    assert engine.count(spec) == len(engine.execute(spec)) == 2


def test_query_with_current_index_matches_scan() -> None:
    store = _populated_store()
    spec = QuerySpec(
        all_of=("position",),
        predicates=(FieldPredicate("position", "x", CompareOp.GE, 1),),
    )
    scan = QueryEngine(store).ids(spec)
    indexed = QueryEngine(store, index=ComponentIndex(store)).ids(spec)
    assert indexed == scan


def test_query_with_stale_index_fails_closed() -> None:
    store = _populated_store()
    index = ComponentIndex(store)
    store.create_entity("entity:d")
    with pytest.raises(QueryError):
        QueryEngine(store, index=index).execute(QuerySpec())


@pytest.mark.parametrize("limit", [-1, True, 100_001])
def test_query_rejects_invalid_limit(limit) -> None:
    with pytest.raises(QueryError):
        QuerySpec(limit=limit)


@pytest.mark.parametrize("offset", [-1, True, 1.5])
def test_query_rejects_invalid_offset(offset) -> None:
    with pytest.raises(QueryError):
        QuerySpec(offset=offset)
