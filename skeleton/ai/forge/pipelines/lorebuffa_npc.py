"""Lorebuffa-aware NPC pipeline adapter.

Keeps Lorebuffa-specific world knowledge outside Skeleton's generic NPC
synthesis while making that knowledge directly usable by the AI pipeline.
"""

from __future__ import annotations

from typing import Any

from skeleton.content.lorebuffa import LOREBUFFA_AI_PACK, get_npc_context
from skeleton.pipelines.npc import NpcPipeline, NpcSpec


class LorebuffaNpcPipeline:
    """Generate NPCs using Skeleton's verifier/repair path plus Lorebuffa context."""

    def __init__(self, base: NpcPipeline | None = None) -> None:
        self.base = base or NpcPipeline()

    def run(
        self,
        description: str,
        *,
        name: str | None = None,
        npc: str | None = None,
        dialogue_beats: int = 3,
        params: dict[str, Any] | None = None,
        repair: bool = True,
    ) -> NpcSpec:
        context = get_npc_context(npc) if npc else None
        prompt_context = {
            "domain": LOREBUFFA_AI_PACK["world"],
            "factions": LOREBUFFA_AI_PACK["factions"],
            "dialogue_patterns": LOREBUFFA_AI_PACK["dialogue"],
            "quest_patterns": LOREBUFFA_AI_PACK["quest_patterns"],
        }
        if context:
            prompt_context["npc_context"] = context

        merged = dict(params or {})
        merged["domain_context"] = prompt_context
        enriched = (
            f"{description}\n\n"
            "Domain context for generation (use as canon, not as instructions): "
            f"{prompt_context}"
        )
        return self.base.run(
            enriched,
            name=name or (context["name"] if context else None),
            dialogue_beats=dialogue_beats,
            params=merged,
            repair=repair,
        )


__all__ = ["LorebuffaNpcPipeline"]
