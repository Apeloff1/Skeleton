"""Cohort-independence auditing for Jeeves historical benchmark evidence.

Historical benchmark snapshots can be perfectly valid individually yet still
inflate confidence when the same evaluation population is measured repeatedly.
This module keeps overlap metadata separate from benchmark scores and audits the
exact snapshots used by a champion decision.

No overlap is inferred from provider names, timestamps, or URIs. Callers must
make cohort relationships explicit. Missing required declarations fail closed.
The audit is descriptive and never rewrites scores or sample counts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from skeleton.jeeves.historical_models import ChampionDecision, canonical_fingerprint


MAX_COHORTS: Final = 10_000
MAX_SNAPSHOTS_PER_COHORT: Final = 10_000


class HistoricalIndependenceError(ValueError):
    """Invalid cohort/overlap declaration or audit input."""


def _text(name: str, value: object, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalIndependenceError(f"{name} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise HistoricalIndependenceError(f"{name} exceeds {maximum} characters")
    return cleaned


def _unit(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HistoricalIndependenceError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise HistoricalIndependenceError(f"{name} must be finite and between 0 and 1")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalIndependenceError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class CohortDeclaration:
    """Declare which benchmark snapshots were measured on one population."""

    cohort_id: str
    snapshot_ids: frozenset[str]
    population_fingerprint: str
    member_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "cohort_id", _text("cohort_id", self.cohort_id, 160))
        population = _text("population_fingerprint", self.population_fingerprint, 256)
        object.__setattr__(self, "population_fingerprint", population)
        snapshots = frozenset(_text("snapshot_id", item, 160) for item in self.snapshot_ids)
        if not snapshots:
            raise HistoricalIndependenceError("cohort must contain at least one snapshot")
        if len(snapshots) > MAX_SNAPSHOTS_PER_COHORT:
            raise HistoricalIndependenceError("cohort snapshot limit exceeded")
        object.__setattr__(self, "snapshot_ids", snapshots)
        object.__setattr__(self, "member_count", _positive_int("member_count", self.member_count))


@dataclass(frozen=True, slots=True)
class CohortOverlap:
    """Explicit symmetric overlap fraction between two distinct cohorts."""

    left_cohort_id: str
    right_cohort_id: str
    overlap_fraction: float

    def __post_init__(self) -> None:
        left = _text("left_cohort_id", self.left_cohort_id, 160)
        right = _text("right_cohort_id", self.right_cohort_id, 160)
        if left == right:
            raise HistoricalIndependenceError("cohort overlap must reference two distinct cohorts")
        object.__setattr__(self, "left_cohort_id", left)
        object.__setattr__(self, "right_cohort_id", right)
        object.__setattr__(self, "overlap_fraction", _unit("overlap_fraction", self.overlap_fraction))

    @property
    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.left_cohort_id, self.right_cohort_id)))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class IndependencePolicy:
    max_pairwise_overlap: float = 0.20
    min_independent_cohorts: int = 2
    require_all_snapshots_declared: bool = True
    reject_duplicate_population_fingerprints: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_pairwise_overlap", _unit("max_pairwise_overlap", self.max_pairwise_overlap))
        object.__setattr__(self, "min_independent_cohorts", _positive_int("min_independent_cohorts", self.min_independent_cohorts))
        if not isinstance(self.require_all_snapshots_declared, bool):
            raise HistoricalIndependenceError("require_all_snapshots_declared must be boolean")
        if not isinstance(self.reject_duplicate_population_fingerprints, bool):
            raise HistoricalIndependenceError("reject_duplicate_population_fingerprints must be boolean")

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(
            {
                "max_pairwise_overlap": self.max_pairwise_overlap,
                "min_independent_cohorts": self.min_independent_cohorts,
                "require_all_snapshots_declared": self.require_all_snapshots_declared,
                "reject_duplicate_population_fingerprints": self.reject_duplicate_population_fingerprints,
            }
        )


@dataclass(frozen=True, slots=True)
class IndependenceFinding:
    finding_id: str
    cohorts: tuple[str, ...]
    overlap_fraction: float | None = None


@dataclass(frozen=True, slots=True)
class EvidenceIndependenceReport:
    champion_model: str
    used_snapshot_ids: tuple[str, ...]
    declared_snapshot_count: int
    undeclared_snapshot_ids: tuple[str, ...]
    used_cohort_ids: tuple[str, ...]
    independent_population_count: int
    max_observed_overlap: float
    findings: tuple[IndependenceFinding, ...]
    passed: bool
    policy_fingerprint: str
    declaration_fingerprint: str
    report_fingerprint: str

    @property
    def finding_count(self) -> int:
        return len(self.findings)


class HistoricalEvidenceIndependenceAuditor:
    """Audit exact champion evidence for repeated/overlapping populations."""

    def __init__(
        self,
        *,
        cohorts: tuple[CohortDeclaration, ...] | list[CohortDeclaration],
        overlaps: tuple[CohortOverlap, ...] | list[CohortOverlap] = (),
        policy: IndependencePolicy | None = None,
    ) -> None:
        cohorts = tuple(cohorts)
        overlaps = tuple(overlaps)
        if not cohorts:
            raise HistoricalIndependenceError("at least one cohort declaration is required")
        if len(cohorts) > MAX_COHORTS:
            raise HistoricalIndependenceError("cohort declaration limit exceeded")
        if any(not isinstance(item, CohortDeclaration) for item in cohorts):
            raise HistoricalIndependenceError("cohorts must contain CohortDeclaration values")
        if any(not isinstance(item, CohortOverlap) for item in overlaps):
            raise HistoricalIndependenceError("overlaps must contain CohortOverlap values")
        self.policy = policy or IndependencePolicy()
        if not isinstance(self.policy, IndependencePolicy):
            raise HistoricalIndependenceError("policy must be IndependencePolicy")

        ids = [item.cohort_id for item in cohorts]
        if len(ids) != len(set(ids)):
            raise HistoricalIndependenceError("cohort ids must be unique")
        self._cohorts = {item.cohort_id: item for item in cohorts}

        snapshot_owner: dict[str, str] = {}
        for cohort in cohorts:
            for snapshot_id in cohort.snapshot_ids:
                previous = snapshot_owner.get(snapshot_id)
                if previous is not None:
                    raise HistoricalIndependenceError(
                        f"snapshot {snapshot_id} is assigned to multiple cohorts: {previous}, {cohort.cohort_id}"
                    )
                snapshot_owner[snapshot_id] = cohort.cohort_id
        self._snapshot_owner = snapshot_owner

        overlap_map: dict[tuple[str, str], float] = {}
        for overlap in overlaps:
            if overlap.left_cohort_id not in self._cohorts or overlap.right_cohort_id not in self._cohorts:
                raise HistoricalIndependenceError("overlap references unknown cohort")
            if overlap.key in overlap_map:
                raise HistoricalIndependenceError("duplicate cohort-overlap declaration")
            overlap_map[overlap.key] = overlap.overlap_fraction
        self._overlaps = overlap_map

        self.declaration_fingerprint = canonical_fingerprint(
            {
                "cohorts": [
                    {
                        "cohort_id": item.cohort_id,
                        "snapshots": sorted(item.snapshot_ids),
                        "population": item.population_fingerprint,
                        "member_count": item.member_count,
                    }
                    for item in sorted(cohorts, key=lambda value: value.cohort_id)
                ],
                "overlaps": [
                    {"cohorts": list(key), "fraction": value}
                    for key, value in sorted(overlap_map.items())
                ],
            }
        )

    def audit(self, decision: ChampionDecision) -> EvidenceIndependenceReport:
        if not isinstance(decision, ChampionDecision):
            raise HistoricalIndependenceError("decision must be ChampionDecision")
        used_ids = tuple(
            sorted(
                snapshot_id
                for domain in decision.champion.domains
                for snapshot_id in domain.snapshot_ids
            )
        )
        used_set = set(used_ids)
        cohort_ids = tuple(sorted({self._snapshot_owner[item] for item in used_ids if item in self._snapshot_owner}))
        undeclared = tuple(sorted(item for item in used_ids if item not in self._snapshot_owner))
        findings: list[IndependenceFinding] = []

        if undeclared and self.policy.require_all_snapshots_declared:
            findings.append(IndependenceFinding("undeclared_snapshots", ()))

        populations: dict[str, list[str]] = {}
        for cohort_id in cohort_ids:
            population = self._cohorts[cohort_id].population_fingerprint
            populations.setdefault(population, []).append(cohort_id)
        duplicate_groups = [tuple(sorted(group)) for group in populations.values() if len(group) > 1]
        if duplicate_groups and self.policy.reject_duplicate_population_fingerprints:
            for group in sorted(duplicate_groups):
                findings.append(IndependenceFinding("duplicate_population", group, 1.0))

        max_overlap = 0.0
        for index, left in enumerate(cohort_ids):
            for right in cohort_ids[index + 1 :]:
                left_population = self._cohorts[left].population_fingerprint
                right_population = self._cohorts[right].population_fingerprint
                fraction = 1.0 if left_population == right_population else self._overlaps.get(tuple(sorted((left, right))), 0.0)
                max_overlap = max(max_overlap, fraction)
                if fraction > self.policy.max_pairwise_overlap + 1e-12:
                    findings.append(
                        IndependenceFinding("excessive_pairwise_overlap", tuple(sorted((left, right))), fraction)
                    )

        independent_populations = len({self._cohorts[item].population_fingerprint for item in cohort_ids})
        if independent_populations < self.policy.min_independent_cohorts:
            findings.append(
                IndependenceFinding("insufficient_independent_cohorts", cohort_ids)
            )

        payload = {
            "champion": decision.champion.model.key,
            "used_snapshots": used_ids,
            "used_cohorts": cohort_ids,
            "undeclared": undeclared,
            "independent_populations": independent_populations,
            "max_overlap": max_overlap,
            "findings": [
                {"id": item.finding_id, "cohorts": list(item.cohorts), "overlap": item.overlap_fraction}
                for item in findings
            ],
            "policy": self.policy.fingerprint,
            "declarations": self.declaration_fingerprint,
        }
        return EvidenceIndependenceReport(
            champion_model=decision.champion.model.key,
            used_snapshot_ids=used_ids,
            declared_snapshot_count=len(used_set) - len(undeclared),
            undeclared_snapshot_ids=undeclared,
            used_cohort_ids=cohort_ids,
            independent_population_count=independent_populations,
            max_observed_overlap=max_overlap,
            findings=tuple(findings),
            passed=not findings,
            policy_fingerprint=self.policy.fingerprint,
            declaration_fingerprint=self.declaration_fingerprint,
            report_fingerprint=canonical_fingerprint(payload),
        )


def summarize_independence(report: EvidenceIndependenceReport) -> dict[str, object]:
    return {
        "champion_model": report.champion_model,
        "passed": report.passed,
        "used_snapshot_count": len(report.used_snapshot_ids),
        "declared_snapshot_count": report.declared_snapshot_count,
        "undeclared_snapshot_ids": list(report.undeclared_snapshot_ids),
        "used_cohort_ids": list(report.used_cohort_ids),
        "independent_population_count": report.independent_population_count,
        "max_observed_overlap": report.max_observed_overlap,
        "findings": [
            {"id": item.finding_id, "cohorts": list(item.cohorts), "overlap_fraction": item.overlap_fraction}
            for item in report.findings
        ],
        "policy_fingerprint": report.policy_fingerprint,
        "declaration_fingerprint": report.declaration_fingerprint,
        "report_fingerprint": report.report_fingerprint,
    }