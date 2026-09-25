"""Skeleton Retrieval — Multi-plane search with auditable fusion.

Fused results preserve which planes contributed and the exact per-plane
contribution used to produce the fused score. The input result objects are
never mutated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Any, Dict, List, Mapping, Optional


class FusionStrategy(Enum):
    RRF = auto()
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
            "content": self.content[:200],
            "score": round(self.score, 6),
            "plane": self.plane,
            "provenance": self.provenance,
        }


def _top_k(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("top_k must be a non-negative integer")
    return value


def _take(items, top_k: int):
    return items[:_top_k(top_k)]


def _finite_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("result score must be a finite number")
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("result score must be a finite number")
    return score


def _fused_result(
    original: ScoredResult,
    *,
    fused_score: float,
    contributions: Mapping[str, float],
) -> ScoredResult:
    """Return a detached result carrying complete fusion lineage."""

    metadata = dict(original.metadata)
    ordered = {
        plane: round(float(value), 12)
        for plane, value in sorted(contributions.items())
    }
    metadata["fusion_planes"] = tuple(ordered)
    metadata["fusion_contributions"] = ordered
    metadata["fusion_score"] = float(fused_score)
    return replace(
        original,
        score=float(fused_score),
        metadata=metadata,
    )


class Fuser:
    """Fuse results from multiple retrieval planes without losing lineage."""

    def __init__(self, strategy: FusionStrategy = FusionStrategy.RRF, k: int = 60):
        if not isinstance(strategy, FusionStrategy):
            raise TypeError("strategy must be a FusionStrategy")
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError("k must be a positive integer")
        self.strategy = strategy
        self.k = k

    def fuse(
        self,
        results_by_plane: Dict[str, List[ScoredResult]],
        top_k: int = 10,
    ) -> List[ScoredResult]:
        """Fuse results from multiple planes into a deterministic ranked list."""

        _top_k(top_k)
        if self.strategy == FusionStrategy.RRF:
            return self._rrf_fuse(results_by_plane, top_k)
        if self.strategy == FusionStrategy.WEIGHTED:
            return self._weighted_fuse(results_by_plane, top_k)
        if self.strategy == FusionStrategy.CONFIDENCE:
            return self._confidence_fuse(results_by_plane, top_k)
        if self.strategy == FusionStrategy.FIRST:
            first_plane, first = next(iter(results_by_plane.items()), ("", []))
            return [
                _fused_result(
                    result,
                    fused_score=_finite_score(result.score),
                    contributions={first_plane: _finite_score(result.score)},
                )
                for result in _take(first, top_k)
            ]
        raise ValueError(f"unsupported fusion strategy: {self.strategy!r}")

    def _rrf_fuse(
        self,
        results_by_plane: Dict[str, List[ScoredResult]],
        top_k: int,
        *,
        weights: Optional[Mapping[str, float]] = None,
    ) -> List[ScoredResult]:
        """Reciprocal Rank Fusion with per-plane contribution evidence."""

        scores: Dict[str, float] = {}
        fragments: Dict[str, ScoredResult] = {}
        contributions: Dict[str, Dict[str, float]] = {}

        for plane, results in results_by_plane.items():
            if weights is None:
                weight = 1.0
            elif plane not in weights:
                raise ValueError(f"fusion weight for {plane!r} is required")
            else:
                weight = _finite_score(weights[plane])
            if weight < 0:
                raise ValueError("fusion weights must be non-negative")
            for rank, result in enumerate(results, 1):
                if not isinstance(result, ScoredResult):
                    raise TypeError("fusion inputs must be ScoredResult")
                fid = result.fragment_id
                contribution = weight / (self.k + rank)
                scores[fid] = scores.get(fid, 0.0) + contribution
                contributions.setdefault(fid, {})[plane] = (
                    contributions.setdefault(fid, {}).get(plane, 0.0) + contribution
                )
                if fid not in fragments:
                    fragments[fid] = result

        ranked = _take(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])),
            top_k,
        )
        return [
            _fused_result(
                fragments[fid],
                fused_score=score,
                contributions=contributions[fid],
            )
            for fid, score in ranked
        ]

    def weighted_rrf(
        self,
        results_by_plane: Dict[str, List[ScoredResult]],
        weights: Mapping[str, float],
        top_k: int = 10,
    ) -> List[ScoredResult]:
        """Public adaptive-RRF primitive used by QuadRetriever."""

        return self._rrf_fuse(results_by_plane, top_k, weights=weights)

    def _weighted_fuse(
        self,
        results_by_plane: Dict[str, List[ScoredResult]],
        top_k: int,
    ) -> List[ScoredResult]:
        """Score-weighted fusion with explicit plane contributions."""

        weights = {"rag": 1.0, "cag": 0.8, "mag": 0.7, "kag": 0.9}
        scores: Dict[str, float] = {}
        fragments: Dict[str, ScoredResult] = {}
        contributions: Dict[str, Dict[str, float]] = {}

        for plane, results in results_by_plane.items():
            if plane not in weights:
                raise ValueError(f"unknown fusion plane {plane!r}")
            weight = weights[plane]
            for result in results:
                if not isinstance(result, ScoredResult):
                    raise TypeError("fusion inputs must be ScoredResult")
                contribution = _finite_score(result.score) * weight
                fid = result.fragment_id
                scores[fid] = scores.get(fid, 0.0) + contribution
                contributions.setdefault(fid, {})[plane] = (
                    contributions.setdefault(fid, {}).get(plane, 0.0) + contribution
                )
                if fid not in fragments:
                    fragments[fid] = result

        ranked = _take(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])),
            top_k,
        )
        return [
            _fused_result(
                fragments[fid],
                fused_score=score,
                contributions=contributions[fid],
            )
            for fid, score in ranked
        ]

    def _confidence_fuse(
        self,
        results_by_plane: Dict[str, List[ScoredResult]],
        top_k: int,
    ) -> List[ScoredResult]:
        """Combine independent confidence-like scores using noisy-OR."""

        misses: Dict[str, float] = {}
        fragments: Dict[str, ScoredResult] = {}
        contributions: Dict[str, Dict[str, float]] = {}
        for plane, results in results_by_plane.items():
            for result in results:
                if not isinstance(result, ScoredResult):
                    raise TypeError("fusion inputs must be ScoredResult")
                confidence = _finite_score(result.score)
                if not 0.0 <= confidence <= 1.0:
                    raise ValueError("confidence fusion scores must be in [0, 1]")
                fid = result.fragment_id
                misses[fid] = misses.get(fid, 1.0) * (1.0 - confidence)
                contributions.setdefault(fid, {})[plane] = confidence
                if fid not in fragments:
                    fragments[fid] = result

        scores = {fid: 1.0 - miss for fid, miss in misses.items()}
        ranked = _take(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])),
            top_k,
        )
        return [
            _fused_result(
                fragments[fid],
                fused_score=score,
                contributions=contributions[fid],
            )
            for fid, score in ranked
        ]

    def stats(self) -> Dict[str, Any]:
        return {"strategy": self.strategy.name, "k": self.k}


class Ranker:
    """Re-rank results using feature-based scoring."""

    def __init__(self):
        self._queries = 0
        self._reranked = 0

    def rerank(
        self,
        results: List[ScoredResult],
        query: str,
        top_k: int = 10,
    ) -> List[ScoredResult]:
        """Re-rank results based on query relevance features."""

        self._queries += 1
        query_terms = set(query.lower().split())
        scored = []
        for result in results:
            content_terms = set(result.content.lower().split())
            overlap = len(query_terms & content_terms)
            feature_score = _finite_score(result.score) * (1 + 0.1 * overlap)
            scored.append((feature_score, result))

        scored.sort(key=lambda item: (-item[0], item[1].fragment_id))
        self._reranked += len(scored)
        return _take([result for _, result in scored], top_k)

    def stats(self) -> Dict[str, Any]:
        return {"queries": self._queries, "reranked": self._reranked}
