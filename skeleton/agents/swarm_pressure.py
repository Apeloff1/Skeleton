"""Pressure classification for queue, resident capacity, and worker saturation."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.agents.swarm_gc import capacity
from skeleton.agents.swarm_runtime import SwarmRuntime


@dataclass(frozen=True, slots=True)
class PressureReport:
    level: str
    queue_ratio: float
    resident_ratio: float
    saturation: float
    queued: int
    available_slots: int


def classify_pressure(runtime: SwarmRuntime) -> PressureReport:
    snap = runtime.snapshot()
    cap = capacity(runtime)
    total_slots = snap.available_slots + snap.leased
    saturation = snap.leased / total_slots if total_slots else (1.0 if snap.queued else 0.0)
    queue_ratio = snap.queued / max(1, snap.available_slots)
    resident_ratio = cap["resident"] / max(1, cap["maximum"])
    level = "normal"
    if queue_ratio >= 10 or resident_ratio >= 0.8 or saturation >= 0.9:
        level = "elevated"
    if queue_ratio >= 50 or resident_ratio >= 0.95 or (snap.queued and snap.available_slots == 0):
        level = "critical"
    return PressureReport(
        level,
        round(queue_ratio, 6),
        round(resident_ratio, 6),
        round(saturation, 6),
        snap.queued,
        snap.available_slots,
    )
