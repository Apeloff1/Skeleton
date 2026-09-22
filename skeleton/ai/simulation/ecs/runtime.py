"""Deterministic ECS runtime, checkpoints, rollback, and replay evidence."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .canonical import chained_digest, digest
from .errors import ReplayDivergenceError, ReplayError, ScheduleError, ValidationError
from .execution import (
    CommandBuffer,
    EventQueue,
    SimulationClock,
    SnapshotHistory,
    capture_snapshot,
    restore_snapshot,
)
from .schedule import SystemGraph, SystemSpec
from .store import EntityStore

SystemHandler = Callable[["SystemContext"], None]


@dataclass
class SystemContext:
    store: EntityStore
    commands: CommandBuffer
    events: EventQueue
    clock: SimulationClock
    system: SystemSpec

    def emit(self, event_type: str, payload: Any):
        return self.events.publish(
            event_type,
            payload,
            tick=self.clock.tick,
            source=self.system.system_id,
        )


@dataclass(frozen=True)
class SystemExecutionReceipt:
    system_id: str
    before_digest: str
    after_digest: str
    command_count: int
    event_count: int


@dataclass(frozen=True)
class TickReceipt:
    tick: int
    before_digest: str
    after_digest: str
    plan_fingerprint: str
    systems: tuple[SystemExecutionReceipt, ...]
    emitted_events: int


@dataclass(frozen=True)
class RuntimeMetrics:
    ticks: int
    system_executions: int
    emitted_events: int
    last_state_digest: str


@dataclass(frozen=True)
class RuntimeCheckpoint:
    store: Any
    clock: Any
    events: Mapping[str, Any]
    checkpoint_digest: str


def capture_checkpoint(runtime: "SimulationRuntime") -> RuntimeCheckpoint:
    store = capture_snapshot(runtime.store)
    clock = runtime.clock.snapshot()
    events = runtime.events.snapshot()
    material = {
        "store": store.state_digest,
        "clock": clock.__dict__,
        "events": events,
    }
    return RuntimeCheckpoint(
        store=store,
        clock=clock,
        events=copy.deepcopy(events),
        checkpoint_digest=digest(material),
    )


def _checkpoint_digest(checkpoint: RuntimeCheckpoint) -> str:
    return digest(
        {
            "store": checkpoint.store.state_digest,
            "clock": checkpoint.clock.__dict__,
            "events": checkpoint.events,
        }
    )


def restore_checkpoint(runtime: "SimulationRuntime", checkpoint: RuntimeCheckpoint) -> None:
    if _checkpoint_digest(checkpoint) != checkpoint.checkpoint_digest:
        raise ReplayError("checkpoint digest mismatch")
    restore_snapshot(runtime.store, checkpoint.store)
    runtime.clock.restore(checkpoint.clock)
    runtime.events.restore(checkpoint.events)


def checkpoint_matches_runtime(runtime: "SimulationRuntime", checkpoint: RuntimeCheckpoint) -> bool:
    return (
        runtime.store.state_digest == checkpoint.store.state_digest
        and runtime.clock.snapshot() == checkpoint.clock
        and runtime.events.snapshot() == checkpoint.events
    )


class SimulationRuntime:
    def __init__(
        self,
        store: EntityStore | None = None,
        graph: SystemGraph | None = None,
        *,
        clock: SimulationClock | None = None,
        history_capacity: int = 128,
    ) -> None:
        self.store = store or EntityStore()
        self.graph = graph or SystemGraph()
        self.clock = clock or SimulationClock()
        self.events = EventQueue()
        self.history = SnapshotHistory(history_capacity)
        self._handlers: dict[str, SystemHandler] = {}
        self._ticks = 0
        self._system_executions = 0
        self._emitted_events = 0

    def bind(self, system_id: str, handler: SystemHandler) -> None:
        self.graph.get(system_id)
        if not callable(handler):
            raise ValidationError("system handler must be callable")
        self._handlers[system_id] = handler

    def register(self, spec: SystemSpec, handler: SystemHandler | None = None) -> SystemSpec:
        registered = self.graph.register(spec)
        if handler is not None:
            self.bind(spec.system_id, handler)
        return registered

    def plan(self):
        return self.graph.plan()

    def step(self) -> TickReceipt:
        """Execute one deterministic tick atomically.

        The checkpoint covers authoritative store state, fixed-step clock, and
        pending events. Runtime counters are restored separately. A failure at
        any point after planning therefore leaves the runtime observationally
        identical to its pre-step state, apart from retained history evidence.
        """

        plan = self.plan()
        checkpoint = capture_checkpoint(self)
        before_digest = self.store.state_digest
        before_metrics = (self._ticks, self._system_executions, self._emitted_events)
        self.history.append(checkpoint.store)
        system_receipts: list[SystemExecutionReceipt] = []
        events_before = len(self.events.pending())

        try:
            self.clock.step(1)
            self.store.advance_tick(self.clock.tick)

            for batch in plan.batches:
                for system_id in batch.system_ids:
                    if system_id not in self._handlers:
                        raise ScheduleError(
                            "system handler missing",
                            context={"system_id": system_id},
                        )
                    spec = self.graph.get(system_id)
                    commands = CommandBuffer()
                    state_before = self.store.state_digest
                    event_count_before = len(self.events.pending())
                    context = SystemContext(
                        self.store,
                        commands,
                        self.events,
                        self.clock,
                        spec,
                    )
                    self._handlers[system_id](context)
                    command_count = len(commands)
                    commands.commit(self.store)
                    emitted = len(self.events.pending()) - event_count_before
                    system_receipts.append(
                        SystemExecutionReceipt(
                            system_id=system_id,
                            before_digest=state_before,
                            after_digest=self.store.state_digest,
                            command_count=command_count,
                            event_count=emitted,
                        )
                    )
                    self._system_executions += 1

            self.store.assert_invariants()
        except Exception:
            restore_checkpoint(self, checkpoint)
            self._ticks, self._system_executions, self._emitted_events = before_metrics
            raise

        self._ticks += 1
        emitted_total = len(self.events.pending()) - events_before
        self._emitted_events += emitted_total
        return TickReceipt(
            tick=self.clock.tick,
            before_digest=before_digest,
            after_digest=self.store.state_digest,
            plan_fingerprint=plan.fingerprint,
            systems=tuple(system_receipts),
            emitted_events=emitted_total,
        )

    def rollback_to_revision(self, revision: int):
        snapshot = self.history.at_revision(revision)
        restore_snapshot(self.store, snapshot)
        return snapshot

    def metrics(self) -> RuntimeMetrics:
        return RuntimeMetrics(
            ticks=self._ticks,
            system_executions=self._system_executions,
            emitted_events=self._emitted_events,
            last_state_digest=self.store.state_digest,
        )


@dataclass(frozen=True)
class ReplayFrame:
    index: int
    tick: int
    before_digest: str
    after_digest: str
    plan_fingerprint: str
    receipt_digest: str


@dataclass(frozen=True)
class ReplayTape:
    initial: RuntimeCheckpoint
    frames: tuple[ReplayFrame, ...]
    chain_digest: str


@dataclass(frozen=True)
class ReplayVerification:
    frames: int
    final_digest: str
    chain_digest: str
    ok: bool


class ReplayRecorder:
    def __init__(self, runtime: SimulationRuntime) -> None:
        self.runtime = runtime
        self.initial = capture_checkpoint(runtime)
        self.frames: list[ReplayFrame] = []
        self._chain = "0" * 64

    def step(self) -> TickReceipt:
        receipt = self.runtime.step()
        frame = ReplayFrame(
            index=len(self.frames),
            tick=receipt.tick,
            before_digest=receipt.before_digest,
            after_digest=receipt.after_digest,
            plan_fingerprint=receipt.plan_fingerprint,
            receipt_digest=digest(receipt.__dict__),
        )
        self._chain = chained_digest(self._chain, frame.__dict__)
        self.frames.append(frame)
        return receipt

    def tape(self) -> ReplayTape:
        return ReplayTape(self.initial, tuple(self.frames), self._chain)


def replay(runtime_factory: Callable[[], SimulationRuntime], tape: ReplayTape) -> ReplayVerification:
    runtime = runtime_factory()
    restore_checkpoint(runtime, tape.initial)
    chain = "0" * 64
    for expected in tape.frames:
        receipt = runtime.step()
        actual = ReplayFrame(
            index=expected.index,
            tick=receipt.tick,
            before_digest=receipt.before_digest,
            after_digest=receipt.after_digest,
            plan_fingerprint=receipt.plan_fingerprint,
            receipt_digest=digest(receipt.__dict__),
        )
        if actual != expected:
            raise ReplayDivergenceError(
                "replay frame diverged",
                context={"frame": expected.index},
            )
        chain = chained_digest(chain, actual.__dict__)
    if chain != tape.chain_digest:
        raise ReplayDivergenceError("replay chain digest mismatch")
    return ReplayVerification(
        frames=len(tape.frames),
        final_digest=runtime.store.state_digest,
        chain_digest=chain,
        ok=True,
    )
