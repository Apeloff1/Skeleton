"""Composite technical-debt register derived from machine repository evidence."""
from __future__ import annotations

from dataclasses import dataclass

from .docs_map import undocumented_code_zones
from .growth import growth_recommendations
from .hotspots import structural_hotspots
from .model import RepositoryModel
from .naming import analyze_naming
from .test_affinity import uncovered_sources


@dataclass(frozen=True, slots=True)
class DebtItem:
    identity: str
    category: str
    zone: str
    score: int
    summary: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "category": self.category,
            "zone": self.zone,
            "score": self.score,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }


def debt_register(
    model: RepositoryModel,
    *,
    limit: int = 128,
) -> tuple[DebtItem, ...]:
    items: list[DebtItem] = []
    for finding in model.findings:
        severity = {
            "critical": 100,
            "high": 80,
            "medium": 55,
            "low": 30,
            "info": 10,
        }[finding.severity]
        items.append(DebtItem(
            identity=f"finding:{finding.identity}",
            category=finding.code,
            zone=finding.zone,
            score=severity,
            summary=finding.detail or finding.code,
            evidence=((finding.path,) if finding.path else ()) + finding.evidence,
        ))

    for hotspot in structural_hotspots(model, limit=100):
        items.append(DebtItem(
            identity=f"hotspot:{hotspot.identity}",
            category="structural-hotspot",
            zone=hotspot.zone,
            score=hotspot.score,
            summary="; ".join(hotspot.reasons),
            evidence=((hotspot.path,) if hotspot.path else ()),
        ))

    for recommendation in growth_recommendations(model, limit=64):
        items.append(DebtItem(
            identity=f"growth:{recommendation.code}:{recommendation.zone}",
            category=recommendation.code,
            zone=recommendation.zone,
            score=recommendation.priority,
            summary=recommendation.objective,
            evidence=(recommendation.rationale,),
        ))

    for zone in undocumented_code_zones(model):
        items.append(DebtItem(
            identity=f"docs:{zone}",
            category="documentation-gap",
            zone=zone,
            score=45,
            summary="code-bearing subsystem lacks high-confidence machine-linked documentation",
            evidence=(),
        ))

    records = {item.path: item for item in model.files}
    for path in uncovered_sources(model)[:256]:
        zone = records[path].zone
        items.append(DebtItem(
            identity=f"test-gap:{path}",
            category="test-affinity-gap",
            zone=zone,
            score=50,
            summary="source file has no high-confidence mapped regression test",
            evidence=(path,),
        ))

    for naming in analyze_naming(model)[:256]:
        records_for_path = records.get(naming.path)
        zone = records_for_path.zone if records_for_path else "unclassified"
        items.append(DebtItem(
            identity=f"naming:{naming.code}:{naming.path}",
            category=naming.code,
            zone=zone,
            score=25 if naming.severity == "low" else 45,
            summary=naming.detail,
            evidence=(naming.path,),
        ))

    dedup: dict[str, DebtItem] = {}
    for item in items:
        current = dedup.get(item.identity)
        if current is None or item.score > current.score:
            dedup[item.identity] = item
    ordered = sorted(
        dedup.values(),
        key=lambda item: (-item.score, item.zone, item.identity),
    )
    return tuple(ordered[:limit])


def debt_by_zone(model: RepositoryModel) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for item in debt_register(model, limit=512):
        entry = result.setdefault(item.zone, {"items": 0, "score": 0})
        entry["items"] += 1
        entry["score"] += item.score
    return result
