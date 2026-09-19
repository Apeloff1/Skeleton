"""Fail-closed health proofs for distributed AI shell authority dependencies.

A process can be locally healthy while the state systems that make execution
single-use or auditable are unavailable.  This module gives production workers
an explicit, bounded health contract for those dependencies.  A versioned-state
probe may perform a private compare-and-swap heartbeat to prove both read and
write authority before a sealed execution proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
import time
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Protocol

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend


class AuthorityHealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AuthorityHealthResult:
    name: str
    state: AuthorityHealthState
    checked_at: float
    latency_seconds: float
    detail: str = ""
    revision: int | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 128:
            raise ValueError("invalid authority health result name")
        if not isinstance(self.state, AuthorityHealthState):
            object.__setattr__(
                self,
                "state",
                AuthorityHealthState(str(self.state)),
            )
        for name in ("checked_at", "latency_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if len(self.detail) > 512:
            raise ValueError("authority health detail too long")
        if self.revision is not None and (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("authority health revision must be positive")
        metadata = {
            str(key): str(value)
            for key, value in dict(self.metadata).items()
        }
        if len(metadata) > 32:
            raise ValueError("too many authority health metadata fields")
        if any(
            not key
            or len(key) > 128
            or len(value) > 512
            for key, value in metadata.items()
        ):
            raise ValueError("invalid authority health metadata")
        object.__setattr__(self, "checked_at", float(self.checked_at))
        object.__setattr__(self, "latency_seconds", float(self.latency_seconds))
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    @property
    def healthy(self) -> bool:
        return self.state is AuthorityHealthState.HEALTHY

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "checked_at": self.checked_at,
            "latency_seconds": self.latency_seconds,
            "detail": self.detail,
            "revision": self.revision,
            "metadata": dict(self.metadata),
        }


class AuthorityHealthProbe(Protocol):
    @property
    def name(self) -> str:
        ...

    def check(self) -> AuthorityHealthResult:
        ...


class CallableAuthorityHealthProbe:
    """Adapter for a bounded synchronous application-specific health check."""

    def __init__(
        self,
        name: str,
        check: Callable[[], bool],
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not name or len(name) > 128:
            raise ValueError("invalid authority health probe name")
        self._name = name
        self._check = check
        self._clock = clock
        self._monotonic = monotonic

    @property
    def name(self) -> str:
        return self._name

    def check(self) -> AuthorityHealthResult:
        started = self._monotonic()
        try:
            healthy = bool(self._check())
        except Exception as exc:
            return AuthorityHealthResult(
                self.name,
                AuthorityHealthState.UNAVAILABLE,
                self._clock(),
                max(0.0, self._monotonic() - started),
                detail=f"probe raised {type(exc).__name__}",
            )
        return AuthorityHealthResult(
            self.name,
            (
                AuthorityHealthState.HEALTHY
                if healthy
                else AuthorityHealthState.UNAVAILABLE
            ),
            self._clock(),
            max(0.0, self._monotonic() - started),
        )


class VersionedStateHealthProbe:
    """Prove read access and optionally CAS write access to a state backend."""

    def __init__(
        self,
        name: str,
        backend: VersionedStateBackend,
        *,
        instance_id: str,
        namespace: str = "shell-ai-authority-health",
        require_write: bool = True,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not name or len(name) > 128:
            raise ValueError("invalid authority health probe name")
        if not instance_id or len(instance_id) > 256:
            raise ValueError("invalid authority health instance_id")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid authority health namespace")
        if not isinstance(require_write, bool):
            raise ValueError("require_write must be boolean")
        self._name = name
        self.backend = backend
        self.instance_id = instance_id
        self.namespace = namespace
        self.require_write = require_write
        self._clock = clock
        self._monotonic = monotonic

    @property
    def name(self) -> str:
        return self._name

    @property
    def key(self) -> str:
        digest = hashlib.sha256(self.instance_id.encode()).hexdigest()[:32]
        return f"{self.name}:{digest}"

    def check(self) -> AuthorityHealthResult:
        started = self._monotonic()
        now = self._clock()
        try:
            current = self.backend.get(self.namespace, self.key)
            if not self.require_write:
                return AuthorityHealthResult(
                    self.name,
                    AuthorityHealthState.HEALTHY,
                    now,
                    max(0.0, self._monotonic() - started),
                    revision=None if current is None else current.revision,
                    metadata={"mode": "read"},
                )

            expected_revision = 0 if current is None else current.revision
            payload = {
                "instance_id_hash": hashlib.sha256(
                    self.instance_id.encode()
                ).hexdigest(),
                "checked_at": now,
                "previous_revision": expected_revision,
            }
            updated = self.backend.compare_and_swap(
                self.namespace,
                self.key,
                expected_revision=expected_revision,
                value=payload,
            )
            return AuthorityHealthResult(
                self.name,
                AuthorityHealthState.HEALTHY,
                now,
                max(0.0, self._monotonic() - started),
                revision=updated.revision,
                metadata={"mode": "read-write-cas"},
            )
        except DistributedStateConflict:
            # A single instance key should not normally conflict.  Treat the
            # store as degraded rather than retrying indefinitely; the caller
            # can fail closed and a later health cycle may recover.
            return AuthorityHealthResult(
                self.name,
                AuthorityHealthState.DEGRADED,
                now,
                max(0.0, self._monotonic() - started),
                detail="CAS heartbeat conflict",
            )
        except Exception as exc:
            return AuthorityHealthResult(
                self.name,
                AuthorityHealthState.UNAVAILABLE,
                now,
                max(0.0, self._monotonic() - started),
                detail=f"backend probe raised {type(exc).__name__}",
            )


@dataclass(frozen=True)
class AuthorityHealthPolicy:
    required: frozenset[str]
    max_latency_seconds: float = 2.0
    max_result_age_seconds: float = 15.0

    def __post_init__(self) -> None:
        required = frozenset(str(item) for item in self.required)
        if len(required) > 64:
            raise ValueError("authority health required dependency bound exceeded")
        if any(not item or len(item) > 128 for item in required):
            raise ValueError("invalid required authority health dependency")
        object.__setattr__(self, "required", required)
        for name in ("max_latency_seconds", "max_result_age_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0.0
            ):
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, float(value))

    def to_dict(self) -> dict[str, object]:
        return {
            "required": sorted(self.required),
            "max_latency_seconds": self.max_latency_seconds,
            "max_result_age_seconds": self.max_result_age_seconds,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AuthorityHealthReport:
    ok: bool
    results: tuple[AuthorityHealthResult, ...]
    reasons: tuple[str, ...]
    policy_digest: str
    observed_at: float

    def __post_init__(self) -> None:
        if len(self.policy_digest) != 64:
            raise ValueError("authority health policy digest invalid")
        names = [item.name for item in self.results]
        if len(names) != len(set(names)):
            raise ValueError("duplicate authority health results")

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "results": [item.to_dict() for item in self.results],
            "reasons": list(self.reasons),
            "policy_digest": self.policy_digest,
            "observed_at": self.observed_at,
        }


class AIAuthorityHealthGuard:
    """Evaluate named authority dependencies under one fail-closed policy."""

    def __init__(
        self,
        probes: Iterable[AuthorityHealthProbe],
        policy: AuthorityHealthPolicy,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        items = tuple(sorted(tuple(probes), key=lambda item: item.name))
        if len(items) > 64:
            raise ValueError("authority health probe bound exceeded")
        names = [item.name for item in items]
        if len(names) != len(set(names)):
            raise ValueError("duplicate authority health probe")
        missing = policy.required.difference(names)
        if missing:
            raise ValueError(
                "required authority health probes missing: "
                + ", ".join(sorted(missing))
            )
        self.probes = items
        self.policy = policy
        self._clock = clock
        self._last_report: AuthorityHealthReport | None = None

    @property
    def last_report(self) -> AuthorityHealthReport | None:
        return self._last_report

    def inspect(self) -> AuthorityHealthReport:
        observed_at = self._clock()
        results = tuple(probe.check() for probe in self.probes)
        reasons: list[str] = []
        by_name = {item.name: item for item in results}

        for name in sorted(self.policy.required):
            result = by_name[name]
            if result.state is not AuthorityHealthState.HEALTHY:
                reasons.append(
                    f"required authority dependency {name} is {result.state.value}"
                )
            if result.latency_seconds > self.policy.max_latency_seconds:
                reasons.append(
                    f"required authority dependency {name} exceeded latency budget"
                )
            age = max(0.0, observed_at - result.checked_at)
            if age > self.policy.max_result_age_seconds:
                reasons.append(
                    f"required authority dependency {name} health result is stale"
                )

        report = AuthorityHealthReport(
            not reasons,
            results,
            tuple(reasons),
            self.policy.digest,
            observed_at,
        )
        self._last_report = report
        return report

    def require(self) -> AuthorityHealthReport:
        report = self.inspect()
        if not report.ok:
            raise RuntimeError("; ".join(report.reasons))
        return report
