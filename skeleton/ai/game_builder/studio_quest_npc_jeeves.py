"""Explicit typed Jeeves adapters for original NPC relationship compilation.

Only a trusted application assembler registers these adapters. The registry
must authorize each execution, and no adapter performs filesystem mutation.
"""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_npc_relationships import (
    PROMPT, propose_quest_npc_relationships, compile_quest_npc_relationships,
    compile_npc_relationship_handoff,
)


def register_quest_npc_relationship_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
) -> dict[str, str]:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    source = _canonical(documents)
    if len(source) > 256 * 1024:
        raise StudioQuestError("NPC Jeeves source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)

    def unchanged() -> None:
        if _canonical(documents) != source:
            raise StudioQuestError("NPC Jeeves source changed since registration")

    def propose(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "actors", "actions", "target_ending",
                "expected_source_digest", "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves NPC proposal request")
        unchanged()
        return propose_quest_npc_relationships(
            documents, payload["prompt"], payload["actors"], payload["actions"],
            payload["target_ending"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compile_plan(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest", "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves NPC compile request")
        unchanged()
        return compile_quest_npc_relationships(
            documents, payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def handoff(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"receipt"}:
            raise StudioQuestError("invalid typed Jeeves NPC handoff request")
        unchanged()
        return compile_npc_relationship_handoff(
            documents, payload["receipt"], authorized=True)

    registry.register("studio_quest_npc_propose", propose,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_npc_compile", compile_plan,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_npc_handoff", handoff,
                      domain="game_building", mutates=False)
    return {"source_digest": program.source_digest,
            "initial_session_digest": initial.digest, "prompt": PROMPT}
