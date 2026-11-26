"""Deterministic source-derived NPC knowledge proposal, not LLM inference."""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_npc_knowledge import (
    REQUEST_SCHEMA, _canonical, _digest, compile_npc_knowledge,
    source_knowledge_facts,
)
from .studio_ecosystem_quest import StudioQuestError

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_prompt.v1"
WORDS = re.compile(r"[a-z0-9]{3,}")


def propose_npc_knowledge(documents: Mapping[str, Any], actions: list[list[str]],
                          prompt: str, *, authorized: bool,
                          expected_source_digest: str,
                          expected_session_digest: str | None = None) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("NPC knowledge planning requires operator authorization")
    if (type(prompt) is not str or not 3 <= len(prompt) <= 512 or
            prompt != prompt.strip() or
            any(ord(char) < 32 or ord(char) == 127 for char in prompt) or
            len(prompt.encode("utf-8", "strict")) > 2048):
        raise StudioQuestError("invalid bounded NPC knowledge prompt")
    facts = source_knowledge_facts(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_session_digest)
    staging = compile_dialogue_staging(
        documents, actions, authorized=True,
        expected_source_digest=expected_source_digest)
    cards = staging["cards"]
    indices = {card["scene_id"]: index for index, card in enumerate(cards)}
    terms = set(WORDS.findall(prompt.casefold()))
    candidates = []
    for fact in facts["facts"]:
        for card in cards:
            if indices[fact["scene_id"]] >= indices[card["scene_id"]]:
                continue
            if card["npc_id"] == fact["npc_id"]:
                continue
            content = set(WORDS.findall(fact["source_text"].casefold()))
            audience = set(WORDS.findall(
                (card["npc_name"] + " " + card["site"]).casefold()))
            score = 3 * len(content & terms) + len(audience & terms)
            candidates.append((-score, indices[fact["scene_id"]],
                               indices[card["scene_id"]], fact["fact_id"],
                               card["scene_id"]))
    candidates.sort()
    if not candidates:
        raise StudioQuestError("no source-bound cross-NPC knowledge handoff exists")
    reveals = []
    used = set()
    for _, _, _, fact_id, target in candidates:
        key = (fact_id, target)
        if key in used:
            continue
        used.add(key)
        reveals.append({"fact_id": fact_id, "recipient_scene_id": target,
                        "required_alternative": None})
        if len(reveals) >= 8:
            break
    request = {"schema": REQUEST_SCHEMA, "reveals": reveals}
    compiled = compile_npc_knowledge(
        documents, actions, request, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=staging["session_digest"])
    result: dict[str, Any] = {
        "schema": SCHEMA, "project_id": staging["project_id"],
        "prompt_digest": sha256(prompt.encode("utf-8")).hexdigest(),
        "source_digest": staging["source_digest"],
        "session_digest": staging["session_digest"],
        "authoring": request, "compiled": compiled,
        "selection_method": "bounded_source_and_recipient_token_overlap",
        "model_inference_performed": False, "new_dialogue_generated": False,
        "file_write_performed": False, "release_certified": False,
    }
    if len(_canonical(result)) > 256 * 1024:
        raise StudioQuestError("NPC knowledge proposal exceeds budget")
    result["proposal_digest"] = _digest(result)
    return result
