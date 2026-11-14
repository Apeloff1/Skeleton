"""Measured champion/candidate validation delta, never a self-promotion."""
from __future__ import annotations
from dataclasses import dataclass
from .validation import ValidationReport
from .errors import deny


@dataclass(frozen=True, slots=True)
class ModelComparison:
    champion_score_ppm: int
    candidate_score_ppm: int
    improved: int
    regressed: int
    unchanged: int
    independent_verified: bool = False

    def record(self) -> dict:
        return {
            **{k: getattr(self, k) for k in self.__dataclass_fields__},
            "candidate_wins_measured_cases": self.candidate_score_ppm > self.champion_score_ppm,
            "production_authorized": False,
            "release_certified": False,
        }


def compare(champion: ValidationReport, candidate: ValidationReport) -> ModelComparison:
    if type(champion) is not ValidationReport or type(candidate) is not ValidationReport:
        deny("comparison-type")
    if (champion.partition_name != candidate.partition_name
            or champion.source_partition_sha256 != candidate.source_partition_sha256
            or len(champion.cases) != len(candidate.cases)
            or not candidate.cases):
        deny("comparison-source-drift")
    b = {r.item_id: r.passed for r in champion.cases}
    c = {r.item_id: r.passed for r in candidate.cases}
    if set(b) != set(c) or len(b) != len(champion.cases) or len(c) != len(candidate.cases):
        deny("comparison-cases")
    return ModelComparison(
        champion_score_ppm=1000000 * sum(b.values()) // len(b),
        candidate_score_ppm=1000000 * sum(c.values()) // len(c),
        improved=sum(not b[k] and c[k] for k in b),
        regressed=sum(b[k] and not c[k] for k in b),
        unchanged=sum(b[k] == c[k] for k in b),
    )
