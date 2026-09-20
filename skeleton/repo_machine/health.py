"""Repository organization health scoring with explicit evidence."""
from __future__ import annotations

from dataclasses import dataclass

from .model import RepositoryModel

_SEVERITY_PENALTY = {"critical": 20, "high": 10, "medium": 4, "low": 1, "info": 0}


@dataclass(frozen=True, slots=True)
class HealthReport:
    score: int
    grade: str
    finding_count: int
    cycle_count: int
    unclassified_ratio: float
    tested_zone_ratio: float
    penalties: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "score": self.score,
            "grade": self.grade,
            "finding_count": self.finding_count,
            "cycle_count": self.cycle_count,
            "unclassified_ratio": self.unclassified_ratio,
            "tested_zone_ratio": self.tested_zone_ratio,
            "penalties": list(self.penalties),
        }


def repository_health(model: RepositoryModel) -> HealthReport:
    total = max(1, len(model.files))
    unclassified_ratio = model.unclassified_count / total
    code_zones = [item for item in model.subsystems if item.code_files > 0]
    tested = [item for item in code_zones if item.test_files > 0]
    tested_zone_ratio = len(tested) / max(1, len(code_zones))

    score = 100
    penalties: list[str] = []
    severity_penalty = sum(_SEVERITY_PENALTY[item.severity] for item in model.findings)
    if severity_penalty:
        applied = min(45, severity_penalty)
        score -= applied
        penalties.append(f"organization findings: -{applied}")
    if model.cycles:
        applied = min(25, len(model.cycles) * 7)
        score -= applied
        penalties.append(f"dependency cycles: -{applied}")
    if unclassified_ratio > 0.20:
        applied = min(20, round(unclassified_ratio * 30))
        score -= applied
        penalties.append(f"unclassified surface: -{applied}")
    if tested_zone_ratio < 0.50 and code_zones:
        applied = min(15, round((0.50 - tested_zone_ratio) * 30))
        score -= applied
        penalties.append(f"zone test coverage: -{applied}")
    if model.truncated:
        score -= 20
        penalties.append("truncated machine inventory: -20")
    score = max(0, min(100, score))
    grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
    return HealthReport(
        score=score,
        grade=grade,
        finding_count=len(model.findings),
        cycle_count=len(model.cycles),
        unclassified_ratio=round(unclassified_ratio, 6),
        tested_zone_ratio=round(tested_zone_ratio, 6),
        penalties=tuple(penalties),
    )
