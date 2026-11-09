"""Purpose-specific bounded machine context slices using one shared intelligence graph."""
from __future__ import annotations
import json
from typing import Literal
from .coordination import build_coordination_plan
from .execution_plan import build_execution_plan
from .health import repository_health
from .metrics import structural_metrics
from .model import RepositoryModel
from .query import RepositoryQuery
from .workgraph import build_work_graph
Intent=Literal["overview","repair","architecture","testing","security","documentation","performance"]
MAX_CONTEXT_BYTES = 48_000
# Each pass halves every reducible sequence. A previously compact surface
# cannot report fictitious progress and keep CI stuck in repeated JSON dumps.
_CONTEXT_SURFACES = (
    "files", "entrypoints", "work", "findings", "subsystems",
    "topology", "coordination", "intelligence",
)
_NESTED_SURFACES = (
    "edges", "cycles", "decisions", "ranked_decisions", "decision_surface",
    "counterfactual_surface", "bridge_candidates", "safe_parallel_groups",
)


def _fits(payload: dict, limit: int) -> bool:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()) <= limit


def _shrink_surface(value: object) -> tuple[object, bool]:
    """Halve retained evidence with strictly decreasing finite list lengths."""
    if isinstance(value, list) and value:
        return value[: len(value) // 2], True
    if not isinstance(value, dict):
        return value, False
    reduced = dict(value)
    changed = False
    for name in _NESTED_SURFACES:
        items = reduced.get(name)
        if isinstance(items, list) and items:
            reduced[name] = items[: len(items) // 2]
            changed = True
    return (reduced, True) if changed else (value, False)


def _bounded(payload: dict, limit: int) -> dict:
    compact = dict(payload)
    compact["truncated_for_context"] = False
    if _fits(compact, limit):
        return compact

    compact["truncated_for_context"] = True
    while True:
        # One serialization per pass, not once per key or an unbounded loop
        # over unchanged coordination/intelligence metadata.
        if _fits(compact, limit):
            return compact
        changed = False
        for name in _CONTEXT_SURFACES:
            if name not in compact:
                continue
            updated, reduced = _shrink_surface(compact[name])
            if reduced:
                compact[name] = updated
                changed = True
        if not changed:
            break

    # Prefer trimming optional plan and metric detail before dropping useful
    # summary sections. Keep plan identities, readiness and execution state.
    while not _fits(compact, limit):
        changed = False
        for name, fields in (("execution", ("steps", "parallel_batches")),
                             ("metrics", ("zones",))):
            value = compact.get(name)
            if not isinstance(value, dict):
                continue
            reduced = dict(value)
            for field in fields:
                items = reduced.get(field)
                if isinstance(items, list) and items:
                    reduced[field] = items[:len(items) // 2]
                    changed = True
            if reduced != value:
                compact[name] = reduced
        if not changed:
            break

    if _fits(compact, limit):
        return compact

    # The fixed summaries alone can exceed a small context budget. Remove
    # nonidentity sections deterministically until the serialized result fits.
    for name in (
        "entrypoints", "files", "topology", "findings", "work",
        "subsystems", "intelligence", "metrics", "health",
    ):
        # Coordination identity, execution constraints and failed-work state
        # are authoritative; never discard them to fit a token budget.
        compact.pop(name, None)
        if _fits(compact, limit):
            return compact

    # Only execution plan detail (not state/identity/constraints) is shrinkable.
    while not _fits(compact, limit):
        execution = compact.get("execution")
        if not isinstance(execution, dict):
            break
        reduced = dict(execution)
        changed = False
        for field in ("steps", "parallel_batches"):
            items = reduced.get(field)
            if isinstance(items, list) and items:
                reduced[field] = items[: len(items) // 2]
                changed = True
        if not changed:
            break
        compact["execution"] = reduced
    if not _fits(compact, limit):
        raise ValueError("required repository context exceeds byte_limit")
    return compact


def context_for_intent(model:RepositoryModel,intent:Intent="overview",*,byte_limit:int=MAX_CONTEXT_BYTES):
    if isinstance(byte_limit,bool) or not isinstance(byte_limit,int) or not 4096<=byte_limit<=256000: raise ValueError("byte_limit must be in [4096,256000]")
    query=RepositoryQuery(model); graph=build_work_graph(model,limit=32)
    coordination=build_coordination_plan(model,limit=8,graph=graph); execution=build_execution_plan(model,limit=8,graph=graph)
    intelligence={"graph_fingerprint":graph.fingerprint,"strategic_value":graph.strategic_value(),"coordination_pressure":graph.pressure(),"critical_path_depth":graph.critical_depth,"bottleneck":graph.bottleneck(),"safe_parallel_groups":[list(x) for x in graph.safe_parallel_groups(limit=4)],"decision_surface":list(graph.decision_surface(limit=8)),"counterfactual_surface":list(graph.counterfactual_surface(limit=8)),"bridge_candidates":list(graph.bridge_candidates(limit=12))}
    base={"intent":intent,"fingerprint":model.fingerprint,"health":repository_health(model).as_dict(),"metrics":structural_metrics(model).as_dict(),
          "subsystems":[x.as_dict() for x in model.subsystems],"work":[x.as_dict() for x in graph.ordered_nodes],
          "coordination":coordination,"execution":execution.as_dict(),"intelligence":intelligence,
          "findings":[x.as_dict() for x in model.findings[:40]]}
    if intent=="architecture": base["topology"]={"edges":[x.as_dict() for x in model.edges],"cycles":[list(x) for x in model.cycles]}; base["files"]=[x.as_dict() for x in query.largest_files(limit=40).files]
    elif intent=="testing": base["files"]=[x.as_dict() for x in query.verification_files(tuple(x.name for x in model.subsystems),limit=100).files]
    elif intent=="repair": base["files"]=[x.as_dict() for x in query.files(kinds=["source","workflow","config"],limit=80).files]
    elif intent=="security": base["files"]=[x.as_dict() for x in query.files(zones=["automation","github","backend","core"],kinds=["source","workflow","config","script"],limit=80).files]
    elif intent=="documentation": base["files"]=[x.as_dict() for x in query.files(kinds=["docs"],limit=100).files]
    elif intent=="performance": base["files"]=[x.as_dict() for x in query.largest_files(limit=60).files]
    else: base["entrypoints"]=[x.as_dict() for x in query.entrypoints(limit=50).files]
    return _bounded(base,byte_limit)
