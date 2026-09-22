"""Structural growth guidance for keeping large repositories machine-navigable."""
from __future__ import annotations

from dataclasses import dataclass

from .metrics import structural_metrics
from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class GrowthRecommendation:
    code: str
    priority: int
    zone: str
    objective: str
    rationale: str

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "priority": self.priority,
            "zone": self.zone,
            "objective": self.objective,
            "rationale": self.rationale,
        }


def growth_recommendations(
    model: RepositoryModel,
    *,
    limit: int = 32,
) -> tuple[GrowthRecommendation, ...]:
    metrics = structural_metrics(model)
    recommendations: list[GrowthRecommendation] = []

    for zone in metrics.zones:
        if zone.line_share >= 0.35 and zone.lines > 5000:
            recommendations.append(GrowthRecommendation(
                code="growth.split-concentration",
                priority=85,
                zone=zone.zone,
                objective="Split concentrated subsystem into explicit cohesive child domains.",
                rationale=f"zone owns {zone.line_share:.1%} of indexed lines",
            ))
        if zone.outbound_edges >= 20 and zone.instability >= 0.70:
            recommendations.append(GrowthRecommendation(
                code="growth.reduce-instability",
                priority=80,
                zone=zone.zone,
                objective="Introduce stable interfaces or adapters around outbound dependency fanout.",
                rationale=f"{zone.outbound_edges} outbound dependency evidences; instability={zone.instability:.2f}",
            ))
        if zone.files >= 100 and zone.test_ratio < 0.15:
            recommendations.append(GrowthRecommendation(
                code="growth.raise-test-density",
                priority=75,
                zone=zone.zone,
                objective="Create subsystem-local regression suites before expanding the zone further.",
                rationale=f"{zone.files} files with test/code ratio {zone.test_ratio:.2f}",
            ))

    if metrics.unclassified_ratio >= 0.10:
        recommendations.append(GrowthRecommendation(
            code="growth.classify-surface",
            priority=90,
            zone="unclassified",
            objective="Reduce the unclassified surface by extending canonical machine zones.",
            rationale=f"{metrics.unclassified_ratio:.1%} of indexed files lack explicit zone ownership",
        ))
    if metrics.cycle_count:
        recommendations.append(GrowthRecommendation(
            code="growth.break-cycles",
            priority=95,
            zone="repository",
            objective="Break cross-zone cycles before adding more coupling to cyclic subsystems.",
            rationale=f"{metrics.cycle_count} cross-zone cycles detected",
        ))
    if metrics.largest_zone_line_share > 0.50:
        recommendations.append(GrowthRecommendation(
            code="growth.rebalance",
            priority=88,
            zone="repository",
            objective="Rebalance repository architecture so no single zone dominates machine context.",
            rationale=f"largest zone holds {metrics.largest_zone_line_share:.1%} of indexed lines",
        ))

    recommendations.sort(key=lambda item: (-item.priority, item.zone, item.code))
    return tuple(recommendations[:limit])
