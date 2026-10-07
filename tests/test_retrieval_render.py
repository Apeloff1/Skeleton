"""Rendered results use the fusion contract and do not inject raw HTML."""

from html import escape

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.ui import ResultRenderer


def test_text_and_html_use_fragment_identity() -> None:
    item = ScoredResult(
        fragment_id="doc<script>",
        content="alpha beta",
        score=0.5,
        plane='rag"plane',
        metadata={"preview": "alpha"},
    )
    text = ResultRenderer.to_text([item])
    html = ResultRenderer.to_html([item])
    assert "doc<script>" in text
    assert "alpha" in text
    assert "<script>" not in html
    assert escape("doc<script>") in html
    assert escape('rag"plane', quote=True) in html
