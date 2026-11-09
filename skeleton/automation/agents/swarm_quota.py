"""Thread-safe hierarchical quota accounting for tenants, queues and worker classes."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


def _integer(value: int, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if positive and value < 1:
        raise ValueError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class Quota:
    max_queued: int = 10_000
    max_leased: int = 1_000
    max_payload_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        _integer(self.max_queued, "max_queued", positive=True)
        _integer(self.max_leased, "max_leased", positive=True)
        _integer(self.max_payload_bytes, "max_payload_bytes", positive=True)


@dataclass(frozen=True, slots=True)
class Usage:
    queued: int = 0
    leased: int = 0
    payload_bytes: int = 0


class QuotaExceeded(ValueError):
    pass


class QuotaLedger:
    def __init__(self, default: Quota | None = None) -> None:
        self.default = default or Quota()
        self._limits: dict[str, Quota] = {}
        self._usage: dict[str, Usage] = {}
        self._lock = RLock()

    @staticmethod
    def _scope(scope: str) -> str:
        scope = scope.strip()
        if not scope:
            raise ValueError("quota scope must not be empty")
        return scope

    @staticmethod
    def _delta(value: int, name: str) -> int:
        return _integer(value, name)

    def configure(self, scope: str, quota: Quota) -> None:
        scope = self._scope(scope)
        with self._lock:
            current = self._usage.get(scope)
            if current is not None:
                if current.queued > quota.max_queued or current.leased > quota.max_leased or current.payload_bytes > quota.max_payload_bytes:
                    raise QuotaExceeded(f"new quota below current usage: {scope}")
            self._limits[scope] = quota

    def configured_limits(self) -> dict[str, Quota]:
        """Return an immutable-value copy of configured quota overrides."""
        with self._lock:
            return dict(sorted(self._limits.items()))

    def limit(self, scope: str) -> Quota:
        scope = self._scope(scope)
        with self._lock:
            return self._limits.get(scope, self.default)

    def usage(self, scope: str) -> Usage:
        scope = self._scope(scope)
        with self._lock:
            return self._usage.get(scope, Usage())

    def reserve(self, scope: str, *, queued: int = 0, leased: int = 0, payload_bytes: int = 0) -> Usage:
        scope = self._scope(scope)
        queued = self._delta(queued, "queued")
        leased = self._delta(leased, "leased")
        payload_bytes = self._delta(payload_bytes, "payload_bytes")
        with self._lock:
            usage = self._usage.get(scope, Usage())
            quota = self._limits.get(scope, self.default)
            next_usage = Usage(
                queued=usage.queued + queued,
                leased=usage.leased + leased,
                payload_bytes=usage.payload_bytes + payload_bytes,
            )
            if min(next_usage.queued, next_usage.leased, next_usage.payload_bytes) < 0:
                raise QuotaExceeded("quota accounting underflow")
            if next_usage.queued > quota.max_queued:
                raise QuotaExceeded(f"queued quota exceeded: {scope}")
            if next_usage.leased > quota.max_leased:
                raise QuotaExceeded(f"leased quota exceeded: {scope}")
            if next_usage.payload_bytes > quota.max_payload_bytes:
                raise QuotaExceeded(f"payload quota exceeded: {scope}")
            self._usage[scope] = next_usage
            return next_usage

    def release(self, scope: str, **amounts: int) -> Usage:
        normalized = {name: self._delta(value, name) for name, value in amounts.items()}
        unknown = set(normalized) - {"queued", "leased", "payload_bytes"}
        if unknown:
            raise TypeError(f"unknown quota release fields: {', '.join(sorted(unknown))}")
        return self.reserve(
            scope,
            queued=-normalized.get("queued", 0),
            leased=-normalized.get("leased", 0),
            payload_bytes=-normalized.get("payload_bytes", 0),
        )

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                scope: {
                    "queued": usage.queued,
                    "leased": usage.leased,
                    "payload_bytes": usage.payload_bytes,
                }
                for scope, usage in sorted(self._usage.items())
            }
