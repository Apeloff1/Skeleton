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

from concurrent.futures import ThreadPoolExecutor
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
    _DEFAULT_PREFETCH_WORKERS = 4
    _MAX_EXECUTION_ATTEMPTS = 2

    def __init__(
        self,
        *,
        fuser: Optional[Fuser] = None,
        ranker: Optional[Ranker] = None,
        prefetch_workers: int = _DEFAULT_PREFETCH_WORKERS,
    ) -> None:
        if isinstance(prefetch_workers, bool) or not isinstance(prefetch_workers, int):
            raise TypeError("prefetch_workers must be an integer")
        if prefetch_workers < 1:
            raise ValueError("prefetch_workers must be >= 1")
        self.fuser = fuser or Fuser(strategy=FusionStrategy.RRF)
        self.ranker = ranker or Ranker()
        self._retrievers: Dict[str, Callable[[str], Sequence[ScoredResult]]] = {}
        self._registry_generation = 0
        self._registry_lock = RLock()
        self._prefetch_workers = prefetch_workers

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
        """Warm the retrieval work selected by *plan* concurrently.

        Retriever callables and the registry generation are snapshotted under
        the registry lock, but retrieval itself executes outside that lock. A
        replacement that races after the snapshot makes this bundle stale; the
        generation fence in :meth:`execute` then ignores these cached results.

        Work is submitted before any result is awaited so independent I/O-bound
        retrievers overlap. Results and failures are materialized in plan order,
        keeping downstream fusion deterministic regardless of completion order.
        """
        with self._registry_lock:
            generation = self._registry_generation
            retrievers = tuple(
                (name, self._retrievers.get(name)) for name in plan.retrievers
            )

        runnable = tuple((name, fn) for name, fn in retrievers if fn is not None)
        results: Dict[str, Tuple[ScoredResult, ...]] = {}
        failures: List[str] = []
        if not runnable:
            return PrefetchedQuery(
                plan=plan,
                results_by_retriever=results,
                failures=(),
                registry_generation=generation,
            )

        workers = min(self._prefetch_workers, len(runnable))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="retrieval-prefetch",
        ) as executor:
            futures = {
                name: executor.submit(fn, plan.query) for name, fn in runnable
            }
            for name, _ in runnable:
                try:
                    results[name] = tuple(futures[name].result())
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

        if top_k is None:
            limit = self._DEFAULT_TOP_K
        else:
            if isinstance(top_k, bool) or not isinstance(top_k, int):
                raise TypeError("top_k must be an integer")
            if top_k < 1:
                raise ValueError("top_k must be >= 1")
            limit = top_k

        for attempt in range(self._MAX_EXECUTION_ATTEMPTS):
            with self._registry_lock:
                current_generation = self._registry_generation
                retrievers = {
                    name: self._retrievers.get(name)
                    for name in resolved_plan.retrievers
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

            # The registry lock must not span arbitrary retriever work, but the
            # selected callable identities still need a stability check before
            # stale results are fused. An unrelated registry update does not
            # force duplicate retrieval; replacing one of this plan's selected
            # retrievers does. Retry once from a fresh snapshot, then fail closed
            # if the selected registry keeps changing under the same execution.
            with self._registry_lock:
                selected_unchanged = all(
                    self._retrievers.get(name) is fn
                    for name, fn in retrievers.items()
                )

            if selected_unchanged:
                fused = self.fuser.fuse(lists, top_k=limit)
                ranked = self.ranker.rank(list(fused), top_k=limit)
                return tuple(ranked)

            prefetched = None
            if attempt + 1 >= self._MAX_EXECUTION_ATTEMPTS:
                raise RetrievalError(
                    "selected retriever registry changed repeatedly during execution"
                )

        raise RetrievalError("retrieval execution exhausted without a stable snapshot")

    def available(self) -> Tuple[str, ...]:
        with self._registry_lock:
            return tuple(sorted(self._retrievers))
