"""Graceful shutdown coordination for the kernel.

Stopping a live swarm is a distributed-systems problem in miniature:
drain the queue, stop intake, let in-flight work finish, then release
resources — in that order, or you either lose work or hang forever.

- :class:`ShutdownPhase` — the ordered ladder: RUNNING → DRAINING →
  STOPPING → STOPPED (plus FAILED for a hung drain).
- :class:`ShutdownCoordinator` — components register with a teardown
  hook and a drain predicate; ``initiate()`` flips the intake gate,
  ``poll()`` advances phases only when every component reports drained,
  and a hard deadline converts a hung drain into FAILED with the
  laggards named, so the bus can publish exactly who held things up.

Pure state machine; the actual signal handling lives in the process
entrypoint, which calls :meth:`initiate`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from .errors import KernelError


class ShutdownError(KernelError):
    code = "KRN.SHUTDOWN"


class ShutdownPhase(str, Enum):
    RUNNING = "RUNNING"
    DRAINING = "DRAINING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass
class Component:
    name: str
    is_drained: Callable[[], bool]
    teardown: Callable[[], None]
    teardown_done: bool = False


class ShutdownCoordinator:
    """One coordinator per kernel instance."""

    def __init__(self, *, drain_timeout_s: float = 30.0,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if drain_timeout_s <= 0:
            raise ShutdownError("drain timeout must be positive",
                                context={"timeout": drain_timeout_s})
        self.drain_timeout_s = drain_timeout_s
        self._now = clock or time.monotonic
        self._phase = ShutdownPhase.RUNNING
        self._initiated_at: Optional[float] = None
        self._components: Dict[str, Component] = {}
        self._errors: List[str] = []

    @property
    def phase(self) -> ShutdownPhase:
        return self._phase

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, *, is_drained: Callable[[], bool],
                 teardown: Callable[[], None]) -> None:
        if self._phase is not ShutdownPhase.RUNNING:
            raise ShutdownError("cannot register during shutdown",
                                context={"component": name,
                                         "phase": self._phase.value})
        if name in self._components:
            raise ShutdownError("component already registered",
                                context={"component": name})
        self._components[name] = Component(name, is_drained, teardown)

    def deregister(self, name: str) -> bool:
        return self._components.pop(name, None) is not None

    # ------------------------------------------------------------------
    # The ladder
    # ------------------------------------------------------------------

    def initiate(self) -> ShutdownPhase:
        """Flip the intake gate. Idempotent."""
        if self._phase is ShutdownPhase.RUNNING:
            self._phase = ShutdownPhase.DRAINING
            self._initiated_at = self._now()
        return self._phase

    def accepting_work(self) -> bool:
        return self._phase is ShutdownPhase.RUNNING

    def poll(self) -> ShutdownPhase:
        """Advance the ladder if conditions allow. Call on a timer."""
        if self._phase is ShutdownPhase.DRAINING:
            laggards = self._laggards()
            elapsed = self._now() - (self._initiated_at or self._now())
            if not laggards:
                self._phase = ShutdownPhase.STOPPING
            elif elapsed >= self.drain_timeout_s:
                self._errors.append(
                    f"drain timed out; laggards: {', '.join(laggards)}")
                self._phase = ShutdownPhase.FAILED
        if self._phase is ShutdownPhase.STOPPING:
            self._teardown_all()
            self._phase = (ShutdownPhase.STOPPED if not self._errors
                           else ShutdownPhase.FAILED)
        return self._phase

    def force_stop(self) -> ShutdownPhase:
        """Skip the drain — teardown whatever exists, report the damage."""
        if self._phase in (ShutdownPhase.STOPPED, ShutdownPhase.FAILED):
            return self._phase
        laggards = self._laggards()
        if laggards:
            self._errors.append(
                f"forced stop abandoned: {', '.join(laggards)}")
        self._teardown_all()
        self._phase = ShutdownPhase.FAILED if self._errors else ShutdownPhase.STOPPED
        return self._phase

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _laggards(self) -> List[str]:
        out = []
        for name, comp in self._components.items():
            try:
                if not comp.is_drained():
                    out.append(name)
            except Exception as exc:  # a broken drain check is a laggard
                out.append(f"{name}(check-error:{exc!r})")
        return sorted(out)

    def _teardown_all(self) -> None:
        # teardown in reverse registration order — dependents first
        for comp in reversed(list(self._components.values())):
            if comp.teardown_done:
                continue
            try:
                comp.teardown()
            except Exception as exc:
                self._errors.append(f"teardown({comp.name}) failed: {exc!r}")
            finally:
                comp.teardown_done = True

    def report(self) -> Dict[str, object]:
        return {
            "phase": self._phase.value,
            "components": sorted(self._components),
            "laggards": self._laggards() if self._phase is ShutdownPhase.DRAINING else [],
            "errors": list(self._errors),
            "elapsed_s": (round(self._now() - self._initiated_at, 3)
                          if self._initiated_at is not None else None),
        }
