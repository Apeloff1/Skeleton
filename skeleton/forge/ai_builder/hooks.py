"""Adapt a ModelPlanner to forge's sync ``PlannerHook``."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Mapping

from .model_planner import ModelPlanner, PlanOutcome


def router_planner_hook(planner: ModelPlanner, *, on_outcome: Callable[[PlanOutcome], None] | None = None):
    """Return ``hook(spec) -> spec`` for ``build_playable_game(planner=...)``.

    build_playable_game discards any spec that changes genre/engine/brief/scope,
    so the compiler remains authoritative even here. Inside a running event
    loop the hook declines (returns the spec unchanged) rather than blocking.
    """

    def hook(spec: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            asyncio.get_running_loop()
            return spec
        except RuntimeError:
            pass
        outcome = asyncio.run(planner.plan(str(spec.get("brief", "")), era=str(spec.get("era", ""))))
        if on_outcome is not None:
            on_outcome(outcome)
        return outcome.spec

    return hook
