"""Speculative RAG for pipeline planning.

F-14 composes the quad retriever with ``PipelineComposer`` so likely-needed
documents are warmed during the planning phase of a run. Prefetch is
best-effort: failures are recorded and later ``execute``/stage work retries
them. A missing retriever never blocks the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence, Tuple

from skeleton.kernel.errors import PipelineError
from skeleton.pipelines.composer import PipelineComposer, PipelineRun, Stage
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.pipeline import SearchPipeline
from skeleton.retrieval.query import PrefetchedQuery, QueryPlanner
from skeleton.retrieval.quad import QuadRetriever

CONTEXT_KEY = "speculative_rag"
_DEFAULT_QUERY_LIMIT = 4

_PIPELINE_QUERY_HINTS: Mapping[str, Tuple[str, ...]] = MappingProxyType(
    {
        "npc": ("persona", "dialogue", "archetype"),
        "game_logic": ("mechanics", "economy", "combat"),
        "game-logic": ("mechanics", "economy", "combat"),
        "animation": ("rig", "clip", "blend"),
    }
)


class SpeculativeRagError(PipelineError):
    code = "PPL.SPECULATIVE_RAG"


def _normalize_pipeline_name(pipeline_name: str) -> str:
    return str(pipeline_name or "").strip().lower().replace(" ", "_")


def _seed_text(context: Mapping[str, Any]) -> str:
    for key in ("description", "query", "vision", "prompt"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def plan_pipeline_queries(
    pipeline_name: str,
    context: Optional[Mapping[str, Any]] = None,
    *,
    limit: int = _DEFAULT_QUERY_LIMIT,
) -> Tuple[str, ...]:
    """Return deterministic, bounded retrieval queries for a pipeline plan."""

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise SpeculativeRagError(
            "query limit must be an integer",
            context={"limit": repr(limit)},
        )
    if limit < 1:
        raise SpeculativeRagError(
            "query limit must be >= 1",
            context={"limit": limit},
        )

    seed = _seed_text(context or {})
    if not seed:
        return ()

    hints = _PIPELINE_QUERY_HINTS.get(_normalize_pipeline_name(pipeline_name), ())
    ordered = [seed]
    for hint in hints:
        candidate = f"{hint} {seed}"
        if candidate not in ordered:
            ordered.append(candidate)
    return tuple(ordered[:limit])


@dataclass(frozen=True)
class SpeculativeRagBundle:
    """Planning-phase prefetch snapshot attached to a pipeline run context."""

    pipeline_name: str
    queries: Tuple[str, ...]
    prepared: Mapping[str, PrefetchedQuery]
    failures: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "queries",
            tuple(str(query) for query in self.queries),
        )
        object.__setattr__(
            self,
            "prepared",
            MappingProxyType(dict(self.prepared)),
        )
        object.__setattr__(self, "failures", tuple(self.failures))

    def documents_for(self, query: str) -> Tuple[ScoredResult, ...]:
        prepared = self.prepared.get(query)
        if prepared is None:
            return ()
        documents: list[ScoredResult] = []
        for results in prepared.results_by_retriever.values():
            documents.extend(results)
        return tuple(documents)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline_name,
            "queries": list(self.queries),
            "failures": list(self.failures),
            "prepared_queries": list(self.prepared),
            "document_ids": [
                item.fragment_id
                for query in self.queries
                for item in self.documents_for(query)
            ],
        }


def prefetch_from_genesis(
    genesis: Any,
    pipeline_name: str,
    context: Optional[Mapping[str, Any]] = None,
    *,
    limit: int = _DEFAULT_QUERY_LIMIT,
) -> SpeculativeRagBundle:
    """Prefetch using a genesis-wired quad retriever when one exists."""

    handles = getattr(genesis, "handles", None)
    quad = handles.get("quad") if isinstance(handles, Mapping) else None
    if quad is not None and not isinstance(quad, QuadRetriever):
        quad = None
    return prefetch_for_pipeline(
        pipeline_name,
        context,
        quad=quad,
        limit=limit,
    )


def planning_prefetch_dict(
    genesis: Any,
    pipeline_name: str,
    context: Optional[Mapping[str, Any]] = None,
    *,
    limit: int = 3,
) -> dict[str, Any]:
    """Return a JSON sidecar for pipeline ``.run()``. Prefetch never fails the run."""

    try:
        return prefetch_from_genesis(
            genesis,
            pipeline_name,
            context,
            limit=limit,
        ).to_dict()
    except Exception:  # noqa: BLE001 — planning prefetch is fail-closed
        name = _normalize_pipeline_name(pipeline_name) or pipeline_name or "pipeline"
        return {
            "pipeline": name,
            "queries": [],
            "failures": ["prefetch"],
            "prepared_queries": [],
            "document_ids": [],
        }


def bind_quad_search_pipeline(quad: QuadRetriever) -> SearchPipeline:
    """Register the quad retriever on a planner used for speculative prefetch."""

    planner = QueryPlanner()
    planner.register("quad", quad.as_retriever())
    return SearchPipeline(planner)


def prefetch_for_pipeline(
    pipeline_name: str,
    context: Optional[Mapping[str, Any]] = None,
    *,
    search_pipeline: Optional[SearchPipeline] = None,
    quad: Optional[QuadRetriever] = None,
    limit: int = _DEFAULT_QUERY_LIMIT,
) -> SpeculativeRagBundle:
    """Warm likely documents. Missing retrieval surfaces yield an empty bundle."""

    queries = plan_pipeline_queries(pipeline_name, context, limit=limit)
    pipeline = search_pipeline
    if pipeline is None and quad is not None:
        pipeline = bind_quad_search_pipeline(quad)
    if pipeline is None or not queries:
        return SpeculativeRagBundle(
            pipeline_name=_normalize_pipeline_name(pipeline_name) or pipeline_name,
            queries=queries,
            prepared={},
            failures=(),
        )

    prepared: dict[str, PrefetchedQuery] = {}
    failures: list[str] = []
    for query in queries:
        try:
            bundle = pipeline.prepare(query)
        except Exception:  # noqa: BLE001 — prefetch is best-effort
            failures.append(query)
            continue
        prepared[query] = bundle
        failures.extend(f"{query}:{name}" for name in bundle.failures)
    return SpeculativeRagBundle(
        pipeline_name=_normalize_pipeline_name(pipeline_name) or pipeline_name,
        queries=queries,
        prepared=prepared,
        failures=tuple(failures),
    )


def execute_with_speculative_rag(
    composer: PipelineComposer,
    pipeline_name: str,
    stages: Sequence[Stage],
    *,
    initial_context: Optional[Mapping[str, Any]] = None,
    search_pipeline: Optional[SearchPipeline] = None,
    quad: Optional[QuadRetriever] = None,
    limit: int = _DEFAULT_QUERY_LIMIT,
) -> PipelineRun:
    """Plan queries, prefetch documents, then execute the composer stages."""

    context = dict(initial_context or {})
    bundle = prefetch_for_pipeline(
        pipeline_name,
        context,
        search_pipeline=search_pipeline,
        quad=quad,
        limit=limit,
    )
    context[CONTEXT_KEY] = bundle
    return composer.execute(
        pipeline_name,
        list(stages),
        initial_context=context,
    )
