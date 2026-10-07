"""Cache handoff must mint valid receipts, including scoped retrieval."""

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever
from skeleton.retrieval.scope import RetrievalScope


class _HandoffCache:
    def __init__(self) -> None:
        self.calls = 0
        self.value = (
            ScoredResult(
                fragment_id="cached",
                content="cached body",
                score=1.0,
                plane="rag",
            ),
        )

    def get(self, key):
        self.calls += 1
        if self.calls == 1:
            return None
        return self.value

    def put(self, key, results):
        self.value = tuple(results)

    def clear(self):
        pass

    def size(self):
        return 1


class _ScopedPlane:
    def query_scoped(self, query: str, top_k: int, scope):
        raise AssertionError("handoff cache should avoid plane dispatch")


def test_handoff_cache_hit_creates_unscoped_receipt() -> None:
    cache = _HandoffCache()
    quad = QuadRetriever(cache=cache)
    quad.register_plane("rag", _ScopedPlane())

    results, receipt = quad.retrieve_with_receipt("handoff")

    assert [row.fragment_id for row in results] == ["cached"]
    assert receipt.source == "cache"
    assert receipt.scope_digest == ""
    assert cache.calls == 2


def test_handoff_cache_hit_preserves_scoped_receipt_binding() -> None:
    cache = _HandoffCache()
    quad = QuadRetriever(cache=cache)
    quad.register_plane("rag", _ScopedPlane())
    scope = RetrievalScope.from_mapping({"tenant_id": "A"})

    results, receipt = quad.retrieve_scoped_with_receipt(
        "handoff",
        scope,
    )

    assert [row.fragment_id for row in results] == ["cached"]
    assert receipt.source == "cache"
    assert receipt.scope_digest == scope.digest
    assert cache.calls == 2
