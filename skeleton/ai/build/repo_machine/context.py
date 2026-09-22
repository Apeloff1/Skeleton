"""Purpose-specific bounded machine context slices for autonomous agents."""
from __future__ import annotations

import json
from typing import Literal

from .health import repository_health
from .metrics import structural_metrics
from .model import RepositoryModel
from .planner import derive_work_candidates
from .query import RepositoryQuery

Intent = Literal[
    "overview",
    "repair",
    "architecture",
    "testing",
    "security",
    "documentation",
    "performance",
]

MAX_CONTEXT_BYTES = 48_000


def _bounded(payload: dict[str, object], byte_limit: int) -> dict[str, object]:
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(rendered.encode("utf-8")) <= byte_limit:
        return payload
    compact = dict(payload)
    compact["truncated_for_context"] = True
    if isinstance(compact.get("files"), list):
        compact["files"] = compact["files"][:25]
    if isinstance(compact.get("work"), list):
        compact["work"] = compact["work"][:12]
    if isinstance(compact.get("findings"), list):
        compact["findings"] = compact["findings"][:16]
    return compact


def context_for_intent(
    model: RepositoryModel,
    intent: Intent = "overview",
    *,
    byte_limit: int = MAX_CONTEXT_BYTES,
) -> dict[str, object]:
    if isinstance(byte_limit, bool) or not isinstance(byte_limit, int) or not 4_096 <= byte_limit <= 256_000:
        raise ValueError("byte_limit must be in [4096,256000]")
    query = RepositoryQuery(model)
    health = repository_health(model)
    metrics = structural_metrics(model)
    work = [item.as_dict() for item in derive_work_candidates(model, limit=32)]
    base: dict[str, object] = {
        "intent": intent,
        "fingerprint": model.fingerprint,
        "health": health.as_dict(),
        "metrics": metrics.as_dict(),
        "subsystems": [item.as_dict() for item in model.subsystems],
        "work": work,
        "findings": [item.as_dict() for item in model.findings[:40]],
    }

    if intent == "architecture":
        base["topology"] = {
            "edges": [item.as_dict() for item in model.edges],
            "cycles": [list(item) for item in model.cycles],
        }
        base["files"] = [
            item.as_dict()
            for item in query.largest_files(limit=40).files
        ]
    elif intent == "testing":
        base["files"] = [
            item.as_dict()
            for item in query.files(kinds=["test"], limit=100).files
        ]
    elif intent == "repair":
        base["files"] = [
            item.as_dict()
            for item in query.files(
                kinds=["source", "workflow", "config"],
                limit=80,
            ).files
        ]
    elif intent == "security":
        base["files"] = [
            item.as_dict()
            for item in query.files(
                zones=["automation", "github", "backend", "core"],
                kinds=["source", "workflow", "config", "script"],
                limit=80,
            ).files
        ]
    elif intent == "documentation":
        base["files"] = [
            item.as_dict()
            for item in query.files(kinds=["docs"], limit=100).files
        ]
    elif intent == "performance":
        base["files"] = [
            item.as_dict()
            for item in query.largest_files(limit=60).files
        ]
    else:
        base["entrypoints"] = [
            item.as_dict()
            for item in query.entrypoints(limit=50).files
        ]

    return _bounded(base, byte_limit)
