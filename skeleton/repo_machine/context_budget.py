"""Allocate bounded model context across repository subsystems."""
from __future__ import annotations

from dataclasses import dataclass

from .hotspots import structural_hotspots
from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class ContextAllocation:
    zone: str
    byte_budget: int
    priority: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "byte_budget": self.byte_budget,
            "priority": self.priority,
            "reasons": list(self.reasons),
        }


def allocate_context(
    model: RepositoryModel,
    *,
    total_bytes: int = 96_000,
    minimum_zone_bytes: int = 2_000,
) -> tuple[ContextAllocation, ...]:
    if isinstance(total_bytes, bool) or not isinstance(total_bytes, int) or total_bytes < 8_000:
        raise ValueError("total_bytes must be at least 8000")
    zones = list(model.subsystems)
    if not zones:
        return ()
    hot_counts: dict[str, int] = {}
    for hotspot in structural_hotspots(model, limit=256):
        hot_counts[hotspot.zone] = hot_counts.get(hotspot.zone, 0) + hotspot.score

    weights: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for subsystem in zones:
        weight = 10
        why: list[str] = []
        if subsystem.criticality == "critical":
            weight += 20
            why.append("critical subsystem")
        elif subsystem.criticality == "high":
            weight += 10
            why.append("high-criticality subsystem")
        if subsystem.code_files:
            weight += min(20, subsystem.code_files // 10)
            why.append("code-bearing subsystem")
        if hot_counts.get(subsystem.name):
            weight += min(25, hot_counts[subsystem.name] // 20)
            why.append("structural hotspots")
        if subsystem.name == "unclassified":
            weight += 10
            why.append("unclassified surface requires navigation attention")
        weights[subsystem.name] = weight
        reasons[subsystem.name] = why

    minimum_total = minimum_zone_bytes * len(zones)
    distributable = max(0, total_bytes - minimum_total)
    total_weight = max(1, sum(weights.values()))
    allocations: list[ContextAllocation] = []
    assigned = 0
    for index, subsystem in enumerate(sorted(zones, key=lambda item: item.name)):
        if index == len(zones) - 1:
            budget = max(
                minimum_zone_bytes,
                total_bytes - assigned,
            )
        else:
            extra = int(distributable * weights[subsystem.name] / total_weight)
            budget = minimum_zone_bytes + extra
            assigned += budget
        allocations.append(ContextAllocation(
            zone=subsystem.name,
            byte_budget=budget,
            priority=weights[subsystem.name],
            reasons=tuple(reasons[subsystem.name]),
        ))
    return tuple(sorted(
        allocations,
        key=lambda item: (-item.priority, item.zone),
    ))
