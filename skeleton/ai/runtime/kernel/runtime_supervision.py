"""Shared runtime lifecycle semantics for backend and engine services.

VOL-004 uses this module as the single process-local lifecycle vocabulary for
service readiness, draining, failure, restart generations and cancellation.
The class is deliberately dependency-free so both application and engine
processes can bind it during startup before heavier runtime wiring exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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


class RuntimeServiceLifecycle:
    """Thread-safe service lifecycle with monotonic receipts and cancellation.

    Rules:
    * startup begins in STARTING and may become READY or FAILED;
    * only READY may admit new work;
    * shutdown begins with DRAINING, atomically cancelling the generation token;
    * DRAINING may only become STOPPED or FAILED;
    * STOPPED/FAILED are terminal for a generation;
    * restart creates a fresh generation and fresh cancellation token;
    * stale generation-specific tokens cannot be reused after restart.
    """

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
        self._token = CancellationToken(clock=clock)
        self._receipts: list[LifecycleReceipt] = []

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

    def require_work_admission(self) -> None:
        with self._lock:
            if self._phase is not ServicePhase.READY:
                raise RuntimeSupervisionError(
                    f"{self.service_id} cannot admit work while {self._phase.value}"
                )
            self._token.require_active()

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

    def mark_stopped(self, *, reason: str = "shutdown-complete") -> LifecycleReceipt:
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
                "cancellation": self._token.snapshot().to_dict(),
                "last_sequence": self._sequence,
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

    def _record(
        self,
        old: ServicePhase,
        target: ServicePhase,
        reason: str,
    ) -> LifecycleReceipt:
        now = float(self._clock())
        if not math.isfinite(now):
            raise RuntimeSupervisionError("lifecycle clock must be finite")
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
        )
        self._receipts.append(receipt)
        return receipt


__all__ = [
    "LifecycleReceipt",
    "RuntimeServiceLifecycle",
    "RuntimeSupervisionError",
    "ServicePhase",
]
