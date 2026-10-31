"""Jeeves game orchestrator — hyper-advanced Pareto composition layer.

Single call path the local model / Jeeves can use to move from
vision → slice → systems → evidence → scope.
Data-only. Operator remains the gate.
"""

from __future__ import annotations

from typing import Any, Mapping

try:
    from skeleton.ai.agents.jeeves.unified_game_capability import make_unified
except ImportError:
    make_unified = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.advanced_game_systems import advanced_package
except ImportError:
    advanced_package = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.vertical_slice_template import vertical_slice
except ImportError:
    vertical_slice = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.scope_cutline import default_adventure_scope
except ImportError:
    default_adventure_scope = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.actionable_checklists import all_checklists
except ImportError:
    all_checklists = None  # type: ignore


class JeevesGameOrchestrator:
    def full_seed(self, title: str, genre: str = "adventure", era: str = "16bit") -> dict[str, Any]:
        out: dict[str, Any] = {"title": title, "genre": genre, "era": era}
        if make_unified:
            out["unified"] = make_unified().quick_brief(title, genre, era)
        if advanced_package:
            out["systems"] = advanced_package(title)
        if vertical_slice:
            out["slice"] = vertical_slice(title)
        if default_adventure_scope:
            out["scope"] = default_adventure_scope(title)
        if all_checklists:
            out["checklists"] = {k: len(v) for k, v in all_checklists().items()}
        out["next"] = [
            "Operator reviews seed",
            "Run design + adventure checklists",
            "Approve or cut vertical slice",
            "Only then consider native evidence on a qualified core",
        ]
        return out

    def authoritative_walk(self, request: Mapping[str, Any], *, authorized: bool = False) -> dict[str, Any]:
        """Execute the typed canonical offline walk tool under explicit operator authority."""
        from .studio_walk_tool import execute_walk_tool
        return execute_walk_tool(request, authorized=authorized)

    def model_card(self) -> str:
        return (
            "Jeeves game orchestrator: one call produces unified brief, advanced systems, "
            "vertical slice, scope/cut-line, and checklist counts. Data-only. "
            "Operator gates every native or content-lock step."
        )


def make_jeeves_orchestrator() -> JeevesGameOrchestrator:
    return JeevesGameOrchestrator()
