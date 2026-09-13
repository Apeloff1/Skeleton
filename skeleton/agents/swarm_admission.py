"""Admission and backpressure policy for the bounded swarm runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    accepted: bool
    reason: str
    pressure: float
    matching_workers: int
    matching_slots: int


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """Fail-closed overload protection without coupling execution to transport."""

    max_queue_pressure: float = 100.0
    require_capability_route: bool = False
    reject_when_no_workers: bool = False

    def __post_init__(self) -> None:
        if self.max_queue_pressure <= 0:
            raise ValueError("max_queue_pressure must be positive")

    def evaluate(self, runtime: SwarmRuntime, task: SwarmTask) -> AdmissionDecision:
        workers = runtime.workers()
        required = task.required_capabilities
        matching = tuple(w for w in workers if required.issubset(w.capabilities))
        matching_slots = sum(w.available for w in matching)
        queued = runtime.snapshot().queued
        denominator = max(1, matching_slots or runtime.snapshot().available_slots)
        pressure = queued / denominator

        if self.reject_when_no_workers and not workers:
            return AdmissionDecision(False, "no workers registered", pressure, 0, 0)
        if self.require_capability_route and required and not matching:
            return AdmissionDecision(False, "no worker satisfies required capabilities", pressure, 0, 0)
        if pressure >= self.max_queue_pressure:
            return AdmissionDecision(False, "queue pressure limit reached", pressure, len(matching), matching_slots)
        return AdmissionDecision(True, "accepted", pressure, len(matching), matching_slots)


def capability_coverage(runtime: SwarmRuntime, capabilities: Iterable[str]) -> dict[str, int]:
    """Return worker/slot coverage for each capability for scheduling diagnostics."""
    coverage: dict[str, int] = {}
    for capability in capabilities:
        workers = tuple(w for w in runtime.workers() if capability in w.capabilities)
        coverage[f"{capability}.workers"] = len(workers)
        coverage[f"{capability}.slots"] = sum(w.available for w in workers)
    return coverage
