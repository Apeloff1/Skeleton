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


@dataclass(frozen=True, slots=True)
class SharedQuota:
    """Host-configured aggregate ceiling over explicit tenants, or all tenants."""

    name: str
    limit: Quota
    members: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or self.name != self.name.strip() or len(self.name) > 256:
            raise ValueError("invalid shared quota name")
        if not isinstance(self.limit, Quota):
            raise TypeError("invalid shared quota limit")
        if self.members is not None and (
            type(self.members) is not frozenset or not 1 <= len(self.members) <= 10000
            or any(type(m) is not str or not m or m != m.strip() or len(m) > 256 for m in self.members)
        ):
            raise ValueError("invalid shared quota members")

    def includes(self, tenant: str) -> bool:
        return self.members is None or tenant in self.members


class QuotaExceeded(ValueError):
    pass


class QuotaLedger:
    def __init__(self, default: Quota | None = None) -> None:
        self.default = default or Quota()
        self._limits: dict[str, Quota] = {}
        self._usage: dict[str, Usage] = {}
        self._shared: dict[str, SharedQuota] = {}
        self._shared_usage: dict[str, Usage] = {}
        self._lock = RLock()

    @staticmethod
    def _check(scope: str, value: Usage, quota: Quota) -> None:
        if min(value.queued, value.leased, value.payload_bytes) < 0:
            raise QuotaExceeded("quota accounting underflow")
        for field, maximum in (("queued", quota.max_queued), ("leased", quota.max_leased),
                               ("payload_bytes", quota.max_payload_bytes)):
            if getattr(value, field) > maximum:
                raise QuotaExceeded(f"{field.replace('_bytes', '')} quota exceeded: {scope}")

    def configure_shared(self, policy: SharedQuota) -> None:
        """Replace an aggregate ceiling atomically without discarding occupied slots."""
        if not isinstance(policy, SharedQuota):
            raise TypeError("invalid shared quota policy")
        with self._lock:
            if policy.name not in self._shared and len(self._shared) >= 256:
                raise QuotaExceeded("shared quota policy ceiling")
            values = [usage for tenant, usage in self._usage.items() if policy.includes(tenant)]
            total = Usage(sum(u.queued for u in values), sum(u.leased for u in values),
                          sum(u.payload_bytes for u in values))
            self._check(policy.name, total, policy.limit)
            self._shared[policy.name] = policy
            self._shared_usage[policy.name] = total

    def configured_shared(self) -> tuple[SharedQuota, ...]:
        with self._lock:
            return tuple(self._shared[key] for key in sorted(self._shared))

    def shared_snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {key: {"queued": u.queued, "leased": u.leased, "payload_bytes": u.payload_bytes}
                    for key, u in sorted(self._shared_usage.items())}

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
            self._check(scope, next_usage, quota)
            aggregate: dict[str, Usage] = {}
            for name, policy in self._shared.items():
                if not policy.includes(scope):
                    continue
                current = self._shared_usage[name]
                projected = Usage(current.queued + queued, current.leased + leased,
                                  current.payload_bytes + payload_bytes)
                self._check(name, projected, policy.limit)
                aggregate[name] = projected
            # All applicable ceilings must fit before publishing any delta.
            self._usage[scope] = next_usage
            self._shared_usage.update(aggregate)
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
