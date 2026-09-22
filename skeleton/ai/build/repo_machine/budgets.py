"""Explicit machine budgets for context, change scope and parallel work."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class ZoneBudget:
    zone: str
    max_changed_files: int
    max_changed_lines: int
    max_parallel_objectives: int
    context_file_limit: int
    rationale: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "max_changed_files": self.max_changed_files,
            "max_changed_lines": self.max_changed_lines,
            "max_parallel_objectives": self.max_parallel_objectives,
            "context_file_limit": self.context_file_limit,
            "rationale": list(self.rationale),
        }


def derive_zone_budgets(model: RepositoryModel) -> tuple[ZoneBudget, ...]:
    cycle_zones = {zone for cycle in model.cycles for zone in cycle}
    result: list[ZoneBudget] = []
    for subsystem in model.subsystems:
        max_files = 20
        max_lines = 3000
        parallel = 2
        context = 120
        reasons: list[str] = []

        if subsystem.criticality == "critical":
            max_files = 8
            max_lines = 1200
            parallel = 1
            context = 80
            reasons.append("critical subsystem uses conservative mutation budget")
        elif subsystem.criticality == "high":
            max_files = 12
            max_lines = 2000
            parallel = 1
            context = 100
            reasons.append("high-criticality subsystem limits parallel mutation")

        if subsystem.name in cycle_zones:
            max_files = min(max_files, 8)
            max_lines = min(max_lines, 1000)
            parallel = 1
            reasons.append("cycle participant requires narrow changes")

        if subsystem.file_count >= 500:
            context = 160
            reasons.append("large subsystem receives larger retrieval context")
        if subsystem.file_count >= 1500:
            context = 220
            max_files = min(max_files, 12)
            reasons.append("very large subsystem uses smaller change batches")

        if subsystem.test_files == 0 and subsystem.code_files:
            max_files = min(max_files, 6)
            max_lines = min(max_lines, 800)
            reasons.append("untested code surface requires conservative edits")

        result.append(ZoneBudget(
            zone=subsystem.name,
            max_changed_files=max_files,
            max_changed_lines=max_lines,
            max_parallel_objectives=parallel,
            context_file_limit=context,
            rationale=tuple(reasons),
        ))

    return tuple(sorted(result, key=lambda item: item.zone))
