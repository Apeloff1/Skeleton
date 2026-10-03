"""Purpose-specific bounded machine context slices for autonomous agents."""
from __future__ import annotations

import json
from typing import Literal

from .coordination import build_coordination_plan
from .execution_plan import build_execution_plan
from .health import repository_health
from .metrics import structural_metrics
from .model import RepositoryModel
from .planner import derive_work_candidates
from .query import RepositoryQuery

Intent = Literal[
    "overview", "repair", "architecture", "testing",
    "security", "documentation", "performance",
]

MAX_CONTEXT_BYTES = 48_000


def _fits(payload: dict[str, object], byte_limit: int) -> bool:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= byte_limit


def _bounded(payload: dict[str, object], byte_limit: int) -> dict[str, object]:
    """Deterministically shrink context until the byte contract is actually met."""
    compact = dict(payload)
    compact["truncated_for_context"] = False
    if _fits(compact, byte_limit):
        return compact

    compact["truncated_for_context"] = True
    while not _fits(compact, byte_limit):
        changed = False
        for key in ("files", "work", "findings", "subsystems", "topology", "coordination"):
            value = compact.get(key)
            if isinstance(value, list) and len(value) > 0:
                compact[key] = value[:max(1, len(value) // 2)]
                changed = True
            elif isinstance(value, dict) and value:
                if key == "topology":
                    edges = value.get("edges", [])
                    compact[key] = {"edges": edges[:max(1, len(edges) // 2)],
                                    "cycles": value.get("cycles", [])[:4]}
                    changed = True
                elif key == "coordination":
                    decisions = value.get("decisions", [])
                    compact[key] = {"decisions": decisions[:max(1, len(decisions) // 2)],
                                    "bottleneck": value.get("bottleneck"),
                                    "frontier_size": value.get("frontier_size", 0)}
                    changed = True
            if _fits(compact, byte_limit):
                return compact
        if not changed:
            break

    if not _fits(compact, byte_limit):
        keep = {"intent", "fingerprint", "health", "metrics", "coordination", "truncated_for_context"}
        compact = {key: compact[key] for key in keep if key in compact}
        compact["truncated_for_context"] = True
    return compact


def context_for_intent(model: RepositoryModel, intent: Intent = "overview", *, byte_limit: int = MAX_CONTEXT_BYTES) -> dict[str, object]:
    if isinstance(byte_limit, bool) or not isinstance(byte_limit, int) or not 4_096 <= byte_limit <= 256_000:
        raise ValueError("byte_limit must be in [4096,256000]")
    query = RepositoryQuery(model)
    base: dict[str, object] = {
        "intent": intent,
        "fingerprint": model.fingerprint,
        "health": repository_health(model).as_dict(),
        "metrics": structural_metrics(model).as_dict(),
        "subsystems": [item.as_dict() for item in model.subsystems],
        "work": [item.as_dict() for item in derive_work_candidates(model, limit=32)],
        "coordination": build_coordination_plan(model, limit=8),
        "execution": build_execution_plan(model, limit=8).as_dict(),
        "findings": [item.as_dict() for item in model.findings[:40]],
    }

    if intent == "architecture":
        base["topology"] = {"edges": [item.as_dict() for item in model.edges], "cycles": [list(item) for item in model.cycles]}
        base["files"] = [item.as_dict() for item in query.largest_files(limit=40).files]
    elif intent == "testing":
        zones = tuple(item.name for item in model.subsystems)
        base["files"] = [item.as_dict() for item in query.verification_files(zones, limit=100).files]
    elif intent == "repair":
        base["files"] = [item.as_dict() for item in query.files(kinds=["source", "workflow", "config"], limit=80).files]
    elif intent == "security":
        base["files"] = [item.as_dict() for item in query.files(zones=["automation", "github", "backend", "core"], kinds=["source", "workflow", "config", "script"], limit=80).files]
    elif intent == "documentation":
        base["files"] = [item.as_dict() for item in query.files(kinds=["docs"], limit=100).files]
    elif intent == "performance":
        base["files"] = [item.as_dict() for item in query.largest_files(limit=60).files]
    else:
        base["entrypoints"] = [item.as_dict() for item in query.entrypoints(limit=50).files]

    return _bounded(base, byte_limit)
