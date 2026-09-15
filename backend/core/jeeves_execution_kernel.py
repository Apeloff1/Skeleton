"""
Jeeves execution kernel.

A dependency-free control substrate for long-running, tool-capable work.  It
turns the old "spawn a worker and hope" model into bounded, observable
execution with:

* strict priority admission and bounded queueing;
* cooperative cancellation and time/step budgets;
* progressive degradation under observed failures;
* typed capability registration with mutation/approval metadata;
* structured in-memory evidence suitable for sealing into provenance later.

This module intentionally contains no database, HTTP or model-provider code.
It is a policy/mechanics layer that game creation and AI orchestration can
share.
"""
from __future__ import annotations

import heapq
import math
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Iterator, Mapping


class AdmissionRejected(RuntimeError):
    """Raised when runtime admission cannot be granted within policy."""


class ExecutionCancelled(RuntimeError):
    """Raised when a cooperative cancellation token is tripped."""


class BudgetExceeded(RuntimeError):
    """Raised when execution exceeds an explicit step or wall-clock budget."""


class CapabilityRejected(RuntimeError):
    """Raised when capability policy blocks invocation."""


class Priority(IntEnum):
    CONTROL = 0
    INTERACTIVE = 1
    NORMAL = 2
    BACKGROUND = 3

    @classmethod
    def parse(cls, value: "Priority | str | int") -> "Priority":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            key = value.strip().upper().replace("-", "_")
            aliases = {
                "HIGH": "INTERACTIVE",
                "DEFAULT": "NORMAL",
                "LOW": "BACKGROUND",
                "BULK": "BACKGROUND",
            }
            key = aliases.get(key, key)
            try:
                return cls[key]
            except KeyError as exc:
                raise ValueError(f"unknown priority: {value!r}") from exc
        try:
            return cls(int(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unknown priority: {value!r}") from exc


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason: str | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def cancel(self, reason: str = "cancelled") -> bool:
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = str(reason or "cancelled")
            self._event.set()
            return True

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise ExecutionCancelled(self.reason or "cancelled")

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


@dataclass
class ExecutionBudget:
    max_steps: int | None = None
    max_seconds: float | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    steps: int = 0

    def __post_init__(self) -> None:
        if self.max_steps is not None and self.max_steps < 0:
            raise ValueError("max_steps must be >= 0")
        if self.max_seconds is not None and self.max_seconds < 0:
            raise ValueError("max_seconds must be >= 0")

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def remaining_seconds(self) -> float | None:
        if self.max_seconds is None:
            return None
        return max(0.0, self.max_seconds - self.elapsed_seconds)

    def check(self, *, consume_step: bool = False) -> None:
        if self.max_seconds is not None and self.elapsed_seconds > self.max_seconds:
            raise BudgetExceeded(
                f"wall-clock budget exceeded: {self.elapsed_seconds:.3f}s > "
                f"{self.max_seconds:.3f}s"
            )
        if consume_step:
            if self.max_steps is not None and self.steps >= self.max_steps:
                raise BudgetExceeded(
                    f"step budget exceeded: attempted step {self.steps + 1} "
                    f"with max_steps={self.max_steps}"
                )
            self.steps += 1


@dataclass(order=True)
class _Ticket:
    priority: int
    sequence: int
    ticket_id: str = field(compare=False)
    enqueued_monotonic: float = field(compare=False)


class _Permit:
    def __init__(self, gate: "PriorityAdmissionGate", wait_seconds: float) -> None:
        self._gate = gate
        self.wait_seconds = wait_seconds
        self._released = False
        self._lock = threading.Lock()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        self._gate._release()

    def __enter__(self) -> "_Permit":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class PriorityAdmissionGate:
    """Hard-cap active work and queue waiters, honoring priority/FIFO order."""

    def __init__(
        self,
        capacity: int = 8,
        queue_capacity: int = 64,
        *,
        wait_sample_capacity: int = 4096,
        poll_interval: float = 0.05,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        if queue_capacity < 0:
            raise ValueError("queue_capacity must be >= 0")
        self.capacity = int(capacity)
        self.queue_capacity = int(queue_capacity)
        self.poll_interval = max(0.005, float(poll_interval))
        self._cv = threading.Condition()
        self._active = 0
        self._sequence = 0
        self._queue: list[_Ticket] = []
        self._wait_samples: deque[float] = deque(maxlen=max(16, int(wait_sample_capacity)))
        self._admitted = 0
        self._rejected = 0
        self._cancelled = 0
        self._timed_out = 0

    def _record_wait(self, seconds: float) -> None:
        self._wait_samples.append(max(0.0, seconds))

    def _remove_ticket(self, ticket: _Ticket) -> None:
        try:
            idx = self._queue.index(ticket)
        except ValueError:
            return
        self._queue.pop(idx)
        heapq.heapify(self._queue)

    def acquire(
        self,
        priority: Priority | str | int = Priority.NORMAL,
        *,
        timeout: float | None = None,
        cancellation: CancellationToken | None = None,
    ) -> _Permit:
        priority = Priority.parse(priority)
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be >= 0")
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout

        with self._cv:
            cancellation and cancellation.raise_if_cancelled()

            # Preserve FIFO/priority fairness: only bypass when nobody is queued.
            if self._active < self.capacity and not self._queue:
                self._active += 1
                self._admitted += 1
                self._record_wait(0.0)
                return _Permit(self, 0.0)

            if len(self._queue) >= self.queue_capacity:
                self._rejected += 1
                raise AdmissionRejected(
                    f"execution queue full ({len(self._queue)}/{self.queue_capacity})"
                )

            self._sequence += 1
            ticket = _Ticket(
                int(priority), self._sequence, uuid.uuid4().hex[:12], started
            )
            heapq.heappush(self._queue, ticket)

            while True:
                try:
                    cancellation and cancellation.raise_if_cancelled()
                except ExecutionCancelled:
                    self._remove_ticket(ticket)
                    self._cancelled += 1
                    self._cv.notify_all()
                    raise

                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    self._remove_ticket(ticket)
                    self._timed_out += 1
                    self._cv.notify_all()
                    raise AdmissionRejected(
                        f"admission timed out after {max(0.0, now - started):.3f}s"
                    )

                is_head = bool(self._queue) and self._queue[0] is ticket
                if is_head and self._active < self.capacity:
                    heapq.heappop(self._queue)
                    self._active += 1
                    self._admitted += 1
                    wait_seconds = max(0.0, now - started)
                    self._record_wait(wait_seconds)
                    return _Permit(self, wait_seconds)

                wait_for = self.poll_interval
                if deadline is not None:
                    wait_for = min(wait_for, max(0.0, deadline - now))
                self._cv.wait(wait_for)

    def _release(self) -> None:
        with self._cv:
            if self._active <= 0:
                raise RuntimeError("admission gate release underflow")
            self._active -= 1
            self._cv.notify_all()

    @staticmethod
    def _percentile(samples: list[float], q: float) -> float:
        if not samples:
            return 0.0
        values = sorted(samples)
        idx = max(0, min(len(values) - 1, math.ceil(q * len(values)) - 1))
        return values[idx]

    def snapshot(self) -> dict[str, Any]:
        with self._cv:
            samples = list(self._wait_samples)
            queued_by_priority: dict[str, int] = {p.name.lower(): 0 for p in Priority}
            for ticket in self._queue:
                queued_by_priority[Priority(ticket.priority).name.lower()] += 1
            return {
                "capacity": self.capacity,
                "queue_capacity": self.queue_capacity,
                "active": self._active,
                "queued": len(self._queue),
                "queued_by_priority": queued_by_priority,
                "admitted": self._admitted,
                "rejected": self._rejected,
                "cancelled_while_waiting": self._cancelled,
                "timed_out": self._timed_out,
                "wait_p50_ms": round(self._percentile(samples, 0.50) * 1000, 3),
                "wait_p95_ms": round(self._percentile(samples, 0.95) * 1000, 3),
            }


class DegradationRung(IntEnum):
    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    EMERGENCY_READ_ONLY = 4


class RuntimeGovernor:
    """Escalate/recover from observed truth rather than component self-report."""

    def __init__(
        self,
        *,
        window_seconds: float = 30.0,
        min_samples: int = 16,
        escalate_at: float = 0.25,
        recover_at: float = 0.05,
    ) -> None:
        if not (0.0 <= recover_at < escalate_at <= 1.0):
            raise ValueError("require 0 <= recover_at < escalate_at <= 1")
        if min_samples < 1:
            raise ValueError("min_samples must be >= 1")
        self.window_seconds = float(window_seconds)
        self.min_samples = int(min_samples)
        self.escalate_at = float(escalate_at)
        self.recover_at = float(recover_at)
        self._lock = threading.Lock()
        self._rung = DegradationRung.NORMAL
        self._window: deque[tuple[float, bool]] = deque()

    @property
    def rung(self) -> DegradationRung:
        with self._lock:
            return self._rung

    def observe(self, ok: bool) -> DegradationRung:
        now = time.monotonic()
        with self._lock:
            self._window.append((now, bool(ok)))
            cutoff = now - self.window_seconds
            while self._window and self._window[0][0] <= cutoff:
                self._window.popleft()
            if len(self._window) >= self.min_samples:
                errors = sum(1 for _, success in self._window if not success)
                rate = errors / len(self._window)
                if rate > self.escalate_at and self._rung < DegradationRung.EMERGENCY_READ_ONLY:
                    self._rung = DegradationRung(self._rung + 1)
                elif rate < self.recover_at and self._rung > DegradationRung.NORMAL:
                    self._rung = DegradationRung(self._rung - 1)
            return self._rung

    def permits(self, priority: Priority | str | int, *, mutates: bool = False) -> bool:
        priority = Priority.parse(priority)
        with self._lock:
            rung = self._rung
        if priority is Priority.CONTROL:
            return True
        if rung >= DegradationRung.SHED_BACKGROUND and priority is Priority.BACKGROUND:
            return False
        if rung >= DegradationRung.EMERGENCY_READ_ONLY and mutates:
            return False
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._window)
            rung = self._rung
        errors = sum(1 for _, ok in samples if not ok)
        rate = errors / len(samples) if samples else 0.0
        return {
            "rung": rung.name.lower(),
            "samples": len(samples),
            "error_rate": round(rate, 6),
            "permits_background": rung < DegradationRung.SHED_BACKGROUND,
            "permits_writes": rung < DegradationRung.EMERGENCY_READ_ONLY,
        }


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    handler: Callable[..., Any]
    mutates: bool = False
    approval_required: bool = False
    evidence_required: bool = True
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("capability name must be non-empty")
        if not callable(self.handler):
            raise TypeError("capability handler must be callable")


class CapabilityRegistry:
    """Typed runtime capabilities; replaces implicit persona authority."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._capabilities: dict[str, CapabilitySpec] = {}

    def register(self, spec: CapabilitySpec, *, replace: bool = False) -> None:
        key = spec.name.strip()
        with self._lock:
            if key in self._capabilities and not replace:
                raise ValueError(f"capability already registered: {key}")
            self._capabilities[key] = spec

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._capabilities.pop(name, None) is not None

    def get(self, name: str) -> CapabilitySpec | None:
        with self._lock:
            return self._capabilities.get(name)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            specs = sorted(self._capabilities.values(), key=lambda s: s.name)
        return [
            {
                "name": spec.name,
                "mutates": spec.mutates,
                "approval_required": spec.approval_required,
                "evidence_required": spec.evidence_required,
                "tags": sorted(spec.tags),
            }
            for spec in specs
        ]


@dataclass
class ExecutionEvidence:
    sequence: int
    kind: str
    ok: bool
    monotonic_offset_ms: float
    data: dict[str, Any]


class ExecutionContext:
    def __init__(
        self,
        *,
        run_id: str | None = None,
        build_id: str | None = None,
        priority: Priority | str | int = Priority.NORMAL,
        cancellation: CancellationToken | None = None,
        budget: ExecutionBudget | None = None,
        evidence_capacity: int = 2048,
    ) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:16]
        self.build_id = build_id
        self.priority = Priority.parse(priority)
        self.cancellation = cancellation or CancellationToken()
        self.budget = budget or ExecutionBudget()
        self._started = time.monotonic()
        self._lock = threading.Lock()
        self._evidence: deque[ExecutionEvidence] = deque(maxlen=max(32, evidence_capacity))
        self._sequence = 0

    def check(self, *, consume_step: bool = False) -> None:
        self.cancellation.raise_if_cancelled()
        self.budget.check(consume_step=consume_step)

    def record(
        self,
        kind: str,
        data: Mapping[str, Any] | None = None,
        *,
        ok: bool = True,
    ) -> ExecutionEvidence:
        with self._lock:
            self._sequence += 1
            event = ExecutionEvidence(
                sequence=self._sequence,
                kind=str(kind),
                ok=bool(ok),
                monotonic_offset_ms=round((time.monotonic() - self._started) * 1000, 3),
                data=dict(data or {}),
            )
            self._evidence.append(event)
            return event

    def checkpoint(
        self,
        label: str,
        data: Mapping[str, Any] | None = None,
        *,
        consume_step: bool = False,
    ) -> ExecutionEvidence:
        self.check(consume_step=consume_step)
        payload = {"label": label}
        if data:
            payload.update(dict(data))
        return self.record("checkpoint", payload)

    def invoke(
        self,
        registry: CapabilityRegistry,
        governor: RuntimeGovernor,
        name: str,
        *,
        approved: bool = False,
        kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        self.check(consume_step=True)
        spec = registry.get(name)
        if spec is None:
            raise CapabilityRejected(f"unknown capability: {name}")
        if spec.approval_required and not approved:
            raise CapabilityRejected(f"capability requires approval: {name}")
        if not governor.permits(self.priority, mutates=spec.mutates):
            raise CapabilityRejected(
                f"capability blocked by runtime governor: {name}"
            )

        started = time.monotonic()
        self.record(
            "capability.start",
            {"name": name, "mutates": spec.mutates, "tags": sorted(spec.tags)},
        )
        try:
            result = spec.handler(self, **dict(kwargs or {}))
        except Exception as exc:
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            self.record(
                "capability.finish",
                {
                    "name": name,
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                },
                ok=False,
            )
            governor.observe(False)
            raise
        duration_ms = round((time.monotonic() - started) * 1000, 3)
        self.record(
            "capability.finish",
            {"name": name, "duration_ms": duration_ms},
            ok=True,
        )
        governor.observe(True)
        return result

    def evidence(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._evidence)
        return [
            {
                "sequence": event.sequence,
                "kind": event.kind,
                "ok": event.ok,
                "offset_ms": event.monotonic_offset_ms,
                "data": dict(event.data),
            }
            for event in events
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "build_id": self.build_id,
            "priority": self.priority.name.lower(),
            "cancelled": self.cancellation.cancelled,
            "cancel_reason": self.cancellation.reason,
            "budget": {
                "steps": self.budget.steps,
                "max_steps": self.budget.max_steps,
                "elapsed_seconds": round(self.budget.elapsed_seconds, 6),
                "max_seconds": self.budget.max_seconds,
                "remaining_seconds": (
                    None
                    if self.budget.remaining_seconds is None
                    else round(self.budget.remaining_seconds, 6)
                ),
            },
            "evidence_events": len(self.evidence()),
        }


class JeevesRuntime:
    def __init__(
        self,
        *,
        capacity: int = 8,
        queue_capacity: int = 64,
        governor: RuntimeGovernor | None = None,
    ) -> None:
        self.gate = PriorityAdmissionGate(capacity, queue_capacity)
        self.governor = governor or RuntimeGovernor()
        self.capabilities = CapabilityRegistry()

    @contextmanager
    def execution(
        self,
        *,
        run_id: str | None = None,
        build_id: str | None = None,
        priority: Priority | str | int = Priority.NORMAL,
        cancellation: CancellationToken | None = None,
        max_steps: int | None = None,
        max_seconds: float | None = None,
        admission_timeout: float | None = None,
    ) -> Iterator[ExecutionContext]:
        priority = Priority.parse(priority)
        token = cancellation or CancellationToken()
        if not self.governor.permits(priority):
            raise AdmissionRejected(
                f"runtime governor rejects {priority.name.lower()} execution"
            )
        permit = self.gate.acquire(
            priority,
            timeout=admission_timeout,
            cancellation=token,
        )
        ctx = ExecutionContext(
            run_id=run_id,
            build_id=build_id,
            priority=priority,
            cancellation=token,
            budget=ExecutionBudget(
                max_steps=max_steps,
                max_seconds=max_seconds,
            ),
        )
        ctx.record(
            "execution.admitted",
            {"wait_ms": round(permit.wait_seconds * 1000, 3)},
        )
        try:
            yield ctx
        except (ExecutionCancelled, BudgetExceeded) as exc:
            ctx.record(
                "execution.finish",
                {"error_type": type(exc).__name__, "error": str(exc)[:500]},
                ok=False,
            )
            self.governor.observe(False)
            raise
        except Exception as exc:
            ctx.record(
                "execution.finish",
                {"error_type": type(exc).__name__, "error": str(exc)[:500]},
                ok=False,
            )
            self.governor.observe(False)
            raise
        else:
            ctx.record("execution.finish", {}, ok=True)
            self.governor.observe(True)
        finally:
            permit.release()

    def snapshot(self) -> dict[str, Any]:
        return {
            "admission": self.gate.snapshot(),
            "governor": self.governor.snapshot(),
            "capabilities": self.capabilities.snapshot(),
        }


_DEFAULT_RUNTIME = JeevesRuntime()


def get_default_runtime() -> JeevesRuntime:
    return _DEFAULT_RUNTIME
