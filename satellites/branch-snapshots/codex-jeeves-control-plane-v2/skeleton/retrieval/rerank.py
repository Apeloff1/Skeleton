"""Semantic-ish reranking — metadata-aware re-score for top candidates.

The fused list is a first pass; rerank inspects candidate metadata for
exact boosts (recency anchor, source tag, explicit preference rules)
without an embedding dependency.

- :class:`RerankRule` — predicate + boost
- :class:`Reranker` — applied rules in order
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from skeleton.kernel.errors import RetrievalError
from skeleton.retrieval.fusion import ScoredResult


@dataclass(frozen=True)
class RerankRule:
    name: str
    predicate: Callable[[ScoredResult], bool]
    boost: float  # added to score if predicate hits
    position: int = 0  # lower-first ordering


class Reranker:
    """Applies ordered rules; stable sort on final score."""

    def __init__(self, rules: Optional[Sequence[RerankRule]] = None) -> None:
        self._rules = sorted(rules or [], key=lambda r: r.position)

    def rerank(
        self, items: Sequence[ScoredResult], *, top_k: Optional[int] = None
    ) -> Tuple[ScoredResult, ...]:
        rescored: List[Tuple[float, ScoredResult]] = []
        for item in items:
            boosted = item.score
            for rule in self._rules:
                if rule.predicate(item):
                    boosted += rule.boost
            rescored.append((boosted, item))
        rescored.sort(key=lambda kv: -kv[0])
        trimmed = rescored[: top_k] if top_k else rescored
        return tuple(
            ScoredResult(
                item_id=item.item_id,
                score=round(boost, 6),
                source=item.source,
                metadata=item.metadata,
            )
            for boost, item in trimmed
        )

    @staticmethod
    def source_boost(source: str, boost: float, position: int = 0) -> RerankRule:
        return RerankRule(
            name=f"source-{source}",
            predicate=lambda item: item.source == source,
            boost=boost,
            position=position,
        )

    @staticmethod
    def metadata_boost(key: str, boost: float, position: int = 0) -> RerankRule:
        return RerankRule(
            name=f"meta-{key}",
            predicate=lambda item: bool(item.metadata.get(key)),
            boost=boost,
            position=position,
        )
