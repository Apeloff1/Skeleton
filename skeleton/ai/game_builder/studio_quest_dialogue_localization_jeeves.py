"""Least-privilege Jeeves tools for original NPC dialogue localization."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_dialogue_localization import (
    PROMPT, propose_dialogue_localization, compile_dialogue_localization,
    compile_dialogue_localized_handoff,
)


def register_dialogue_localization_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    npc_receipt: object, dialogue_receipt: object,
) -> dict[str, str]:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    source = _canonical((documents, npc_receipt, dialogue_receipt))
    if len(source) > 1024 * 1024:
        raise StudioQuestError("Jeeves localization inputs exceed budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)

    def unchanged() -> None:
        if _canonical((documents, npc_receipt, dialogue_receipt)) != source:
            raise StudioQuestError("Jeeves dialogue localization source changed")

    def propose(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "locale", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves localization proposal")
        unchanged()
        return propose_dialogue_localization(
            documents, npc_receipt, dialogue_receipt,
            payload["prompt"], payload["locale"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compile_plan(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves localization compile")
        unchanged()
        return compile_dialogue_localization(
            documents, npc_receipt, dialogue_receipt,
            payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def handoff(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"receipt"}:
            raise StudioQuestError("invalid typed Jeeves localization handoff")
        unchanged()
        return compile_dialogue_localized_handoff(
            documents, npc_receipt, dialogue_receipt,
            payload["receipt"], authorized=True)

    registry.register("studio_dialogue_locale_propose", propose,
                      domain="game_building", mutates=False)
    registry.register("studio_dialogue_locale_compile", compile_plan,
                      domain="game_building", mutates=False)
    registry.register("studio_dialogue_locale_handoff", handoff,
                      domain="game_building", mutates=False)
    return {"source_digest": program.source_digest,
            "initial_session_digest": initial.digest, "prompt": PROMPT}
