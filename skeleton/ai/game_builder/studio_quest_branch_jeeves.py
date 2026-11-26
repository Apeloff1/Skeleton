"""Explicit least-privilege Jeeves capability adapters for original quest branch review.

The registry is a typed authorization boundary. This module does not grant
Jeeves an implicit filesystem write, arbitrary code execution, or game release.
"""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_branch_review import (
    PROMPT, propose_quest_branch_review, compile_quest_branch_review,
    compile_quest_branch_handoff,
)


def register_quest_branch_review_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
) -> dict[str, str]:
    """Install three read-only typed tools on an explicitly supplied registry."""
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    source = _canonical(documents)
    if len(source) > 256 * 1024:
        raise StudioQuestError("Jeeves branch source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)

    def unchanged() -> None:
        if _canonical(documents) != source:
            raise StudioQuestError("Jeeves branch source changed since tool registration")

    def propose(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "left_actions", "right_actions", "target_ending",
                "expected_source_digest", "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves branch proposal request")
        unchanged()
        return propose_quest_branch_review(
            documents, payload["prompt"], payload["left_actions"],
            payload["right_actions"], payload["target_ending"],
            authorized=True, expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compile_plan(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest", "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves branch compile request")
        unchanged()
        return compile_quest_branch_review(
            documents, payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def handoff(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"receipt"}:
            raise StudioQuestError("invalid typed Jeeves branch handoff request")
        unchanged()
        return compile_quest_branch_handoff(
            documents, payload["receipt"], authorized=True)

    registry.register("studio_quest_branch_propose", propose,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_branch_compile", compile_plan,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_branch_handoff", handoff,
                      domain="game_building", mutates=False)
    return {
        "source_digest": program.source_digest,
        "initial_session_digest": initial.digest,
        "prompt": PROMPT,
    }
