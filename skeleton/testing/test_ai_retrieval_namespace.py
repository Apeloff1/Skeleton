from __future__ import annotations

def test_ai_retrieval_pipeline_uses_canonical_ai_tree_contracts() -> None:
    from skeleton.ai.runtime.retrieval import pipeline
    from skeleton.ai.runtime.retrieval.fusion import ScoredResult
    from skeleton.ai.runtime.retrieval.query import QueryPlanner
    assert pipeline.ScoredResult is ScoredResult
    assert pipeline.QueryPlanner is QueryPlanner

def test_ai_retrieval_pipeline_does_not_import_legacy_namespace() -> None:
    from pathlib import Path
    source=Path("skeleton/ai/runtime/retrieval/pipeline.py").read_text(encoding="utf-8")
    assert "skeleton.retrieval" not in source
