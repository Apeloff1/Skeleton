"""End-to-end search pipeline — parse → plan → execute → rerank stages → highlight.

QueryPlanner.execute() returns ranked candidates; interactive demos
need the parse/plan/highlight steps glued. SearchPipeline composes
the primitives the package already ships.

Rank stages (optional, fixed order):
  1. rule boost      — ``rerank.Reranker`` (metadata predicate boosts)
  2. feature rerank  — ``reranker.FeatureReranker`` (query–doc features)
  3. diversity rank  — ``ranking.Ranker`` (source diversity + recency)

Each stage is independent and optional; an unconfigured pipeline behaves
exactly as before (planner output straight through).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.highlight import Highlighter
from skeleton.retrieval.query import QueryPlan, QueryPlanner
from skeleton.retrieval.query_language import QueryParser, QueryTerm


@dataclass(frozen=True)
class SearchOutcome:
    query: str
    plan: QueryPlan
    results: Tuple[ScoredResult, ...]
    rendered: str


class SearchPipeline:
    """String-in, rendered-ranked-results-out helper.

    Optional rank stages run in fixed order after the planner:
    rule boost → feature rerank → diversity rank. Supply any subset.
    """

    def __init__(
        self,
        planner: QueryPlanner,
        *,
        highlighter: Optional[Highlighter] = None,
        renderer: Optional[callable] = None,
        rule_reranker: Optional[Any] = None,
        feature_reranker: Optional[Any] = None,
        ranker: Optional[Any] = None,
    ) -> None:
        self._planner = planner
        self._highlighter = highlighter or Highlighter()
        self._renderer = renderer
        self._rule_reranker = rule_reranker
        self._feature_reranker = feature_reranker
        self._ranker = ranker

    def search(
        self, query: str, *, top_k: Optional[int] = None, render: bool = False
    ) -> SearchOutcome:
        terms = QueryParser.parse(query)
        plan = self._planner.plan(query)
        results = tuple(self._planner.execute(query, top_k=top_k))
        results = self._apply_stages(query, results, top_k=top_k)
        rendered = "" if not render else self._render(query, results, terms)
        return SearchOutcome(
            query=query, plan=plan, results=results, rendered=rendered
        )

    def _apply_stages(
        self,
        query: str,
        results: Tuple[ScoredResult, ...],
        *,
        top_k: Optional[int],
    ) -> Tuple[ScoredResult, ...]:
        # Stage 1 — rule-based boost (metadata predicates)
        if self._rule_reranker is not None and results:
            results = tuple(self._rule_reranker.rerank(results, top_k=top_k))
        # Stage 2 — feature-based rerank (query–document features)
        if self._feature_reranker is not None and results:
            candidates = [
                {
                    "id": r.item_id,
                    "text": str(r.metadata.get("preview", r.item_id)),
                    "metadata": r.metadata,
                    "score": r.score,
                }
                for r in results
            ]
            ranked = self._feature_reranker.rerank(
                query, candidates, top_k=top_k or len(candidates)
            )
            results = tuple(
                ScoredResult(
                    item_id=item.item_id,
                    score=item.score,
                    source="feature_rerank",
                    metadata=item.metadata,
                )
                for item in ranked
            )
        # Stage 3 — diversity + recency post-rank
        if self._ranker is not None and results:
            results = tuple(self._ranker.rank(results, top_k=top_k or len(results)))
        return results

    def _render(
        self,
        query: str,
        results: Sequence[ScoredResult],
        terms: Sequence[QueryTerm],
    ) -> str:
        lines = [f"query: {query}"]
        for idx, item in enumerate(results, start=1):
            preview = item.metadata.get("preview", "")
            highlighted = self._highlighter.highlight(str(preview), tuple(terms))
            lines.append(f"[{idx}] {item.item_id} ({highlighted})")
        return "\n".join(lines)
