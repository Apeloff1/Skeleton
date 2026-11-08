"""Human-labeled lexical query suggestions without autonomous query mutation.

A reviewed passage label is only a relevance judgment, not approval to
transform external web text into a new research objective or executable
instruction. This module generates bounded, explainable term proposals
from exact current indexed excerpts, including positive-minus-negative
evidence counts and source diversity. No proposal is activated or dispatched
without a separate operator decision at the existing authenticated boundary.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from math import log
from typing import Iterable

from .contracts import CampaignMandate, digest, integer
from .objectives import ObjectivePlan
from .policy_matrix import SourcePolicyProjection
from .query_lattice import QueryLattice
from .retrieval_benchmark import PassageJudgment
from .source_index import EphemeralIndex, _terms

_NOISE = frozenset(("http", "https", "www", "com", "source",
                     "this", "these", "they", "their", "those", "when",
                     "into", "from", "about", "with", "without",
                     "reviewed", "unreviewed", "previous", "ignore"))


@dataclass(frozen=True)
class FeedbackTermCandidate:
    objective_id: str
    term: str
    positive_label_count: int
    negative_label_count: int
    reviewed_source_count: int
    document_frequency: int
    lexical_specificity: float
    proposed_weight: float
    evidence_source_ids: tuple[str, ...]
    is_authoritative_query: bool = False
    evidence_is_factual_truth: bool = False


@dataclass(frozen=True)
class ObjectiveFeedback:
    objective_id: str
    reviewed_positive_labels: int
    reviewed_negative_labels: int
    candidates: tuple[FeedbackTermCandidate, ...]
    withheld_reasons: tuple[str, ...]
    query_mutation_approved: bool = False


@dataclass(frozen=True)
class FeedbackReport:
    mandate_digest: str
    source_snapshot_digest: str
    objective_plan_digest: str
    query_lattice_digest: str
    policy_digest: str
    indexed_passage_count: int
    label_count: int
    objectives: tuple[ObjectiveFeedback, ...]
    rejected_untrusted_term_count: int
    feedback_digest: str
    source_publication_authorized: bool = False
    automatic_query_approval: bool = False
    crawler_rights_extended: bool = False


def propose_reviewed_query_terms(
    mandate: CampaignMandate,
    policy: SourcePolicyProjection,
    objectives: ObjectivePlan,
    lattice: QueryLattice,
    index: EphemeralIndex,
    judgments: Iterable[PassageJudgment],
    *,
    now: float,
    authorized: bool,
    min_grade: int = 2,
    max_labels: int = 256,
    max_per_objective: int = 8,
    min_support_sources: int = 1,
    max_term_length: int = 32,
) -> FeedbackReport:
    mandate.admit(now=now, authorized=authorized)
    integer(min_grade, "positive label threshold", 1, 3)
    integer(max_labels, "feedback labels", 1, 512)
    integer(max_per_objective, "feedback proposals per objective", 1, 32)
    integer(min_support_sources, "feedback source evidence target", 1, 16)
    integer(max_term_length, "feedback token maximum length", 2, 64)
    if any(x != mandate.fingerprint for x in (
        policy.mandate_digest, objectives.mandate_digest,
        lattice.mandate_digest, index.mandate_digest,
    )):
        raise PermissionError("cross-mandate query feedback")
    if index.source_snapshot_digest != policy.source_snapshot_digest:
        raise PermissionError("feedback index uses stale source policy")
    if lattice.objective_plan_digest != objectives.plan_digest:
        raise PermissionError("feedback query lattice not bound to operator objectives")
    if set(index.admitted_source_ids) - set(policy.allowed_source_ids):
        raise PermissionError("query feedback contains source no longer eligible")
    if not set(index.rejected_source_ids).issubset(
        set(policy.allowed_source_ids) | set(policy.excluded_source_ids)
    ):
        raise PermissionError("feedback source rejection outside current policy universe")
    rows = tuple(judgments)
    if len(rows) > max_labels:
        raise ValueError("feedback relevance-label capacity exceeded")
    objective_ids = {x.objective_id for x in objectives.objectives}
    passages = {
        (x.source_id, x.passage_hash, x.start, x.end): x
        for x in index.passages
    }
    if len(passages) != len(index.passages):
        raise ValueError("ambiguous feedback passage identity")
    seen = set()
    positive = defaultdict(list)
    negative = defaultdict(list)
    for item in rows:
        if not isinstance(item, PassageJudgment):
            raise TypeError("typed reviewed feedback label required")
        key = (item.source_id, item.passage_hash, item.start, item.end)
        if item.objective_id not in objective_ids or key not in passages:
            raise PermissionError("feedback label outside objective or current index")
        if item.source_id not in policy.allowed_source_ids:
            raise PermissionError("feedback refers to withdrawn source")
        if not item.operator_reviewed:
            raise PermissionError("automated/unsupported relevance labels denied")
        identity = item.objective_id, key
        if identity in seen:
            raise ValueError("duplicate reviewed relevance judgment")
        seen.add(identity)
        (positive if item.grade >= min_grade else negative)[item.objective_id].append(item)
    frequency = Counter()
    for passage in index.passages:
        for token in passage.terms:
            frequency[token] += 1
    outcomes = []
    excluded_tokens = 0
    for objective in objectives.objectives:
        existing = {token for variant in lattice.queries
                    if variant.objective_id == objective.objective_id
                    for token in variant.terms}
        blocked = set(objective.blocked_terms)
        positive_labels = positive[objective.objective_id]
        negative_labels = negative[objective.objective_id]
        positive_terms: dict[str, set] = defaultdict(set)
        negative_terms: dict[str, set] = defaultdict(set)
        supporting_sources: dict[str, set[str]] = defaultdict(set)
        for label in positive_labels:
            snippet = passages[(
                label.source_id, label.passage_hash, label.start, label.end
            )]
            for term in snippet.terms:
                positive_terms[term].add(
                    (label.source_id, label.passage_hash, label.start, label.end)
                )
                supporting_sources[term].add(label.source_id)
        for label in negative_labels:
            snippet = passages[(
                label.source_id, label.passage_hash, label.start, label.end
            )]
            for term in snippet.terms:
                negative_terms[term].add(
                    (label.source_id, label.passage_hash, label.start, label.end)
                )
        proposed = []
        for term, pos in positive_terms.items():
            if (term in existing or term in blocked or term in _NOISE
                or len(term) < 3 or len(term) > max_term_length
                or not term.isalnum() or not term.isascii()):
                excluded_tokens += 1
                continue
            hosts = supporting_sources[term]
            if len(hosts) < min_support_sources:
                continue
            count_negative = len(negative_terms.get(term, set()))
            specificity = log(
                (len(index.passages) + 1) / (frequency.get(term, 0) + 1)
            ) + 1.0
            # The score is an explainable local ranking heuristic, not a
            # relevance probability or a claim of source independence.
            heuristic = (
                len(pos) / max(1, len(positive_labels))
                - count_negative / max(1, len(negative_labels))
            )
            if heuristic <= 0:
                continue
            weight = heuristic * specificity * min(1.0, len(hosts) / 3)
            proposed.append(FeedbackTermCandidate(
                objective_id=objective.objective_id,
                term=term,
                positive_label_count=len(pos),
                negative_label_count=count_negative,
                reviewed_source_count=len(hosts),
                document_frequency=frequency.get(term, 0),
                lexical_specificity=round(specificity, 8),
                proposed_weight=round(weight, 8),
                evidence_source_ids=tuple(sorted(hosts)),
            ))
        proposed.sort(key=lambda x: (
            -x.proposed_weight, -x.reviewed_source_count, x.term
        ))
        reasons = []
        if not positive_labels:
            reasons.append("no_positive_human_relevance_labels")
        if not proposed:
            reasons.append("no_safe_explainable_feedback_terms")
        reasons.append("operator_must_approve_any_future_query_change")
        outcomes.append(ObjectiveFeedback(
            objective_id=objective.objective_id,
            reviewed_positive_labels=len(positive_labels),
            reviewed_negative_labels=len(negative_labels),
            candidates=tuple(proposed[:max_per_objective]),
            withheld_reasons=tuple(reasons),
        ))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": policy.source_snapshot_digest,
        "objectives": objectives.plan_digest,
        "lattice": lattice.lattice_digest,
        "index": index.index_digest,
        "policy": policy.policy_digest,
        "labels": [asdict(x) for x in rows],
        "recommendations": [asdict(x) for x in outcomes],
        "excluded": excluded_tokens,
        "limits": (min_grade, max_labels, max_per_objective,
                   min_support_sources, max_term_length),
    }
    return FeedbackReport(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=policy.source_snapshot_digest,
        objective_plan_digest=objectives.plan_digest,
        query_lattice_digest=lattice.lattice_digest,
        policy_digest=policy.policy_digest,
        indexed_passage_count=len(index.passages),
        label_count=len(rows),
        objectives=tuple(outcomes),
        rejected_untrusted_term_count=excluded_tokens,
        feedback_digest=digest(payload),
    )
