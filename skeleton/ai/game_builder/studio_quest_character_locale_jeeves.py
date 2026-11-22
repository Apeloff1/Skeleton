"""Jeeves read-only adapter for locale-consistent original character handoff."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_character_locale import (
    compile_quest_character_locale_handoff,
)


def register_quest_character_locale_tool(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    branch: object, npc: object, dialogue: object, dialogue_locale: object,
    localization: object, achievements: object, pacing: object,
    advisories: object, accepted_topics: object,
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    parts = (documents, branch, npc, dialogue, dialogue_locale,
             localization, achievements, pacing, advisories, accepted_topics)
    baseline = _canonical(parts)
    if len(baseline) > 1024 * 1024:
        raise StudioQuestError("Jeeves localized character inputs exceed budget")

    def compile_adapter(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "expected_source_digest", "expected_locale"}:
            raise StudioQuestError("invalid typed Jeeves localized character request")
        if _canonical(parts) != baseline:
            raise StudioQuestError("Jeeves localized character inputs changed")
        result = compile_quest_character_locale_handoff(
            *parts, authorized=True)
        if (result["source_digest"] != payload["expected_source_digest"]
                or result["locale"] != payload["expected_locale"]):
            raise StudioQuestError("stale Jeeves character source or locale")
        return result

    registry.register("studio_quest_character_locale", compile_adapter,
                      domain="game_building", mutates=False)
