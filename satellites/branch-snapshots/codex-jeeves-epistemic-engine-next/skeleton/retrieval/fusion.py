"""
Skeleton Retrieval — Multi-plane search with fusion

Provides:
- Fuser: Result fusion across retrieval planes
- FusionStrategy: RRF, weighted, confidence-based
- ScoredResult: Typed retrieval result
- Ranker: Result re-ranking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class FusionStrategy(Enum):
    RRF = auto()  # Reciprocal Rank Fusion
    WEIGHTED = auto()
    CONFIDENCE = auto()
    FIRST = auto()


@dataclass
class ScoredResult:
    """A single retrieval result with score and provenance."""
    fragment_id: str
    content: str
    score: float
    plane: str = "rag"
    provenance: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "content": self.content[:200],  # Truncate for display
            "score": round(self.score, 6),
            "plane": self.plane,
            "provenance": self.provenance,
        }


class Fuser:
    """Fuse results from multiple retrieval planes."""

    def __init__(self, strategy: FusionStrategy = FusionStrategy.RRF, k: int = 60):
        self.strategy = strategy
        self.k = k

    def fuse(self, results_by_plane: Dict[str, List[ScoredResult]], top_k: int = 10) -> List[ScoredResult]:
        """Fuse results from multiple planes into a single ranked list."""
        if self.strategy == FusionStrategy.RRF:
            return self._rrf_fuse(results_by_plane, top_k)
        elif self.strategy == FusionStrategy.WEIGHTED:
            return self._weighted_fuse(results_by_plane, top_k)
        elif self.strategy == FusionStrategy.FIRST:
            # Return first plane's results
            first = next(iter(results_by_plane.values()), [])
            return first[:top_k]
        else:
            return self._rrf_fuse(results_by_plane, top_k)

    def _rrf_fuse(self, results_by_plane: Dict[str, List[ScoredResult]], top_k: int) -> List[ScoredResult]:
        """Reciprocal Rank Fusion across planes."""
        scores: Dict[str, float] = {}
        fragments: Dict[str, ScoredResult] = {}

        for plane, results in results_by_plane.items():
            for rank, result in enumerate(results, 1):
                fid = result.fragment_id
                scores[fid] = scores.get(fid, 0) + 1.0 / (self.k + rank)
                if fid not in fragments:
                    fragments[fid] = result

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [fragments[fid] for fid, _ in ranked]

    def _weighted_fuse(self, results_by_plane: Dict[str, List[ScoredResult]], top_k: int) -> List[ScoredResult]:
        """Weighted fusion with plane weights."""
        weights = {"rag": 1.0, "cag": 0.8, "mag": 0.7, "kag": 0.9}
        scores: Dict[str, float] = {}
        fragments: Dict[str, ScoredResult] = {}

        for plane, results in results_by_plane.items():
            w = weights.get(plane, 0.5)
            for result in results:
                fid = result.fragment_id
                scores[fid] = scores.get(fid, 0) + result.score * w
                if fid not in fragments:
                    fragments[fid] = result

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [fragments[fid] for fid, _ in ranked]

    def stats(self) -> Dict[str, Any]:
        return {"strategy": self.strategy.name, "k": self.k}


class Ranker:
    """Re-rank results using feature-based scoring."""

    def __init__(self):
        self._queries = 0
        self._reranked = 0

    def rerank(self, results: List[ScoredResult], query: str, top_k: int = 10) -> List[ScoredResult]:
        """Re-rank results based on query relevance features."""
        self._queries += 1
        
        # Simple feature-based scoring
        query_terms = set(query.lower().split())
        scored = []
        for result in results:
            content_terms = set(result.content.lower().split())
            overlap = len(query_terms & content_terms)
            feature_score = result.score * (1 + 0.1 * overlap)
            scored.append((feature_score, result))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        self._reranked += len(scored)
        return [r for _, r in scored[:top_k]]

    def stats(self) -> Dict[str, Any]:
        return {"queries": self._queries, "reranked": self._reranked}
