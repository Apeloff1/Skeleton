"""Retriever source registry — pluggable back-ends for QueryPlanner.

RagSettings names backends (\"memory\" / \"chromadb\"); the source registry
maps those names to factory callables so the planner instantiates once
and routes queries to the right retrieval implementation.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Sequence, Tuple

from skeleton.kernel.errors import RetrievalError
from skeleton.retrieval.fusion import ScoredResult


class SourceRegistry:
    """Registry of queryable sources by name."""

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], Callable[[str], Sequence[ScoredResult]]]] = {}
        self._sources: Dict[str, Callable[[str], Sequence[ScoredResult]]] = {}

    def register(
        self, name: str, factory: Callable[[], Callable[[str], Sequence[ScoredResult]]]
    ) -> None:
        self._factories[name] = factory

    def resolve(self, name: str) -> Callable[[str], Sequence[ScoredResult]]:
        if name not in self._sources:
            factory = self._factories.get(name)
            if factory is None:
                raise RetrievalError(
                    "unknown source",
                    context={"name": name, "known": sorted(self._factories)},
                )
            self._sources[name] = factory()
        return self._sources[name]

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._factories))
