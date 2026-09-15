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
from threading import RLock
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
    """Results fetched for a concrete planner registry generation.

    Prefetch is deliberately best-effort: failures are recorded instead of
    changing search semantics. ``execute`` retries failed/missing retrievers and
    discards the entire prefetched result snapshot after registry replacement so
    an old retriever cannot continue serving through a reusable bundle.
    """

    plan: QueryPlan
    results_by_retriever: Mapping[str, Tuple[ScoredResult, ...]] = field(
        default_factory=dict
    )
    failures: Tuple[str, ...] = ()
    registry_generation: int = 0

    def __post_init__(self) -> None:
        # Freeze the mapping shape so consumers cannot add/remove retriever
        # entries from a prepared bundle after the planner has stamped it.
        frozen_results = MappingProxyType(
            {
                str(name): tuple(results)
                for name, results in self.results_by_retriever.items()
            }
        )
        object.__setattr__(self, "results_by_retriever", frozen_results)
        object.__setattr__(self, "failures", tuple(self.failures))


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
        self._registry_generation = 0
        self._registry_lock = RLock()

    def register(
        self, name: str, retriever: Callable[[str], Sequence[ScoredResult]]
    ) -> None:
        with self._registry_lock:
            self._retrievers[name] = retriever
            self._registry_generation += 1

    def plan(self, query: str) -> QueryPlan:
        # Default heuristic: lexical-tagged queries prefer tfidf; the rest
        # fire every retriever. Anything richer plugs in via strategy hooks.
        with self._registry_lock:
            selected = tuple(sorted(self._retrievers))
        if not selected:
            raise RetrievalError("no retrievers registered")
        return QueryPlan(query=query, retrievers=selected, reason="default-all")

    def prefetch(self, plan: QueryPlan) -> PrefetchedQuery:
        """Warm the retrieval work selected by *plan*.

        Retriever callables and the registry generation are snapshotted under
        the registry lock, but retrieval itself executes outside that lock. A
        replacement that races after the snapshot makes this bundle stale; the
        generation fence in :meth:`execute` then ignores these cached results.
        """
        with self._registry_lock:
            generation = self._registry_generation
            retrievers = tuple(
                (name, self._retrievers.get(name)) for name in plan.retrievers
            )

        results: Dict[str, Tuple[ScoredResult, ...]] = {}
        failures: List[str] = []
        for name, fn in retrievers:
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
            registry_generation=generation,
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

        with self._registry_lock:
            current_generation = self._registry_generation
            retrievers = {
                name: self._retrievers.get(name) for name in resolved_plan.retrievers
            }

        prefetched_results: Mapping[str, Tuple[ScoredResult, ...]] = {}
        if (
            prefetched is not None
            and prefetched.registry_generation == current_generation
        ):
            prefetched_results = prefetched.results_by_retriever

        lists: Dict[str, List[ScoredResult]] = {}
        for name in resolved_plan.retrievers:
            cached = prefetched_results.get(name)
            if cached is not None:
                lists[name] = list(cached)
                continue

            fn = retrievers.get(name)
            if fn is None:
                continue
            lists[name] = list(fn(query))

        limit = top_k if top_k is not None else self._DEFAULT_TOP_K
        fused = self.fuser.fuse(lists, top_k=limit)
        ranked = self.ranker.rank(list(fused), top_k=limit)
        return tuple(ranked)

    def available(self) -> Tuple[str, ...]:
        with self._registry_lock:
            return tuple(sorted(self._retrievers))
