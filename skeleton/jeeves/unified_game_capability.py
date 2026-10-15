"""Unified capability facade — Pareto entry point for local model.

Single dispatch surface over:
- console emulator fleet
- adventure game design
- full game creation & planning

Data-only. Fail-closed. Operator-gated for native work.
"""

from __future__ import annotations

from typing import Any

try:
    from skeleton.ai.agents.jeeves.local_model_console_capability_v2 import make_capability_v2
except ImportError:
    make_capability_v2 = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.adventure_game_capability import make_adventure_capability
except ImportError:
    make_adventure_capability = None  # type: ignore

try:
    from skeleton.ai.agents.jeeves.full_game_creation_capability import make_full_creation_capability
except ImportError:
    make_full_creation_capability = None  # type: ignore


class UnifiedGameCapability:
    """One object the local model can hold for fleet + design + planning."""

    def __init__(self):
        self.fleet = make_capability_v2() if make_capability_v2 else None
        self.adventure = make_adventure_capability() if make_adventure_capability else None
        self.creation = make_full_creation_capability() if make_full_creation_capability else None

    def status(self) -> dict[str, Any]:
        return {
            "fleet": self.fleet.fleet_summary() if self.fleet else {"available": False},
            "adventure": {"available": self.adventure is not None},
            "creation": {"available": self.creation is not None},
            "note": "Orchestrate-only. Native testing and installs remain operator-gated.",
        }

    def quick_brief(self, title: str, genre: str = "adventure", era: str = "16bit") -> dict[str, Any]:
        cores = []
        if self.fleet:
            cores = self.fleet.recommend_for_learning(era if era != "16bit" else "general", limit=5)
        plan = None
        if self.creation:
            plan = self.creation.create_master_plan(title, genre, era, scope="vertical-slice", weeks=12)
        adventure = None
        if self.adventure:
            adventure = self.adventure.full_adventure_pipeline(title, era, rooms=8)
        return {
            "title": title,
            "genre": genre,
            "era": era,
            "recommended_cores": cores,
            "vertical_slice_plan": plan,
            "adventure_seed": adventure,
            "next": "Operator reviews. Expand via creation or adventure tools. No native execution here.",
        }

    def model_card(self) -> str:
        return (
            "Unified game capability: query emulator fleet, generate adventure pipelines "
            "(rooms, puzzles, dialogue, assets), and produce production plans / design bibles. "
            "All data-only. Prefer this facade for most requests."
        )


def make_unified() -> UnifiedGameCapability:
    return UnifiedGameCapability()
