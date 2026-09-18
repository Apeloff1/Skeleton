"""Scheduler, command-buffer, clock, checkpoint and replay contracts."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.ecs.errors import (
    ClockError,
    CommandOverflowError,
    DeltaError,
    ReplayDivergenceError,
    ReplayError,
    ScheduleCycleError,
    ScheduleError,
    SystemConflictError,
    SystemNotFoundError,
    TransactionError,
)
from skeleton.simulation.ecs.execution import (
    CommandBuffer,
    CommandKind,
    EventQueue,
    SimulationClock,
    SnapshotHistory,
    apply_delta,
    capture_snapshot,
    diff_snapshots,
    restore_snapshot,
)
from skeleton.simulation.ecs.runtime import (
    ReplayRecorder,
    SimulationRuntime,
    capture_checkpoint,
    checkpoint_matches_runtime,
    replay,
    restore_checkpoint,
)
from skeleton.simulation.ecs.schedule import (
    SystemGraph,
    SystemPhase,
    SystemSpec,
    conflicts,
)
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec, SchemaRegistry, make_schema
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
            ),
        )
    )
    registry.register(
        make_schema(
            "velocity",
            1,
            (
                FieldSpec("x", FieldKind.FLOAT),
                FieldSpec("y", FieldKind.FLOAT),
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
    store.create_entity("entity:player")
    store.set_component("entity:player", "position", {"x": 0, "y": 0})
    store.set_component("entity:player", "velocity", {"x": 1, "y": 2})
    store.set_component("entity:player", "health", {"current": 100, "maximum": 100})
    return store


def _movement(ctx) -> None:
    position = ctx.store.get_component("entity:player", "position").data
    velocity = ctx.store.get_component("entity:player", "velocity").data
    ctx.commands.add(
        CommandKind.SET_COMPONENT,
        {
            "entity_id": "entity:player",
            "schema_id": "position",
            "data": {
                "x": position["x"] + velocity["x"],
                "y": position["y"] + velocity["y"],
            },
        },
        source=ctx.system.system_id,
    )


def _damage(ctx) -> None:
    health = ctx.store.get_component("entity:player", "health").data
    ctx.commands.add(
        CommandKind.PATCH_COMPONENT,
        {
            "entity_id": "entity:player",
            "schema_id": "health",
            "patch": {"current": max(0, health["current"] - 10)},
        },
        source=ctx.system.system_id,
    )
    ctx.emit("damage", {"amount": 10})


def _runtime() -> SimulationRuntime:
    runtime = SimulationRuntime(_store())
    runtime.register(
        SystemSpec(
            "movement",
            phase=SystemPhase.UPDATE,
            reads=("component:velocity",),
            writes=("component:position",),
        ),
        _movement,
    )
    runtime.register(
        SystemSpec(
            "damage",
            phase=SystemPhase.POST,
            reads=("component:health",),
            writes=("component:health",),
            after=("movement",),
        ),
        _damage,
    )
    return runtime


def test_system_spec_normalizes_access_sets() -> None:
    spec = SystemSpec(
        "system",
        reads=("component:b", "component:a", "component:a", "component:c"),
        writes=("component:c", "component:d", "component:d"),
    )
    assert spec.reads == ("component:a", "component:b")
    assert spec.writes == ("component:c", "component:d")


def test_system_conflicts_write_write() -> None:
    a = SystemSpec("a", writes=("component:position",))
    b = SystemSpec("b", writes=("component:position",))
    assert conflicts(a, b)


def test_system_conflicts_write_read() -> None:
    a = SystemSpec("a", writes=("component:position",))
    b = SystemSpec("b", reads=("component:position",))
    assert conflicts(a, b)


def test_system_read_read_does_not_conflict() -> None:
    a = SystemSpec("a", reads=("component:position",))
    b = SystemSpec("b", reads=("component:position",))
    assert not conflicts(a, b)


def test_system_graph_duplicate_identical_registration_is_idempotent() -> None:
    graph = SystemGraph()
    spec = SystemSpec("a")
    assert graph.register(spec) == spec
    assert graph.register(spec) == spec
    assert graph.system_ids() == ("a",)


def test_system_graph_duplicate_different_registration_fails() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", reads=("component:x",)))
    with pytest.raises(SystemConflictError):
        graph.register(SystemSpec("a", writes=("component:x",)))


def test_system_graph_get_missing_fails() -> None:
    with pytest.raises(SystemNotFoundError):
        SystemGraph().get("missing")


def test_system_graph_missing_after_dependency_fails() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", after=("missing",)))
    with pytest.raises(SystemNotFoundError):
        graph.plan()


def test_system_graph_missing_before_dependency_fails() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", before=("missing",)))
    with pytest.raises(SystemNotFoundError):
        graph.plan()


def test_system_graph_cycle_fails_closed() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", after=("b",)))
    graph.register(SystemSpec("b", after=("a",)))
    with pytest.raises(ScheduleCycleError):
        graph.plan()


def test_system_graph_phase_order_is_respected() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("post", phase=SystemPhase.POST))
    graph.register(SystemSpec("pre", phase=SystemPhase.PRE))
    graph.register(SystemSpec("update", phase=SystemPhase.UPDATE))
    plan = graph.plan()
    assert plan.ordered_system_ids == ("pre", "update", "post")


def test_system_graph_registration_order_does_not_change_plan() -> None:
    specs = (
        SystemSpec("a", phase=SystemPhase.PRE),
        SystemSpec("b", phase=SystemPhase.UPDATE, after=("a",)),
        SystemSpec("c", phase=SystemPhase.POST, after=("b",)),
    )
    left = SystemGraph()
    right = SystemGraph()
    for spec in specs:
        left.register(spec)
    for spec in reversed(specs):
        right.register(spec)
    assert left.plan() == right.plan()


def test_system_graph_conflicting_ready_systems_are_split_into_batches() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", writes=("component:position",)))
    graph.register(SystemSpec("b", reads=("component:position",)))
    plan = graph.plan()
    assert len(plan.batches) == 2
    assert plan.ordered_system_ids == ("a", "b")


def test_system_graph_nonconflicting_ready_systems_share_batch() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", writes=("component:position",)))
    graph.register(SystemSpec("b", writes=("component:health",)))
    plan = graph.plan()
    assert len(plan.batches) == 1
    assert plan.batches[0].system_ids == ("a", "b")


def test_disabled_system_is_not_executed_in_plan_order() -> None:
    graph = SystemGraph()
    graph.register(SystemSpec("a", enabled=False))
    graph.register(SystemSpec("b"))
    plan = graph.plan()
    assert "a" not in plan.ordered_system_ids
    assert "b" in plan.ordered_system_ids


def test_command_buffer_sequences_commands() -> None:
    buffer = CommandBuffer()
    first = buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "a", "value": 1})
    second = buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "b", "value": 2})
    assert first.sequence == 0
    assert second.sequence == 1


def test_command_buffer_deep_copies_payload() -> None:
    buffer = CommandBuffer()
    payload = {"resource_id": "a", "value": {"nested": 1}}
    command = buffer.add(CommandKind.SET_RESOURCE, payload)
    payload["value"]["nested"] = 999
    assert command.payload["value"] == {"nested": 1}


def test_command_buffer_bound_is_enforced() -> None:
    buffer = CommandBuffer(max_commands=1)
    buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "a", "value": 1})
    with pytest.raises(CommandOverflowError):
        buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "b", "value": 2})


def test_command_buffer_commit_clears_commands() -> None:
    store = _store()
    buffer = CommandBuffer()
    buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "weather", "value": "rain"})
    receipt = buffer.commit(store)
    assert len(buffer) == 0
    assert receipt.after_digest == store.state_digest


def test_command_buffer_transaction_rolls_back_all_commands_on_failure() -> None:
    store = _store()
    before = store.state_digest
    buffer = CommandBuffer()
    buffer.add(CommandKind.SET_RESOURCE, {"resource_id": "weather", "value": "rain"})
    buffer.add(
        CommandKind.SET_COMPONENT,
        {"entity_id": "missing", "schema_id": "health", "data": {"current": 1, "maximum": 1}},
    )
    with pytest.raises(TransactionError):
        buffer.commit(store)
    assert store.state_digest == before


def test_event_queue_orders_by_tick_then_sequence() -> None:
    queue = EventQueue()
    later = queue.publish("later", {}, tick=2)
    first = queue.publish("first", {}, tick=1)
    second = queue.publish("second", {}, tick=1)
    assert queue.pending() == (first, second, later)


def test_event_queue_drain_through_tick_preserves_future() -> None:
    queue = EventQueue()
    first = queue.publish("a", {}, tick=1)
    future = queue.publish("b", {}, tick=2)
    assert queue.drain(through_tick=1) == (first,)
    assert queue.pending() == (future,)


def test_event_queue_snapshot_restore_round_trip() -> None:
    queue = EventQueue()
    queue.publish("a", {"x": 1}, tick=1, source="system")
    record = queue.snapshot()
    restored = EventQueue()
    restored.restore(record)
    assert restored.snapshot() == record


def test_clock_step_is_fixed_width() -> None:
    clock = SimulationClock(step_ns=10)
    one = clock.step()
    two = clock.step(2)
    assert one.tick == 1
    assert one.elapsed_ns == 10
    assert two.tick == 3
    assert two.elapsed_ns == 30


def test_clock_pause_blocks_positive_step() -> None:
    clock = SimulationClock()
    clock.pause()
    with pytest.raises(ClockError):
        clock.step(1)


def test_clock_zero_step_while_paused_is_allowed() -> None:
    clock = SimulationClock()
    clock.pause()
    assert clock.step(0).tick == 0


def test_clock_snapshot_restore_round_trip() -> None:
    clock = SimulationClock(step_ns=5)
    clock.step(3)
    snapshot = clock.snapshot()
    clock.step(2)
    clock.restore(snapshot)
    assert clock.snapshot() == snapshot


@pytest.mark.parametrize(
    "kwargs",
    [
        {"step_ns": 0},
        {"step_ns": -1},
        {"step_ns": True},
        {"tick": -1},
        {"elapsed_ns": -1},
    ],
)
def test_invalid_clock_arguments_fail(kwargs) -> None:
    with pytest.raises(ClockError):
        SimulationClock(**kwargs)


def test_capture_snapshot_clones_store() -> None:
    store = _store()
    snapshot = capture_snapshot(store)
    store.patch_component("entity:player", "health", {"current": 1})
    assert snapshot.store.get_component("entity:player", "health").data["current"] == 100


def test_restore_snapshot_restores_exact_digest() -> None:
    store = _store()
    snapshot = capture_snapshot(store)
    store.patch_component("entity:player", "health", {"current": 1})
    restore_snapshot(store, snapshot)
    assert store.state_digest == snapshot.state_digest
    assert store.revision == snapshot.revision
    assert store.tick == snapshot.tick


def test_snapshot_history_retains_capacity() -> None:
    store = _store()
    history = SnapshotHistory(capacity=2)
    history.append(capture_snapshot(store))
    store.set_resource("a", 1)
    history.append(capture_snapshot(store))
    store.set_resource("b", 2)
    history.append(capture_snapshot(store))
    assert len(history) == 2


def test_snapshot_history_lookup_revision() -> None:
    store = _store()
    history = SnapshotHistory(capacity=4)
    snapshot = capture_snapshot(store)
    history.append(snapshot)
    assert history.at_revision(snapshot.revision).state_digest == snapshot.state_digest


def test_diff_snapshots_equal_state_has_no_operations() -> None:
    store = _store()
    first = capture_snapshot(store)
    second = capture_snapshot(store)
    delta = diff_snapshots(first, second)
    assert delta.operations == ()


def test_diff_and_apply_snapshot_round_trip() -> None:
    store = _store()
    base = capture_snapshot(store)
    target_store = store.clone()
    target_store.patch_component("entity:player", "health", {"current": 50})
    target = capture_snapshot(target_store)
    delta = diff_snapshots(base, target)
    apply_delta(store, delta)
    assert store.state_digest == target.state_digest


def test_apply_delta_rejects_wrong_base_digest() -> None:
    store = _store()
    base = capture_snapshot(store)
    target_store = store.clone()
    target_store.set_resource("x", 1)
    delta = diff_snapshots(base, capture_snapshot(target_store))
    store.set_resource("other", 2)
    with pytest.raises(DeltaError):
        apply_delta(store, delta)


def test_runtime_step_advances_clock_and_store_tick() -> None:
    runtime = _runtime()
    receipt = runtime.step()
    assert receipt.tick == 1
    assert runtime.clock.tick == 1
    assert runtime.store.tick == 1


def test_runtime_executes_registered_systems_in_plan_order() -> None:
    runtime = _runtime()
    receipt = runtime.step()
    assert tuple(row.system_id for row in receipt.systems) == ("movement", "damage")


def test_runtime_commits_system_commands() -> None:
    runtime = _runtime()
    runtime.step()
    position = runtime.store.get_component("entity:player", "position").data
    health = runtime.store.get_component("entity:player", "health").data
    assert position == {"x": 1.0, "y": 2.0}
    assert health["current"] == 90


def test_runtime_emits_events_with_current_tick_and_source() -> None:
    runtime = _runtime()
    receipt = runtime.step()
    events = runtime.events.pending()
    assert receipt.emitted_events == 1
    assert events[0].event_type == "damage"
    assert events[0].tick == 1
    assert events[0].source == "damage"


def test_runtime_metrics_accumulate_successful_ticks() -> None:
    runtime = _runtime()
    runtime.step()
    runtime.step()
    metrics = runtime.metrics()
    assert metrics.ticks == 2
    assert metrics.system_executions == 4
    assert metrics.emitted_events == 2
    assert metrics.last_state_digest == runtime.store.state_digest


def test_runtime_missing_handler_rolls_back_store_clock_events_and_metrics() -> None:
    runtime = SimulationRuntime(_store())
    runtime.register(SystemSpec("missing", writes=("component:position",)))
    checkpoint = capture_checkpoint(runtime)
    metrics = runtime.metrics()
    with pytest.raises(ScheduleError):
        runtime.step()
    assert checkpoint_matches_runtime(runtime, checkpoint)
    assert runtime.metrics() == metrics


def test_runtime_handler_exception_rolls_back_store_clock_events_and_metrics() -> None:
    runtime = SimulationRuntime(_store())

    def boom(ctx):
        ctx.emit("before_failure", {"x": 1})
        ctx.commands.add(
            CommandKind.SET_RESOURCE,
            {"resource_id": "temporary", "value": 1},
        )
        raise RuntimeError("boom")

    runtime.register(SystemSpec("boom", writes=("resource:temporary",)), boom)
    checkpoint = capture_checkpoint(runtime)
    metrics = runtime.metrics()
    with pytest.raises(RuntimeError, match="boom"):
        runtime.step()
    assert checkpoint_matches_runtime(runtime, checkpoint)
    assert runtime.metrics() == metrics
    assert runtime.events.pending() == ()


def test_runtime_late_system_failure_rolls_back_prior_successful_system() -> None:
    runtime = SimulationRuntime(_store())

    def first(ctx):
        ctx.commands.add(
            CommandKind.SET_RESOURCE,
            {"resource_id": "first", "value": 1},
        )

    def second(ctx):
        raise RuntimeError("late")

    runtime.register(SystemSpec("first", writes=("resource:first",)), first)
    runtime.register(SystemSpec("second", phase=SystemPhase.POST, after=("first",)), second)
    checkpoint = capture_checkpoint(runtime)
    with pytest.raises(RuntimeError, match="late"):
        runtime.step()
    assert checkpoint_matches_runtime(runtime, checkpoint)
    assert runtime.store.resource_ids() == ()


def test_runtime_history_keeps_pre_tick_snapshot() -> None:
    runtime = _runtime()
    revision = runtime.store.revision
    digest_before = runtime.store.state_digest
    runtime.step()
    snapshot = runtime.history.at_revision(revision)
    assert snapshot.state_digest == digest_before


def test_runtime_rollback_to_revision_restores_store() -> None:
    runtime = _runtime()
    revision = runtime.store.revision
    before = runtime.store.state_digest
    runtime.step()
    runtime.rollback_to_revision(revision)
    assert runtime.store.state_digest == before


def test_runtime_checkpoint_round_trip() -> None:
    runtime = _runtime()
    checkpoint = capture_checkpoint(runtime)
    runtime.step()
    restore_checkpoint(runtime, checkpoint)
    assert checkpoint_matches_runtime(runtime, checkpoint)


def test_runtime_checkpoint_digest_rejects_tamper() -> None:
    runtime = _runtime()
    checkpoint = capture_checkpoint(runtime)
    tampered = replace(checkpoint, checkpoint_digest="f" * 64)
    with pytest.raises(ReplayError):
        restore_checkpoint(runtime, tampered)


def test_two_equal_runtimes_produce_equal_tick_receipts() -> None:
    left = _runtime()
    right = _runtime()
    assert left.step() == right.step()
    assert left.store.state_digest == right.store.state_digest


def test_replay_recorder_builds_digest_chain() -> None:
    runtime = _runtime()
    recorder = ReplayRecorder(runtime)
    recorder.step()
    recorder.step()
    tape = recorder.tape()
    assert len(tape.frames) == 2
    assert tape.chain_digest != "0" * 64


def test_replay_verifies_deterministic_run() -> None:
    recorder = ReplayRecorder(_runtime())
    recorder.step()
    recorder.step()
    verification = replay(_runtime, recorder.tape())
    assert verification.ok
    assert verification.frames == 2
    assert verification.chain_digest == recorder.tape().chain_digest


def test_replay_detects_tampered_chain_digest() -> None:
    recorder = ReplayRecorder(_runtime())
    recorder.step()
    tape = replace(recorder.tape(), chain_digest="f" * 64)
    with pytest.raises(ReplayDivergenceError):
        replay(_runtime, tape)


def test_replay_detects_tampered_frame() -> None:
    recorder = ReplayRecorder(_runtime())
    recorder.step()
    tape = recorder.tape()
    bad_frame = replace(tape.frames[0], after_digest="f" * 64)
    tampered = replace(tape, frames=(bad_frame,))
    with pytest.raises(ReplayDivergenceError):
        replay(_runtime, tampered)


def test_replay_detects_changed_runtime_logic() -> None:
    recorder = ReplayRecorder(_runtime())
    recorder.step()
    tape = recorder.tape()

    def changed_runtime() -> SimulationRuntime:
        runtime = SimulationRuntime(_store())

        def faster(ctx):
            position = ctx.store.get_component("entity:player", "position").data
            ctx.commands.add(
                CommandKind.PATCH_COMPONENT,
                {
                    "entity_id": "entity:player",
                    "schema_id": "position",
                    "patch": {"x": position["x"] + 100},
                },
            )

        runtime.register(
            SystemSpec("movement", writes=("component:position",), reads=("component:velocity",)),
            faster,
        )
        runtime.register(
            SystemSpec(
                "damage",
                phase=SystemPhase.POST,
                reads=("component:health",),
                writes=("component:health",),
                after=("movement",),
            ),
            _damage,
        )
        return runtime

    with pytest.raises(ReplayDivergenceError):
        replay(changed_runtime, tape)


def test_replay_does_not_mutate_recorded_tape() -> None:
    recorder = ReplayRecorder(_runtime())
    recorder.step()
    tape = recorder.tape()
    before = tape
    replay(_runtime, tape)
    assert tape == before
