"""Adversarial analysis of probabilistic evidence and source dependencies.

Runs deterministic leave-one-group-out influence, contradiction mapping,
source concentration and sensitivity to priors. This diagnoses a belief,
rather than claiming the belief is true or statistically calibrated.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

from .dragon_probabilistic_distillation import (
    EvidencePass, EvidencePolicy, ProbabilisticKnowledgeDistiller,
)


@dataclass(frozen=True)
class GroupInfluence:
    group: str
    readings: int
    probability_without: float
    signed_influence: float
    direction: str


@dataclass(frozen=True)
class BeliefStressReport:
    claim_id: str
    baseline_probability: float
    independent_groups: int
    source_revisions: int
    influence: tuple[GroupInfluence, ...]
    prior_sensitivity: tuple[tuple[float, float], ...]
    largest_group_fraction: float
    maximum_probability_shift: float
    contradiction_count: int
    failure_modes: tuple[str, ...]
    requires_adversarial_review: bool


def stress_test_belief(
    claim_id: str, evidence: tuple[EvidencePass, ...], *,
    authorized: bool,
    policy: EvidencePolicy = EvidencePolicy(),
    priors: tuple[float, ...] = (0.2, 0.5, 0.8),
    max_groups: int = 500,
) -> BeliefStressReport:
    if not authorized:
        raise PermissionError("belief stress testing requires authorization")
    if not 1 <= max_groups <= 10000 or not 1 <= len(priors) <= 20:
        raise ValueError("invalid stress test budget")
    if any(not isfinite(p) or not 0 < p < 1 for p in priors):
        raise ValueError("invalid prior sensitivity range")
    engine = ProbabilisticKnowledgeDistiller(policy)
    baseline = engine.distill(claim_id, evidence)
    groups: dict[str, list[EvidencePass]] = {}
    revisions = set()
    for item in evidence:
        groups.setdefault(item.independence_group, []).append(item)
        revisions.add((item.source_id, item.source_revision))
    if len(groups) > max_groups:
        raise ValueError("source group budget exceeded")
    influence = []
    for group, readings in sorted(groups.items()):
        without = engine.distill(
            claim_id, tuple(item for item in evidence
                            if item.independence_group != group),
        )
        delta = round(baseline.probability - without.probability, 8)
        influence.append(GroupInfluence(
            group, len(readings), without.probability, delta,
            "support" if delta > 0 else "oppose" if delta < 0 else "neutral",
        ))
    influence.sort(key=lambda x: (-abs(x.signed_influence), x.group))
    sensitivity = []
    for prior in priors:
        revised = EvidencePolicy(
            prior_probability=prior,
            min_passes_per_source=policy.min_passes_per_source,
            max_passes_per_source=policy.max_passes_per_source,
            max_evidence=policy.max_evidence,
            max_group_log_bayes=policy.max_group_log_bayes,
            max_total_log_bayes=policy.max_total_log_bayes,
            review_probability_low=policy.review_probability_low,
            review_probability_high=policy.review_probability_high,
        )
        result = ProbabilisticKnowledgeDistiller(revised).distill(
            claim_id, evidence,
        )
        sensitivity.append((prior, result.probability))
    largest = (
        max(len(readings) for readings in groups.values()) / len(evidence)
        if evidence else 0.0
    )
    shift = max(
        (abs(item.signed_influence) for item in influence), default=0.0,
    )
    contradiction_count = sum(
        1 for group in groups.values()
        if any(item.supports for item in group)
        and any(not item.supports for item in group)
    )
    problems = []
    if len(groups) < 2:
        problems.append("No independent corroborating source groups")
    if largest > 0.7:
        problems.append("Evidence is concentrated in one source group")
    if shift > 0.15:
        problems.append("Belief is sensitive to removal of one source group")
    if contradiction_count or baseline.conflicting:
        problems.append("Conflicting evidence requires causal investigation")
    if max(p for _, p in sensitivity) - min(p for _, p in sensitivity) > 0.3:
        problems.append("Belief is sensitive to the prior")
    if baseline.review_required:
        problems.append("Minimum reread or uncertainty review incomplete")
    return BeliefStressReport(
        claim_id, baseline.probability, len(groups), len(revisions),
        tuple(influence), tuple(sensitivity), round(largest, 6),
        round(shift, 8), contradiction_count, tuple(problems),
        bool(problems),
    )
