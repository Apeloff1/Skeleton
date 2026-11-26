"""Read-only typed Jeeves tools for original quest voice direction."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_voice_direction import (
    PROMPT, propose_voice_direction, compile_voice_direction,
)


def register_quest_voice_direction_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    *parts: object,
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    frozen = _canonical((documents, parts))
    if len(frozen) > 1024 * 1024:
        raise StudioQuestError("Jeeves voice direction inputs exceed budget")

    def guard() -> None:
        if _canonical((documents, parts)) != frozen:
            raise StudioQuestError("Jeeves voice direction inputs changed")

    def proposal(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "expected_handoff_digest"}:
            raise StudioQuestError("invalid typed voice direction proposal")
        guard()
        return propose_voice_direction(
            documents, *parts, prompt=payload["prompt"],
            expected_handoff_digest=payload["expected_handoff_digest"],
            authorized=True)

    def compilation(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_handoff_digest"}:
            raise StudioQuestError("invalid typed voice direction compile request")
        guard()
        return compile_voice_direction(
            documents, *parts, plan=payload["plan"],
            expected_handoff_digest=payload["expected_handoff_digest"],
            authorized=True)

    registry.register("studio_quest_voice_proposal", proposal,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_voice_compile", compilation,
                      domain="game_building", mutates=False)
