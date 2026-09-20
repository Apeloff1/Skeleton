"""Structural hotspot detection for autonomous repository maintenance."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .metrics import structural_metrics
from .model import RepositoryModel


@dataclass(frozen=True, slots=True)
class Hotspot:
    identity: str
    scope: str
    zone: str
    path: str
    score: int
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "scope": self.scope,
            "zone": self.zone,
            "path": self.path,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def structural_hotspots(
    model: RepositoryModel,
    *,
    limit: int = 64,
) -> tuple[Hotspot, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 512:
        raise ValueError("limit must be in [1,512]")
    zone_metrics = {
        item.zone: item
        for item in structural_metrics(model).zones
    }
    criticality = {
        item.name: item.criticality
        for item in model.subsystems
    }
    cycle_zones = {
        zone
        for cycle in model.cycles
        for zone in cycle
    }

    hotspots: list[Hotspot] = []
    for record in model.files:
        if record.kind not in {"source", "workflow", "config", "script"}:
            continue
        score = 0
        reasons: list[str] = []
        if record.lines >= 2000:
            score += 35
            reasons.append("very large file")
        elif record.lines >= 1000:
            score += 20
            reasons.append("large file")
        elif record.lines >= 500:
            score += 10
            reasons.append("moderately large file")
        if record.symbols >= 80:
            score += 20
            reasons.append("high symbol density")
        elif record.symbols >= 40:
            score += 10
            reasons.append("elevated symbol density")
        if len(record.imports) >= 30:
            score += 20
            reasons.append("high import fanout")
        elif len(record.imports) >= 15:
            score += 10
            reasons.append("elevated import fanout")
        if record.zone in cycle_zones:
            score += 15
            reasons.append("zone participates in dependency cycle")
        if criticality.get(record.zone) == "critical":
            score += 15
            reasons.append("critical subsystem surface")
        elif criticality.get(record.zone) == "high":
            score += 8
            reasons.append("high-criticality subsystem surface")
        metric = zone_metrics.get(record.zone)
        if metric and metric.outbound_edges >= 20:
            score += 10
            reasons.append("zone has high outbound coupling")
        if record.kind == "workflow":
            score += 12
            reasons.append("workflow control-plane surface")
        if record.zone == "unclassified":
            score += 8
            reasons.append("unclassified ownership surface")
        if score:
            hotspots.append(Hotspot(
                identity=f"file:{record.path}",
                scope="file",
                zone=record.zone,
                path=record.path,
                score=min(score, 100),
                reasons=tuple(reasons),
            ))

    for subsystem in model.subsystems:
        metric = zone_metrics[subsystem.name]
        score = 0
        reasons: list[str] = []
        if metric.line_share >= 0.40:
            score += 30
            reasons.append("dominant line concentration")
        if metric.outbound_edges >= 40:
            score += 25
            reasons.append("very high outbound coupling")
        elif metric.outbound_edges >= 20:
            score += 15
            reasons.append("high outbound coupling")
        if metric.inbound_edges >= 40:
            score += 20
            reasons.append("high inbound dependency pressure")
        if subsystem.name in cycle_zones:
            score += 20
            reasons.append("cross-zone cycle participant")
        if subsystem.code_files >= 20 and subsystem.test_files == 0:
            score += 20
            reasons.append("large code surface without local tests")
        if score:
            hotspots.append(Hotspot(
                identity=f"zone:{subsystem.name}",
                scope="zone",
                zone=subsystem.name,
                path="",
                score=min(score, 100),
                reasons=tuple(reasons),
            ))

    hotspots.sort(key=lambda item: (-item.score, item.scope, item.zone, item.path))
    return tuple(hotspots[:limit])
