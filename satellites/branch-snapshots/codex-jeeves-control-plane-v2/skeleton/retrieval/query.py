"""Query planner for the retrieval subsystem.

A query doesn't know which retriever it needs until someone inspects it.
The planner scores registered retrievers against each query, runs the
selected ones, and hands their candidate lists to the Fuser/Ranker.

- :class:`QueryPlan` — which retrievers fired and why
- :class:`QueryPlanner` — retriever registry, selection heuristics,
  and the execute() path that returns ranked results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

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


class QueryPlanner:
    """Registry of retrievers + execute → fused, ranked results."""

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
        # fire every retriever. Anything richer plugs in via `strategy hooks`.
        if not self._retrievers:
            raise RetrievalError("no retrievers registered")
        selected = tuple(sorted(self._retrievers))
        return QueryPlan(query=query, retrievers=selected, reason="default-all")

    def execute(
        self, query: str, *, top_k: Optional[int] = None
    ) -> Tuple[ScoredResult, ...]:
        plan = self.plan(query)
        lists: Dict[str, Sequence[ScoredResult]] = {}
        for name in plan.retrievers:
            fn = self._retrievers.get(name)
            if fn is None:
                continue
            lists[name] = fn(query)
        fused = self.fuser.fuse(lists)
        ranked = self.ranker.rank(fused, top_k=top_k or self.fuser.top_k)
        return ranked

    def available(self) -> Tuple[str, ...]:
        return tuple(sorted(self._retrievers))
