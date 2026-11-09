"""Hardware and resource pressure heuristics without changing crawler limits.

Only operator-supplied, measured, bounded telemetry is consumed. No new
resource budget or model admission authority is created. Output is a
conservative advisory stop/reduce decision, not a dispatch grant.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .budget import BudgetProjection
from .contracts import CampaignMandate, digest, finite, integer


@dataclass(frozen=True)
class ResourceObservation:
    at: float
    memory_available_bytes: int
    memory_total_bytes: int
    disk_free_bytes: int
    cpu_pressure: float
    worker_count: int
    active_fetches: int
    observed_p99_latency_ms: float | None = None

    def __post_init__(self):
        finite(self.at, "resource observation time")
        integer(self.memory_available_bytes, "available memory", 0, 2**63 - 1)
        integer(self.memory_total_bytes, "total memory", 1, 2**63 - 1)
        if self.memory_available_bytes > self.memory_total_bytes:
            raise ValueError("memory observations contradict")
        integer(self.disk_free_bytes, "free disk", 0, 2**63 - 1)
        finite(self.cpu_pressure, "cpu pressure", 0, 1)
        integer(self.worker_count, "worker count", 0, 10000)
        integer(self.active_fetches, "active fetches", 0, 10000)
        if self.active_fetches > self.worker_count:
            raise ValueError("fetch count exceeds workers")
        if self.observed_p99_latency_ms is not None:
            finite(self.observed_p99_latency_ms, "observed tail latency", 0, 3_600_000)


@dataclass(frozen=True)
class PressureDecision:
    pressure: str
    recommend_pause: bool
    recommend_max_slice_steps: int
    recommend_max_parallel_workers: int
    expected_memory_headroom_bytes: int
    reasons: tuple[str, ...]
    observed_latency_p99_ms: float | None
    decision_digest: str
    physical_capacity_certified: bool = False


def recommend_crawl_pressure(
    mandate: CampaignMandate,
    budget: BudgetProjection,
    observations: Iterable[ResourceObservation], *,
    now: float,
    authorized: bool,
    max_observations: int = 32,
) -> PressureDecision:
    mandate.admit(now=now, authorized=authorized)
    integer(max_observations, "observation bound", 1, 128)
    values = tuple(observations)
    if not values or len(values) > max_observations:
        raise ValueError("measured telemetry window required")
    for item in values:
        if not isinstance(item, ResourceObservation):
            raise TypeError("typed measured telemetry required")
        if item.at > now:
            raise ValueError("future resource telemetry cannot justify admission")
    if any(a.at > b.at for a, b in zip(values, values[1:])):
        raise ValueError("nonmonotonic resource samples")
    most_recent = values[-1]
    reasons = list(budget.blockers)
    if now - most_recent.at > 60:
        reasons.append("resource_telemetry_stale")
    if most_recent.memory_available_bytes < 64 * 1024 * 1024:
        reasons.append("memory_headroom_low")
    if most_recent.disk_free_bytes < 100 * 1024 * 1024:
        reasons.append("disk_headroom_low")
    if most_recent.cpu_pressure >= 0.90:
        reasons.append("cpu_pressure_critical")
    if most_recent.active_fetches >= 4:
        reasons.append("canonical_slice_concurrency_saturated")
    if most_recent.observed_p99_latency_ms is not None and most_recent.observed_p99_latency_ms > 15_000:
        reasons.append("tail_latency_over_budget")
    critical = bool(reasons)
    high = most_recent.cpu_pressure >= 0.75 or (
        most_recent.memory_available_bytes < 256 * 1024 * 1024
    )
    if high and not critical:
        reasons.append("reduce_parallel_pressure")
    pressure = "blocked" if critical else "degraded" if high else "nominal"
    steps = 0 if critical else 1 if high else min(4, budget.requests_remaining)
    workers = 0 if critical else min(1, most_recent.worker_count) if high else min(4, most_recent.worker_count)
    payload = {
        "mandate": mandate.fingerprint,
        "budget": asdict(budget),
        "observations": [asdict(x) for x in values],
        "pressure": pressure,
        "recommended_steps": steps,
        "recommended_workers": workers,
        "reasons": reasons,
    }
    return PressureDecision(
        pressure=pressure, recommend_pause=critical,
        recommend_max_slice_steps=steps,
        recommend_max_parallel_workers=workers,
        expected_memory_headroom_bytes=most_recent.memory_available_bytes,
        reasons=tuple(sorted(set(reasons))),
        observed_latency_p99_ms=most_recent.observed_p99_latency_ms,
        decision_digest=digest(payload),
    )
