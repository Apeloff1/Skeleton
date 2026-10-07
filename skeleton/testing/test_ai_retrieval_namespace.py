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

def test_ai_retrieval_index_and_ingestor_use_ai_tree_types() -> None:
    from skeleton.ai.runtime.retrieval.chunking import Chunker
    from skeleton.ai.runtime.retrieval.freshness import PlaneFreshness
    from skeleton.ai.runtime.retrieval.fusion import ScoredResult
    from skeleton.ai.runtime.retrieval.index import InvertedIndex
    from skeleton.ai.runtime.retrieval.ingest import CorpusIngestor
    assert InvertedIndex.search.__globals__["ScoredResult"] is ScoredResult
    assert InvertedIndex.freshness_state.__globals__["PlaneFreshness"] is PlaneFreshness
    assert CorpusIngestor.__init__.__annotations__.get("chunker") in {None, Chunker, "Chunker"}

def test_ai_retrieval_core_has_no_legacy_retrieval_imports() -> None:
    from pathlib import Path
    for relative in ("pipeline.py","index.py","ingest.py"):
        source=Path("skeleton/ai/runtime/retrieval",relative).read_text(encoding="utf-8")
        assert "skeleton.retrieval" not in source
