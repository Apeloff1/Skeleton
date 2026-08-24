"""Result ranking for the retrieval subsystem.

Post-fusion ranking: apply diversity, recency, and relevance
re-ranking to the fused result set before it enters the context window.
"""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult


class Ranker:
    """Re-rank fused results with diversity and recency bonuses."""

    def __init__(self, *, diversity_weight: float = 0.2, recency_weight: float = 0.1) -> None:
        self.diversity_weight = diversity_weight
        self.recency_weight = recency_weight

    def rank(
        self, items: Sequence[ScoredResult], top_k: int = 10
    ) -> Tuple[ScoredResult, ...]:
        scored = []
        seen_sources: set = set()
        for item in items:
            source_bonus = (
                self.diversity_weight if item.source not in seen_sources else 0.0
            )
            seen_sources.add(item.source)
            recency = item.metadata.get("timestamp", 0)
            recency_bonus = self.recency_weight * recency if recency else 0.0
            final_score = item.score + source_bonus + recency_bonus
            scored.append((item, final_score))
        scored.sort(key=lambda kv: -kv[1])
        return tuple(item for item, _ in scored[:top_k])
