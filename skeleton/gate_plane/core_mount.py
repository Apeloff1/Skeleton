"""Mount Backend core v1 (/api/v1/core/*) behind the v1 edge and schedule dispatch.

Middleware-owned composition hook (see docs/architecture/contracts/backend_core_v1.md).
Extend-only: does not edit ``skeleton/api/server.py`` or any Backend file. The
scheduler is attached by wrapping ``app.router.lifespan_context`` so it composes
with whatever lifespan the app already has.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skeleton.api.v1_edge.registry import RouteRegistry, RouteSpec

log = logging.getLogger(__name__)

CORE_PREFIX = "/core"
WRITE_SCOPE = "core:write"
READ_SCOPE = "core:read"


def core_v1_route_specs() -> List[RouteSpec]:
    """Edge specs for every endpoint in the core v1 contract table."""
    r = dict(scopes=frozenset({READ_SCOPE}), quota_class="core_read", owner="backend")
    w = dict(scopes=frozenset({WRITE_SCOPE}), quota_class="core_write", owner="backend")
    p = CORE_PREFIX
    return [
        RouteSpec("POST", p + "/webhooks", idempotent_writes=True, **w),
        RouteSpec("GET", p + "/webhooks", **r),
        RouteSpec("GET", p + "/webhooks/{webhook_id}", **r),
        RouteSpec("PATCH", p + "/webhooks/{webhook_id}", **w),
        RouteSpec("DELETE", p + "/webhooks/{webhook_id}", **w),
        RouteSpec("POST", p + "/webhooks/{webhook_id}/rotate-secret", **w),
        RouteSpec("GET", p + "/webhooks/{webhook_id}/deliveries", **r),
        RouteSpec("GET", p + "/deliveries/{delivery_id}", **r),
        RouteSpec("POST", p + "/deliveries/{delivery_id}/replay", idempotent_writes=True, **w),
        RouteSpec("POST", p + "/events", **w),
    ]


def register_core_v1_routes(registry: RouteRegistry) -> int:
    """Register core specs; already-present (method, path) pairs are skipped."""
    have = {(s.method, s.path) for s in registry.routes()}
    n = 0
    for spec in core_v1_route_specs():
        if (spec.method, spec.path) not in have:
            registry.register(spec)
            n += 1
    return n


def _default_router_module():
    from routes import core_v1_webhooks  # Backend adapter; backend/ on sys.path

    return core_v1_webhooks


def _default_dispatch(limit: int):
    from core.core_v1_webhooks import get_runtime

    return get_runtime().webhooks.dispatch_due(limit)


def mount_core_v1_router(app, loader: Callable[[], Any] = _default_router_module) -> bool:
    """Contract mount: install_error_handler + include_router. Idempotent per app."""
    state = getattr(app, "state", None)
    if state is not None and getattr(state, "core_v1_mounted", False):
        return False
    mod = loader()
    mod.install_error_handler(app)
    app.include_router(mod.router)
    if state is not None:
        state.core_v1_mounted = True
    return True


@dataclass
class SchedulerStats:
    ticks: int = 0
    skipped_overlap: int = 0
    errors: int = 0
    consecutive_errors: int = 0
    last_report: Any = None
    last_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {k: (repr(v) if k == "last_report" and v is not None else v)
                for k, v in self.__dict__.items()}


@dataclass
class DispatchScheduler:
    """Periodic ``dispatch_due`` runner.

    - interval with +/- ``jitter`` fraction, exponential backoff after errors (capped);
    - single-flight: a tick never overlaps a running one (overlaps are counted, not queued);
    - error isolation: exceptions are logged and counted, the loop keeps going;
    - clean shutdown: ``stop()`` cancels the sleep and waits for an in-flight tick
      up to ``shutdown_timeout`` (the sync call runs in a worker thread; leases make
      an abandoned claim safe per the contract).
    """

    dispatch: Callable[[int], Any] = _default_dispatch
    interval: float = 5.0
    jitter: float = 0.2
    limit: int = 50
    max_backoff: float = 60.0
    shutdown_timeout: float = 10.0
    rng: random.Random = field(default_factory=random.Random)
    stats: SchedulerStats = field(default_factory=SchedulerStats)

    def __post_init__(self):
        if self.interval <= 0:
            raise ValueError("interval must be > 0")
        if not 0 <= self.jitter < 1:
            raise ValueError("jitter must be in [0, 1)")
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        self._task: Optional[asyncio.Task] = None
        self._stop: Optional[asyncio.Event] = None
        self._inflight: Optional[asyncio.Future] = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def next_delay(self) -> float:
        base = self.interval
        if self.stats.consecutive_errors:
            base = min(self.max_backoff, self.interval * (2 ** self.stats.consecutive_errors))
        return max(0.0, base * (1 + self.rng.uniform(-self.jitter, self.jitter)))

    async def tick(self) -> bool:
        """Run one dispatch unless one is already in flight. Returns True if it ran."""
        if self._inflight is not None and not self._inflight.done():
            self.stats.skipped_overlap += 1
            return False
        loop = asyncio.get_running_loop()
        self._inflight = loop.run_in_executor(None, self.dispatch, self.limit)
        try:
            self.stats.last_report = await asyncio.shield(self._inflight)
            self.stats.consecutive_errors = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # isolate: never kill the loop
            self.stats.errors += 1
            self.stats.consecutive_errors += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("core v1 dispatch_due failed: %s", self.stats.last_error)
        finally:
            self.stats.ticks += 1
        return True

    async def _run(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            await self.tick()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._stop.wait(), self.next_delay())

    def start(self) -> None:
        if self.running:
            return
        self._stop = asyncio.Event()
        self._task = asyncio.get_running_loop().create_task(self._run(), name="core-v1-dispatch")

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop is not None
        self._stop.set()
        try:
            await asyncio.wait_for(asyncio.shield(self._task), self.shutdown_timeout)
        except asyncio.TimeoutError:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None


def attach_scheduler(app, scheduler: DispatchScheduler) -> None:
    """Compose scheduler start/stop around the app's existing lifespan."""
    router = app.router
    inner = router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(a):
        async with inner(a) as state:
            scheduler.start()
            try:
                yield state
            finally:
                await scheduler.stop()

    router.lifespan_context = lifespan
    app.state.core_v1_scheduler = scheduler


def install_core_v1(app, *, registry: Optional[RouteRegistry] = None,
                    scheduler: Optional[DispatchScheduler] = None,
                    loader: Callable[[], Any] = _default_router_module,
                    schedule: bool = True) -> Dict[str, Any]:
    """create_app hook: edge specs + router mount + dispatch scheduler."""
    added = register_core_v1_routes(registry) if registry is not None else 0
    mounted = mount_core_v1_router(app, loader)
    sched = None
    if schedule and mounted:
        sched = scheduler or DispatchScheduler()
        attach_scheduler(app, sched)
    return {"edge_routes_added": added, "mounted": mounted, "scheduled": sched is not None}
