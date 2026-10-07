"""An untracked plane is not fresh."""

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever


class _Registry:
    def metadata(self, plane):
        return None


def test_untracked_and_planeless_results_are_stale() -> None:
    quad = QuadRetriever.__new__(QuadRetriever)
    quad._freshness = _Registry()
    hit = ScoredResult(fragment_id="doc", content="body", score=0.4, plane="rag", metadata={})
    refreshed = quad._refresh_result_freshness([hit])
    row = refreshed[0].metadata["fusion_freshness"]["rag"]
    assert row == {"tracked": False, "stale": True}
    assert refreshed[0].metadata["stale"] is True
    assert refreshed[0].metadata["freshness_complete"] is False
    blank = ScoredResult(fragment_id="doc", content="body", score=0.4, plane="", metadata={})
    missing = quad._refresh_result_freshness([blank])
    assert missing[0].metadata["stale"] is True
    assert missing[0].metadata["freshness_complete"] is False
