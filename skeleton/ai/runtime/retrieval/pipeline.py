"""End-to-end search pipeline — parse → plan → execute → rerank stages → highlight.

QueryPlanner.execute() returns ranked candidates; interactive demos
need the parse/plan/highlight steps glued. SearchPipeline composes
the primitives the package already ships.

Rank stages (optional, fixed order):
  1. rule boost      — ``rerank.Reranker`` (metadata predicate boosts)
  2. feature rerank  — ``reranker.FeatureReranker`` (query–doc features)
  3. diversity rank  — ``ranking.Ranker`` (source diversity + recency)

Speculative retrieval is opt-in. ``prepare()`` warms selected retrievers and
returns a reusable bundle; ``search_prepared()`` consumes it without repeating
successful retrieval work. ``speculative_prefetch=True`` performs the same
composition inside ``search()``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Tuple

from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.highlight import Highlighter
from skeleton.retrieval.query import PrefetchedQuery, QueryPlan, QueryPlanner
from skeleton.retrieval.query_language import QueryParser, QueryTerm


def _planner_execute_kwargs(
    execute: Callable[..., Any],
    *,
    top_k: Optional[int],
    plan: QueryPlan,
    prefetched: Optional[PrefetchedQuery],
) -> dict[str, Any]:
    """Forward prefetch kwargs only when the planner accepts them."""

    params = inspect.signature(execute).parameters
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in params.values()):
        return {"top_k": top_k, "plan": plan, "prefetched": prefetched}
    kwargs: dict[str, Any] = {}
    if "top_k" in params:
        kwargs["top_k"] = top_k
    if "plan" in params:
        kwargs["plan"] = plan
    if "prefetched" in params:
        kwargs["prefetched"] = prefetched
    return kwargs


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

    Set ``speculative_prefetch`` to warm the selected retrievers between plan
    construction and execution. For a wider planning/composition layer, call
    :meth:`prepare` early and :meth:`search_prepared` when results are needed.
    """

    def __init__(
        self,
        planner: QueryPlanner,
        *,
        highlighter: Optional[Highlighter] = None,
        renderer: Optional[Callable[..., str]] = None,
        rule_reranker: Optional[Any] = None,
        feature_reranker: Optional[Any] = None,
        ranker: Optional[Any] = None,
        speculative_prefetch: bool = False,
    ) -> None:
        self._planner = planner
        self._highlighter = highlighter or Highlighter()
        self._renderer = renderer
        self._rule_reranker = rule_reranker
        self._feature_reranker = feature_reranker
        self._ranker = ranker
        self._speculative_prefetch = speculative_prefetch

    def prepare(self, query: str) -> PrefetchedQuery:
        """Plan *query* and warm the selected retrievers for later execution."""

        return self._planner.prefetch(self._planner.plan(query))

    def search(
        self, query: str, *, top_k: Optional[int] = None, render: bool = False
    ) -> SearchOutcome:
        plan = self._planner.plan(query)
        prefetched = self._planner.prefetch(plan) if self._speculative_prefetch else None
        return self._search(
            query,
            plan=plan,
            prefetched=prefetched,
            top_k=top_k,
            render=render,
        )

    def search_prepared(
        self,
        prepared: PrefetchedQuery,
        *,
        top_k: Optional[int] = None,
        render: bool = False,
    ) -> SearchOutcome:
        """Execute a bundle returned by :meth:`prepare` without refetching it."""

        return self._search(
            prepared.plan.query,
            plan=prepared.plan,
            prefetched=prepared,
            top_k=top_k,
            render=render,
        )

    def _search(
        self,
        query: str,
        *,
        plan: QueryPlan,
        prefetched: Optional[PrefetchedQuery],
        top_k: Optional[int],
        render: bool,
    ) -> SearchOutcome:
        terms = QueryParser.parse(query)
        results = tuple(
            self._planner.execute(
                query,
                **_planner_execute_kwargs(
                    self._planner.execute,
                    top_k=top_k,
                    plan=plan,
                    prefetched=prefetched,
                ),
            )
        )
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

        # Stage 2 — feature-based rerank. FeatureReranker accepts typed result
        # objects directly and preserves them; converting to dicts here loses
        # fragment/content provenance and breaks the ScoredResult contract.
        if self._feature_reranker is not None and results:
            results = tuple(
                self._feature_reranker.rerank(
                    query,
                    list(results),
                    top_k=top_k or len(results),
                )
            )

        # Stage 3 — diversity + recency post-rank
        if self._ranker is not None and results:
            results = tuple(self._ranker.rank(list(results), top_k=top_k or len(results)))
        return results

    def _render(
        self,
        query: str,
        results: Sequence[ScoredResult],
        terms: Sequence[QueryTerm],
    ) -> str:
        if self._renderer is not None:
            return str(self._renderer(query, results, terms))

        lines = [f"query: {query}"]
        for idx, item in enumerate(results, start=1):
            preview = item.metadata.get("preview", item.content)
            highlighted = self._highlighter.highlight(str(preview), tuple(terms))
            lines.append(f"[{idx}] {item.fragment_id} ({highlighted})")
        return "\n".join(lines)
