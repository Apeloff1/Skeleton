"""Runtime resilience primitives mined from Newmove2's browser game engine.

The original implementation mixed React/browser APIs with reusable ideas. This
module keeps the useful mechanisms: bounded object pools, TTL/LRU caches, sliding
error budgets, error classification, and deterministic recovery-mode decisions.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


class ErrorClass(StrEnum):
    MEMORY = "memory"
    NETWORK = "network"
    RENDER = "render"
    AUDIO = "audio"
    GRAPHICS = "graphics"
    UNKNOWN = "unknown"


class ObjectPool(Generic[T]):
    def __init__(self, factory: Callable[[], T], *, initial_size: int = 0, max_size: int = 100) -> None:
        if initial_size < 0 or max_size <= 0 or initial_size > max_size:
            raise ValueError("invalid pool sizing")
        self._factory = factory
        self._max_size = max_size
        self._pool = [factory() for _ in range(initial_size)]
        self.active_count = 0

    def acquire(self) -> T:
        self.active_count += 1
        return self._pool.pop() if self._pool else self._factory()

    def release(self, obj: T) -> None:
        if self.active_count <= 0:
            raise RuntimeError("pool release without matching acquire")
        self.active_count -= 1
        reset = getattr(obj, "reset", None)
        if callable(reset):
            reset()
        if len(self._pool) < self._max_size:
            self._pool.append(obj)

    def clear(self) -> None:
        self._pool.clear()
        self.active_count = 0

    def stats(self) -> dict[str, int]:
        return {"pooled": len(self._pool), "active": self.active_count, "max": self._max_size}


@dataclass(slots=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TtlLruCache(Generic[T]):
    def __init__(self, max_size: int = 100, *, clock: Callable[[], float] = monotonic) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self.clock = clock
        self._items: OrderedDict[str, _CacheEntry[T]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> T | None:
        entry = self._items.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at <= self.clock():
            del self._items[key]
            self.misses += 1
            return None
        self._items.move_to_end(key)
        self.hits += 1
        return entry.value

    def set(self, key: str, value: T, *, ttl_seconds: float = 60.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if key in self._items:
            del self._items[key]
        while len(self._items) >= self.max_size:
            self._items.popitem(last=False)
        self._items[key] = _CacheEntry(value=value, expires_at=self.clock() + ttl_seconds)

    def clear_expired(self) -> int:
        now = self.clock()
        expired = [key for key, entry in self._items.items() if entry.expires_at <= now]
        for key in expired:
            del self._items[key]
        return len(expired)

    def stats(self) -> dict[str, float | int]:
        total = self.hits + self.misses
        return {
            "size": len(self._items),
            "max": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total else 0.0,
        }


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    error_class: ErrorClass
    should_reset: bool
    recovery_action: str
    recent_error_count: int


class CrashGuard:
    def __init__(
        self,
        *,
        max_errors: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_errors <= 0 or window_seconds <= 0:
            raise ValueError("invalid crash guard limits")
        self.max_errors = max_errors
        self.window_seconds = window_seconds
        self.clock = clock
        self._errors: deque[tuple[float, ErrorClass]] = deque()
        self.recovery_mode = False

    @staticmethod
    def classify(error: BaseException | str) -> ErrorClass:
        message = str(error).lower()
        name = error.__class__.__name__.lower() if isinstance(error, BaseException) else ""
        if "memory" in message or name == "memoryerror":
            return ErrorClass.MEMORY
        if "network" in message or "fetch" in message or "timeout" in message:
            return ErrorClass.NETWORK
        if "render" in message or "react" in message:
            return ErrorClass.RENDER
        if "audio" in message:
            return ErrorClass.AUDIO
        if "canvas" in message or "webgl" in message or "graphics" in message:
            return ErrorClass.GRAPHICS
        return ErrorClass.UNKNOWN

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._errors and self._errors[0][0] < cutoff:
            self._errors.popleft()

    def handle(self, error: BaseException | str) -> RecoveryDecision:
        now = self.clock()
        self._trim(now)
        kind = self.classify(error)
        self._errors.append((now, kind))
        count = len(self._errors)
        if count >= self.max_errors:
            self.recovery_mode = True
            return RecoveryDecision(kind, True, "full_reset", count)
        action = {
            ErrorClass.MEMORY: "clear_caches",
            ErrorClass.AUDIO: "disable_audio",
            ErrorClass.RENDER: "reduce_quality",
            ErrorClass.GRAPHICS: "reduce_quality",
            ErrorClass.NETWORK: "retry_with_backoff",
            ErrorClass.UNKNOWN: "none",
        }[kind]
        return RecoveryDecision(kind, False, action, count)

    def reset(self) -> None:
        self._errors.clear()
        self.recovery_mode = False

    def status(self) -> dict[str, object]:
        now = self.clock()
        self._trim(now)
        return {"recent_errors": len(self._errors), "recovery_mode": self.recovery_mode}
