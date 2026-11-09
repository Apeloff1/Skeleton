"""World-session, partition, and diagnostics regression contracts."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.ecs.batch import BatchOperation, BatchOperationKind
from skeleton.simulation.ecs.diagnostics import DiagnosticSeverity, diagnose
from skeleton.simulation.ecs.errors import BoundsError, SnapshotError, ValidationError
from skeleton.simulation.ecs.journal import MutationJournal
from skeleton.simulation.ecs.partitions import PartitionPolicy, WorldPartitionIndex
from skeleton.simulation.ecs.schedule import SystemGraph, SystemSpec
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec, SchemaRegistry, make_schema
from skeleton.simulation.ecs.store import EntityStore
from skeleton.simulation.ecs.tables import TableRegistry
from skeleton.simulation.ecs.world import ChangeSet, WorldPolicy, WorldSession, make_changeset


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
    return registry


def _store() -> EntityStore:
    store = EntityStore(_registry())
    for entity_id in ("entity:a", "entity:b", "entity:c"):
        store.create_entity(entity_id)
    store.set_component("entity:a", "position", {"x": 0, "y": 0})
    store.set_component("entity:b", "position", {"x": 10, "y": 20, "zone": "north"})
    store.set_component("entity:a", "health", {"current": 100, "maximum": 100})
    return store


def _weather_change(store: EntityStore, value: str = "rain") -> ChangeSet:
    return make_changeset(
        "weather-change",
        (
            BatchOperation(
                "weather",
                BatchOperationKind.SET_RESOURCE,
                {"resource_id": "weather", "value": {"kind": value}},
            ),
        ),
        expected_base_digest=store.state_digest,
    )


def test_world_policy_fingerprint_is_deterministic() -> None:
    assert WorldPolicy().fingerprint == WorldPolicy().fingerprint


@pytest.mark.parametrize(
    "kwargs",
    [
        {"checkpoint_capacity": 0},
        {"checkpoint_capacity": True},
        {"journal_capacity": 0},
        {"max_changeset_operations": 0},
    ],
)
def test_world_policy_invalid_bounds_fail(kwargs) -> None:
    with pytest.raises(ValidationError):
        WorldPolicy(**kwargs)


def test_world_session_status_reflects_store() -> None:
    store = _store()
    session = WorldSession("main", store)
    status = session.status()
    assert status.name == "main"
    assert status.entities == 3
    assert status.components == 3
    assert status.state_digest == store.state_digest


def test_world_checkpoint_records_exact_state() -> None:
    session = WorldSession("main", _store())
    checkpoint = session.checkpoint("before-edit", reason="test")
    assert checkpoint.state_digest == session.store.state_digest
    assert checkpoint.revision == session.store.revision
    assert checkpoint.tick == session.store.tick


def test_world_checkpoint_adds_journal_evidence() -> None:
    session = WorldSession("main", _store())
    session.checkpoint("before-edit")
    rows = session.journal.find(operation="world_checkpoint")
    assert len(rows) == 1
    assert rows[0].subject == "before-edit"


def test_world_checkpoint_same_name_replaces_value_without_duplicate_order_entry() -> None:
    session = WorldSession("main", _store())
    first = session.checkpoint("save")
    session.store.set_resource("x", 1)
    second = session.checkpoint("save")
    assert first.state_digest != second.state_digest
    assert session.checkpoint_names() == ("save",)


def test_world_checkpoint_capacity_evicts_oldest_name() -> None:
    session = WorldSession("main", _store(), policy=WorldPolicy(checkpoint_capacity=2))
    session.checkpoint("a")
    session.checkpoint("b")
    session.checkpoint("c")
    assert session.checkpoint_names() == ("b", "c")
    with pytest.raises(SnapshotError):
        session.get_checkpoint("a")


def test_world_restore_returns_exact_checkpoint_state() -> None:
    session = WorldSession("main", _store())
    checkpoint = session.checkpoint("base")
    session.store.set_resource("weather", "rain")
    assert session.store.state_digest != checkpoint.state_digest
    session.restore("base")
    assert session.store.state_digest == checkpoint.state_digest


def test_world_restore_logs_evidence() -> None:
    session = WorldSession("main", _store())
    session.checkpoint("base")
    session.store.set_resource("x", 1)
    session.restore("base")
    rows = session.journal.find(operation="restore_checkpoint")
    assert len(rows) == 1
    assert rows[0].payload["after_digest"] == session.store.state_digest


def test_world_restore_current_digest_precondition() -> None:
    session = WorldSession("main", _store())
    session.checkpoint("base")
    session.store.set_resource("x", 1)
    with pytest.raises(SnapshotError):
        session.restore("base", require_current_digest="f" * 64)


def test_changeset_fingerprint_is_stable() -> None:
    store = _store()
    left = _weather_change(store)
    right = _weather_change(store)
    assert left.fingerprint == right.fingerprint


def test_changeset_duplicate_operation_ids_fail() -> None:
    operation = BatchOperation(
        "duplicate",
        BatchOperationKind.SET_RESOURCE,
        {"resource_id": "x", "value": 1},
    )
    with pytest.raises(ValidationError):
        ChangeSet("change", (operation, operation))


def test_world_preview_does_not_mutate_authoritative_store() -> None:
    store = _store()
    session = WorldSession("main", store)
    before = store.state_digest
    preview = session.preview(_weather_change(store))
    assert store.state_digest == before
    assert preview.changed
    assert preview.base_digest == before


def test_world_preview_state_diff_describes_change() -> None:
    store = _store()
    session = WorldSession("main", store)
    preview = session.preview(_weather_change(store))
    assert len(preview.state_diff.resources) == 1
    assert preview.state_diff.resources[0].resource_id == "weather"


def test_world_apply_matches_preview_result() -> None:
    store = _store()
    session = WorldSession("main", store)
    change = _weather_change(store)
    preview = session.preview(change)
    receipt = session.apply(change)
    assert receipt.after_digest == preview.result_digest
    assert store.state_digest == preview.result_digest


def test_world_apply_records_changeset_journal_entry() -> None:
    store = _store()
    session = WorldSession("main", store)
    change = _weather_change(store)
    receipt = session.apply(change)
    rows = session.journal.find(operation="apply_changeset", subject=change.change_id)
    assert len(rows) == 1
    assert rows[0].sequence == receipt.journal_sequence


def test_world_apply_rejects_stale_expected_base() -> None:
    store = _store()
    change = _weather_change(store)
    session = WorldSession("main", store)
    store.set_resource("unrelated", 1)
    with pytest.raises(ValidationError):
        session.apply(change)


def test_world_policy_limits_changeset_operations() -> None:
    store = _store()
    session = WorldSession("main", store, policy=WorldPolicy(max_changeset_operations=1))
    operations = (
        BatchOperation("a", BatchOperationKind.SET_RESOURCE, {"resource_id": "a", "value": 1}),
        BatchOperation("b", BatchOperationKind.SET_RESOURCE, {"resource_id": "b", "value": 2}),
    )
    change = make_changeset("too-large", operations)
    with pytest.raises(BoundsError):
        session.preview(change)


def test_world_fork_clones_store_state() -> None:
    session = WorldSession("main", _store())
    fork = session.fork("experiment")
    assert fork.parent_digest == session.store.state_digest
    assert fork.session.store.state_digest == session.store.state_digest


def test_world_fork_isolated_from_parent_mutation() -> None:
    session = WorldSession("main", _store())
    fork = session.fork("experiment")
    fork.session.store.set_resource("fork-only", 1)
    assert "fork-only" not in session.store.resource_ids()
    assert fork.session.store.state_digest != session.store.state_digest


def test_world_fork_parent_mutation_isolated_from_child() -> None:
    session = WorldSession("main", _store())
    fork = session.fork("experiment")
    child_before = fork.session.store.state_digest
    session.store.set_resource("parent-only", 1)
    assert fork.session.store.state_digest == child_before


def test_world_diff_checkpoint_detects_edits() -> None:
    session = WorldSession("main", _store())
    session.checkpoint("base")
    session.store.patch_component("entity:a", "health", {"current": 10})
    delta = session.diff_checkpoint("base")
    assert delta.changed
    assert delta.changed_entities == ("entity:a",)


def test_partition_policy_fingerprint_is_stable() -> None:
    assert PartitionPolicy().fingerprint == PartitionPolicy().fingerprint


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_partitions": 0},
        {"max_partitions": True},
        {"max_entities_per_partition": 0},
    ],
)
def test_partition_policy_invalid_bounds_fail(kwargs) -> None:
    with pytest.raises(ValidationError):
        PartitionPolicy(**kwargs)


def test_partition_assign_and_lookup() -> None:
    store = _store()
    index = WorldPartitionIndex(store)
    move = index.assign("entity:a", "region:north")
    assert move.from_partition is None
    assert move.to_partition == "region:north"
    assert index.partition_of("entity:a") == "region:north"
    assert index.entities("region:north") == ("entity:a",)


def test_partition_reassignment_removes_old_membership() -> None:
    store = _store()
    index = WorldPartitionIndex(store)
    index.assign("entity:a", "region:north")
    index.assign("entity:a", "region:south")
    assert index.entities("region:north") == ()
    assert index.entities("region:south") == ("entity:a",)


def test_partition_assign_many_is_sorted_and_atomic() -> None:
    store = _store()
    index = WorldPartitionIndex(store)
    moves = index.assign_many("region:north", ("entity:c", "entity:a", "entity:b"))
    assert tuple(row.entity_id for row in moves) == ("entity:a", "entity:b", "entity:c")
    assert index.entities("region:north") == ("entity:a", "entity:b", "entity:c")


def test_partition_assign_missing_entity_fails() -> None:
    index = WorldPartitionIndex(_store())
    with pytest.raises(Exception):
        index.assign("entity:missing", "region:north")


def test_partition_unassigned_lists_live_entities() -> None:
    index = WorldPartitionIndex(_store())
    index.assign("entity:a", "region:north")
    assert index.unassigned() == ("entity:b", "entity:c")


def test_partition_require_complete_respects_policy() -> None:
    index = WorldPartitionIndex(_store(), policy=PartitionPolicy(allow_unassigned=False))
    with pytest.raises(ValidationError):
        index.require_complete()


def test_partition_complete_assignment_passes_strict_policy() -> None:
    store = _store()
    index = WorldPartitionIndex(store, policy=PartitionPolicy(allow_unassigned=False))
    for entity_id in store.entity_ids():
        index.assign(entity_id, "region:all")
    index.require_complete()
    assert index.unassigned() == ()


def test_partition_snapshot_is_deterministic() -> None:
    left = WorldPartitionIndex(_store())
    right = WorldPartitionIndex(_store())
    for index in (left, right):
        index.assign("entity:a", "region:north")
        index.assign("entity:b", "region:south")
    assert left.snapshot() == right.snapshot()


def test_partition_plan_describes_required_moves() -> None:
    index = WorldPartitionIndex(_store())
    index.assign("entity:a", "region:north")
    plan = index.plan_to({"entity:a": "region:south", "entity:b": "region:north"})
    assert plan.changed
    moves = {row.entity_id: row for row in plan.moves}
    assert moves["entity:a"].from_partition == "region:north"
    assert moves["entity:a"].to_partition == "region:south"
    assert moves["entity:b"].to_partition == "region:north"


def test_partition_apply_plan_reaches_target_assignments() -> None:
    index = WorldPartitionIndex(_store())
    plan = index.plan_to({"entity:a": "region:a", "entity:b": "region:b", "entity:c": "region:c"})
    index.apply_plan(plan)
    assert index.partition_of("entity:a") == "region:a"
    assert index.partition_of("entity:b") == "region:b"
    assert index.partition_of("entity:c") == "region:c"


def test_partition_apply_plan_rejects_stale_source() -> None:
    index = WorldPartitionIndex(_store())
    plan = index.plan_to({"entity:a": "region:a"})
    index.assign("entity:b", "region:b")
    with pytest.raises(ValidationError):
        index.apply_plan(plan)


def test_partition_refresh_purges_deleted_entities() -> None:
    store = _store()
    index = WorldPartitionIndex(store)
    index.assign("entity:a", "region:a")
    store.delete_entity("entity:a")
    removed = index.refresh_store_marker()
    assert removed == ("entity:a",)
    assert index.partition_of("entity:a") is None


def test_partition_assert_invariants_accepts_valid_index() -> None:
    store = _store()
    index = WorldPartitionIndex(store)
    index.assign("entity:a", "region:a")
    index.assign("entity:b", "region:b")
    index.assert_invariants()


def test_diagnostics_report_is_read_only() -> None:
    store = _store()
    before = store.state_digest
    report = diagnose(store)
    assert store.state_digest == before
    assert report.state_digest == before


def test_diagnostics_healthy_store_has_no_errors() -> None:
    report = diagnose(_store())
    assert report.ok
    assert report.summary.errors == 0


def test_diagnostics_includes_store_invariant_finding() -> None:
    report = diagnose(_store())
    assert report.by_code("STORE.INVARIANT_OK")


def test_diagnostics_reports_unused_schema_as_info() -> None:
    store = _store()
    store.registry.register(make_schema("unused", 1, (FieldSpec("x", FieldKind.INT),)))
    report = diagnose(store)
    rows = report.by_code("SCHEMA.UNUSED")
    assert rows
    assert rows[0].severity is DiagnosticSeverity.INFO


def test_diagnostics_validates_journal_chain() -> None:
    store = _store()
    journal = MutationJournal()
    journal.mutation("set", "entity:a", {"x": 1}, tick=0)
    report = diagnose(store, journal=journal)
    assert report.by_code("JOURNAL.VALID")


def test_diagnostics_reports_partition_unassigned_warning() -> None:
    store = _store()
    partitions = WorldPartitionIndex(store)
    partitions.assign("entity:a", "region:a")
    report = diagnose(store, partitions=partitions)
    rows = report.by_code("PARTITION.UNASSIGNED")
    assert rows
    assert rows[0].severity is DiagnosticSeverity.WARNING


def test_diagnostics_partition_complete_has_no_unassigned_warning() -> None:
    store = _store()
    partitions = WorldPartitionIndex(store)
    for entity_id in store.entity_ids():
        partitions.assign(entity_id, "region:all")
    report = diagnose(store, partitions=partitions)
    assert not report.by_code("PARTITION.UNASSIGNED")


def test_diagnostics_reports_current_tables() -> None:
    store = _store()
    tables = TableRegistry(store)
    tables.get("position")
    report = diagnose(store, tables=tables)
    assert report.by_code("TABLE.CURRENT")


def test_diagnostics_reports_stale_tables() -> None:
    store = _store()
    tables = TableRegistry(store)
    tables.get("position")
    store.patch_component("entity:a", "position", {"x": 5})
    report = diagnose(store, tables=tables)
    assert report.by_code("TABLE.STALE")


def test_diagnostics_reports_schedule_plan() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", reads=("component:position",)))
    report = diagnose(_store(), graph=graph)
    assert report.by_code("SCHEDULE.PLAN")


def test_diagnostics_report_digest_is_deterministic() -> None:
    left = diagnose(_store())
    right = diagnose(_store())
    assert left.report_digest == right.report_digest


def test_diagnostics_at_least_filters_severity() -> None:
    store = _store()
    partitions = WorldPartitionIndex(store)
    report = diagnose(store, partitions=partitions)
    warnings = report.at_least(DiagnosticSeverity.WARNING)
    assert all(row.severity >= DiagnosticSeverity.WARNING for row in warnings)


def test_world_partition_diagnostics_integration() -> None:
    session = WorldSession("main", _store())
    partitions = WorldPartitionIndex(session.store)
    for entity_id in session.store.entity_ids():
        partitions.assign(entity_id, "region:all")
    session.checkpoint("base")
    report = diagnose(session.store, journal=session.journal, partitions=partitions)
    assert report.ok
    assert report.by_code("JOURNAL.VALID")
    assert report.by_code("PARTITION.VALID")


def test_forked_world_can_have_independent_partition_plan() -> None:
    session = WorldSession("main", _store())
    fork = session.fork("branch")
    parent_index = WorldPartitionIndex(session.store)
    child_index = WorldPartitionIndex(fork.session.store)
    parent_index.assign("entity:a", "region:parent")
    child_index.assign("entity:a", "region:child")
    assert parent_index.partition_of("entity:a") == "region:parent"
    assert child_index.partition_of("entity:a") == "region:child"


def test_world_status_digest_changes_after_committed_change() -> None:
    session = WorldSession("main", _store())
    before = session.status().status_digest
    session.apply(_weather_change(session.store))
    after = session.status().status_digest
    assert before != after
