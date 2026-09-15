"""Runtime admission and graceful-degradation controls mined from GameForge-RS.

The Rust service stack contains two broadly reusable ideas that were not yet
present in Skeleton: adaptive token-bucket admission and a progressive chaos
governor.  This module ports those semantics into small synchronous Python
primitives suitable for the existing Skeleton runtime.

The port preserves the doctrine that control-plane work survives longer than
bulk/background work and that degradation/recovery is driven by observed
outcomes rather than component self-report.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from threading import Lock
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from skeleton.kernel.events import EventBus


class AdmissionVerdict(str, Enum):
    ADMITTED = "admitted"
    SHED = "shed"


class WorkPriority(IntEnum):
    """Lower values represent more important work."""

    CONTROL = 0
    INTERACTIVE = 1
    STANDARD = 2
    BACKGROUND = 3
    BULK = 4


class DegradationRung(IntEnum):
    NORMAL = 0
    REDUCED_CACHING = 1
    SHED_BACKGROUND = 2
    STALE_READS = 3
    EMERGENCY_READ_ONLY = 4

    @property
    def label(self) -> str:
        return {
            DegradationRung.NORMAL: "normal",
            DegradationRung.REDUCED_CACHING: "reduced_caching",
            DegradationRung.SHED_BACKGROUND: "shed_background",
            DegradationRung.STALE_READS: "stale_reads",
            DegradationRung.EMERGENCY_READ_ONLY: "emergency_read_only",
        }[self]


@dataclass(frozen=True)
class RuntimePolicy:
    rung: DegradationRung
    permits_writes: bool
    permits_background: bool
    should_cache: bool
    stale_reads_allowed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rung": self.rung.label,
            "permits_writes": self.permits_writes,
            "permits_background": self.permits_background,
            "should_cache": self.should_cache,
            "stale_reads_allowed": self.stale_reads_allowed,
        }


class AdaptiveGate:
    """Token-bucket admission gate with a control-plane reserve.

    Unlike the original Rust implementation, the reserve is explicit instead
    of relying on saturating subtraction at zero.  That makes the documented
    "control may overdraw" behavior real and testable while still bounding it.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        *,
        control_reserve_ratio: float = 0.05,
        clock: Callable[[], float] = time.monotonic,
        bus: Optional[EventBus] = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_per_sec < 0:
            raise ValueError("refill_per_sec cannot be negative")
        self.capacity = int(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self.control_reserve = max(1, int(round(self.capacity * max(0.0, control_reserve_ratio))))
        self._clock = clock
        self._tokens = float(self.capacity)
        self._reserve = self.control_reserve
        self._last_refill = self._clock()
        self._lock = Lock()
        self._admitted = 0
        self._shed = 0
        self._bus = bus

    def _refill_locked(self, now: float) -> None:
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0.0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
        # Replenish reserve only when the main bucket is fully healthy, so
        # emergency traffic cannot permanently consume system headroom.
        if self._tokens >= self.capacity:
            self._reserve = self.control_reserve
        self._last_refill = now

    def admit(self, priority: WorkPriority | int = WorkPriority.STANDARD) -> AdmissionVerdict:
        priority = WorkPriority(int(priority))
        with self._lock:
            self._refill_locked(self._clock())
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                verdict = AdmissionVerdict.ADMITTED
            elif priority is WorkPriority.CONTROL and self._reserve > 0:
                self._reserve -= 1
                verdict = AdmissionVerdict.ADMITTED
            else:
                verdict = AdmissionVerdict.SHED

            if verdict is AdmissionVerdict.ADMITTED:
                self._admitted += 1
            else:
                self._shed += 1

        if self._bus:
            self._bus.emit(
                "acquired.runtime.admission",
                {"priority": priority.name.lower(), "verdict": verdict.value},
            )
        return verdict

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._refill_locked(self._clock())
            return {
                "tokens_available": round(self._tokens, 3),
                "capacity": self.capacity,
                "control_reserve_available": self._reserve,
                "control_reserve_capacity": self.control_reserve,
                "admitted": self._admitted,
                "shed": self._shed,
            }


class ChaosGovernor:
    """Observed-outcome governor with hysteretic progressive degradation."""

    def __init__(
        self,
        *,
        window_span: float = 30.0,
        min_samples: int = 16,
        escalate_at: float = 0.25,
        recover_at: float = 0.05,
        max_samples: int = 2048,
        clock: Callable[[], float] = time.monotonic,
        bus: Optional[EventBus] = None,
    ):
        if window_span <= 0:
            raise ValueError("window_span must be positive")
        if min_samples <= 0:
            raise ValueError("min_samples must be positive")
        if not 0.0 <= recover_at < escalate_at <= 1.0:
            raise ValueError("require 0 <= recover_at < escalate_at <= 1")
        if max_samples < min_samples:
            raise ValueError("max_samples must be >= min_samples")

        self.window_span = float(window_span)
        self.min_samples = int(min_samples)
        self.escalate_at = float(escalate_at)
        self.recover_at = float(recover_at)
        self._clock = clock
        self._window: Deque[Tuple[float, bool]] = deque(maxlen=int(max_samples))
        self._rung = DegradationRung.NORMAL
        self._lock = Lock()
        self._bus = bus
        self._transitions = 0

    @property
    def rung(self) -> DegradationRung:
        with self._lock:
            return self._rung

    def _prune_locked(self, now: float) -> None:
        cutoff = now - self.window_span
        while self._window and self._window[0][0] <= cutoff:
            self._window.popleft()

    def observe(self, ok: bool) -> DegradationRung:
        """Record one observed outcome and possibly move one ladder rung."""

        now = self._clock()
        transition: Optional[Tuple[DegradationRung, DegradationRung, float]] = None
        with self._lock:
            self._window.append((now, bool(ok)))
            self._prune_locked(now)
            if len(self._window) >= self.min_samples:
                errors = sum(1 for _, passed in self._window if not passed)
                rate = errors / len(self._window)
                previous = self._rung
                if rate > self.escalate_at and self._rung < DegradationRung.EMERGENCY_READ_ONLY:
                    self._rung = DegradationRung(self._rung + 1)
                elif rate < self.recover_at and self._rung > DegradationRung.NORMAL:
                    self._rung = DegradationRung(self._rung - 1)
                if self._rung != previous:
                    self._transitions += 1
                    transition = (previous, self._rung, rate)
            rung = self._rung

        if transition and self._bus:
            previous, current, rate = transition
            self._bus.emit(
                "acquired.runtime.degradation",
                {
                    "from": previous.label,
                    "to": current.label,
                    "error_rate": round(rate, 4),
                },
            )
        return rung

    def policy(self) -> RuntimePolicy:
        rung = self.rung
        return RuntimePolicy(
            rung=rung,
            permits_writes=rung < DegradationRung.EMERGENCY_READ_ONLY,
            permits_background=rung < DegradationRung.SHED_BACKGROUND,
            should_cache=rung < DegradationRung.REDUCED_CACHING,
            stale_reads_allowed=rung >= DegradationRung.STALE_READS,
        )

    def error_rate(self) -> float:
        now = self._clock()
        with self._lock:
            self._prune_locked(now)
            if not self._window:
                return 0.0
            errors = sum(1 for _, passed in self._window if not passed)
            return round(errors / len(self._window), 4)

    def stats(self) -> Dict[str, Any]:
        policy = self.policy()
        with self._lock:
            samples = len(self._window)
            transitions = self._transitions
        return {
            **policy.to_dict(),
            "samples": samples,
            "error_rate": self.error_rate(),
            "transitions": transitions,
        }


__all__ = [
    "AdaptiveGate",
    "AdmissionVerdict",
    "ChaosGovernor",
    "DegradationRung",
    "RuntimePolicy",
    "WorkPriority",
]
