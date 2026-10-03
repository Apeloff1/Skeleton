"""Pack H admit pressure: backpressure as load, queue depth and retry-after.

Contract (agreed with Middleware for the Pack F gate plane, schema_version 1)::

    {
      "schema_version": 1,
      "load": 0.0-1.0,
      "queue_depth": int,
      "max_queue_depth": int,
      "tenant_queue_depth": int | null,
      "retry_after_s": float,       # two decimals, same field as RateLimitError
      "state": "open" | "throttle" | "shed",
      "observed_at": ISO-8601 UTC
    }

State rules:

* ``open``      load < 0.7 and retry_after_s == 0
* ``throttle``  0.7 <= load < 0.95, or retry_after_s > 0
* ``shed``      load >= 0.95, or the global/tenant queue is full

The module is read-only with respect to the shared pressure ledger: it never
configures policy, enqueues, acquires or releases. It only observes.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, runtime_checkable

SCHEMA_VERSION = 1
THROTTLE_LOAD = 0.7
SHED_LOAD = 0.95
MAX_RETRY_AFTER_S = 300.0
MIN_RETRY_AFTER_S = 0.05


class PressureState(str, Enum):
    OPEN = "open"
    THROTTLE = "throttle"
    SHED = "shed"


class PressureSourceError(RuntimeError):
    """Raised when a pressure source cannot produce an observation."""


@dataclass(frozen=True, slots=True)
class RawPressure:
    """Source-neutral observation, before classification."""

    active: int
    queued: int
    max_concurrency: int
    max_queue_depth: int
    tenant_id: Optional[str] = None
    tenant_active: int = 0
    tenant_queued: int = 0
    max_tenant_queue_depth: Optional[int] = None
    drain_per_s: Optional[float] = None

    def __post_init__(self) -> None:
        for name in ("active", "queued", "tenant_active", "tenant_queued"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PressureSourceError(f"{name} must be a non-negative int")
        for name in ("max_concurrency", "max_queue_depth"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise PressureSourceError(f"{name} must be a positive int")
        if self.max_tenant_queue_depth is not None:
            v = self.max_tenant_queue_depth
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise PressureSourceError("max_tenant_queue_depth must be a positive int")
        if self.drain_per_s is not None:
            d = float(self.drain_per_s)
            if not math.isfinite(d) or d < 0:
                raise PressureSourceError("drain_per_s must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class PressureSnapshot:
    load: float
    queue_depth: int
    max_queue_depth: int
    tenant_queue_depth: Optional[int]
    retry_after_s: float
    state: PressureState
    observed_at: datetime
    schema_version: int = SCHEMA_VERSION
    reason: str = field(default="", compare=False)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "load": self.load,
            "queue_depth": self.queue_depth,
            "max_queue_depth": self.max_queue_depth,
            "tenant_queue_depth": self.tenant_queue_depth,
            "retry_after_s": self.retry_after_s,
            "state": self.state.value,
            "observed_at": self.observed_at.isoformat(),
        }

    @property
    def admits(self) -> bool:
        return self.state is not PressureState.SHED

    def retry_after_header(self) -> Optional[str]:
        """``Retry-After`` value in whole seconds (ceil), or None when open."""
        if self.retry_after_s <= 0 and self.state is PressureState.OPEN:
            return None
        return str(max(1, int(math.ceil(self.retry_after_s))))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PressureSnapshot":
        if int(payload.get("schema_version", -1)) != SCHEMA_VERSION:
            raise ValueError("unsupported pressure schema_version")
        observed = datetime.fromisoformat(str(payload["observed_at"]))
        if observed.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        tq = payload.get("tenant_queue_depth")
        return cls(
            load=float(payload["load"]),
            queue_depth=int(payload["queue_depth"]),
            max_queue_depth=int(payload["max_queue_depth"]),
            tenant_queue_depth=None if tq is None else int(tq),
            retry_after_s=float(payload["retry_after_s"]),
            state=PressureState(str(payload["state"])),
            observed_at=observed,
        )


@runtime_checkable
class PressureSource(Protocol):
    def observe(self, tenant_id: Optional[str] = None) -> RawPressure: ...


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return max(0.0, min(1.0, value))


def estimate_retry_after(raw: RawPressure, load: float) -> float:
    """Seconds a caller should wait before retrying.

    With a known drain rate, the wait is the time to drain the excess queue
    above the throttle line. Without one, it scales linearly from 0 at the
    throttle line to ``MAX_RETRY_AFTER_S / 10`` at saturation. Always rounded to
    two decimals to match ``RateLimitError.context['retry_after_s']``.
    """
    if load < THROTTLE_LOAD:
        return 0.0
    if raw.drain_per_s:
        target = int(math.floor(raw.max_queue_depth * THROTTLE_LOAD))
        excess = max(1, raw.queued - target)
        seconds = excess / raw.drain_per_s
    else:
        span = (load - THROTTLE_LOAD) / (1.0 - THROTTLE_LOAD)
        seconds = (MAX_RETRY_AFTER_S / 10.0) * span
    seconds = max(MIN_RETRY_AFTER_S, min(MAX_RETRY_AFTER_S, seconds))
    return round(seconds, 2)


def classify(raw: RawPressure, *, now: Optional[datetime] = None) -> PressureSnapshot:
    concurrency_ratio = raw.active / raw.max_concurrency
    queue_ratio = raw.queued / raw.max_queue_depth
    load = _clamp01(max(concurrency_ratio, queue_ratio))
    tenant_full = (
        raw.tenant_id is not None
        and raw.max_tenant_queue_depth is not None
        and raw.tenant_queued >= raw.max_tenant_queue_depth
    )
    queue_full = raw.queued >= raw.max_queue_depth
    if raw.tenant_id is not None and raw.max_tenant_queue_depth:
        load = _clamp01(max(load, raw.tenant_queued / raw.max_tenant_queue_depth))
    retry_after = estimate_retry_after(raw, load)
    if queue_full or tenant_full or load >= SHED_LOAD:
        state = PressureState.SHED
        reason = "queue_full" if queue_full else "tenant_queue_full" if tenant_full else "load_shed"
        retry_after = max(retry_after, MIN_RETRY_AFTER_S)
    elif load >= THROTTLE_LOAD or retry_after > 0:
        state = PressureState.THROTTLE
        reason = "load_throttle"
    else:
        state = PressureState.OPEN
        reason = "open"
    return PressureSnapshot(
        load=round(load, 4),
        queue_depth=raw.queued,
        max_queue_depth=raw.max_queue_depth,
        tenant_queue_depth=raw.tenant_queued if raw.tenant_id is not None else None,
        retry_after_s=round(retry_after, 2),
        state=state,
        observed_at=(now or datetime.now(timezone.utc)),
        reason=reason,
    )


class DrainMeter:
    """EWMA of completions per second, used to turn queue depth into a wait."""

    def __init__(self, *, half_life_s: float = 10.0, clock: Callable[[], float] = time.monotonic) -> None:
        if not math.isfinite(half_life_s) or half_life_s <= 0:
            raise ValueError("half_life_s must be finite and positive")
        self._half_life = half_life_s
        self._clock = clock
        self._rate = 0.0
        self._last = clock()
        self._lock = threading.Lock()

    def _decay(self, now: float) -> None:
        dt = max(0.0, now - self._last)
        if dt:
            self._rate *= 0.5 ** (dt / self._half_life)
            self._last = now

    def record(self, completions: int = 1) -> None:
        if completions < 0:
            raise ValueError("completions must be non-negative")
        with self._lock:
            now = self._clock()
            self._decay(now)
            self._rate += completions * math.log(2) / self._half_life

    @property
    def rate(self) -> float:
        with self._lock:
            self._decay(self._clock())
            return self._rate


class InProcessPressureSource:
    """Counter-backed source for single-process deployments and tests."""

    def __init__(
        self,
        *,
        max_concurrency: int,
        max_queue_depth: int,
        max_tenant_queue_depth: Optional[int] = None,
        drain: Optional[DrainMeter] = None,
    ) -> None:
        RawPressure(0, 0, max_concurrency, max_queue_depth, max_tenant_queue_depth=max_tenant_queue_depth)
        self.max_concurrency = max_concurrency
        self.max_queue_depth = max_queue_depth
        self.max_tenant_queue_depth = max_tenant_queue_depth
        self.drain = drain or DrainMeter()
        self._active: Dict[str, int] = {}
        self._queued: Dict[str, int] = {}
        self._lock = threading.Lock()

    def _bump(self, table: Dict[str, int], tenant: str, delta: int) -> None:
        value = table.get(tenant, 0) + delta
        if value < 0:
            raise PressureSourceError("counter would go negative")
        if value:
            table[tenant] = value
        else:
            table.pop(tenant, None)

    def enqueue(self, tenant_id: str) -> None:
        with self._lock:
            self._bump(self._queued, tenant_id, 1)

    def start(self, tenant_id: str) -> None:
        with self._lock:
            self._bump(self._queued, tenant_id, -1)
            self._bump(self._active, tenant_id, 1)

    def finish(self, tenant_id: str) -> None:
        with self._lock:
            self._bump(self._active, tenant_id, -1)
        self.drain.record()

    def abandon(self, tenant_id: str) -> None:
        with self._lock:
            self._bump(self._queued, tenant_id, -1)

    def observe(self, tenant_id: Optional[str] = None) -> RawPressure:
        with self._lock:
            active = sum(self._active.values())
            queued = sum(self._queued.values())
            t_active = self._active.get(tenant_id, 0) if tenant_id else 0
            t_queued = self._queued.get(tenant_id, 0) if tenant_id else 0
        rate = self.drain.rate
        return RawPressure(
            active=active,
            queued=queued,
            max_concurrency=self.max_concurrency,
            max_queue_depth=self.max_queue_depth,
            tenant_id=tenant_id,
            tenant_active=t_active,
            tenant_queued=t_queued,
            max_tenant_queue_depth=self.max_tenant_queue_depth,
            drain_per_s=rate if rate > 0 else None,
        )


class LedgerPressureSource:
    """Read-only adapter over ``SqliteSharedPressureLedger.snapshot``."""

    def __init__(
        self,
        ledger: Any,
        scope: str,
        *,
        max_tenant_queue_depth: Optional[int] = None,
        drain: Optional[DrainMeter] = None,
    ) -> None:
        if not hasattr(ledger, "snapshot"):
            raise TypeError("ledger must expose snapshot(scope, tenant_id=...)")
        self._ledger = ledger
        self._scope = scope
        self._max_tenant_queue_depth = max_tenant_queue_depth
        self._drain = drain

    def observe(self, tenant_id: Optional[str] = None) -> RawPressure:
        try:
            snap = self._ledger.snapshot(self._scope, tenant_id=tenant_id)
        except Exception as exc:  # ledger errors are observation failures
            raise PressureSourceError(f"pressure ledger unavailable: {type(exc).__name__}") from exc
        rate = self._drain.rate if self._drain is not None else 0.0
        return RawPressure(
            active=int(snap.active),
            queued=int(snap.queued),
            max_concurrency=int(snap.max_concurrency),
            max_queue_depth=int(snap.max_queue_depth),
            tenant_id=tenant_id,
            tenant_active=int(getattr(snap, "tenant_active", 0)),
            tenant_queued=int(getattr(snap, "tenant_queued", 0)),
            max_tenant_queue_depth=self._max_tenant_queue_depth,
            drain_per_s=rate if rate > 0 else None,
        )


class PressureBoard:
    """Classifies a source with a tiny TTL cache so hot gates don't hammer it.

    When the source fails, the board fails closed: it reports ``shed`` with the
    maximum configured queue depth and a conservative retry-after.
    """

    def __init__(
        self,
        source: PressureSource,
        *,
        ttl_s: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
        fail_closed_retry_s: float = 5.0,
    ) -> None:
        if not math.isfinite(ttl_s) or ttl_s < 0:
            raise ValueError("ttl_s must be finite and non-negative")
        self._source = source
        self._ttl = ttl_s
        self._clock = clock
        self._fail_retry = round(float(fail_closed_retry_s), 2)
        self._cache: Dict[Optional[str], tuple[float, PressureSnapshot]] = {}
        self._lock = threading.Lock()
        self.source_failures = 0

    @property
    def source(self) -> PressureSource:
        return self._source

    def snapshot(self, tenant_id: Optional[str] = None) -> PressureSnapshot:
        now = self._clock()
        with self._lock:
            hit = self._cache.get(tenant_id)
            if hit is not None and now - hit[0] <= self._ttl:
                return hit[1]
        try:
            snap = classify(self._source.observe(tenant_id))
        except PressureSourceError:
            self.source_failures += 1
            snap = PressureSnapshot(
                load=1.0,
                queue_depth=0,
                max_queue_depth=getattr(self._source, "max_queue_depth", 1) or 1,
                tenant_queue_depth=0 if tenant_id is not None else None,
                retry_after_s=self._fail_retry,
                state=PressureState.SHED,
                observed_at=datetime.now(timezone.utc),
                reason="source_unavailable",
            )
            return snap
        with self._lock:
            self._cache[tenant_id] = (now, snap)
            if len(self._cache) > 4096:
                oldest = sorted(self._cache.items(), key=lambda kv: kv[1][0])[:1024]
                for key, _ in oldest:
                    self._cache.pop(key, None)
        return snap

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()


_DEFAULT_BOARD: Optional[PressureBoard] = None
_DEFAULT_LOCK = threading.Lock()


def _board_from_settings() -> PressureBoard:
    """Build the default board from existing pressure settings (read-only)."""
    from skeleton.config.settings import get_settings

    settings = get_settings()
    settings = getattr(settings, "engine", settings)
    max_q = int(settings.pressure_max_queue_depth)
    max_tq = int(settings.pressure_max_tenant_queue_depth)
    max_c = int(settings.pressure_max_concurrency)
    path = str(settings.pressure_state_path)
    if path != ":memory:":
        try:
            from skeleton.intelligence.shared_pressure import SqliteSharedPressureLedger

            ledger = SqliteSharedPressureLedger(path)
            return PressureBoard(LedgerPressureSource(ledger, settings.pressure_scope, max_tenant_queue_depth=max_tq))
        except Exception:
            pass
    return PressureBoard(
        InProcessPressureSource(max_concurrency=max_c, max_queue_depth=max_q, max_tenant_queue_depth=max_tq)
    )


def default_board() -> PressureBoard:
    global _DEFAULT_BOARD
    with _DEFAULT_LOCK:
        if _DEFAULT_BOARD is None:
            _DEFAULT_BOARD = _board_from_settings()
        return _DEFAULT_BOARD


def install_board(board: Optional[PressureBoard]) -> None:
    """Replace (or with None, reset) the process default board."""
    global _DEFAULT_BOARD
    with _DEFAULT_LOCK:
        _DEFAULT_BOARD = board


def snapshot(tenant_id: Optional[str] = None) -> PressureSnapshot:
    """In-process helper for the gate plane: same fields as the HTTP API."""
    return default_board().snapshot(tenant_id)
