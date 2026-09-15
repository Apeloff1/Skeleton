from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from skeleton.retrieval.cache import ResultCache
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever
from skeleton.retrieval.query import QueryPlanner


def _result(
    fragment_id: str,
    content: str,
    *,
    score: float = 1.0,
    plane: str = "rag",
) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=content,
        score=score,
        plane=plane,
        provenance="test",
    )


def test_quad_dispatches_planes_concurrently() -> None:
    rendezvous = Barrier(2)

    class Plane:
        def __init__(self, name: str) -> None:
            self.name = name

        def query(self, query: str, top_k: int):
            rendezvous.wait(timeout=2.0)
            return [_result(f"{self.name}-doc", query)]

    quad = QuadRetriever()
    quad.register_plane("rag", Plane("rag"))
    quad.register_plane("kag", Plane("kag"))

    results = quad.retrieve("parallel", k=4, use_cache=False)

    assert {item.fragment_id for item in results} == {"rag-doc", "kag-doc"}
    assert quad.stats()["plane_failures"] == 0


def test_quad_fusion_order_is_deterministic_when_completion_order_reverses() -> None:
    fast_finished = Event()

    class SlowPlane:
        def query(self, query: str, top_k: int):
            assert fast_finished.wait(timeout=2.0)
            return [_result("slow-doc", query)]

    class FastPlane:
        def query(self, query: str, top_k: int):
            fast_finished.set()
            return [_result("fast-doc", query)]

    quad = QuadRetriever()
    quad.register_plane("slow", SlowPlane())
    quad.register_plane("fast", FastPlane())

    results = quad.retrieve("stable", k=4, use_cache=False)

    assert [item.fragment_id for item in results] == ["slow-doc", "fast-doc"]


def test_registering_plane_invalidates_cached_topology() -> None:
    rag_calls = 0

    class RagPlane:
        def query(self, query: str, top_k: int):
            nonlocal rag_calls
            rag_calls += 1
            return [_result("rag-doc", query)]

    class KagPlane:
        def query(self, query: str, top_k: int):
            return [_result("kag-doc", query)]

    quad = QuadRetriever()
    quad.register_plane("rag", RagPlane())

    first = quad.retrieve("topology", k=4)
    cached = quad.retrieve("topology", k=4)
    assert [item.fragment_id for item in first] == ["rag-doc"]
    assert [item.fragment_id for item in cached] == ["rag-doc"]
    assert rag_calls == 1

    generation_before = quad.stats()["cache_generation"]
    quad.register_plane("kag", KagPlane())
    refreshed = quad.retrieve("topology", k=4)

    assert {item.fragment_id for item in refreshed} == {"rag-doc", "kag-doc"}
    assert rag_calls == 2
    assert quad.stats()["cache_generation"] > generation_before


def test_failed_plane_isolated_and_observable() -> None:
    class BrokenPlane:
        def query(self, query: str, top_k: int):
            raise RuntimeError("plane unavailable")

    class GoodPlane:
        def query(self, query: str, top_k: int):
            return [_result("good-doc", query)]

    quad = QuadRetriever()
    quad.register_plane("broken", BrokenPlane())
    quad.register_plane("good", GoodPlane())

    results = quad.retrieve("degrade gracefully", use_cache=False)

    assert [item.fragment_id for item in results] == ["good-doc"]
    assert quad.stats()["plane_failures"] == 1


def test_normalization_does_not_mutate_caller_owned_result() -> None:
    original = _result("shared", "knowledge", plane="rag")

    normalized = QuadRetriever._normalize_result("kag", original)

    assert normalized is not None
    assert normalized is not original
    assert normalized.plane == "kag"
    assert original.plane == "rag"


def test_quad_adapter_composes_with_planner_prefetch_without_double_query() -> None:
    calls = 0

    class RagPlane:
        def query(self, query: str, top_k: int):
            nonlocal calls
            calls += 1
            return [_result("quad-doc", query)]

    quad = QuadRetriever()
    quad.register_plane("rag", RagPlane())

    planner = QueryPlanner()
    planner.register("quad", quad.as_retriever(k=3, use_cache=False))
    plan = planner.plan("prefetch")
    prefetched = planner.prefetch(plan)
    results = planner.execute("prefetch", plan=plan, prefetched=prefetched)

    assert prefetched.failures == ()
    assert calls == 1
    assert [item.fragment_id for item in results] == ["quad-doc"]


def test_result_cache_isolates_put_and_get_mutations() -> None:
    cache = ResultCache(ttl_s=30.0, max_entries=8)
    original = _result("cached", "original")
    original.metadata["nested"] = {"value": 1}
    cache.put("query", (original,))

    original.content = "mutated after put"
    original.metadata["nested"]["value"] = 999

    first = cache.get("query")
    assert first is not None
    assert first[0].content == "original"
    assert first[0].metadata["nested"]["value"] == 1

    first[0].content = "mutated cache hit"
    first[0].metadata["nested"]["value"] = 777
    second = cache.get("query")

    assert second is not None
    assert second[0].content == "original"
    assert second[0].metadata["nested"]["value"] == 1


def test_result_cache_survives_concurrent_lru_activity() -> None:
    cache = ResultCache(ttl_s=30.0, max_entries=8)
    cached_result = (_result("cached", "value"),)

    def hammer(worker: int) -> None:
        for iteration in range(100):
            key = f"{worker}:{iteration % 16}"
            cache.put(key, cached_result)
            cache.get(key)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(hammer, range(8)))

    assert 0 < cache.size() <= 8
