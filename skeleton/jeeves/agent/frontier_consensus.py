"""Best-of-N and self-consistency aggregation for Jeeves deliberation.

The deliberation engine intentionally keeps candidate generation simple and
auditable.  This module adds a separate aggregation layer that asks a different
question: do independently generated candidate summaries converge on the same
action/outcome, or is the apparent winner merely the highest single score?

Agreement is treated as supporting evidence about *model consistency*, never as
external factual evidence.  Shared evidence and shared provider/model lineage
are discounted so repeated correlated samples do not create false certainty.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .deliberation import CandidateProposal, CandidateScore, SearchResult
from .types import AgentContractError, finite_number, positive_int, probability, stable_fingerprint


_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN_RE.findall(value or ""))


def _jaccard(left: Sequence[str] | frozenset[str], right: Sequence[str] | frozenset[str]) -> float:
    a = set(left)
    b = set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _semantic_similarity(left: CandidateProposal, right: CandidateProposal) -> float:
    action = _jaccard(_tokens(left.proposed_action), _tokens(right.proposed_action))
    outcome = _jaccard(_tokens(left.predicted_outcome), _tokens(right.predicted_outcome))
    summary = _jaccard(_tokens(left.summary), _tokens(right.summary))
    return max(0.0, min(1.0, action * 0.50 + outcome * 0.35 + summary * 0.15))


def _evidence_ids(candidate: CandidateProposal) -> tuple[str, ...]:
    return tuple(sorted({ref.evidence_id for ref in candidate.evidence}))


def _provenance_key(candidate: CandidateProposal) -> str:
    metadata = dict(candidate.metadata)
    provider = str(metadata.get("provider", "")).strip().casefold()
    model = str(metadata.get("model", "")).strip().casefold()
    if not provider and not model:
        return ""
    return provider + ":" + model


def _quality(candidate: CandidateProposal, score: CandidateScore) -> float:
    score_unit = max(0.0, min(1.0, (score.total + 1.0) * 0.5))
    return max(
        0.0,
        min(
            1.0,
            0.34 * score_unit
            + 0.24 * candidate.confidence
            + 0.20 * score.evidence_quality
            + 0.18 * score.verifier_score
            + 0.04 * score.novelty_bonus
            - 0.10 * score.risk_penalty
            - 0.04 * score.cost_penalty,
        ),
    )


@dataclass(frozen=True, slots=True)
class ConsensusPolicy:
    maximum_candidates: int = 32
    cluster_similarity_threshold: float = 0.66
    evidence_overlap_discount: float = 0.65
    same_model_discount: float = 0.30
    maximum_member_weight: float = 0.85
    minimum_agreement: float = 0.58
    minimum_plurality_margin: float = 0.10
    maximum_cluster_entropy: float = 0.94

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_candidates",
            positive_int("maximum_candidates", self.maximum_candidates, maximum=10_000),
        )
        for name in (
            "cluster_similarity_threshold",
            "evidence_overlap_discount",
            "same_model_discount",
            "maximum_member_weight",
            "minimum_agreement",
            "minimum_plurality_margin",
            "maximum_cluster_entropy",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ConsensusMember:
    candidate_id: str
    raw_quality: float
    independence_discount: float
    effective_weight: float
    strongest_evidence_overlap: float
    same_model_reuse: bool

    def __post_init__(self) -> None:
        for name in (
            "raw_quality",
            "independence_discount",
            "effective_weight",
            "strongest_evidence_overlap",
        ):
            value = finite_number(name, getattr(self, name))
            if value < 0.0:
                raise AgentContractError(f"{name} cannot be negative")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class ConsensusCluster:
    cluster_id: str
    representative_id: str
    candidate_ids: tuple[str, ...]
    members: tuple[ConsensusMember, ...]
    support: float
    probability: float
    mean_quality: float
    mean_similarity: float
    evidence_diversity: float
    model_diversity: float
    best_candidate_id: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ConsensusResult:
    selected_candidate_id: str | None
    agreement: float
    plurality_margin: float
    normalized_entropy: float
    effective_clusters: float
    requires_more_sampling: bool
    clusters: tuple[ConsensusCluster, ...]
    candidate_count: int
    fingerprint: str

    def __post_init__(self) -> None:
        for name in ("agreement", "plurality_margin", "normalized_entropy"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        effective = finite_number("effective_clusters", self.effective_clusters)
        if effective < 0.0:
            raise AgentContractError("effective_clusters cannot be negative")
        object.__setattr__(self, "effective_clusters", effective)


class ConsensusSelector:
    """Cluster candidate decisions and select the strongest independent consensus."""

    def __init__(self, policy: ConsensusPolicy | None = None) -> None:
        self.policy = policy or ConsensusPolicy()

    def select(self, search: SearchResult) -> ConsensusResult:
        if not isinstance(search, SearchResult):
            raise TypeError("search must be SearchResult")
        ranking = tuple(search.ranking[: self.policy.maximum_candidates])
        if not ranking:
            fingerprint = stable_fingerprint({"search": search.trace_fingerprint, "clusters": []})
            return ConsensusResult(None, 0.0, 0.0, 0.0, 0.0, True, (), 0, fingerprint)

        raw_clusters: list[list[tuple[CandidateProposal, CandidateScore]]] = []
        representatives: list[CandidateProposal] = []
        for candidate, score in ranking:
            if not isinstance(candidate, CandidateProposal) or not isinstance(score, CandidateScore):
                raise TypeError("search ranking must contain candidate/score pairs")
            best_index: int | None = None
            best_similarity = -1.0
            for index, representative in enumerate(representatives):
                similarity = _semantic_similarity(candidate, representative)
                if similarity >= self.policy.cluster_similarity_threshold and similarity > best_similarity:
                    best_index = index
                    best_similarity = similarity
            if best_index is None:
                representatives.append(candidate)
                raw_clusters.append([(candidate, score)])
            else:
                raw_clusters[best_index].append((candidate, score))

        clusters: list[ConsensusCluster] = []
        for index, values in enumerate(raw_clusters):
            representative = values[0][0]
            members: list[ConsensusMember] = []
            accepted: list[CandidateProposal] = []
            effective_weights: list[float] = []
            qualities: list[float] = []
            similarities: list[float] = []
            models: set[str] = set()
            evidence_sets: set[tuple[str, ...]] = set()
            best_pair: tuple[CandidateProposal, CandidateScore] | None = None
            best_effective = -1.0

            for candidate, score in values:
                raw = min(self.policy.maximum_member_weight, _quality(candidate, score))
                strongest_overlap = 0.0
                discount = 1.0
                current_evidence = _evidence_ids(candidate)
                current_model = _provenance_key(candidate)
                same_model_reuse = False
                for prior in accepted:
                    overlap = _jaccard(current_evidence, _evidence_ids(prior))
                    strongest_overlap = max(strongest_overlap, overlap)
                    discount *= max(
                        0.05,
                        1.0 - self.policy.evidence_overlap_discount * overlap,
                    )
                    prior_model = _provenance_key(prior)
                    if current_model and prior_model and current_model == prior_model:
                        same_model_reuse = True
                if same_model_reuse:
                    discount *= max(0.05, 1.0 - self.policy.same_model_discount)
                effective = raw * discount
                members.append(
                    ConsensusMember(
                        candidate_id=candidate.candidate_id,
                        raw_quality=raw,
                        independence_discount=discount,
                        effective_weight=effective,
                        strongest_evidence_overlap=strongest_overlap,
                        same_model_reuse=same_model_reuse,
                    )
                )
                accepted.append(candidate)
                qualities.append(raw)
                effective_weights.append(effective)
                similarities.append(_semantic_similarity(candidate, representative))
                if current_model:
                    models.add(current_model)
                evidence_sets.add(current_evidence)
                if effective > best_effective or (
                    math.isclose(effective, best_effective)
                    and best_pair is not None
                    and score.total > best_pair[1].total
                ):
                    best_effective = effective
                    best_pair = (candidate, score)

            support = sum(effective_weights)
            mean_quality = sum(qualities) / len(qualities) if qualities else 0.0
            mean_similarity = sum(similarities) / len(similarities) if similarities else 0.0
            evidence_diversity = min(1.0, len(evidence_sets) / max(1, len(values)))
            model_diversity = min(1.0, len(models) / max(1, len(values))) if models else 0.0
            best_candidate = best_pair[0] if best_pair is not None else representative
            cluster_id = f"consensus:{index + 1}"
            cluster_fingerprint = stable_fingerprint(
                {
                    "cluster": cluster_id,
                    "representative": representative.candidate_id,
                    "members": [
                        (
                            member.candidate_id,
                            member.raw_quality,
                            member.independence_discount,
                            member.effective_weight,
                        )
                        for member in members
                    ],
                    "support": support,
                    "best": best_candidate.candidate_id,
                }
            )
            clusters.append(
                ConsensusCluster(
                    cluster_id=cluster_id,
                    representative_id=representative.candidate_id,
                    candidate_ids=tuple(candidate.candidate_id for candidate, _ in values),
                    members=tuple(members),
                    support=support,
                    probability=0.0,
                    mean_quality=mean_quality,
                    mean_similarity=mean_similarity,
                    evidence_diversity=evidence_diversity,
                    model_diversity=model_diversity,
                    best_candidate_id=best_candidate.candidate_id,
                    fingerprint=cluster_fingerprint,
                )
            )

        total_support = sum(cluster.support for cluster in clusters)
        if total_support <= 0.0:
            probabilities = tuple(1.0 / len(clusters) for _ in clusters)
        else:
            probabilities = tuple(cluster.support / total_support for cluster in clusters)
        with_probabilities = [
            ConsensusCluster(
                cluster_id=cluster.cluster_id,
                representative_id=cluster.representative_id,
                candidate_ids=cluster.candidate_ids,
                members=cluster.members,
                support=cluster.support,
                probability=probability_value,
                mean_quality=cluster.mean_quality,
                mean_similarity=cluster.mean_similarity,
                evidence_diversity=cluster.evidence_diversity,
                model_diversity=cluster.model_diversity,
                best_candidate_id=cluster.best_candidate_id,
                fingerprint=cluster.fingerprint,
            )
            for cluster, probability_value in zip(clusters, probabilities)
        ]
        with_probabilities.sort(
            key=lambda item: (item.probability, item.support, item.mean_quality, item.cluster_id),
            reverse=True,
        )
        ordered_probabilities = [item.probability for item in with_probabilities]
        agreement = ordered_probabilities[0] if ordered_probabilities else 0.0
        plurality_margin = (
            agreement - ordered_probabilities[1]
            if len(ordered_probabilities) > 1
            else agreement
        )
        if len(ordered_probabilities) <= 1:
            entropy = 0.0
        else:
            raw_entropy = -sum(p * math.log(p) for p in ordered_probabilities if p > 0.0)
            entropy = raw_entropy / math.log(len(ordered_probabilities))
        denominator = sum(p * p for p in ordered_probabilities)
        effective_clusters = 0.0 if denominator <= 0.0 else 1.0 / denominator
        requires_more = (
            agreement < self.policy.minimum_agreement
            or plurality_margin < self.policy.minimum_plurality_margin
            or entropy > self.policy.maximum_cluster_entropy
        )
        selected = with_probabilities[0].best_candidate_id if with_probabilities else None
        fingerprint = stable_fingerprint(
            {
                "search": search.trace_fingerprint,
                "clusters": [
                    (item.fingerprint, item.probability, item.support)
                    for item in with_probabilities
                ],
                "selected": selected,
                "agreement": agreement,
                "margin": plurality_margin,
                "entropy": entropy,
                "more": requires_more,
            }
        )
        return ConsensusResult(
            selected_candidate_id=selected,
            agreement=max(0.0, min(1.0, agreement)),
            plurality_margin=max(0.0, min(1.0, plurality_margin)),
            normalized_entropy=max(0.0, min(1.0, entropy)),
            effective_clusters=effective_clusters,
            requires_more_sampling=requires_more,
            clusters=tuple(with_probabilities),
            candidate_count=len(ranking),
            fingerprint=fingerprint,
        )


def promote_consensus(search: SearchResult, consensus: ConsensusResult) -> SearchResult:
    """Move the consensus representative to rank one without changing scores."""

    if consensus.selected_candidate_id is None:
        return search
    selected: tuple[CandidateProposal, CandidateScore] | None = None
    rest: list[tuple[CandidateProposal, CandidateScore]] = []
    for pair in search.ranking:
        if pair[0].candidate_id == consensus.selected_candidate_id and selected is None:
            selected = pair
        else:
            rest.append(pair)
    if selected is None:
        return search
    ranking = (selected, *rest)
    trace = stable_fingerprint(
        {
            "source": search.trace_fingerprint,
            "consensus": consensus.fingerprint,
            "ranking": [candidate.candidate_id for candidate, _ in ranking],
        }
    )
    return SearchResult(
        mode=search.mode,
        best=selected[0],
        ranking=tuple(ranking),
        explored=search.explored,
        ledger=dict(search.ledger),
        stopped_reason=search.stopped_reason + "; consensus promoted",
        trace_fingerprint=trace,
    )


def merge_search_results(*results: SearchResult) -> SearchResult:
    """Merge bounded search rounds while deduplicating semantic-identical candidates."""

    values = tuple(result for result in results if isinstance(result, SearchResult))
    if not values:
        raise ValueError("at least one SearchResult is required")

    by_fingerprint: dict[str, tuple[CandidateProposal, CandidateScore]] = {}
    explored: dict[str, CandidateProposal] = {}
    for result in values:
        for candidate in result.explored:
            explored.setdefault(candidate.fingerprint, candidate)
        for candidate, score in result.ranking:
            prior = by_fingerprint.get(candidate.fingerprint)
            if prior is None or (score.total, candidate.confidence, candidate.candidate_id) > (
                prior[1].total,
                prior[0].confidence,
                prior[0].candidate_id,
            ):
                by_fingerprint[candidate.fingerprint] = (candidate, score)

    ranking = sorted(
        by_fingerprint.values(),
        key=lambda item: (item[1].total, item[0].confidence, item[0].candidate_id),
        reverse=True,
    )
    ledger: dict[str, Any] = {}
    additive = {
        "model_calls",
        "candidates",
        "estimated_tokens",
        "verifier_calls",
        "pruned",
        "expanded",
        "duplicate_candidates",
    }
    for key in additive:
        ledger[key] = sum(int(result.ledger.get(key, 0)) for result in values)
    ledger["rounds"] = len(values)
    ledger["source_traces"] = [result.trace_fingerprint for result in values]
    trace = stable_fingerprint(
        {
            "sources": [result.trace_fingerprint for result in values],
            "ranking": [(candidate.candidate_id, score.total) for candidate, score in ranking],
            "ledger": ledger,
        }
    )
    return SearchResult(
        mode=values[-1].mode,
        best=ranking[0][0] if ranking else None,
        ranking=tuple(ranking),
        explored=tuple(explored.values()),
        ledger=ledger,
        stopped_reason="; ".join(result.stopped_reason for result in values),
        trace_fingerprint=trace,
    )


__all__ = [
    "ConsensusCluster",
    "ConsensusMember",
    "ConsensusPolicy",
    "ConsensusResult",
    "ConsensusSelector",
    "merge_search_results",
    "promote_consensus",
]
