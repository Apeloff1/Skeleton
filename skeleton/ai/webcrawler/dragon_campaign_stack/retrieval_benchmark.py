"""Operator-labeled offline retrieval evaluation, comparative without self-grant.

A source query rank is not a factual-confidence estimate. These metrics
measure exact captured passage ranking against operator-reported relevance
labels, all attached to the same immutable campaign snapshot and ephemeral
index. Labels cannot come from untrusted web instructions or auto-approve
publication. Never claim state-of-the-art performance without an independently
controlled comparator, dataset custody, environment and full acceptance gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log2
from typing import Iterable

from .contracts import CampaignMandate, bounded_text, digest, integer
from .objectives import ObjectivePlan
from .query_lattice import QueryLattice
from .retrieval_fusion import RetrievalFusion
from .source_index import EphemeralIndex


@dataclass(frozen=True)
class PassageJudgment:
    objective_id: str
    source_id: str
    passage_hash: str
    start: int
    end: int
    grade: int
    operator_reference: str
    operator_reviewed: bool

    def __post_init__(self) -> None:
        bounded_text(self.objective_id, "objective label", 64)
        from .contracts import exact_digest
        exact_digest(self.source_id, "judgment source")
        exact_digest(self.passage_hash, "judgment passage")
        integer(self.start, "judged span start", 0, 24_000)
        integer(self.end, "judged span end", 1, 24_000)
        if self.end <= self.start:
            raise ValueError("invalid judged source span")
        integer(self.grade, "judged relevance", 0, 3)
        bounded_text(self.operator_reference, "human judgment reference", 256)
        if type(self.operator_reviewed) is not bool:
            raise ValueError("explicit human judgment status required")


@dataclass(frozen=True)
class ObjectiveRetrievalMetrics:
    objective_id: str
    total_judgments: int
    relevant_judgments: int
    examined_results: int
    relevant_found: int
    recall_at_k: float | None
    reciprocal_rank_at_k: float | None
    normalized_dcg_at_k: float | None
    label_coverage: bool
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalBenchmark:
    mandate_digest: str
    source_snapshot_digest: str
    objective_plan_digest: str
    lattice_digest: str
    index_digest: str
    retrieval_digest: str
    label_universe_digest: str
    top_k: int
    objectives: tuple[ObjectiveRetrievalMetrics, ...]
    macro_recall_at_k: float | None
    macro_reciprocal_rank_at_k: float | None
    macro_ndcg_at_k: float | None
    unjudged_result_count: int
    unlabeled_objective_count: int
    benchmark_digest: str
    performance_certified: bool = False
    external_fact_verification: bool = False
    autonomous_optimization_authorized: bool = False


@dataclass(frozen=True)
class RetrievalComparison:
    baseline_digest: str
    candidate_digest: str
    compatible: bool
    objective_delta: tuple[tuple[str, float | None], ...]
    macro_ndcg_delta: float | None
    macro_recall_delta: float | None
    review_reasons: tuple[str, ...]
    comparison_digest: str
    superiority_certified: bool = False


def _mean(values: Iterable[float | None]) -> float | None:
    known = tuple(x for x in values if x is not None)
    return round(sum(known) / len(known), 8) if known else None


def _dcg(grades: Iterable[int]) -> float:
    return sum((2**value - 1) / log2(position + 2)
               for position, value in enumerate(grades))


def evaluate_fused_retrieval(
    mandate: CampaignMandate,
    plan: ObjectivePlan,
    lattice: QueryLattice,
    index: EphemeralIndex,
    retrieval: RetrievalFusion,
    judgments: Iterable[PassageJudgment],
    *,
    now: float,
    authorized: bool,
    top_k: int = 10,
    max_labels: int = 512,
) -> RetrievalBenchmark:
    mandate.admit(now=now, authorized=authorized)
    integer(top_k, "retrieval benchmark k", 1, 32)
    integer(max_labels, "benchmark label bound", 1, 1024)
    if plan.mandate_digest != mandate.fingerprint or (
        lattice.mandate_digest != mandate.fingerprint
        or index.mandate_digest != mandate.fingerprint
        or retrieval.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("cross-mandate benchmark")
    if lattice.objective_plan_digest != plan.plan_digest or (
        retrieval.lattice_digest != lattice.lattice_digest
        or retrieval.index_digest != index.index_digest
    ):
        raise PermissionError("benchmark used incompatible query or index receipt")
    if index.source_snapshot_digest != retrieval.source_snapshot_digest:
        raise PermissionError("benchmark mixes different crawl snapshots")
    if len(retrieval.results) > 64 or len(plan.objectives) > 64:
        raise ValueError("benchmark exceeds bounded research universe")
    rows = tuple(judgments)
    if len(rows) > max_labels:
        raise ValueError("judgment capacity exceeded")
    current_passages = {
        (x.source_id, x.passage_hash, x.start, x.end)
        for x in index.passages
    }
    objective_universe = {x.objective_id for x in plan.objectives}
    labels = {}
    for judgment in rows:
        if not isinstance(judgment, PassageJudgment):
            raise TypeError("typed operator judgment required")
        if judgment.objective_id not in objective_universe:
            raise PermissionError("judgment refers to unapproved objective")
        key = (judgment.source_id, judgment.passage_hash, judgment.start, judgment.end)
        if key not in current_passages:
            raise PermissionError("judgment not anchored to exact current source index")
        identity = (judgment.objective_id, key)
        if identity in labels:
            raise ValueError("duplicate relevance judgment")
        if judgment.operator_reviewed is not True:
            raise PermissionError("unreviewed relevance label cannot certify ranking")
        labels[identity] = judgment.grade
    hit_keys = []
    for hit in retrieval.results:
        key = (hit.source_id, hit.passage_hash, hit.start, hit.end)
        if key not in current_passages:
            raise PermissionError("retrieval hit outside current source index")
        if key in hit_keys:
            raise ValueError("duplicate ranked passage identity")
        hit_keys.append(key)
    metrics = []
    for objective in plan.objectives:
        relevant = {
            key: grade for (obj_id, key), grade in labels.items()
            if obj_id == objective.objective_id
        }
        observed = hit_keys[:top_k]
        ranked_grades = [relevant.get(key, 0) for key in observed]
        positives = sum(grade > 0 for grade in relevant.values())
        found = sum(grade > 0 for grade in ranked_grades)
        judged = bool(relevant)
        if not judged:
            recall = rr = ndcg = None
        else:
            recall = round(found / positives, 8) if positives else None
            rr = next((round(1 / i, 8) for i, grade in enumerate(ranked_grades, 1)
                       if grade > 0), 0.0) if positives else None
            ideal = _dcg(sorted(relevant.values(), reverse=True)[:top_k])
            ndcg = round(_dcg(ranked_grades) / ideal, 8) if ideal else None
        limitations = []
        if not judged:
            limitations.append("no_reviewed_relevance_labels")
        elif not positives:
            limitations.append("no_positive_relevance_labels")
        if any(key not in relevant for key in observed):
            limitations.append("unjudged_ranked_passages")
        limitations.append("lexical_retrieval_metrics_not_factual_truth")
        metrics.append(ObjectiveRetrievalMetrics(
            objective_id=objective.objective_id,
            total_judgments=len(relevant), relevant_judgments=positives,
            examined_results=len(observed), relevant_found=found,
            recall_at_k=recall, reciprocal_rank_at_k=rr,
            normalized_dcg_at_k=ndcg,
            label_coverage=judged,
            limitations=tuple(limitations),
        ))
    unjudged = sum(
        all((obj, key) not in labels for obj in objective_universe)
        for key in hit_keys[:top_k]
    )
    label_digest = digest({
        "snapshot": index.source_snapshot_digest,
        "judgments": [asdict(x) for x in sorted(
            rows, key=lambda x: (x.objective_id, x.source_id, x.start, x.end)
        )],
    })
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": index.source_snapshot_digest,
        "objective_plan": plan.plan_digest,
        "lattice": lattice.lattice_digest,
        "index": index.index_digest,
        "retrieval": retrieval.fusion_digest,
        "labels": label_digest,
        "top_k": top_k,
        "metrics": [asdict(x) for x in metrics],
        "unjudged": unjudged,
    }
    return RetrievalBenchmark(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=index.source_snapshot_digest,
        objective_plan_digest=plan.plan_digest,
        lattice_digest=lattice.lattice_digest, index_digest=index.index_digest,
        retrieval_digest=retrieval.fusion_digest,
        label_universe_digest=label_digest, top_k=top_k,
        objectives=tuple(metrics),
        macro_recall_at_k=_mean(x.recall_at_k for x in metrics),
        macro_reciprocal_rank_at_k=_mean(
            x.reciprocal_rank_at_k for x in metrics
        ),
        macro_ndcg_at_k=_mean(x.normalized_dcg_at_k for x in metrics),
        unjudged_result_count=unjudged,
        unlabeled_objective_count=sum(not x.label_coverage for x in metrics),
        benchmark_digest=digest(payload),
    )


def compare_retrieval_benchmarks(
    baseline: RetrievalBenchmark,
    candidate: RetrievalBenchmark,
) -> RetrievalComparison:
    if not isinstance(baseline, RetrievalBenchmark) or not isinstance(candidate, RetrievalBenchmark):
        raise TypeError("two typed benchmark receipts required")
    compatible = all((
        baseline.mandate_digest == candidate.mandate_digest,
        baseline.source_snapshot_digest == candidate.source_snapshot_digest,
        baseline.objective_plan_digest == candidate.objective_plan_digest,
        baseline.index_digest == candidate.index_digest,
        baseline.label_universe_digest == candidate.label_universe_digest,
        baseline.top_k == candidate.top_k,
    ))
    if not compatible:
        raise PermissionError("benchmark comparison violates same-corpus custody")
    if len(baseline.objectives) != len(candidate.objectives):
        raise ValueError("different objective benchmark universes")
    before = {x.objective_id: x for x in baseline.objectives}
    after = {x.objective_id: x for x in candidate.objectives}
    if set(before) != set(after):
        raise ValueError("different objective identities in comparison")
    deltas = []
    for ident in sorted(before):
        a, b = before[ident], after[ident]
        x = (
            round(b.normalized_dcg_at_k - a.normalized_dcg_at_k, 8)
            if a.normalized_dcg_at_k is not None and
               b.normalized_dcg_at_k is not None else None
        )
        deltas.append((ident, x))
    macro = (
        round(candidate.macro_ndcg_at_k - baseline.macro_ndcg_at_k, 8)
        if baseline.macro_ndcg_at_k is not None and candidate.macro_ndcg_at_k is not None
        else None
    )
    recall = (
        round(candidate.macro_recall_at_k - baseline.macro_recall_at_k, 8)
        if baseline.macro_recall_at_k is not None and candidate.macro_recall_at_k is not None
        else None
    )
    reasons = ["human_ground_truth_and_comparator_review_required"]
    if macro is None or recall is None:
        reasons.append("incomplete_relevance_judgment_coverage")
    if macro is not None and macro <= 0:
        reasons.append("no_observed_ndcg_improvement")
    if recall is not None and recall < 0:
        reasons.append("relevant_passage_recall_regressed")
    payload = {
        "baseline": baseline.benchmark_digest,
        "candidate": candidate.benchmark_digest,
        "objectives": deltas, "macro_ndcg": macro,
        "macro_recall": recall, "reasons": reasons,
    }
    return RetrievalComparison(
        baseline_digest=baseline.benchmark_digest,
        candidate_digest=candidate.benchmark_digest,
        compatible=True, objective_delta=tuple(deltas),
        macro_ndcg_delta=macro, macro_recall_delta=recall,
        review_reasons=tuple(reasons),
        comparison_digest=digest(payload),
    )
