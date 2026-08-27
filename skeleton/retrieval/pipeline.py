"""End-to-end search pipeline — parse → plan → execute → rerank → highlight.

QueryPlanner.execute() returns ranked candidates; interactive demos
need the parse/plan/highlight steps glued. SearchPipeline composes
the primitives the package already ships.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

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
    """String-in, rendered-ranked-results-out helper."""

    def __init__(
        self,
        planner: QueryPlanner,
        *,
        highlighter: Optional[Highlighter] = None,
        renderer: Optional[callable] = None,
    ) -> None:
        self._planner = planner
        self._highlighter = highlighter or Highlighter()
        self._renderer = renderer

    def search(
        self, query: str, *, top_k: Optional[int] = None, render: bool = False
    ) -> SearchOutcome:
        terms = QueryParser.parse(query)
        plan = self._planner.plan(query)
        results = self._planner.execute(query, top_k=top_k)
        rendered = "" if not render else self._render(query, results, terms)
        return SearchOutcome(
            query=query, plan=plan, results=results, rendered=rendered
        )

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
