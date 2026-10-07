"""Evidence-plane and derived-view regression contracts for deterministic ECS.

This suite concentrates on the parts of the simulation core that can silently
become nondeterministic if future optimizations bypass ordering or copy rules:
append-only journals, batch planning, relation traversal, derived tables,
access contracts, and structural state inspection.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from skeleton.simulation.ecs.access import AccessAnalyzer, AccessKey, AccessMode
from skeleton.simulation.ecs.batch import (
    BatchOperation,
    BatchOperationKind,
    BatchPlanner,
)
from skeleton.simulation.ecs.canonical import digest
from skeleton.simulation.ecs.errors import (
    BoundsError,
    CommandError,
    QueryError,
    ScheduleError,
    ValidationError,
)
from skeleton.simulation.ecs.inspection import ChangeKind, diff_state, inspect_entity, inspect_store
from skeleton.simulation.ecs.journal import GENESIS_DIGEST, JournalKind, MutationJournal
from skeleton.simulation.ecs.relations import RelationGraph, RelationKey
from skeleton.simulation.ecs.schedule import SystemGraph, SystemPhase, SystemSpec
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec, SchemaRegistry, make_schema
from skeleton.simulation.ecs.store import EntityStore
from skeleton.simulation.ecs.tables import ComponentTable, TableRegistry


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
    registry.register(
        make_schema(
            "name",
            1,
            (FieldSpec("value", FieldKind.TEXT),),
        )
    )
    return registry


def _store() -> EntityStore:
    store = EntityStore(_registry())
    for entity_id in ("entity:a", "entity:b", "entity:c", "entity:d"):
        store.create_entity(entity_id)
    store.set_component("entity:a", "position", {"x": 1, "y": 2})
    store.set_component("entity:a", "health", {"current": 90, "maximum": 100})
    store.set_component("entity:b", "position", {"x": 3, "y": 4, "zone": "cave"})
    store.set_component("entity:b", "health", {"current": 50, "maximum": 80})
    store.set_component("entity:c", "name", {"value": "charlie"})
    store.set_resource("weather", {"kind": "rain"})
    return store


def _set_component_operation(
    operation_id: str,
    entity_id: str,
    schema_id: str,
    data: dict,
    *,
    depends_on: tuple[str, ...] = (),
) -> BatchOperation:
    return BatchOperation(
        operation_id,
        BatchOperationKind.SET_COMPONENT,
        {"entity_id": entity_id, "schema_id": schema_id, "data": data},
        depends_on,
    )


def test_empty_journal_has_genesis_head() -> None:
    journal = MutationJournal()
    assert len(journal) == 0
    assert journal.next_sequence == 0
    assert journal.head_digest == GENESIS_DIGEST
    assert journal.verify().valid


def test_journal_append_assigns_monotonic_sequence() -> None:
    journal = MutationJournal()
    first = journal.mutation("create", "entity:a", {"x": 1}, tick=0, source="test")
    second = journal.event("spawned", {"entity": "entity:a"}, tick=1, source="test")
    assert first.sequence == 0
    assert second.sequence == 1
    assert second.previous_digest == first.entry_digest
    assert journal.next_sequence == 2


def test_journal_payload_is_deep_copied() -> None:
    journal = MutationJournal()
    payload = {"nested": {"value": 1}}
    entry = journal.mutation("set", "entity:a", payload, tick=0)
    payload["nested"]["value"] = 999
    assert entry.payload == {"nested": {"value": 1}}
    assert journal.verify().valid


def test_journal_payload_digest_matches_frozen_payload() -> None:
    journal = MutationJournal()
    entry = journal.mutation("set", "entity:a", {"a": [1, 2]}, tick=0)
    assert entry.payload_digest == digest({"a": [1, 2]})


def test_journal_head_changes_after_append() -> None:
    journal = MutationJournal()
    before = journal.head_digest
    journal.mutation("set", "entity:a", {"a": 1}, tick=0)
    assert journal.head_digest != before


def test_identical_journal_history_has_identical_head() -> None:
    left = MutationJournal()
    right = MutationJournal()
    for journal in (left, right):
        journal.mutation("set", "entity:a", {"x": 1}, tick=0, source="system")
        journal.event("changed", {"x": 1}, tick=1, source="system")
        journal.checkpoint("stable", "a" * 64, tick=1, source="system")
    assert left.head_digest == right.head_digest
    assert left.snapshot() == right.snapshot()


def test_journal_source_changes_chain_digest() -> None:
    left = MutationJournal()
    right = MutationJournal()
    left.mutation("set", "entity:a", {"x": 1}, tick=0, source="left")
    right.mutation("set", "entity:a", {"x": 1}, tick=0, source="right")
    assert left.head_digest != right.head_digest


def test_journal_tick_changes_chain_digest() -> None:
    left = MutationJournal()
    right = MutationJournal()
    left.mutation("set", "entity:a", {"x": 1}, tick=0)
    right.mutation("set", "entity:a", {"x": 1}, tick=1)
    assert left.head_digest != right.head_digest


def test_journal_find_filters_kind_subject_and_source() -> None:
    journal = MutationJournal()
    journal.mutation("set", "entity:a", {"x": 1}, tick=0, source="alpha")
    journal.mutation("set", "entity:b", {"x": 2}, tick=1, source="beta")
    journal.event("ping", {}, tick=1, source="alpha")
    assert len(journal.find(kind=JournalKind.MUTATION)) == 2
    assert len(journal.find(subject="entity:a")) == 1
    assert len(journal.find(source="alpha")) == 2
    assert len(journal.find(operation="set", from_tick=1)) == 1


def test_journal_slice_preserves_chain_boundary() -> None:
    journal = MutationJournal()
    rows = [
        journal.mutation("set", f"entity:{index}", {"x": index}, tick=index)
        for index in range(5)
    ]
    part = journal.slice(1, 4)
    assert part.count == 3
    assert part.first_previous_digest == rows[0].entry_digest
    assert part.final_digest == rows[3].entry_digest


def test_journal_empty_slice_is_well_formed() -> None:
    journal = MutationJournal()
    journal.mutation("set", "entity:a", {}, tick=0)
    part = journal.slice(1, 1)
    assert part.count == 0
    assert part.start_sequence == 1
    assert part.end_sequence == 0


def test_journal_restore_round_trip() -> None:
    journal = MutationJournal(capacity=16)
    journal.mutation("set", "entity:a", {"x": 1}, tick=0)
    journal.event("changed", {"x": 1}, tick=1)
    restored = MutationJournal.restore(journal.snapshot())
    assert restored.snapshot() == journal.snapshot()
    assert restored.verify().valid


def test_journal_restore_rejects_wrong_schema() -> None:
    record = MutationJournal().snapshot()
    record["schema"] = "wrong"
    with pytest.raises(ValidationError):
        MutationJournal.restore(record)


def test_journal_restore_rejects_tampered_head() -> None:
    journal = MutationJournal()
    journal.mutation("set", "entity:a", {}, tick=0)
    record = journal.snapshot()
    record["head_digest"] = "f" * 64
    with pytest.raises(ValidationError):
        MutationJournal.restore(record)


def test_journal_capacity_is_enforced() -> None:
    journal = MutationJournal(capacity=1)
    journal.mutation("set", "entity:a", {}, tick=0)
    with pytest.raises(BoundsError):
        journal.mutation("set", "entity:b", {}, tick=0)


@pytest.mark.parametrize("capacity", [0, -1, True, 100_001])
def test_invalid_journal_capacity_fails_closed(capacity) -> None:
    with pytest.raises(ValidationError):
        MutationJournal(capacity=capacity)


def test_batch_plan_orders_dependencies() -> None:
    create = BatchOperation(
        "create",
        BatchOperationKind.CREATE_ENTITY,
        {"entity_id": "entity:new"},
    )
    set_name = _set_component_operation(
        "name",
        "entity:new",
        "name",
        {"value": "new"},
        depends_on=("create",),
    )
    plan = BatchPlanner((set_name, create)).plan()
    assert [row.operation_id for row in plan.ordered_operations] == ["create", "name"]


def test_batch_plan_is_stable_across_input_order() -> None:
    first = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 1})
    second = BatchOperation("b", BatchOperationKind.SET_RESOURCE, {"resource_id": "b", "value": 2})
    left = BatchPlanner((first, second)).plan()
    right = BatchPlanner((second, first)).plan()
    assert left.plan_digest == right.plan_digest
    assert left.ordered_operations == right.ordered_operations


def test_batch_duplicate_identical_operation_is_idempotent() -> None:
    operation = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 1})
    planner = BatchPlanner()
    assert planner.add(operation) is operation
    assert planner.add(operation) is operation
    assert planner.operation_ids() == ("a",)


def test_batch_duplicate_different_operation_fails() -> None:
    planner = BatchPlanner()
    planner.add(BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 1}))
    with pytest.raises(ValidationError):
        planner.add(BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 2}))


def test_batch_missing_dependency_fails() -> None:
    operation = BatchOperation(
        "a",
        BatchOperationKind.SET_RESOURCE,
        {"resource_id": "a", "value": 1},
        ("missing",),
    )
    with pytest.raises(ValidationError):
        BatchPlanner((operation,)).plan()


def test_batch_dependency_cycle_fails() -> None:
    a = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 1}, ("b",))
    b = BatchOperation("b", BatchOperationKind.SET_RESOURCE, {"resource_id": "b", "value": 2}, ("a",))
    with pytest.raises(ValidationError):
        BatchPlanner((a, b)).plan()


def test_batch_detects_unordered_same_resource_mutations() -> None:
    a = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": 1})
    b = BatchOperation("b", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": 2})
    plan = BatchPlanner((a, b)).plan()
    assert not plan.executable
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].subject == "resource:weather"


def test_batch_allows_explicitly_ordered_same_resource_mutations() -> None:
    a = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": 1})
    b = BatchOperation(
        "b",
        BatchOperationKind.SET_RESOURCE,
        {"resource_id": "weather", "value": 2},
        ("a",),
    )
    plan = BatchPlanner((b, a)).plan()
    assert plan.executable
    assert not plan.conflicts


def test_batch_detects_same_component_mutation_conflict() -> None:
    a = _set_component_operation("a", "entity:a", "name", {"value": "one"})
    b = _set_component_operation("b", "entity:a", "name", {"value": "two"})
    plan = BatchPlanner((a, b)).plan()
    assert not plan.executable
    assert "component:entity:a::name" == plan.conflicts[0].subject


def test_batch_dry_run_does_not_mutate_store() -> None:
    store = _store()
    before = store.state_digest
    op = BatchOperation("weather", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": {"kind": "sun"}})
    result = BatchPlanner((op,)).dry_run(store)
    assert store.state_digest == before
    assert result.before_digest == before
    assert result.after_digest != before
    assert result.changed


def test_batch_preview_and_commit_have_same_result_digest() -> None:
    store = _store()
    op = BatchOperation("weather", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": {"kind": "sun"}})
    planner = BatchPlanner((op,))
    preview = planner.dry_run(store)
    planner.commit(store)
    assert store.state_digest == preview.after_digest


def test_non_executable_batch_commit_fails_without_mutation() -> None:
    store = _store()
    before = store.state_digest
    a = BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": 1})
    b = BatchOperation("b", BatchOperationKind.SET_RESOURCE, {"resource_id": "weather", "value": 2})
    with pytest.raises(CommandError):
        BatchPlanner((a, b)).commit(store)
    assert store.state_digest == before


def test_batch_create_then_set_component_is_atomic() -> None:
    store = _store()
    create = BatchOperation("create", BatchOperationKind.CREATE_ENTITY, {"entity_id": "entity:new"})
    name = _set_component_operation("name", "entity:new", "name", {"value": "neo"}, depends_on=("create",))
    result = BatchPlanner((name, create)).commit(store)
    assert result.receipt.after_digest == store.state_digest
    assert store.get_component("entity:new", "name").data["value"] == "neo"


def test_relation_tags_are_sorted_and_idempotent() -> None:
    store = _store()
    graph = RelationGraph(store)
    assert graph.add_tag("entity:a", "player")
    assert graph.add_tag("entity:a", "alive")
    assert not graph.add_tag("entity:a", "player")
    assert graph.tags("entity:a") == ("alive", "player")


def test_relation_remove_missing_tag_is_false() -> None:
    graph = RelationGraph(_store())
    assert not graph.remove_tag("entity:a", "missing")


def test_relation_entities_with_tag_are_sorted() -> None:
    graph = RelationGraph(_store())
    graph.add_tag("entity:c", "enemy")
    graph.add_tag("entity:a", "enemy")
    assert graph.entities_with_tag("enemy") == ("entity:a", "entity:c")


def test_relation_set_and_lookup() -> None:
    graph = RelationGraph(_store())
    relation = graph.set_relation("parent", "entity:a", "entity:b", {"weight": 1})
    assert relation.key == RelationKey("parent", "entity:a", "entity:b")
    assert graph.get_relation("parent", "entity:a", "entity:b") == relation


def test_relation_update_preserves_created_revision() -> None:
    graph = RelationGraph(_store())
    first = graph.set_relation("link", "entity:a", "entity:b", {"value": 1})
    second = graph.set_relation("link", "entity:a", "entity:b", {"value": 2})
    assert second.created_revision == first.created_revision
    assert second.updated_revision > first.updated_revision


def test_relation_outgoing_and_incoming_are_sorted() -> None:
    graph = RelationGraph(_store())
    graph.set_relation("link", "entity:a", "entity:c")
    graph.set_relation("link", "entity:a", "entity:b")
    graph.set_relation("link", "entity:d", "entity:b")
    assert [row.key.target for row in graph.outgoing("entity:a")] == ["entity:b", "entity:c"]
    assert [row.key.source for row in graph.incoming("entity:b")] == ["entity:a", "entity:d"]


def test_relation_neighbors_support_direction() -> None:
    graph = RelationGraph(_store())
    graph.set_relation("link", "entity:a", "entity:b")
    graph.set_relation("link", "entity:c", "entity:a")
    assert graph.neighbors("entity:a", direction="out") == ("entity:b",)
    assert graph.neighbors("entity:a", direction="in") == ("entity:c",)
    assert graph.neighbors("entity:a", direction="both") == ("entity:b", "entity:c")


def test_relation_invalid_direction_fails() -> None:
    graph = RelationGraph(_store())
    with pytest.raises(ValidationError):
        graph.neighbors("entity:a", direction="sideways")


def test_relation_roots_find_nodes_without_incoming_edges() -> None:
    graph = RelationGraph(_store())
    graph.set_relation("tree", "entity:a", "entity:b")
    graph.set_relation("tree", "entity:b", "entity:c")
    assert graph.roots("tree") == ("entity:a", "entity:d")


def test_relation_descendants_walk_transitively() -> None:
    graph = RelationGraph(_store())
    graph.set_relation("tree", "entity:a", "entity:b")
    graph.set_relation("tree", "entity:b", "entity:c")
    graph.set_relation("tree", "entity:c", "entity:d")
    assert graph.descendants("entity:a", "tree") == ("entity:b", "entity:c", "entity:d")


def test_relation_descendants_detect_cycle_to_origin() -> None:
    graph = RelationGraph(_store())
    graph.set_relation("tree", "entity:a", "entity:b")
    graph.set_relation("tree", "entity:b", "entity:a")
    with pytest.raises(ValidationError):
        graph.descendants("entity:a", "tree")


def test_relation_purge_missing_entities_removes_stale_edges_and_tags() -> None:
    store = _store()
    graph = RelationGraph(store)
    graph.add_tag("entity:a", "player")
    graph.set_relation("link", "entity:a", "entity:b")
    store.delete_entity("entity:b")
    removed = graph.purge_missing_entities()
    assert removed == (RelationKey("link", "entity:a", "entity:b"),)
    assert graph.relation_count == 0


def test_relation_snapshot_is_deterministic() -> None:
    left = RelationGraph(_store())
    right = RelationGraph(_store())
    for graph in (left, right):
        graph.add_tag("entity:a", "player")
        graph.set_relation("link", "entity:a", "entity:b", {"weight": 2})
    assert left.snapshot() == right.snapshot()


def test_component_table_rows_are_sorted() -> None:
    store = _store()
    table = ComponentTable(store, "position")
    assert table.entity_ids(store) == ("entity:a", "entity:b")
    assert [row.entity_id for row in table.rows(store)] == ["entity:a", "entity:b"]


def test_component_table_values_are_copies() -> None:
    store = _store()
    table = ComponentTable(store, "position")
    values = table.values(store)
    values[0]["x"] = 999
    assert store.get_component("entity:a", "position").data["x"] == 1.0


def test_component_table_field_projection() -> None:
    store = _store()
    table = ComponentTable(store, "position")
    assert table.field(store, "zone") == (("entity:a", "world"), ("entity:b", "cave"))


def test_component_table_detects_stale_store() -> None:
    store = _store()
    table = ComponentTable(store, "position")
    store.patch_component("entity:a", "position", {"x": 10})
    with pytest.raises(QueryError):
        table.rows(store)


def test_component_table_refresh_accepts_new_state() -> None:
    store = _store()
    table = ComponentTable(store, "position")
    store.patch_component("entity:a", "position", {"x": 10})
    table.refresh(store)
    assert table.field(store, "x")[0] == ("entity:a", 10.0)


def test_table_registry_refreshes_stale_table_on_get() -> None:
    store = _store()
    registry = TableRegistry(store)
    first = registry.get("position")
    store.patch_component("entity:a", "position", {"x": 10})
    second = registry.get("position")
    assert first is second
    assert second.is_current(store)


def test_table_registry_fingerprint_changes_with_store() -> None:
    store = _store()
    registry = TableRegistry(store)
    registry.get("position")
    before = registry.fingerprint
    store.patch_component("entity:a", "position", {"x": 10})
    registry.refresh_all()
    assert registry.fingerprint != before


def test_access_key_round_trip() -> None:
    key = AccessKey.parse("component:position")
    assert key.namespace == "component"
    assert key.name == "position"
    assert key.token == "component:position"


def test_access_key_without_namespace_fails() -> None:
    with pytest.raises(ValidationError):
        AccessKey.parse("position")


def test_access_analyzer_detects_write_write_conflict() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", writes=("component:position",)))
    graph.register(SystemSpec("b", writes=("component:position",)))
    report = AccessAnalyzer(graph).report()
    assert not report.conflict_free
    assert report.conflicts[0].first_mode is AccessMode.WRITE
    assert report.conflicts[0].second_mode is AccessMode.WRITE


def test_access_analyzer_detects_write_read_conflict() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", writes=("component:position",)))
    graph.register(SystemSpec("b", reads=("component:position",)))
    report = AccessAnalyzer(graph).report()
    assert len(report.conflicts) == 1


def test_access_analyzer_does_not_flag_read_read() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", reads=("component:position",)))
    graph.register(SystemSpec("b", reads=("component:position",)))
    assert AccessAnalyzer(graph).report().conflict_free


def test_access_report_is_deterministic() -> None:
    left = SystemGraph()
    right = SystemGraph()
    specs = (
        SystemSpec("a", reads=("component:health",), writes=("component:position",)),
        SystemSpec("b", reads=("component:position",)),
    )
    for spec in specs:
        left.register(spec)
    for spec in reversed(specs):
        right.register(spec)
    assert AccessAnalyzer(left).report().report_digest == AccessAnalyzer(right).report().report_digest


def test_access_validate_plan_accepts_scheduler_conflict_separation() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", writes=("component:position",)))
    graph.register(SystemSpec("b", reads=("component:position",)))
    plan = graph.plan()
    AccessAnalyzer(graph).validate_plan(plan)
    assert len(plan.batches) >= 2


def test_inspect_entity_copies_components() -> None:
    store = _store()
    row = inspect_entity(store, "entity:a")
    row.components["position"]["x"] = 999
    assert store.get_component("entity:a", "position").data["x"] == 1.0


def test_inspect_entity_digest_is_stable() -> None:
    store = _store()
    assert inspect_entity(store, "entity:a").entity_digest == inspect_entity(store, "entity:a").entity_digest


def test_inspect_store_lists_sorted_ids() -> None:
    store = _store()
    row = inspect_store(store)
    assert row.entity_ids == tuple(sorted(row.entity_ids))
    assert row.resource_ids == ("weather",)
    assert row.state_digest == store.state_digest


def test_state_diff_detects_component_change() -> None:
    before = _store()
    after = before.clone()
    after.patch_component("entity:a", "health", {"current": 10})
    delta = diff_state(before, after)
    assert delta.changed
    assert delta.changed_entities == ("entity:a",)
    entity = delta.entities[0]
    assert entity.kind is ChangeKind.CHANGED
    assert entity.component_changes[0].schema_id == "health"


def test_state_diff_detects_entity_addition() -> None:
    before = _store()
    after = before.clone()
    after.create_entity("entity:new")
    delta = diff_state(before, after)
    assert delta.entities[0].entity_id == "entity:new"
    assert delta.entities[0].kind is ChangeKind.ADDED


def test_state_diff_detects_entity_removal() -> None:
    before = _store()
    after = before.clone()
    after.delete_entity("entity:c")
    delta = diff_state(before, after)
    rows = {row.entity_id: row for row in delta.entities}
    assert rows["entity:c"].kind is ChangeKind.REMOVED


def test_state_diff_detects_resource_change() -> None:
    before = _store()
    after = before.clone()
    after.set_resource("weather", {"kind": "sun"})
    delta = diff_state(before, after)
    assert len(delta.resources) == 1
    assert delta.resources[0].kind is ChangeKind.CHANGED


def test_state_diff_omits_unchanged_by_default() -> None:
    store = _store()
    delta = diff_state(store, store.clone())
    assert not delta.changed
    assert delta.entities == ()
    assert delta.resources == ()


def test_state_diff_can_include_unchanged() -> None:
    store = _store()
    delta = diff_state(store, store.clone(), include_unchanged=True)
    assert len(delta.entities) == store.entity_count
    assert all(row.kind is ChangeKind.UNCHANGED for row in delta.entities)


def test_state_diff_digest_is_deterministic() -> None:
    left_before = _store()
    left_after = left_before.clone()
    left_after.patch_component("entity:a", "health", {"current": 1})
    right_before = _store()
    right_after = right_before.clone()
    right_after.patch_component("entity:a", "health", {"current": 1})
    assert diff_state(left_before, left_after).diff_digest == diff_state(right_before, right_after).diff_digest


def test_batch_relation_table_and_inspection_can_share_same_store() -> None:
    store = _store()
    relations = RelationGraph(store)
    tables = TableRegistry(store)
    tables.get("health")
    before = copy.deepcopy(inspect_store(store))
    planner = BatchPlanner(
        (
            BatchOperation(
                "weather",
                BatchOperationKind.SET_RESOURCE,
                {"resource_id": "weather", "value": {"kind": "sun"}},
            ),
        )
    )
    planner.commit(store)
    relations.add_tag("entity:a", "player")
    tables.refresh_all()
    after = inspect_store(store)
    assert after.state_digest != before.state_digest
    assert relations.tags("entity:a") == ("player",)
    assert tables.get("health").is_current(store)
