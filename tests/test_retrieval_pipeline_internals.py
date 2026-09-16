from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.pipeline import SearchPipeline
from skeleton.retrieval.query import QueryPlanner, RetrievalError
from skeleton.retrieval.reranker import FeatureReranker


def _result(fragment_id: str, content: str, score: float = 1.0) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content,
        score=score,
        plane="rag",
        provenance="test",
    )


def test_prepare_then_search_reuses_prefetched_retrieval_work() -> None:
    calls = []

    def retrieve(query: str):
        calls.append(query)
        return [_result("doc-1", "alpha document")]

    planner = QueryPlanner()
    planner.register("quad", retrieve)
    pipeline = SearchPipeline(planner)

    prepared = pipeline.prepare("alpha")
    outcome = pipeline.search_prepared(prepared)

    assert calls == ["alpha"]
    assert prepared.failures == ()
    assert [item.fragment_id for item in outcome.results] == ["doc-1"]


def test_prefetch_overlaps_independent_retrievers_and_keeps_plan_order() -> None:
    rendezvous = Barrier(2)

    def retrieve(name: str):
        def _retrieve(query: str):
            rendezvous.wait(timeout=2.0)
            return [_result(name, query)]

        return _retrieve

    planner = QueryPlanner(prefetch_workers=2)
    planner.register("beta", retrieve("beta"))
    planner.register("alpha", retrieve("alpha"))

    plan = planner.plan("parallel")
    prepared = planner.prefetch(plan)

    assert prepared.failures == ()
    assert tuple(prepared.results_by_retriever) == ("alpha", "beta")
    assert [item.fragment_id for item in prepared.results_by_retriever["alpha"]] == [
        "alpha"
    ]
    assert [item.fragment_id for item in prepared.results_by_retriever["beta"]] == [
        "beta"
    ]


def test_prefetch_worker_count_must_be_positive() -> None:
    with pytest.raises(ValueError, match="prefetch_workers"):
        QueryPlanner(prefetch_workers=0)


def test_failed_prefetch_is_retried_by_normal_execution() -> None:
    calls = 0

    def flaky_retrieve(query: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient prefetch failure")
        return [_result("recovered", query)]

    planner = QueryPlanner()
    planner.register("quad", flaky_retrieve)
    pipeline = SearchPipeline(planner)

    prepared = pipeline.prepare("recover")
    assert prepared.failures == ("quad",)

    outcome = pipeline.search_prepared(prepared)

    assert calls == 2
    assert [item.fragment_id for item in outcome.results] == ["recovered"]


def test_replaced_retriever_invalidates_prefetched_results() -> None:
    old_calls = []
    new_calls = []

    def old_retriever(query: str):
        old_calls.append(query)
        return [_result("old", "stale result")]

    def new_retriever(query: str):
        new_calls.append(query)
        return [_result("new", "fresh result")]

    planner = QueryPlanner()
    planner.register("quad", old_retriever)
    pipeline = SearchPipeline(planner)
    prepared = pipeline.prepare("alpha")

    planner.register("quad", new_retriever)
    outcome = pipeline.search_prepared(prepared)

    assert old_calls == ["alpha"]
    assert new_calls == ["alpha"]
    assert [item.fragment_id for item in outcome.results] == ["new"]


def test_execute_retries_when_selected_retriever_is_replaced_midflight() -> None:
    old_started = Event()
    release_old = Event()
    old_calls = []
    new_calls = []

    def old_retriever(query: str):
        old_calls.append(query)
        old_started.set()
        assert release_old.wait(timeout=2.0)
        return [_result("old", "stale result")]

    def new_retriever(query: str):
        new_calls.append(query)
        return [_result("new", "fresh result")]

    planner = QueryPlanner()
    planner.register("quad", old_retriever)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(planner.execute, "alpha")
        assert old_started.wait(timeout=2.0)
        planner.register("quad", new_retriever)
        release_old.set()
        results = future.result(timeout=2.0)

    assert old_calls == ["alpha"]
    assert new_calls == ["alpha"]
    assert [item.fragment_id for item in results] == ["new"]


def test_execute_fails_closed_when_selected_retriever_keeps_changing() -> None:
    old_started = Event()
    release_old = Event()
    middle_started = Event()
    release_middle = Event()

    def old_retriever(query: str):
        old_started.set()
        assert release_old.wait(timeout=2.0)
        return [_result("old", query)]

    def middle_retriever(query: str):
        middle_started.set()
        assert release_middle.wait(timeout=2.0)
        return [_result("middle", query)]

    def newest_retriever(query: str):
        return [_result("newest", query)]

    planner = QueryPlanner()
    planner.register("quad", old_retriever)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(planner.execute, "alpha")
        assert old_started.wait(timeout=2.0)
        planner.register("quad", middle_retriever)
        release_old.set()

        assert middle_started.wait(timeout=2.0)
        planner.register("quad", newest_retriever)
        release_middle.set()

        with pytest.raises(RetrievalError, match="changed repeatedly"):
            future.result(timeout=2.0)


def test_prefetched_result_mapping_shape_is_read_only() -> None:
    planner = QueryPlanner()
    planner.register("quad", lambda query: [_result("doc-1", query)])

    prepared = SearchPipeline(planner).prepare("alpha")

    with pytest.raises(TypeError):
        prepared.results_by_retriever["quad"] = ()  # type: ignore[index]


def test_search_plans_once_and_speculative_mode_does_not_double_fetch() -> None:
    class CountingPlanner(QueryPlanner):
        def __init__(self) -> None:
            super().__init__()
            self.plan_calls = 0

        def plan(self, query: str):
            self.plan_calls += 1
            return super().plan(query)

    fetches = []
    planner = CountingPlanner()
    planner.register(
        "quad",
        lambda query: fetches.append(query) or [_result("doc-1", query)],
    )
    pipeline = SearchPipeline(planner, speculative_prefetch=True)

    outcome = pipeline.search("single pass")

    assert planner.plan_calls == 1
    assert fetches == ["single pass"]
    assert outcome.results[0].fragment_id == "doc-1"


def test_default_top_k_path_uses_planner_limit_without_fuser_attribute() -> None:
    planner = QueryPlanner()
    planner.register(
        "rag",
        lambda query: [
            _result(f"doc-{index}", f"{query} {index}", score=20.0 - index)
            for index in range(20)
        ],
    )

    results = planner.execute("limit")

    assert len(results) == 10


def test_feature_reranker_receives_and_returns_scored_results() -> None:
    planner = QueryPlanner()
    planner.register(
        "rag",
        lambda query: [
            _result("weak", "unrelated words", score=0.2),
            _result("strong", "alpha alpha exact", score=0.2),
        ],
    )
    pipeline = SearchPipeline(planner, feature_reranker=FeatureReranker())

    outcome = pipeline.search("alpha", top_k=2)

    assert all(isinstance(item, ScoredResult) for item in outcome.results)
    assert {item.fragment_id for item in outcome.results} == {"weak", "strong"}
    assert outcome.results[0].fragment_id == "strong"


def test_render_uses_current_fragment_and_content_contract() -> None:
    planner = QueryPlanner()
    planner.register("rag", lambda query: [_result("frag-7", "alpha body")])
    pipeline = SearchPipeline(planner)

    outcome = pipeline.search("alpha", render=True)

    assert "frag-7" in outcome.rendered
    assert "alpha" in outcome.rendered.lower()


def test_custom_renderer_is_honored() -> None:
    planner = QueryPlanner()
    planner.register("rag", lambda query: [_result("frag-1", "body")])
    pipeline = SearchPipeline(
        planner,
        renderer=lambda query, results, terms: f"custom:{query}:{len(results)}",
    )

    outcome = pipeline.search("alpha", render=True)

    assert outcome.rendered == "custom:alpha:1"