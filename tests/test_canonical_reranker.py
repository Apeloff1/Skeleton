"""Canonical reranking must be typed, bounded, and auditable."""

import pytest

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.pipeline import SearchPipeline
from skeleton.retrieval.query import QueryPlanner
from skeleton.retrieval.rerank import Reranker as RuleReranker
from skeleton.retrieval.reranker import FeatureReranker
from skeleton.retrieval.reranker_contract import (
    CanonicalReranker,
    DiversityRerankStage,
    FeatureRerankStage,
    RuleRerankStage,
)
from skeleton.retrieval.ranking import Ranker


def _hit(fragment_id: str, content: str, score: float) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content,
        score=score,
        plane="rag",
        provenance="test",
    )


def test_canonical_pipeline_emits_stage_receipts() -> None:
    rules = RuleReranker(
        [RuleReranker.metadata_boost("priority", 2.0)]
    )
    feature = FeatureReranker()
    diversity = Ranker(recency_weight=0.0, diversity_weight=0.0)
    pipeline = CanonicalReranker(
        (
            RuleRerankStage(rules),
            FeatureRerankStage(feature),
            DiversityRerankStage(diversity),
        )
    )
    rows = [
        _hit("a", "alpha exact", 0.1),
        _hit("b", "unrelated", 0.9),
    ]
    rows[0].metadata["priority"] = True

    outcome = pipeline.run("alpha", rows, top_k=2)

    assert len(outcome.results) == 2
    assert [receipt.stage for receipt in outcome.receipts] == [
        "rule",
        "feature",
        "diversity",
    ]
    assert all(receipt.before_digest for receipt in outcome.receipts)
    assert all(receipt.after_digest for receipt in outcome.receipts)


def test_stage_cannot_inject_unknown_fragment() -> None:
    class Inject:
        name = "inject"

        def rerank(self, query, items, *, top_k):
            return [_hit("new", "evil", 1.0)]

    pipeline = CanonicalReranker((Inject(),))
    with pytest.raises(ValueError, match="injected unknown fragment"):
        pipeline.run("alpha", [_hit("a", "alpha", 1.0)], top_k=1)


def test_stage_cannot_duplicate_fragment() -> None:
    class Duplicate:
        name = "duplicate"

        def rerank(self, query, items, *, top_k):
            return [items[0], items[0]]

    pipeline = CanonicalReranker((Duplicate(),))
    with pytest.raises(ValueError, match="duplicated fragment"):
        pipeline.run("alpha", [_hit("a", "alpha", 1.0)], top_k=2)


def test_stage_cannot_exceed_limit() -> None:
    class Overrun:
        name = "overrun"

        def rerank(self, query, items, *, top_k):
            return list(items)

    pipeline = CanonicalReranker((Overrun(),))
    with pytest.raises(ValueError, match="exceeded top_k"):
        pipeline.run(
            "alpha",
            [_hit("a", "a", 1.0), _hit("b", "b", 0.5)],
            top_k=1,
        )


def test_search_pipeline_exposes_canonical_rerank_receipts() -> None:
    planner = QueryPlanner()
    planner.register(
        "rag",
        lambda query: [
            _hit("a", f"{query} exact", 0.1),
            _hit("b", "other", 0.9),
        ],
    )
    canonical = CanonicalReranker(
        (FeatureRerankStage(FeatureReranker()),)
    )
    search = SearchPipeline(planner, rerank_pipeline=canonical)

    outcome = search.search("alpha", top_k=2)

    assert outcome.rerank_receipts
    assert outcome.rerank_receipts[0].stage == "feature"


def test_canonical_and_legacy_pipeline_configuration_cannot_mix() -> None:
    planner = QueryPlanner()
    planner.register("rag", lambda query: [_hit("a", query, 1.0)])
    canonical = CanonicalReranker()

    with pytest.raises(ValueError, match="cannot be combined"):
        SearchPipeline(
            planner,
            rerank_pipeline=canonical,
            ranker=Ranker(),
        )
