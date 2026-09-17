from __future__ import annotations

from types import MappingProxyType

import pytest

from skeleton.pipelines.composer import PipelineComposer, Stage
from skeleton.pipelines.speculative_rag import (
    CONTEXT_KEY,
    SpeculativeRagError,
    bind_quad_search_pipeline,
    execute_with_speculative_rag,
    plan_pipeline_queries,
    prefetch_for_pipeline,
    prefetch_from_genesis,
)
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.pipeline import SearchPipeline
from skeleton.retrieval.query import QueryPlanner
from skeleton.retrieval.quad import QuadRetriever


def _result(fragment_id: str, content: str, score: float = 1.0) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content,
        score=score,
        plane="rag",
        provenance="speculative-test",
    )


def test_pipeline_query_plan_is_bounded_deterministic_and_seeded() -> None:
    queries = plan_pipeline_queries(
        "NPC",
        {"description": "  a weary  ferryman  "},
        limit=3,
    )

    assert queries == (
        "a weary ferryman",
        "persona a weary ferryman",
        "dialogue a weary ferryman",
    )


def test_empty_or_blank_context_plans_no_queries() -> None:
    assert plan_pipeline_queries("npc", {}) == ()
    assert plan_pipeline_queries("npc", {"description": "   "}) == ()


def test_unknown_pipeline_uses_seed_only() -> None:
    assert plan_pipeline_queries("custom", {"vision": "forge a keep"}) == (
        "forge a keep",
    )


@pytest.mark.parametrize("limit", [True, 1.5, "2"])
def test_query_limit_must_be_a_real_integer(limit) -> None:
    with pytest.raises(SpeculativeRagError, match="integer"):
        plan_pipeline_queries("npc", {"description": "x"}, limit=limit)


def test_query_limit_must_be_positive() -> None:
    with pytest.raises(SpeculativeRagError, match=">= 1"):
        plan_pipeline_queries("npc", {"description": "x"}, limit=0)


def test_missing_retriever_does_not_block_planning() -> None:
    bundle = prefetch_for_pipeline("npc", {"description": "a spy"})
    assert bundle.queries == (
        "a spy",
        "persona a spy",
        "dialogue a spy",
        "archetype a spy",
    )
    assert bundle.prepared == MappingProxyType({})
    assert bundle.failures == ()


def test_quad_prefetch_is_reused_by_composer_stages_without_double_fetch() -> None:
    calls: list[str] = []

    class RagPlane:
        def query(self, query: str, top_k: int):
            calls.append(query)
            return [_result(f"doc:{query}", query)]

    quad = QuadRetriever()
    quad.register_plane("rag", RagPlane())
    seen: list[str] = []

    def consume(context):
        bundle = context[CONTEXT_KEY]
        docs = bundle.documents_for("a weary ferryman")
        seen.extend(item.fragment_id for item in docs)
        return {"consumed": len(docs)}

    run = execute_with_speculative_rag(
        PipelineComposer(),
        "npc",
        [Stage("consume", consume)],
        initial_context={"description": "a weary ferryman"},
        search_pipeline=bind_quad_search_pipeline(quad),
        limit=1,
    )

    assert run.succeeded is True
    assert calls == ["a weary ferryman"]
    assert seen == ["doc:a weary ferryman"]
    assert run.context[CONTEXT_KEY].to_dict()["document_ids"] == [
        "doc:a weary ferryman"
    ]


def test_prefetch_failure_does_not_fail_the_pipeline() -> None:
    def broken(_query: str):
        raise RuntimeError("transient plane outage")

    planner = QueryPlanner()
    planner.register("quad", broken)
    observed = {}

    def inspect(context):
        observed["failures"] = context[CONTEXT_KEY].failures
        return {"ok": True}

    run = execute_with_speculative_rag(
        PipelineComposer(),
        "animation",
        [Stage("inspect", inspect)],
        initial_context={"description": "a knight"},
        search_pipeline=SearchPipeline(planner),
        limit=1,
    )

    assert run.succeeded is True
    assert observed["failures"] == ("a knight:quad",)
    assert run.context["ok"] is True


def test_prefetch_from_genesis_uses_quad_and_ignores_unknown_handles() -> None:
    calls: list[str] = []

    class RagPlane:
        def query(self, query: str, top_k: int):
            calls.append(query)
            return [_result(f"doc:{query}", query)]

    quad = QuadRetriever()
    quad.register_plane("rag", RagPlane())

    class Genesis:
        handles = {"quad": quad, "other": object()}

    bundle = prefetch_from_genesis(
        Genesis(),
        "npc",
        {"description": "a spy"},
        limit=1,
    )
    assert calls == ["a spy"]
    assert bundle.documents_for("a spy")[0].fragment_id == "doc:a spy"

    empty = prefetch_from_genesis(object(), "npc", {"description": "a spy"}, limit=1)
    assert empty.prepared == MappingProxyType({})


def test_prepared_mapping_is_immutable() -> None:
    planner = QueryPlanner()
    planner.register("quad", lambda query: [_result("doc", query)])
    bundle = prefetch_for_pipeline(
        "npc",
        {"description": "a spy"},
        search_pipeline=SearchPipeline(planner),
        limit=1,
    )

    with pytest.raises(TypeError):
        bundle.prepared["npc"] = bundle.prepared["a spy"]  # type: ignore[index]
