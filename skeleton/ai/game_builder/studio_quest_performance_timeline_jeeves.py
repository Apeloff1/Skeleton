"""Typed read-only Jeeves bridge for cross-source performance budgets."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_performance_timeline import (
    PROMPT, propose_performance_timeline, compile_performance_timeline,
)


def register_quest_performance_timeline_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    *parts: object, voice_receipt: object, chronology_receipt: object,
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    frozen = _canonical((documents, parts, voice_receipt, chronology_receipt))
    if len(frozen) > 1024 * 1024:
        raise StudioQuestError("Jeeves performance timeline inputs exceed budget")

    def guard() -> None:
        if _canonical((documents, parts, voice_receipt, chronology_receipt)) != frozen:
            raise StudioQuestError("Jeeves performance timeline inputs changed")

    def proposal(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "expected_voice_digest", "expected_chronology_digest"}:
            raise StudioQuestError("invalid typed Jeeves performance proposal")
        guard()
        return propose_performance_timeline(
            documents, *parts, voice_receipt=voice_receipt,
            chronology_receipt=chronology_receipt,
            prompt=payload["prompt"],
            expected_voice_digest=payload["expected_voice_digest"],
            expected_chronology_digest=payload["expected_chronology_digest"],
            authorized=True)

    def compilation(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_voice_digest", "expected_chronology_digest"}:
            raise StudioQuestError("invalid typed Jeeves performance compile")
        guard()
        return compile_performance_timeline(
            documents, *parts, voice_receipt=voice_receipt,
            chronology_receipt=chronology_receipt, plan=payload["plan"],
            expected_voice_digest=payload["expected_voice_digest"],
            expected_chronology_digest=payload["expected_chronology_digest"],
            authorized=True)

    registry.register("studio_quest_performance_proposal", proposal,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_performance_compile", compilation,
                      domain="game_building", mutates=False)
