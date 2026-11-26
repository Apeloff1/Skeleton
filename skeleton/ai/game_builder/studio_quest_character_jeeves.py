"""Jeeves typed assembly of source-verified character experience handoff."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_character_experience import (
    compile_quest_character_experience,
    compile_quest_character_experience_handoff,
)


def register_quest_character_experience_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    branch: object, npc: object, dialogue: object, localization: object,
    achievements: object, pacing: object, advisories: object,
    accepted_topics: object,
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    parts = (documents, branch, npc, dialogue, localization, achievements,
             pacing, advisories, accepted_topics)
    baseline = _canonical(parts)
    if len(baseline) > 1024 * 1024:
        raise StudioQuestError("Jeeves character experience inputs exceed budget")

    def unchanged() -> None:
        if _canonical(parts) != baseline:
            raise StudioQuestError("Jeeves character experience input lease changed")

    def compile_adapter(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"expected_source_digest"}:
            raise StudioQuestError("invalid typed Jeeves character experience request")
        unchanged()
        result = compile_quest_character_experience(*parts, authorized=True)
        if result["source_digest"] != payload["expected_source_digest"]:
            raise StudioQuestError("stale Jeeves character experience source")
        return result

    def handoff_adapter(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"expected_source_digest"}:
            raise StudioQuestError("invalid typed Jeeves character handoff request")
        unchanged()
        result = compile_quest_character_experience_handoff(
            *parts, authorized=True)
        if result["source_digest"] != payload["expected_source_digest"]:
            raise StudioQuestError("stale Jeeves character handoff source")
        return result

    registry.register("studio_quest_character_compile", compile_adapter,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_character_handoff", handoff_adapter,
                      domain="game_building", mutates=False)
