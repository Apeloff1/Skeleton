"""Typed Jeeves original dialogue tools bound to one canonical NPC receipt."""
from __future__ import annotations

from typing import Any, Mapping

from .jeeves_app_capabilities import CapabilityRegistry
from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_npc_relationships import replay_quest_npc_relationships
from .studio_quest_dialogue import (
    PROMPT, propose_quest_dialogue, compile_quest_dialogue,
    compile_quest_dialogue_handoff,
)


def register_quest_dialogue_tools(
    registry: CapabilityRegistry, documents: Mapping[str, Any],
    npc_receipt: object,
) -> dict[str, str]:
    if not isinstance(registry, CapabilityRegistry):
        raise TypeError("Jeeves capability registry required")
    source = _canonical(documents)
    if len(source) > 256 * 1024:
        raise StudioQuestError("Jeeves dialogue source exceeds byte budget")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    npc = replay_quest_npc_relationships(
        documents, npc_receipt, authorized=True)
    npc_source = _canonical(npc)

    def unchanged() -> None:
        if _canonical(documents) != source or _canonical(npc_receipt) != npc_source:
            raise StudioQuestError("Jeeves dialogue source or NPC receipt changed")

    def propose(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "prompt", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves dialogue proposal request")
        unchanged()
        return propose_quest_dialogue(
            documents, npc_receipt, payload["prompt"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def compile_plan(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {
                "plan", "expected_source_digest",
                "expected_initial_session_digest"}:
            raise StudioQuestError("invalid typed Jeeves dialogue compile request")
        unchanged()
        return compile_quest_dialogue(
            documents, npc_receipt, payload["plan"], authorized=True,
            expected_source_digest=payload["expected_source_digest"],
            expected_initial_session_digest=payload["expected_initial_session_digest"])

    def handoff(payload: dict[str, Any]) -> dict[str, Any]:
        if type(payload) is not dict or set(payload) != {"receipt"}:
            raise StudioQuestError("invalid typed Jeeves dialogue handoff request")
        unchanged()
        return compile_quest_dialogue_handoff(
            documents, npc_receipt, payload["receipt"], authorized=True)

    registry.register("studio_quest_dialogue_propose", propose,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_dialogue_compile", compile_plan,
                      domain="game_building", mutates=False)
    registry.register("studio_quest_dialogue_handoff", handoff,
                      domain="game_building", mutates=False)
    return {"source_digest": program.source_digest,
            "initial_session_digest": initial.digest,
            "npc_relationship_digest": npc["relationship_digest"],
            "prompt": PROMPT}
