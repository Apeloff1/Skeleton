"""Health probe evaluation for deploy gates.

Probes are evaluated from observations supplied by a runtime adapter
(status code, latency, body markers); this module never performs I/O.
A rollout step is healthy only when every required probe passes on a
quorum of replicas within the configured latency budget.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

from skeleton.build.delivery._util import DeliveryError, require_id

VERDICTS = ("healthy", "degraded", "unhealthy")


@dataclass(frozen=True)
class ProbeSpec:
    probe_id: str
    path: str
    expect_status: tuple[int, ...] = (200,)
    max_latency_ms: int = 1000
    body_marker: str | None = None
    required: bool = True

    def __post_init__(self) -> None:
        require_id(self.probe_id, field="probe_id")
        if not self.path.startswith("/"):
            raise DeliveryError("probe path must start with /")
        if not self.expect_status or any(not 100 <= s <= 599 for s in self.expect_status):
            raise DeliveryError("expect_status must be HTTP status codes")
        if not 1 <= self.max_latency_ms <= 120_000:
            raise DeliveryError("max_latency_ms out of range")


@dataclass(frozen=True)
class ProbeObservation:
    probe_id: str
    replica: str
    status: int | None
    latency_ms: int | None
    body: str = ""
    error: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    replica: str
    passed: bool
    reason: str


@dataclass(frozen=True)
class HealthReport:
    verdict: str
    results: tuple[ProbeResult, ...]
    failing_probes: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return self.verdict == "healthy"


def evaluate_observation(spec: ProbeSpec, obs: ProbeObservation) -> ProbeResult:
    if obs.probe_id != spec.probe_id:
        raise DeliveryError("observation does not match probe")
    if obs.error:
        return ProbeResult(spec.probe_id, obs.replica, False, f"error:{obs.error}")
    if obs.status is None:
        return ProbeResult(spec.probe_id, obs.replica, False, "no-response")
    if type(obs.status) is not int or not 100 <= obs.status <= 599:
        return ProbeResult(spec.probe_id, obs.replica, False, "invalid-status")
    if obs.status not in spec.expect_status:
        return ProbeResult(spec.probe_id, obs.replica, False, f"status:{obs.status}")
    if (type(obs.latency_ms) is not int or obs.latency_ms < 0
            or obs.latency_ms > spec.max_latency_ms):
        return ProbeResult(spec.probe_id, obs.replica, False, f"latency:{obs.latency_ms}")
    if spec.body_marker is not None and spec.body_marker not in obs.body:
        return ProbeResult(spec.probe_id, obs.replica, False, "body-marker-missing")
    return ProbeResult(spec.probe_id, obs.replica, True, "ok")


def evaluate(
    specs: Sequence[ProbeSpec],
    observations: Iterable[ProbeObservation],
    *,
    replicas: Sequence[str],
    quorum: float = 1.0,
) -> HealthReport:
    if not specs:
        raise DeliveryError("at least one probe is required")
    if not replicas:
        raise DeliveryError("at least one replica is required")
    if (type(quorum) not in (int, float) or not math.isfinite(quorum)
            or not 0 < quorum <= 1):
        raise DeliveryError("quorum must be a finite fraction in (0, 1]")
    if (any(type(replica) is not str or not replica for replica in replicas)
            or len(set(replicas)) != len(replicas)):
        raise DeliveryError("replicas must be distinct nonempty identities")
    ids = [s.probe_id for s in specs]
    if len(ids) != len(set(ids)):
        raise DeliveryError("duplicate probe ids")
    spec_map = {s.probe_id: s for s in specs}
    latest: dict[tuple[str, str], ProbeObservation] = {}
    for obs in observations:
        if obs.probe_id not in spec_map:
            raise DeliveryError(f"unknown probe {obs.probe_id!r}")
        if obs.replica in replicas:
            latest[(obs.probe_id, obs.replica)] = obs
    results: list[ProbeResult] = []
    failing_required: list[str] = []
    failing_optional: list[str] = []
    # Never round quorum down to thousandths: 0.5001 of two replicas
    # requires both, not one. Duplicate replica identities are rejected above.
    needed = max(1, math.ceil(quorum * len(replicas)))
    for spec in specs:
        passes = 0
        for replica in replicas:
            obs = latest.get((spec.probe_id, replica))
            result = (
                evaluate_observation(spec, obs)
                if obs is not None
                else ProbeResult(spec.probe_id, replica, False, "missing")
            )
            results.append(result)
            passes += result.passed
        if passes < needed:
            (failing_required if spec.required else failing_optional).append(spec.probe_id)
    if failing_required:
        verdict = "unhealthy"
    elif failing_optional:
        verdict = "degraded"
    else:
        verdict = "healthy"
    return HealthReport(verdict, tuple(results), tuple(sorted(failing_required + failing_optional)))


def specs_from_config(health: Mapping) -> tuple[ProbeSpec, ...]:
    """Build probe specs from an environment config ``health`` block."""
    base = ProbeSpec(
        "liveness",
        health["path"],
        tuple(health.get("expect_status", (200,))),
        int(health.get("max_latency_ms", 1000)),
        health.get("body_marker"),
    )
    extra = []
    for item in health.get("probes", ()):
        extra.append(
            ProbeSpec(
                item["id"],
                item["path"],
                tuple(item.get("expect_status", (200,))),
                int(item.get("max_latency_ms", 1000)),
                item.get("body_marker"),
                bool(item.get("required", True)),
            )
        )
    return (base, *extra)
