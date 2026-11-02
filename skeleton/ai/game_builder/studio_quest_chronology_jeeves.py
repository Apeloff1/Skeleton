"""Read-only typed Jeeves authoring tools for causal quest chronology."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_chronology import (
    PROMPT, propose_quest_chronology, compile_quest_chronology,
)


def register_quest_chronology_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    frozen = _canonical(documents)
    if len(frozen) > 256 * 1024:
        raise StudioQuestError("Jeeves chronology source exceeds byte budget")

    def guard() -> None:
        if _canonical(documents) != frozen:
            raise StudioQuestError("Jeeves chronology source changed")

    def proposal(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "actions", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves chronology proposal")
        guard()
        return propose_quest_chronology(
            documents, payload["prompt"], payload["actions"],
            authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compilation(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves chronology compile")
        guard()
        return compile_quest_chronology(
            documents, payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    registry.register("studio_quest_chronology_proposal", proposal,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_chronology_compile", compilation,
                      domain="game_building", mutates=False)
