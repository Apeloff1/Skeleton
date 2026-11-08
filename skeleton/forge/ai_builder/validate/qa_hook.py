"""QaHook-compatible callable: ``hook(build) -> report``.

Reads the plan from ``build["game_plan"]`` (or a fixed plan given at
construction). Sets ``repair_requested`` only on a ``repair`` verdict, which
is what forge's QA loop understands; ``regenerate`` is reported, not acted on.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .scoring import REPAIR, Thresholds, score_plan


def plan_qa_hook(plan: Mapping[str, Any] | None = None, *, thresholds: Thresholds = Thresholds(),
                 plan_key: str = "game_plan") -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def hook(build: Mapping[str, Any]) -> dict[str, Any]:
        target = plan if plan is not None else (build or {}).get(plan_key)
        if target is None:
            return {"kind": "plan_validation", "skipped": "no game_plan",
                    "issues": ["required game plan missing"], "repair_requested": True,
                    "release_certified": False}
        v = score_plan(target, thresholds)
        return {"kind": "plan_validation", **v.as_dict(),
                "issues": [p.message for p in v.errors], "repair_requested": v.verdict == REPAIR}

    return hook
