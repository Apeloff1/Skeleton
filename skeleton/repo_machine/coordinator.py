"""High-level machine repository coordinator for always-on autonomous stewardship."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .budgets import derive_zone_budgets
from .config import MachineConfig
from .context_budget import allocate_context
from .docs_map import undocumented_code_zones
from .governance import validate_governance
from .growth import growth_recommendations
from .health import repository_health
from .hotspots import structural_hotspots
from .layout import analyze_layout
from .model import RepositoryModel
from .naming import analyze_naming
from .package_graph import package_findings
from .refactor import plan_refactors
from .reorganize import propose_reorganization
from .steward import select_steward_plan
from .test_affinity import uncovered_sources
from .work_queue import MachineWorkQueue


@dataclass(frozen=True, slots=True)
class CoordinatorSnapshot:
    repository_fingerprint: str
    health: dict[str, object]
    steward: dict[str, object]
    queue_ready: tuple[dict[str, object], ...]
    growth: tuple[dict[str, object], ...]
    hotspots: tuple[dict[str, object], ...]
    refactors: tuple[dict[str, object], ...]
    reorganization: tuple[dict[str, object], ...]
    governance: tuple[dict[str, object], ...]
    package_findings: tuple[dict[str, object], ...]
    undocumented_zones: tuple[str, ...]
    uncovered_source_sample: tuple[str, ...]
    layout: dict[str, object]
    zone_budgets: tuple[dict[str, object], ...]
    context_allocations: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "repository_fingerprint": self.repository_fingerprint,
            "health": self.health,
            "steward": self.steward,
            "queue_ready": list(self.queue_ready),
            "growth": list(self.growth),
            "hotspots": list(self.hotspots),
            "refactors": list(self.refactors),
            "reorganization": list(self.reorganization),
            "governance": list(self.governance),
            "package_findings": list(self.package_findings),
            "undocumented_zones": list(self.undocumented_zones),
            "uncovered_source_sample": list(self.uncovered_source_sample),
            "layout": self.layout,
            "zone_budgets": list(self.zone_budgets),
            "context_allocations": list(self.context_allocations),
        }


def build_coordinator_snapshot(
    model: RepositoryModel,
    config: MachineConfig,
    *,
    queue: MachineWorkQueue | None = None,
    active_conflicts: Iterable[str] = (),
) -> CoordinatorSnapshot:
    queue = queue or MachineWorkQueue()
    queue.refresh(model, config)
    ready = queue.ready(active_conflicts=active_conflicts, limit=6)
    return CoordinatorSnapshot(
        repository_fingerprint=model.fingerprint,
        health=repository_health(model).as_dict(),
        steward=select_steward_plan(
            model,
            active_conflicts=active_conflicts,
            max_objectives=3,
        ).as_dict(),
        queue_ready=tuple(item.as_dict() for item in ready),
        growth=tuple(
            item.as_dict()
            for item in growth_recommendations(model, limit=16)
        ),
        hotspots=tuple(
            item.as_dict()
            for item in structural_hotspots(model, limit=24)
        ),
        refactors=tuple(
            item.as_dict()
            for item in plan_refactors(model, limit=12)
        ),
        reorganization=tuple(
            item.as_dict()
            for item in propose_reorganization(model, config, limit=16)
        ),
        governance=tuple(
            item.as_dict()
            for item in validate_governance(model, config)[:24]
        ),
        package_findings=tuple(package_findings(model)[:24]),
        undocumented_zones=undocumented_code_zones(model)[:32],
        uncovered_source_sample=uncovered_sources(model)[:64],
        layout=analyze_layout(model).as_dict(),
        zone_budgets=tuple(
            item.as_dict()
            for item in derive_zone_budgets(model)
        ),
        context_allocations=tuple(
            item.as_dict()
            for item in allocate_context(model)
        ),
    )
