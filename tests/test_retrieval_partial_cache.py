"""Partial plane failures are explicit and never cached as complete retrieval."""

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever


def test_partial_result_is_not_cached_and_receipt_names_failed_plane() -> None:
    good_calls = []

    class Good:
        def query(self, query: str, top_k: int):
            good_calls.append(query)
            return [ScoredResult("good", query, 1.0, plane="rag")]

    class Broken:
        def query(self, query: str, top_k: int):
            raise RuntimeError("down")

    quad = QuadRetriever()
    quad.register_plane("rag", Good())
    quad.register_plane("kag", Broken())

    first, first_receipt = quad.retrieve_with_receipt("alpha")
    second, second_receipt = quad.retrieve_with_receipt("alpha")

    assert [item.fragment_id for item in first] == ["good"]
    assert [item.fragment_id for item in second] == ["good"]
    assert good_calls == ["alpha", "alpha"]
    assert first_receipt.partial is True
    assert first_receipt.failed_planes == ("kag",)
    assert second_receipt.source == "live"
    assert quad.stats()["cache_size"] == 0
    assert quad.stats()["partial_queries"] == 2
