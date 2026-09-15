"""Query planner for the retrieval subsystem.

A query doesn't know which retriever it needs until someone inspects it.
The planner scores registered retrievers against each query, runs the
selected ones, and hands their candidate lists to the Fuser/Ranker.

- :class:`QueryPlan` — which retrievers fired and why
- :class:`PrefetchedQuery` — reusable retrieval work produced ahead of execution
- :class:`QueryPlanner` — retriever registry, selection heuristics,
  speculative prefetch, and the execute() path that returns ranked results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from skeleton.kernel.errors import KernelError
from skeleton.retrieval.fusion import Fuser, FusionStrategy, ScoredResult
from skeleton.retrieval.ranking import Ranker


class RetrievalError(KernelError):
    code = "RET.PLANNER"


@dataclass(frozen=True)
class QueryPlan:
    query: str
    retrievers: Tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class PrefetchedQuery:
    """Results fetched for a concrete plan before normal execution.

    Prefetch is deliberately best-effort: failures are recorded instead of
    changing search semantics. ``execute`` retries any failed or missing
    retriever through the normal path.
    """

    plan: QueryPlan
    results_by_retriever: Mapping[str, Tuple[ScoredResult, ...]] = field(
        default_factory=dict
    )
    failures: Tuple[str, ...] = ()


class QueryPlanner:
    """Registry of retrievers + execute → fused, ranked results."""

    _DEFAULT_TOP_K = 10

    def __init__(
        self,
        *,
        fuser: Optional[Fuser] = None,
        ranker: Optional[Ranker] = None,
    ) -> None:
        self.fuser = fuser or Fuser(strategy=FusionStrategy.RRF)
        self.ranker = ranker or Ranker()
        self._retrievers: Dict[str, Callable[[str], Sequence[ScoredResult]]] = {}

    def register(
        self, name: str, retriever: Callable[[str], Sequence[ScoredResult]]
    ) -> None:
        self._retrievers[name] = retriever

    def plan(self, query: str) -> QueryPlan:
        # Default heuristic: lexical-tagged queries prefer tfidf; the rest
        # fire every retriever. Anything richer plugs in via strategy hooks.
        if not self._retrievers:
            raise RetrievalError("no retrievers registered")
        selected = tuple(sorted(self._retrievers))
        return QueryPlan(query=query, retrievers=selected, reason="default-all")

    def prefetch(self, plan: QueryPlan) -> PrefetchedQuery:
        """Warm the retrieval work selected by *plan*.

        The returned bundle can be handed to :meth:`execute` so successful
        retrievers are not invoked a second time. A failed speculative fetch is
        intentionally non-fatal and is retried by normal execution.
        """

        results: Dict[str, Tuple[ScoredResult, ...]] = {}
        failures: List[str] = []
        for name in plan.retrievers:
            fn = self._retrievers.get(name)
            if fn is None:
                continue
            try:
                results[name] = tuple(fn(plan.query))
            except Exception:
                failures.append(name)
        return PrefetchedQuery(
            plan=plan,
            results_by_retriever=results,
            failures=tuple(failures),
        )

    def execute(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        plan: Optional[QueryPlan] = None,
        prefetched: Optional[PrefetchedQuery] = None,
    ) -> Tuple[ScoredResult, ...]:
        resolved_plan = plan or self.plan(query)
        if resolved_plan.query != query:
            raise RetrievalError("query does not match supplied plan")
        if prefetched is not None and prefetched.plan != resolved_plan:
            raise RetrievalError("prefetched results do not match supplied plan")

        lists: Dict[str, List[ScoredResult]] = {}
        prefetched_results = (
            prefetched.results_by_retriever if prefetched is not None else {}
        )

        for name in resolved_plan.retrievers:
            cached = prefetched_results.get(name)
            if cached is not None:
                lists[name] = list(cached)
                continue

            fn = self._retrievers.get(name)
            if fn is None:
                continue
            lists[name] = list(fn(query))

        limit = top_k if top_k is not None else self._DEFAULT_TOP_K
        fused = self.fuser.fuse(lists, top_k=limit)
        ranked = self.ranker.rank(list(fused), top_k=limit)
        return tuple(ranked)

    def available(self) -> Tuple[str, ...]:
        return tuple(sorted(self._retrievers))
