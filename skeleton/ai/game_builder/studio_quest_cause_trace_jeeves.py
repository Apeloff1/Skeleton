"""Typed, read-only Jeeves capabilities for source-replayed ending causes."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_cause_trace import (
    PROMPT, propose_quest_cause_trace, compile_quest_cause_trace,
    compile_quest_cause_handoff,
)


def register_quest_cause_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
) -> None:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    source = _canonical(documents)
    if len(source) > 256 * 1024:
        raise StudioQuestError("Jeeves causal source exceeds budget")

    def guard() -> None:
        if _canonical(documents) != source:
            raise StudioQuestError("Jeeves causal source changed during invocation")

    def proposal(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "actions", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves causal proposal")
        guard()
        return propose_quest_cause_trace(
            documents, payload["prompt"], payload["actions"],
            authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compilation(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves causal compile")
        guard()
        return compile_quest_cause_trace(
            documents, payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def handoff(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"trace"}:
            raise StudioQuestError("invalid typed Jeeves causal handoff")
        guard()
        return compile_quest_cause_handoff(
            documents, payload["trace"], authorized=True)

    registry.register("studio_quest_cause_proposal", proposal,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_cause_compile", compilation,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_cause_handoff", handoff,
                      domain="game_building", mutates=False)
