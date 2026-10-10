"""Execute trusted Dragon callbacks in bounded, resource-admitted chunks.

No execution without the existing shared global scheduler. Synchronous callbacks
must themselves have bounded native/provider timeouts; Python cannot safely kill
a callback thread and claim its resources stopped. No detached threads are used.
"""
from __future__ import annotations
from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable
import time

from skeleton.ai.game_builder.resource_governor import ResourceGovernor, ResourceDelta, ResourceLimitError
from .dragon_resource_session import DragonResourceSession, HardwareSample, SessionTask, ResourcePlan, plan_resources


@dataclass(frozen=True, slots=True)
class ChunkResult:
    done: bool
    checkpoint_ref: str
    usage: ResourceDelta

    def __post_init__(self):
        if not isinstance(self.done, bool) or not isinstance(self.usage, ResourceDelta):
            raise ValueError("invalid chunk result")
        if not isinstance(self.checkpoint_ref, str) or not 1 <= len(self.checkpoint_ref) <= 256 or any(ord(c) < 32 for c in self.checkpoint_ref):
            raise ValueError("bounded checkpoint reference required")


@dataclass(frozen=True, slots=True)
class ChunkRun:
    completed_chunks: int
    done: bool
    reason: str
    checkpoints: tuple[str, ...]
    effort: str


class DragonChunkExecutor:
    def __init__(self, session: DragonResourceSession, governor: ResourceGovernor,
                 hardware: Callable[[], HardwareSample], *, clock: Callable[[], float] = time.time):
        self.session, self.governor = session, governor
        self.hardware, self.clock = hardware, clock
        self.foreground_waiting = Event()
        self._running = Lock()
        self._foreground_lock = Lock()
        self._foreground_count = 0

    def foreground_arrived(self) -> None:
        with self._foreground_lock:
            self._foreground_count += 1
            self.foreground_waiting.set()

    def foreground_finished(self) -> None:
        with self._foreground_lock:
            if self._foreground_count == 0:
                raise ValueError("no foreground request to finish")
            self._foreground_count -= 1
            if self._foreground_count == 0:
                self.foreground_waiting.clear()

    def should_yield(self, task: SessionTask) -> bool:
        return task.lane != "user" and self.foreground_waiting.is_set()

    def run(self, task: SessionTask, callback: Callable[[ResourcePlan, Callable[[], bool]], ChunkResult],
            *, authorized: bool, consent: bool, max_chunks: int = 1, reserved_usage: ResourceDelta | None = None) -> ChunkRun:
        if authorized is not True or consent is not True:
            raise PermissionError("chunk execution requires authority and consent")
        if isinstance(max_chunks, bool) or not isinstance(max_chunks, int) or not 1 <= max_chunks <= 1000:
            raise ValueError("invalid chunk budget")
        task.request()
        reservation = reserved_usage or ResourceDelta(tokens=task.provider_tokens)
        if not isinstance(reservation, ResourceDelta) or reservation.tokens > task.provider_tokens:
            raise ValueError("invalid chunk usage reservation")
        if not self._running.acquire(blocking=False):
            return ChunkRun(0, False, "executor_busy", (), "defer")
        try:
            return self._run(task, callback, max_chunks, reservation)
        finally:
            self._running.release()

    def _run(self, task, callback, max_chunks, reservation):
        checkpoints = []; effort = "defer"
        for _ in range(max_chunks):
            if self.should_yield(task):
                return ChunkRun(len(checkpoints), False, "foreground_waiting", tuple(checkpoints), effort)
            sample = self.hardware()
            now = self.clock()
            plan = plan_resources(sample, now=now, foreground=task.lane == "user")
            # Every prospective model chunk must fit remaining cumulative tokens
            # BEFORE the global reservation and before calling trusted code.
            if self.governor.tokens + task.provider_tokens > self.governor.envelope.max_tokens:
                return ChunkRun(len(checkpoints), False, "token_budget", tuple(checkpoints), effort)
            for field in ("tokens", "tool_calls", "artifact_bytes", "retries", "active_branches", "concurrency"):
                value = getattr(reservation, field)
                if value is None:
                    continue
                proposed = value if field in ("active_branches", "concurrency") else getattr(self.governor, field) + value
                if proposed > getattr(self.governor.envelope, "max_" + field):
                    return ChunkRun(len(checkpoints), False, field + "_budget", tuple(checkpoints), effort)
            dispatch = self.session.dispatch((task,), sample, now=now)
            if task.task_id not in dispatch.admitted:
                return ChunkRun(len(checkpoints), False, dispatch.reason, tuple(checkpoints), effort)
            if not dispatch.execution_authorized:
                self.session.stopped(task.task_id)
                return ChunkRun(len(checkpoints), False, "global_ledger_required", tuple(checkpoints), effort)
            try:
                stop = lambda: self.should_yield(task) or self.session.yield_requested(task.task_id)
                if stop():
                    return ChunkRun(len(checkpoints), False, "checkpoint_requested", tuple(checkpoints), effort)
                result = callback(plan, stop)
                if not isinstance(result, ChunkResult):
                    raise ValueError("trusted worker returned invalid chunk result")
                if result.usage.tokens > task.provider_tokens:
                    raise ResourceLimitError("worker exceeded declared provider reservation")
                for field in ("tokens", "tool_calls", "artifact_bytes", "retries", "active_branches", "concurrency"):
                    actual, reserved = getattr(result.usage, field), getattr(reservation, field)
                    if actual is not None and (reserved is None or actual > reserved):
                        raise ResourceLimitError("worker exceeded declared " + field + " reservation")
                self.governor.charge(result.usage)
                checkpoints.append(result.checkpoint_ref)
                effort = dispatch.effort if task.lane == "user" else plan.effort
                if result.done:
                    return ChunkRun(len(checkpoints), True, "completed", tuple(checkpoints), effort)
            finally:
                # Callback has returned/raised: no worker was abandoned. This
                # acknowledgement is the only place the grant is released.
                self.session.stopped(task.task_id)
        return ChunkRun(len(checkpoints), False, "chunk_budget", tuple(checkpoints), effort)
