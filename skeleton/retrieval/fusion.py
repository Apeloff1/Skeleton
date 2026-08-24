"""Result fusion for the retrieval subsystem.

When multiple retrievers (TF-IDF, ChromaDB, MAG) return candidates,
fusion decides which items survive to the final context window.

- FusionStrategy: RR (round-robin), RRF (reciprocal rank fusion), weighted
- Fuser: applies a strategy to any number of ranked lists
- ScoredResult: lightweight result wrapper with source attribution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class FusionStrategy(str, Enum):
    ROUND_ROBIN = "ROUND_ROBIN"
    RRF = "RRF"  # Reciprocal Rank Fusion
    WEIGHTED = "WEIGHTED"


@dataclass(frozen=True)
class ScoredResult:
    item_id: str
    score: float
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class Fuser:
    """Combine ranked lists from multiple retrievers."""

    def __init__(
        self,
        strategy: FusionStrategy = FusionStrategy.RRF,
        *,
        rrf_k: float = 60.0,
        weights: Optional[Dict[str, float]] = None,
        top_k: int = 10,
    ) -> None:
        self.strategy = strategy
        self.rrf_k = rrf_k
        self.weights = weights or {}
        self.top_k = top_k

    def fuse(
        self, lists: Dict[str, Sequence[ScoredResult]]
    ) -> Tuple[ScoredResult, ...]:
        """Returns top_k results after applying the configured strategy."""
        if self.strategy is FusionStrategy.RRF:
            return self._rrf(lists)
        if self.strategy is FusionStrategy.WEIGHTED:
            return self._weighted(lists)
        return self._round_robin(lists)

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _round_robin(
        lists: Dict[str, Sequence[ScoredResult]]
    ) -> Tuple[ScoredResult, ...]:
        iterators = {k: iter(v) for k, v in lists.items()}
        seen: set = set()
        out: List[ScoredResult] = []
        while iterators and len(out) < sum(len(v) for v in lists.values()):
            for k in list(iterators):
                try:
                    item = next(iterators[k])
                except StopIteration:
                    del iterators[k]
                    continue
                if item.item_id not in seen:
                    seen.add(item.item_id)
                    out.append(item)
        return tuple(out)

    def _rrf(
        self, lists: Dict[str, Sequence[ScoredResult]]
    ) -> Tuple[ScoredResult, ...]:
        scores: Dict[str, List[float]] = {}
        meta: Dict[str, Dict[str, Any]] = {}
        for source, items in lists.items():
            for rank, item in enumerate(items, start=1):
                scores.setdefault(item.item_id, []).append(
                    1.0 / (self.rrf_k + rank)
                )
                meta.setdefault(item.item_id, {}).update(item.metadata)
        fused = sorted(
            ((sid, sum(vals)) for sid, vals in scores.items()),
            key=lambda kv: -kv[1],
        )
        return tuple(
            ScoredResult(
                item_id=sid,
                score=total,
                source="fused",
                metadata=meta.get(sid, {}),
            )
            for sid, total in fused[: self.top_k]
        )

    def _weighted(
        self, lists: Dict[str, Sequence[ScoredResult]]
    ) -> Tuple[ScoredResult, ...]:
        scores: Dict[str, float] = {}
        meta: Dict[str, Dict[str, Any]] = {}
        for source, items in lists.items():
            w = self.weights.get(source, 1.0)
            for item in items:
                scores[item.item_id] = scores.get(item.item_id, 0.0) + item.score * w
                meta.setdefault(item.item_id, {}).update(item.metadata)
        top = sorted(scores.items(), key=lambda kv: -kv[1])[: self.top_k]
        return tuple(
            ScoredResult(
                item_id=sid, score=total, source="fused", metadata=meta.get(sid, {})
            )
            for sid, total in top
        )
