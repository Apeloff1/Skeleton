"""Memory warmer — preemptive KV-cache refresh for prefix fillers.

Ported from ``backend/services/mag.py`` (Track B3 of the build plan).
Fillers are canonical, hash-versioned prompt blocks (system prefix,
curriculum digests, domain canon) whose job is to occupy the front of the
context window at the cached billing rate. The warmer refreshes each filler
BEFORE its TTL expires (at 80% of TTL), so a live request never pays a
cold-cache rebuild.

Pure domain with injectable clock; the async loop is opt-in
(:meth:`MemoryWarmer.start`) and only runs when an event loop exists.
Persistence is the caller's concern — the backend service's JSON store
stays backend-side until the adapter cutover (B4).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from .prefix_renderer import CAGPrefix

# A builder returns a fresh CAGPrefix for its key (re-render from source).
FillerBuilder = Callable[[], Union[CAGPrefix, Awaitable[CAGPrefix]]]

DEFAULT_TTL_S = 3300      # 55 min — under provider cache TTL
REFRESH_AT = 0.8          # refresh at 80% of the TTL window
WARMER_INTERVAL_S = 60


@dataclass
class Filler:
    """One preemptively-warmed token filler."""
    key: str
    sha: str
    text: str
    tokens: int
    ttl_s: int
    built_at: float
    refreshed_at: float
    refresh_count: int = 0

    @property
    def expires_at(self) -> float:
        return self.refreshed_at + self.ttl_s

    @property
    def refresh_due_at(self) -> float:
        """Preemptive point: 80% through the TTL window."""
        return self.refreshed_at + self.ttl_s * REFRESH_AT

    def is_fresh(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) < self.expires_at

    def needs_refresh(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) >= self.refresh_due_at

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "sha": self.sha,
            "tokens": self.tokens,
            "ttl_s": self.ttl_s,
            "built_at": self.built_at,
            "refreshed_at": self.refreshed_at,
            "refresh_count": self.refresh_count,
            "fresh": self.is_fresh(),
            "expires_in_s": max(0, round(self.expires_at - time.time())),
        }


class FillerStore:
    """In-memory filler registry with builder wiring.

    Persistence is deliberately out of scope here (pure domain); callers
    that need restart-survival snapshot ``all()``/``put()`` themselves.
    """

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.time
        self._fillers: Dict[str, Filler] = {}
        self._builders: Dict[str, FillerBuilder] = {}

    def register_builder(self, key: str, builder: FillerBuilder,
                         ttl_s: int = DEFAULT_TTL_S) -> None:
        self._builders[key] = builder
        if key in self._fillers:
            self._fillers[key].ttl_s = ttl_s

    def put(self, filler: Filler) -> None:
        self._fillers[filler.key] = filler

    def get(self, key: str) -> Optional[Filler]:
        return self._fillers.get(key)

    def all(self) -> List[Filler]:
        return list(self._fillers.values())

    def due(self, now: Optional[float] = None) -> List[str]:
        return [k for k, f in self._fillers.items() if f.needs_refresh(now)]

    def builder_keys(self) -> List[str]:
        return sorted(self._builders)

    def builder_for(self, key: str) -> Optional[FillerBuilder]:
        return self._builders.get(key)

    def stats(self) -> dict:
        now = self._now()
        fresh = sum(1 for f in self._fillers.values() if f.is_fresh(now))
        return {
            "fillers": len(self._fillers),
            "fresh": fresh,
            "stale": len(self._fillers) - fresh,
            "cached_tokens": sum(f.tokens for f in self._fillers.values()),
            "refresh_total": sum(f.refresh_count for f in self._fillers.values()),
        }


class MemoryWarmer:
    """Background refresher: warms fillers before their TTL lapses."""

    def __init__(
        self,
        store: FillerStore,
        *,
        interval_s: int = WARMER_INTERVAL_S,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.store = store
        self.interval_s = interval_s
        self._now = clock or time.time
        self._task: Optional[asyncio.Task] = None
        self._stop: Optional[asyncio.Event] = None
        self.cycles = 0
        self.refreshes = 0

    def _stop_event(self) -> asyncio.Event:
        # Created lazily: asyncio.Event() must be made inside a running loop.
        if self._stop is None:
            self._stop = asyncio.Event()
        return self._stop

    async def refresh_one(self, key: str) -> Optional[Filler]:
        builder = self.store.builder_for(key)
        if builder is None:
            return None
        result = builder()
        prefix: CAGPrefix = await result if asyncio.iscoroutine(result) else result
        now = self._now()
        old = self.store.get(key)
        filler = Filler(
            key=key,
            sha=prefix.sha,
            text=prefix.text,
            tokens=prefix.tokens,
            ttl_s=old.ttl_s if old else DEFAULT_TTL_S,
            built_at=old.built_at if old else now,
            refreshed_at=now,
            refresh_count=(old.refresh_count + 1) if old else 1,
        )
        self.store.put(filler)
        self.refreshes += 1
        return filler

    async def warm_all(self, force: bool = False) -> List[str]:
        now = self._now()
        targets = list(self.store.builder_keys()) if force else self.store.due(now)
        # Also prime builders that have no filler yet (first boot).
        for key in self.store.builder_keys():
            if self.store.get(key) is None and key not in targets:
                targets.append(key)
        warmed: List[str] = []
        for key in targets:
            try:
                if await self.refresh_one(key) is not None:
                    warmed.append(key)
            except Exception:
                continue  # one bad filler must not stall the cycle
        return warmed

    async def _loop(self) -> None:
        stop = self._stop_event()
        while not stop.is_set():
            try:
                await self.warm_all()
                self.cycles += 1
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop yet (e.g. imported outside app runtime); skip
        if self._task is None or self._task.done():
            self._stop_event().clear()
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()

    def stats(self) -> Dict[str, Any]:
        return {
            "cycles": self.cycles,
            "refreshes": self.refreshes,
            "running": bool(self._task and not self._task.done()),
        }
