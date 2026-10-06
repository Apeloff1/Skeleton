"""Shared runtime lifecycle semantics for backend and engine services.

VOL-004 uses this module as the single process-local lifecycle vocabulary for
service readiness, draining, failure, restart generations, work admission and
cancellation. It is dependency-light so application and engine processes can
bind it before heavier runtime wiring exists.

The contract is intentionally stricter than a boolean ready flag:
- lifecycle transitions are explicit and receipted;
- work admission is generation-bound;
- draining atomically revokes new-work authority and cancels the generation;
- in-flight work is accounted for by immutable leases;
- a service cannot claim STOPPED while work leases remain;
- restart creates a fresh generation and fresh cancellation token;
- stale leases and stale cancellation tokens cannot cross generations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
import threading
import time
from typing import Callable

from skeleton.shells.cancellation import (
    CancellationReason,
    CancellationState,
    CancellationToken,
)


class RuntimeSupervisionError(RuntimeError):
    """A service lifecycle transition violated the VOL-004 contract."""


class ServicePhase(str, Enum):
    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


_TERMINAL_PHASES = frozenset({ServicePhase.STOPPED, ServicePhase.FAILED})


@dataclass(frozen=True, slots=True)
class LifecycleReceipt:
    service_id: str
    sequence: int
    generation: int
    from_phase: ServicePhase
    to_phase: ServicePhase
    reason: str
    at_monotonic: float
    cancellation: CancellationState
    inflight_work: int

    def as_dict(self) -> dict[str, object]:
        return {
            "service_id": self.service_id,
            "sequence": self.sequence,
            "generation": self.generation,
            "from_phase": self.from_phase.value,
            "to_phase": self.to_phase.value,
            "reason": self.reason,
            "at_monotonic": self.at_monotonic,
            "cancellation": self.cancellation.to_dict(),
            "inflight_work": self.inflight_work,
        }


@dataclass(frozen=True, slots=True)
class WorkLease:
    service_id: str
    work_id: str
    generation: int
    sequence: int
    acquired_at_monotonic: float

    def as_dict(self) -> dict[str, object]:
        return {
            "service_id": self.service_id,
            "work_id": self.work_id,
            "generation": self.generation,
            "sequence": self.sequence,
            "acquired_at_monotonic": self.acquired_at_monotonic,
        }


def _service_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("service_id must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > 128
        or "\x00" in normalized
    ):
        raise ValueError("service_id is invalid")
    return normalized


def _work_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("work_id must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > 512
        or "\x00" in normalized
    ):
        raise ValueError("work_id is invalid")
    return normalized


def _reason(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("lifecycle reason must be text")
    normalized = value.strip()
    if (
        not normalized
        or normalized != value
        or len(normalized) > 512
        or "\x00" in normalized
    ):
        raise ValueError("lifecycle reason is invalid")
    return normalized


class RuntimeAdmissionMiddleware:
    """ASGI middleware enforcing lifecycle admission without framework coupling."""

    def __init__(
        self,
        app,
        *,
        lifecycle: "RuntimeServiceLifecycle",
        exempt_prefixes: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(lifecycle, RuntimeServiceLifecycle):
            raise TypeError("lifecycle must be RuntimeServiceLifecycle")
        normalized: list[str] = []
        for raw in exempt_prefixes:
            if (
                not isinstance(raw, str)
                or not raw.startswith("/")
                or "\x00" in raw
            ):
                raise ValueError("runtime admission exempt prefix is invalid")
            value = raw.rstrip("/") or "/"
            if value not in normalized:
                normalized.append(value)
        self.app = app
        self.lifecycle = lifecycle
        self.exempt_prefixes = tuple(normalized)

    @staticmethod
    def _path_matches(path: str, prefix: str) -> bool:
        if prefix == "/":
            return path == "/"
        return path == prefix or path.startswith(prefix + "/")

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        raw_path = scope.get("path", "")
        path = raw_path if isinstance(raw_path, str) else ""
        if any(
            self._path_matches(path, prefix)
            for prefix in self.exempt_prefixes
        ):
            await self.app(scope, receive, send)
            return

        work_id = (
            "http:"
            + str(self.lifecycle.generation)
            + ":"
            + str(id(scope))
        )
        try:
            lease = self.lifecycle.acquire_work(work_id)
        except RuntimeSupervisionError:
            body = json.dumps(
                {
                    "error": "service_unavailable",
                    "reason": "runtime_not_accepting_work",
                    "lifecycle": self.lifecycle.snapshot(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", b"1"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": body,
                    "more_body": False,
                }
            )
            return

        try:
            await self.app(scope, receive, send)
        finally:
            self.lifecycle.release_work(lease)


class RuntimeServiceLifecycle:
    """Thread-safe lifecycle and work-admission authority for one service."""

    def __init__(
        self,
        service_id: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.service_id = _service_id(service_id)
        self._clock = clock
        self._lock = threading.RLock()
        self._phase = ServicePhase.STARTING
        self._generation = 1
        self._sequence = 0
        self._lease_sequence = 0
        self._token = CancellationToken(clock=clock)
        self._receipts: list[LifecycleReceipt] = []
        self._leases: dict[str, WorkLease] = {}

    @property
    def phase(self) -> ServicePhase:
        with self._lock:
            return self._phase

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def cancellation(self) -> CancellationToken:
        with self._lock:
            return self._token

    @property
    def admits_work(self) -> bool:
        with self._lock:
            return self._phase is ServicePhase.READY and not self._token.cancelled

    @property
    def inflight_work(self) -> int:
        with self._lock:
            return len(self._leases)

    def require_work_admission(self, *, allow_starting: bool = False) -> None:
        if not isinstance(allow_starting, bool):
            raise TypeError("allow_starting must be bool")
        with self._lock:
            allowed = (
                self._phase is ServicePhase.READY
                or (allow_starting and self._phase is ServicePhase.STARTING)
            )
            if not allowed:
                raise RuntimeSupervisionError(
                    f"{self.service_id} cannot admit work while {self._phase.value}"
                )
            self._token.require_active()

    def acquire_work(
        self,
        work_id: str,
        *,
        allow_starting: bool = False,
    ) -> WorkLease:
        normalized = _work_id(work_id)
        with self._lock:
            self.require_work_admission(allow_starting=allow_starting)
            if normalized in self._leases:
                raise RuntimeSupervisionError(
                    f"{self.service_id} work already leased: {normalized}"
                )
            self._lease_sequence += 1
            now = self._now()
            lease = WorkLease(
                service_id=self.service_id,
                work_id=normalized,
                generation=self._generation,
                sequence=self._lease_sequence,
                acquired_at_monotonic=now,
            )
            self._leases[normalized] = lease
            return lease

    def release_work(self, lease: WorkLease) -> bool:
        if not isinstance(lease, WorkLease):
            raise TypeError("lease must be WorkLease")
        with self._lock:
            if lease.service_id != self.service_id:
                raise RuntimeSupervisionError("work lease belongs to another service")
            current = self._leases.get(lease.work_id)
            if current is None:
                return False
            if current != lease:
                raise RuntimeSupervisionError("work lease identity mismatch")
            if lease.generation != self._generation:
                raise RuntimeSupervisionError("stale work lease crossed generation")
            del self._leases[lease.work_id]
            return True

    def active_work(self) -> tuple[WorkLease, ...]:
        with self._lock:
            return tuple(self._leases[key] for key in sorted(self._leases))

    def mark_ready(self, *, reason: str = "startup-complete") -> LifecycleReceipt:
        return self._transition(
            expected=(ServicePhase.STARTING,),
            target=ServicePhase.READY,
            reason=reason,
        )

    def begin_drain(
        self,
        *,
        reason: str = "shutdown-requested",
        cancellation_reason: CancellationReason = CancellationReason.SHUTDOWN,
    ) -> LifecycleReceipt:
        normalized = _reason(reason)
        with self._lock:
            if self._phase is ServicePhase.DRAINING:
                return self._receipts[-1]
            if self._phase in _TERMINAL_PHASES:
                raise RuntimeSupervisionError(
                    f"{self.service_id} cannot drain terminal generation"
                )
            old = self._phase
            self._token.cancel(cancellation_reason, detail=normalized)
            return self._record(old, ServicePhase.DRAINING, normalized)

    def mark_stopped(
        self,
        *,
        reason: str = "shutdown-complete",
        require_quiescent: bool = True,
    ) -> LifecycleReceipt:
        if not isinstance(require_quiescent, bool):
            raise TypeError("require_quiescent must be bool")
        with self._lock:
            if require_quiescent and self._leases:
                raise RuntimeSupervisionError(
                    f"{self.service_id} cannot stop with {len(self._leases)} "
                    "in-flight work leases"
                )
            return self._transition(
                expected=(ServicePhase.DRAINING,),
                target=ServicePhase.STOPPED,
                reason=reason,
            )

    def fail(self, *, reason: str) -> LifecycleReceipt:
        normalized = _reason(reason)
        with self._lock:
            if self._phase in _TERMINAL_PHASES:
                if self._phase is ServicePhase.FAILED:
                    return self._receipts[-1]
                raise RuntimeSupervisionError(
                    f"{self.service_id} stopped generation cannot fail afterward"
                )
            old = self._phase
            self._token.cancel(CancellationReason.INTERNAL, detail=normalized)
            return self._record(old, ServicePhase.FAILED, normalized)

    def restart(self, *, reason: str = "supervised-restart") -> LifecycleReceipt:
        normalized = _reason(reason)
        with self._lock:
            if self._phase not in _TERMINAL_PHASES:
                raise RuntimeSupervisionError(
                    f"{self.service_id} restart requires terminal generation"
                )
            if self._leases:
                raise RuntimeSupervisionError(
                    f"{self.service_id} restart forbidden with in-flight work"
                )
            old = self._phase
            self._generation += 1
            self._token = CancellationToken(clock=self._clock)
            return self._record(old, ServicePhase.STARTING, normalized)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "service_id": self.service_id,
                "phase": self._phase.value,
                "generation": self._generation,
                "admits_work": (
                    self._phase is ServicePhase.READY
                    and not self._token.cancelled
                ),
                "inflight_work": len(self._leases),
                "active_work_ids": sorted(self._leases),
                "cancellation": self._token.snapshot().to_dict(),
                "last_sequence": self._sequence,
                "last_lease_sequence": self._lease_sequence,
            }

    def receipts(self) -> tuple[LifecycleReceipt, ...]:
        with self._lock:
            return tuple(self._receipts)

    def _transition(
        self,
        *,
        expected: tuple[ServicePhase, ...],
        target: ServicePhase,
        reason: str,
    ) -> LifecycleReceipt:
        normalized = _reason(reason)
        with self._lock:
            if self._phase not in expected:
                allowed = ",".join(item.value for item in expected)
                raise RuntimeSupervisionError(
                    f"{self.service_id} transition {self._phase.value}->{target.value} "
                    f"requires phase in {{{allowed}}}"
                )
            return self._record(self._phase, target, normalized)

    def _now(self) -> float:
        now = float(self._clock())
        if not math.isfinite(now):
            raise RuntimeSupervisionError("lifecycle clock must be finite")
        return now

    def _record(
        self,
        old: ServicePhase,
        target: ServicePhase,
        reason: str,
    ) -> LifecycleReceipt:
        now = self._now()
        self._phase = target
        self._sequence += 1
        receipt = LifecycleReceipt(
            service_id=self.service_id,
            sequence=self._sequence,
            generation=self._generation,
            from_phase=old,
            to_phase=target,
            reason=reason,
            at_monotonic=now,
            cancellation=self._token.snapshot(),
            inflight_work=len(self._leases),
        )
        self._receipts.append(receipt)
        return receipt


__all__ = [
    "LifecycleReceipt",
    "RuntimeAdmissionMiddleware",
    "RuntimeServiceLifecycle",
    "RuntimeSupervisionError",
    "ServicePhase",
    "WorkLease",
]
