"""Pressure sources for the gate plane.

* :class:`PackHSource` — reads Backend's Pack H in-process helper
  ``skeleton.api.pack_h.admit_pressure.snapshot(tenant_id=None)``, injected
  directly or registered by the API layer (see :mod:`.registry`; the gate
  plane must not import ``skeleton.api``). Works before Pack H lands and
  picks it up as soon as it is registered. No Backend module is edited.
* :class:`AdaptiveGateSource` — derives a snapshot from the Pack A/root
  ``AdaptiveGate`` token bucket (read-only ``stats()``). Always available
  in-process, so it is the default fallback.
* :class:`PackAPoolSource` — optional contributor from Pack A's
  ``BufferPool`` leases and ``Coalescer`` in-flight fetches.
* :class:`CompositeSource` — worst-of several sources.
* :class:`FallbackChain` — first healthy, fresh source wins.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from skeleton.gate_plane.backpressure.snapshot import (
    SCHEMA_VERSION,
    PressureState,
    PressureUnavailable,
    PressureView,
    coerce_view,
    derive_state,
    iso_now,
    round_retry_after,
)
from skeleton.gate_plane.backpressure.registry import adaptive_gate as registered_adaptive_gate
from skeleton.gate_plane.backpressure.registry import pressure_provider
from skeleton.gate_plane.s2s.clock import Clock, system_clock

#: Backend's Pack H helper — registered by the API layer, never imported here.
PACK_H_MODULE = "skeleton.api.pack_h.admit_pressure"


@runtime_checkable
class PressureSource(Protocol):
    name: str

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        """Return a view or raise :class:`PressureUnavailable`."""


class PackHSource:
    """Backend Pack H admit-pressure reader (in-process, no HTTP hop).

    ``snapshot_fn`` is Pack H's ``snapshot(tenant_id=None)``; when omitted the
    provider registered via :func:`register_pressure_provider` is used, looked
    up on every read so a late registration is picked up without a restart.
    """

    name = "pack_h"

    def __init__(
        self,
        snapshot_fn: Optional[Callable[..., Any]] = None,
        *,
        resolver: Optional[Callable[[], Optional[Callable[..., Any]]]] = None,
    ) -> None:
        self._fn = snapshot_fn
        self._resolver = resolver or pressure_provider
        self._last_error: Optional[str] = None

    def _resolve(self) -> Callable[..., Any]:
        fn = self._fn if self._fn is not None else self._resolver()
        if fn is None:
            self._last_error = "no Pack H pressure provider registered"
            raise PressureUnavailable(self._last_error)
        return fn

    @property
    def available(self) -> bool:
        try:
            self._resolve()
            return True
        except PressureUnavailable:
            return False

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        fn = self._resolve()
        try:
            raw = fn(tenant_id=tenant_id)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"snapshot failed: {type(exc).__name__}"
            raise PressureUnavailable(f"pack_h {self._last_error}") from None
        try:
            view = coerce_view(raw, source=self.name)
        except PressureUnavailable as exc:
            self._last_error = str(exc)
            raise
        self._last_error = None
        return view

    def status(self) -> Dict[str, Any]:
        return {"injected": self._fn is not None, "available": self.available, "last_error": self._last_error}


class AdaptiveGateSource:
    """Snapshot derived from an ``AdaptiveGate`` token bucket.

    ``load = 1 - tokens/capacity``; ``queue_depth`` is the consumed tokens and
    ``max_queue_depth`` the capacity, so an empty bucket reads as a full
    queue (``shed``). When empty, ``retry_after_s`` is the time to refill one
    token. ``gate=None`` uses the gate registered via
    :func:`register_adaptive_gate` (read-only ``stats()``).
    """

    name = "adaptive_gate"

    def __init__(self, gate: Any = None, *, clock: Optional[Clock] = None) -> None:
        self._gate = gate
        self._clock = clock or system_clock()

    def _gate_obj(self) -> Any:
        gate = self._gate if self._gate is not None else registered_adaptive_gate()
        if gate is None:
            raise PressureUnavailable("no AdaptiveGate injected or registered")
        return gate

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        gate = self._gate_obj()
        try:
            stats = gate.stats()
            capacity = int(stats.get("capacity", 0))
            tokens = int(stats.get("tokens_available", 0))
        except Exception as exc:  # noqa: BLE001
            raise PressureUnavailable(f"adaptive gate stats failed: {type(exc).__name__}") from None
        refill = getattr(gate, "_refill_per_sec", None)
        try:
            refill_per_sec = float(refill) if refill is not None else 1.0
        except (TypeError, ValueError):
            refill_per_sec = 1.0
        tokens = max(0, min(tokens, capacity)) if capacity > 0 else 0
        load = 1.0 if capacity <= 0 else 1.0 - tokens / capacity
        queue_depth = capacity - tokens if capacity > 0 else 1
        max_queue = capacity if capacity > 0 else 1
        retry_after = 0.0
        if tokens == 0:
            retry_after = 1.0 / refill_per_sec if refill_per_sec > 0 else 30.0
        state = derive_state(load, queue_depth, max_queue, retry_after)
        return PressureView(
            schema_version=SCHEMA_VERSION,
            load=round(load, 4),
            queue_depth=queue_depth,
            max_queue_depth=max_queue,
            tenant_queue_depth=None,
            retry_after_s=round_retry_after(retry_after),
            state=state,
            observed_at=iso_now(self._clock.now()),
            source=self.name,
        )


class PackAPoolSource:
    """Pressure from Pack A ``BufferPool`` leases and ``Coalescer`` in-flight keys.

    Reads only public ``stats()`` / ``leased`` plus the length of the
    coalescer's in-flight map; never mutates either object.
    """

    name = "pack_a_pool"

    def __init__(
        self,
        *,
        pool: Any = None,
        coalescer: Any = None,
        max_leases: int = 256,
        max_in_flight: int = 1024,
        clock: Optional[Clock] = None,
    ) -> None:
        if pool is None and coalescer is None:
            raise ValueError("PackAPoolSource needs a pool and/or a coalescer")
        if max_leases <= 0 or max_in_flight <= 0:
            raise ValueError("max_leases and max_in_flight must be > 0")
        self.pool = pool
        self.coalescer = coalescer
        self.max_leases = int(max_leases)
        self.max_in_flight = int(max_in_flight)
        self._clock = clock or system_clock()

    def _leased(self) -> int:
        if self.pool is None:
            return 0
        stats = self.pool.stats() if hasattr(self.pool, "stats") else {"leased": getattr(self.pool, "leased", 0)}
        return int(stats.get("leased", 0))

    def _in_flight(self) -> int:
        if self.coalescer is None:
            return 0
        flights = getattr(self.coalescer, "_in_flight", None)
        lock = getattr(self.coalescer, "_lock", None)
        if flights is None:
            return 0
        if lock is not None:
            with lock:
                return len(flights)
        return len(flights)

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        try:
            leased = self._leased()
            in_flight = self._in_flight()
        except Exception as exc:  # noqa: BLE001
            raise PressureUnavailable(f"pack_a pool stats failed: {type(exc).__name__}") from None
        load = max(leased / self.max_leases, in_flight / self.max_in_flight)
        load = min(1.0, max(0.0, load))
        queue_depth = in_flight
        state = derive_state(load, queue_depth, self.max_in_flight, 0.0)
        retry_after = 0.0 if state is PressureState.OPEN else round_retry_after(0.25 + load)
        return PressureView(
            schema_version=SCHEMA_VERSION,
            load=round(load, 4),
            queue_depth=queue_depth,
            max_queue_depth=self.max_in_flight,
            tenant_queue_depth=None,
            retry_after_s=retry_after,
            state=state,
            observed_at=iso_now(self._clock.now()),
            source=self.name,
        )


class StaticSource:
    """Fixed or callable-backed source (tests, chaos, manual overrides)."""

    def __init__(self, view_or_fn: Any, *, name: str = "static") -> None:
        self.name = name
        self._v = view_or_fn

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        v = self._v(tenant_id) if callable(self._v) else self._v
        if isinstance(v, BaseException):
            raise v
        if isinstance(v, PressureView):
            return v
        return coerce_view(v, source=self.name)


class CompositeSource:
    """Worst-of: highest effective severity wins, ties broken by load.

    Sources that are unavailable are skipped; if all are, raises.
    """

    def __init__(self, sources: Sequence[PressureSource], *, name: str = "composite") -> None:
        if not sources:
            raise ValueError("CompositeSource needs at least one source")
        self.name = name
        self.sources = list(sources)

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        best: Optional[PressureView] = None
        errors: List[str] = []
        for src in self.sources:
            try:
                v = src.read(tenant_id)
            except PressureUnavailable as exc:
                errors.append(f"{src.name}: {exc}")
                continue
            if best is None or (v.effective_state.severity, v.load) > (best.effective_state.severity, best.load):
                best = v
        if best is None:
            raise PressureUnavailable("; ".join(errors) or "no sources")
        return best


class FallbackChain:
    """Try sources in order; skip unavailable or stale (``max_age_s``) ones."""

    def __init__(
        self,
        sources: Sequence[PressureSource],
        *,
        max_age_s: float = 5.0,
        clock: Optional[Clock] = None,
        name: str = "fallback",
    ) -> None:
        if not sources:
            raise ValueError("FallbackChain needs at least one source")
        self.name = name
        self.sources = list(sources)
        self.max_age_s = float(max_age_s)
        self._clock = clock or system_clock()
        self._lock = threading.Lock()
        self._served: Dict[str, int] = {}
        self._skipped: Dict[str, int] = {}

    def _bump(self, d: Dict[str, int], key: str) -> None:
        with self._lock:
            d[key] = d.get(key, 0) + 1

    def read(self, tenant_id: Optional[str] = None) -> PressureView:
        reasons: List[str] = []
        for src in self.sources:
            try:
                v = src.read(tenant_id)
            except PressureUnavailable as exc:
                self._bump(self._skipped, src.name)
                reasons.append(f"{src.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - a buggy source must not break admission
                self._bump(self._skipped, src.name)
                reasons.append(f"{src.name}: {type(exc).__name__}")
                continue
            age = v.age_s(self._clock.now())
            if age > self.max_age_s:
                self._bump(self._skipped, src.name)
                reasons.append(f"{src.name}: stale ({age:.1f}s)")
                continue
            self._bump(self._served, src.name)
            return v
        raise PressureUnavailable("; ".join(reasons))

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {"served": dict(self._served), "skipped": dict(self._skipped)}


def default_pressure_source(*, clock: Optional[Clock] = None, gate: Any = None) -> FallbackChain:
    """Pack H first, AdaptiveGate fallback — the contract agreed with Backend."""
    clk = clock or system_clock()
    return FallbackChain([PackHSource(), AdaptiveGateSource(gate, clock=clk)], clock=clk)


__all__ = [
    "AdaptiveGateSource",
    "CompositeSource",
    "FallbackChain",
    "PACK_H_MODULE",
    "PackAPoolSource",
    "PackHSource",
    "PressureSource",
    "StaticSource",
    "default_pressure_source",
]
