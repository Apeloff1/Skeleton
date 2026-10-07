"""Timeline and composable selector regression contracts."""
from __future__ import annotations

import pytest

from skeleton.simulation.ecs.errors import QueryError, SnapshotError, ValidationError
from skeleton.simulation.ecs.partitions import WorldPartitionIndex
from skeleton.simulation.ecs.query import CompareOp, FieldPredicate
from skeleton.simulation.ecs.relations import RelationGraph
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec, SchemaRegistry, make_schema
from skeleton.simulation.ecs.selectors import (
    SelectionEngine,
    SelectorSpec,
    intersect_results,
    union_results,
)
from skeleton.simulation.ecs.store import EntityStore
from skeleton.simulation.ecs.timeline import StateTimeline, TimelinePolicy, record_states


def _registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    registry.register(
        make_schema(
            "position",
            1,
            (
                FieldSpec("x", FieldKind.FLOAT),
                FieldSpec("y", FieldKind.FLOAT),
                FieldSpec("zone", FieldKind.TEXT, default="world"),
            ),
        )
    )
    registry.register(
        make_schema(
            "health",
            1,
            (
                FieldSpec("current", FieldKind.INT, minimum=0),
                FieldSpec("maximum", FieldKind.INT, minimum=1),
            ),
        )
    )
    registry.register(make_schema("name", 1, (FieldSpec("value", FieldKind.TEXT),)))
    return registry


def _store() -> EntityStore:
    store = EntityStore(_registry())
    for entity_id in ("entity:a", "entity:b", "entity:c", "entity:d"):
        store.create_entity(entity_id)
    store.set_component("entity:a", "position", {"x": 0, "y": 0, "zone": "north"})
    store.set_component("entity:a", "health", {"current": 100, "maximum": 100})
    store.set_component("entity:b", "position", {"x": 5, "y": 5, "zone": "north"})
    store.set_component("entity:b", "health", {"current": 40, "maximum": 100})
    store.set_component("entity:c", "position", {"x": 10, "y": 10, "zone": "south"})
    store.set_component("entity:d", "name", {"value": "delta"})
    return store


def test_timeline_policy_fingerprint_is_stable() -> None:
    assert TimelinePolicy().fingerprint == TimelinePolicy().fingerprint


@pytest.mark.parametrize("capacity", [0, -1, True, 4097])
def test_timeline_invalid_capacity_fails(capacity) -> None:
    with pytest.raises(ValidationError):
        TimelinePolicy(capacity=capacity)


def test_empty_timeline_summary() -> None:
    timeline = StateTimeline()
    summary = timeline.summary()
    assert summary["frames"] == 0
    assert summary["next_sequence"] == 0


def test_timeline_append_assigns_monotonic_sequence() -> None:
    store = _store()
    timeline = StateTimeline()
    first = timeline.append(store, label="a")
    store.set_resource("weather", "rain")
    second = timeline.append(store, label="b")
    assert first.sequence == 0
    assert second.sequence == 1
    assert second.previous_digest == first.frame_digest


def test_timeline_frame_snapshot_is_immutable_copy() -> None:
    store = _store()
    timeline = StateTimeline()
    frame = timeline.append(store)
    store.set_resource("weather", "rain")
    assert frame.snapshot.store.resource_ids() == ()


def test_timeline_duplicate_state_rejected_by_default() -> None:
    store = _store()
    timeline = StateTimeline()
    timeline.append(store)
    with pytest.raises(SnapshotError):
        timeline.append(store)


def test_timeline_duplicate_state_allowed_by_policy() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(allow_duplicate_state=True))
    timeline.append(store)
    timeline.append(store)
    assert len(timeline) == 2


def test_timeline_capacity_evicts_oldest_frames() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(capacity=2))
    first = timeline.append(store, label="0")
    store.set_resource("one", 1)
    second = timeline.append(store, label="1")
    store.set_resource("two", 2)
    third = timeline.append(store, label="2")
    assert len(timeline) == 2
    assert timeline.frames() == (second, third)
    with pytest.raises(SnapshotError):
        timeline.get(first.sequence)


def test_timeline_verifies_after_eviction() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(capacity=2))
    for index in range(4):
        store.set_resource(f"r{index}", index)
        timeline.append(store, label=str(index))
    verification = timeline.verify()
    assert verification.valid
    assert verification.frames == 2


def test_timeline_latest_returns_last_frame() -> None:
    store = _store()
    timeline = StateTimeline()
    timeline.append(store, label="first")
    store.set_resource("x", 1)
    last = timeline.append(store, label="last")
    assert timeline.latest() == last


def test_timeline_latest_empty_fails() -> None:
    with pytest.raises(SnapshotError):
        StateTimeline().latest()


def test_timeline_by_label() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(allow_duplicate_state=True))
    first = timeline.append(store, label="save")
    second = timeline.append(store, label="save")
    assert timeline.by_label("save") == (first, second)


def test_timeline_at_revision() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(allow_duplicate_state=True))
    frame = timeline.append(store)
    assert timeline.at_revision(store.revision) == (frame,)


def test_timeline_at_tick() -> None:
    store = _store()
    timeline = StateTimeline(policy=TimelinePolicy(allow_duplicate_state=True))
    frame = timeline.append(store)
    assert timeline.at_tick(0) == (frame,)


def test_timeline_seek_restores_exact_state() -> None:
    store = _store()
    timeline = StateTimeline()
    first = timeline.append(store)
    store.set_resource("weather", "rain")
    timeline.append(store)
    timeline.seek(store, first.sequence)
    assert store.state_digest == first.state_digest
    assert store.resource_ids() == ()


def test_timeline_diff_reports_change() -> None:
    store = _store()
    timeline = StateTimeline()
    first = timeline.append(store)
    store.patch_component("entity:a", "health", {"current": 1})
    second = timeline.append(store)
    delta = timeline.diff(first.sequence, second.sequence)
    assert delta.changed
    assert delta.changed_entities == ("entity:a",)


def test_timeline_range_is_inclusive() -> None:
    store = _store()
    timeline = StateTimeline()
    frames = []
    for index in range(3):
        store.set_resource(f"r{index}", index)
        frames.append(timeline.append(store, label=str(index)))
    selected = timeline.range(1, 2)
    assert selected.frames == (frames[1], frames[2])


def test_timeline_verify_is_deterministic() -> None:
    left_store = _store()
    right_store = _store()
    left = StateTimeline()
    right = StateTimeline()
    for index in range(3):
        left_store.set_resource(f"r{index}", index)
        right_store.set_resource(f"r{index}", index)
        left.append(left_store, label=str(index))
        right.append(right_store, label=str(index))
    assert left.head_digest == right.head_digest
    assert left.verify() == right.verify()


def test_record_states_builds_timeline() -> None:
    first = _store()
    second = first.clone()
    second.set_resource("weather", "rain")
    timeline = record_states((first, second), label_prefix="fixture")
    assert len(timeline) == 2
    assert timeline.frames()[0].label == "fixture:0"
    assert timeline.frames()[1].label == "fixture:1"


def test_selector_spec_fingerprint_is_order_normalized() -> None:
    left = SelectorSpec(all_components=("health", "position", "health"))
    right = SelectorSpec(all_components=("position", "health"))
    assert left.fingerprint == right.fingerprint


def test_selector_components_all_filter() -> None:
    store = _store()
    result = SelectionEngine(store).select(SelectorSpec(all_components=("position", "health")))
    assert result.entity_ids == ("entity:a", "entity:b")


def test_selector_components_any_filter() -> None:
    store = _store()
    result = SelectionEngine(store).select(SelectorSpec(any_components=("health", "name")))
    assert result.entity_ids == ("entity:a", "entity:b", "entity:d")


def test_selector_components_none_filter() -> None:
    store = _store()
    result = SelectionEngine(store).select(SelectorSpec(no_components=("position",)))
    assert result.entity_ids == ("entity:d",)


def test_selector_field_predicate_filter() -> None:
    store = _store()
    spec = SelectorSpec(
        all_components=("health",),
        predicates=(FieldPredicate("health", "current", CompareOp.LT, 50),),
    )
    assert SelectionEngine(store).ids(spec) == ("entity:b",)


def test_selector_all_tags_filter() -> None:
    store = _store()
    relations = RelationGraph(store)
    relations.add_tag("entity:a", "player")
    relations.add_tag("entity:a", "alive")
    relations.add_tag("entity:b", "player")
    spec = SelectorSpec(all_tags=("player", "alive"))
    assert SelectionEngine(store, relations=relations).ids(spec) == ("entity:a",)


def test_selector_any_tags_filter() -> None:
    store = _store()
    relations = RelationGraph(store)
    relations.add_tag("entity:a", "player")
    relations.add_tag("entity:c", "enemy")
    spec = SelectorSpec(any_tags=("player", "enemy"))
    assert SelectionEngine(store, relations=relations).ids(spec) == ("entity:a", "entity:c")


def test_selector_no_tags_filter() -> None:
    store = _store()
    relations = RelationGraph(store)
    relations.add_tag("entity:a", "hidden")
    spec = SelectorSpec(no_tags=("hidden",))
    assert SelectionEngine(store, relations=relations).ids(spec) == ("entity:b", "entity:c", "entity:d")


def test_selector_tag_filter_requires_relation_graph() -> None:
    with pytest.raises(QueryError):
        SelectionEngine(_store()).select(SelectorSpec(all_tags=("player",)))


def test_selector_partition_filter() -> None:
    store = _store()
    partitions = WorldPartitionIndex(store)
    partitions.assign("entity:a", "north")
    partitions.assign("entity:b", "north")
    partitions.assign("entity:c", "south")
    spec = SelectorSpec(partitions=("south",))
    assert SelectionEngine(store, partitions=partitions).ids(spec) == ("entity:c",)


def test_selector_partition_filter_requires_partition_index() -> None:
    with pytest.raises(QueryError):
        SelectionEngine(_store()).select(SelectorSpec(partitions=("north",)))


def test_selector_combines_components_tags_and_partitions() -> None:
    store = _store()
    relations = RelationGraph(store)
    partitions = WorldPartitionIndex(store)
    relations.add_tag("entity:a", "player")
    relations.add_tag("entity:b", "player")
    partitions.assign("entity:a", "north")
    partitions.assign("entity:b", "south")
    spec = SelectorSpec(
        all_components=("health",),
        all_tags=("player",),
        partitions=("north",),
    )
    assert SelectionEngine(store, relations=relations, partitions=partitions).ids(spec) == ("entity:a",)


def test_selector_window_is_stable() -> None:
    store = _store()
    result = SelectionEngine(store).select(SelectorSpec(limit=2, offset=1))
    assert result.total_before_window == 4
    assert result.entity_ids == ("entity:b", "entity:c")


def test_selector_result_digest_is_deterministic() -> None:
    left = SelectionEngine(_store()).select(SelectorSpec(all_components=("position",)))
    right = SelectionEngine(_store()).select(SelectorSpec(all_components=("position",)))
    assert left.result_digest == right.result_digest


def test_selector_count_ignores_window_limit() -> None:
    store = _store()
    spec = SelectorSpec(limit=1)
    assert SelectionEngine(store).count(spec) == 4


def test_selector_contains_uses_windowed_result() -> None:
    store = _store()
    spec = SelectorSpec(limit=1)
    engine = SelectionEngine(store)
    assert engine.contains(spec, "entity:a")
    assert not engine.contains(spec, "entity:b")


def test_selector_relation_graph_must_match_store() -> None:
    with pytest.raises(ValidationError):
        SelectionEngine(_store(), relations=RelationGraph(_store()))


def test_selector_partition_index_must_match_store() -> None:
    with pytest.raises(ValidationError):
        SelectionEngine(_store(), partitions=WorldPartitionIndex(_store()))


def test_union_results_is_sorted_unique() -> None:
    store = _store()
    engine = SelectionEngine(store)
    left = engine.select(SelectorSpec(all_components=("health",)))
    right = engine.select(SelectorSpec(all_components=("name",)))
    assert union_results((right, left)) == ("entity:a", "entity:b", "entity:d")


def test_intersect_results_is_sorted() -> None:
    store = _store()
    engine = SelectionEngine(store)
    left = engine.select(SelectorSpec(all_components=("position",)))
    right = engine.select(SelectorSpec(all_components=("health",)))
    assert intersect_results((left, right)) == ("entity:a", "entity:b")


def test_intersect_empty_results_is_empty() -> None:
    assert intersect_results(()) == ()


def test_timeline_and_selector_can_share_authoritative_store() -> None:
    store = _store()
    timeline = StateTimeline()
    selector = SelectionEngine(store)
    first = timeline.append(store, label="before")
    assert selector.ids(SelectorSpec(all_components=("health",))) == ("entity:a", "entity:b")
    store.remove_component("entity:b", "health")
    second = timeline.append(store, label="after")
    assert selector.ids(SelectorSpec(all_components=("health",))) == ("entity:a",)
    assert timeline.diff(first.sequence, second.sequence).changed_entities == ("entity:b",)
