"""Multi-pass source analysis with calibrated uncertainty and provenance.

Never equates repeated readings of one source with independent corroboration.
Observations are bounded, attributable, and deduplicated by source lineage.
Conflicts are retained rather than erased by a majority vote.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import exp, isfinite, log
from typing import Iterable
import json


@dataclass(frozen=True)
class EvidencePass:
    source_id: str
    source_revision: str
    pass_id: str
    claim_id: str
    supports: bool
    confidence: float
    reliability: float
    independence_group: str
    evidence_locator: str
    observation: str


@dataclass(frozen=True)
class Belief:
    claim_id: str
    probability: float
    log_odds: float
    independent_groups: int
    supporting_groups: int
    opposing_groups: int
    readings: int
    conflicting: bool
    evidence_digest: str
    review_required: bool


@dataclass(frozen=True)
class EvidencePolicy:
    prior_probability: float = 0.5
    min_passes_per_source: int = 3
    max_passes_per_source: int = 12
    max_evidence: int = 10000
    max_group_log_bayes: float = 2.5
    max_total_log_bayes: float = 12.0
    review_probability_low: float = 0.1
    review_probability_high: float = 0.9


def _check_probability(value: float, *, strict: bool = False) -> bool:
    return (isfinite(value) and
            (0 < value < 1 if strict else 0 <= value <= 1))


def _digest(value: object) -> str:
    return sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()


class ProbabilisticKnowledgeDistiller:
    def __init__(self, policy: EvidencePolicy = EvidencePolicy()):
        if not _check_probability(policy.prior_probability, strict=True):
            raise ValueError("prior must be strictly between zero and one")
        if not 1 <= policy.min_passes_per_source <= policy.max_passes_per_source <= 100:
            raise ValueError("invalid multi-pass policy")
        if not 1 <= policy.max_evidence <= 1000000:
            raise ValueError("invalid evidence budget")
        if not isfinite(policy.max_group_log_bayes) or not 0 < policy.max_group_log_bayes <= 20:
            raise ValueError("invalid per-source evidence cap")
        if not isfinite(policy.max_total_log_bayes) or not 0 < policy.max_total_log_bayes <= 100:
            raise ValueError("invalid total evidence cap")
        if not 0 <= policy.review_probability_low < policy.review_probability_high <= 1:
            raise ValueError("invalid review interval")
        self.policy = policy

    def _validate(self, item: EvidencePass) -> None:
        for name, maximum in (
            ("source_id", 256), ("source_revision", 128),
            ("pass_id", 128), ("claim_id", 256),
            ("independence_group", 256), ("evidence_locator", 1024),
            ("observation", 2000),
        ):
            value = getattr(item, name)
            if not isinstance(value, str) or not 1 <= len(value) <= maximum:
                raise ValueError(f"invalid {name}")
        if not isinstance(item.supports, bool):
            raise ValueError("invalid evidence polarity")
        if not _check_probability(item.confidence):
            raise ValueError("invalid observation confidence")
        if not _check_probability(item.reliability):
            raise ValueError("invalid source reliability")

    def distill(self, claim_id: str, passes: Iterable[EvidencePass]) -> Belief:
        if not isinstance(claim_id, str) or not 1 <= len(claim_id) <= 256:
            raise ValueError("invalid claim identity")
        items = tuple(passes)
        if len(items) > self.policy.max_evidence:
            raise ValueError("evidence budget exceeded")
        seen = set()
        by_source: dict[tuple[str, str], list[EvidencePass]] = {}
        for item in items:
            self._validate(item)
            if item.claim_id != claim_id:
                raise ValueError("cross-claim evidence contamination")
            key = (item.source_id, item.source_revision, item.pass_id)
            if key in seen:
                raise ValueError("duplicate reading identity")
            seen.add(key)
            by_source.setdefault(
                (item.source_id, item.source_revision), [],
            ).append(item)
        if any(len(group) > self.policy.max_passes_per_source
               for group in by_source.values()):
            raise ValueError("source reread budget exceeded")
        # Multiple passes improve extraction coverage, but never multiply
        # independent confidence. Correlated evidence shares a single cap.
        by_group: dict[str, list[EvidencePass]] = {}
        for group in by_source.values():
            for item in group:
                by_group.setdefault(item.independence_group, []).append(item)
        prior = self.policy.prior_probability
        log_odds = log(prior / (1 - prior))
        supporting = opposing = 0
        for group_id in sorted(by_group):
            group = by_group[group_id]
            signed = []
            for item in group:
                # Reliability and observation confidence must both contribute.
                # Bounded log evidence avoids false certainty at 0 or 1.
                strength = item.confidence * item.reliability
                likelihood = min(0.95, max(0.05, 0.5 + 0.45 * strength))
                log_bayes = log(likelihood / (1 - likelihood))
                signed.append(log_bayes if item.supports else -log_bayes)
            # Conservative correlation model: aggregate one mean signal
            # per declared independence group, not a sum over rereads.
            group_signal = sum(signed) / len(signed)
            group_signal = max(-self.policy.max_group_log_bayes,
                               min(self.policy.max_group_log_bayes, group_signal))
            log_odds += group_signal
            if any(x > 0 for x in signed):
                supporting += 1
            if any(x < 0 for x in signed):
                opposing += 1
        log_odds = max(-self.policy.max_total_log_bayes,
                       min(self.policy.max_total_log_bayes, log_odds))
        probability = 1 / (1 + exp(-log_odds))
        conflicting = supporting > 0 and opposing > 0
        insufficient = any(
            len(group) < self.policy.min_passes_per_source
            for group in by_source.values()
        )
        digest = _digest([
            claim_id,
            sorted([
                [item.source_id, item.source_revision, item.pass_id,
                 item.supports, item.confidence, item.reliability,
                 item.independence_group, item.evidence_locator,
                 item.observation]
                for item in items
            ]),
        ])
        return Belief(
            claim_id, round(probability, 8), round(log_odds, 8),
            len(by_group), supporting, opposing, len(items),
            conflicting, digest,
            insufficient or conflicting or (
                self.policy.review_probability_low <
                probability < self.policy.review_probability_high
            ),
        )
