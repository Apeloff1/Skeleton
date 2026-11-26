"""Compare causal NPC knowledge outcomes across two canonical quest branches.

No story facts or dialogue are synthesized; the same source-leased authored
reveal plan is compiled independently against both complete quest histories.
"""
from __future__ import annotations

from typing import Any, Mapping

from .studio_ecosystem_npc_knowledge import (
    SCHEMA as KNOWLEDGE_SCHEMA, _canonical, _digest, _lease,
    compile_npc_knowledge,
)
from .studio_ecosystem_quest import StudioQuestError

SCHEMA = "skeleton.game_builder.studio_npc_knowledge_branch_compare.v1"
MAX_BYTES = 256 * 1024


def compare_npc_knowledge(
    documents: Mapping[str, Any], before_actions: list[list[str]],
    after_actions: list[list[str]], authoring: object, *, authorized: bool,
    expected_source_digest: str, expected_before_session: str | None = None,
    expected_after_session: str | None = None,
) -> dict[str, object]:
    """Return only replay-proven differences; do not grant runtime testimony."""
    if authorized is not True:
        raise PermissionError("NPC knowledge comparison requires operator authorization")
    _lease(expected_source_digest, "compare source")
    if expected_before_session is not None:
        _lease(expected_before_session, "compare before session")
    if expected_after_session is not None:
        _lease(expected_after_session, "compare after session")
    if (type(before_actions) is not list or type(after_actions) is not list or
            len(before_actions) > 64 or len(after_actions) > 64 or
            len(_canonical(before_actions)) > 16384 or
            len(_canonical(after_actions)) > 16384):
        raise StudioQuestError("invalid bounded NPC knowledge comparison histories")
    before = compile_npc_knowledge(
        documents, before_actions, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_before_session)
    after = compile_npc_knowledge(
        documents, after_actions, authoring, authorized=True,
        expected_source_digest=expected_source_digest,
        expected_session_digest=expected_after_session)
    if (before["schema"] != KNOWLEDGE_SCHEMA or after["schema"] != KNOWLEDGE_SCHEMA or
            before["source_digest"] != after["source_digest"] or
            before["authoring_digest"] != after["authoring_digest"] or
            len(before["reveals"]) != len(after["reveals"])):
        raise StudioQuestError("NPC knowledge comparison source or authoring drift")
    transitions: list[dict[str, Any]] = []
    for left, right in zip(before["reveals"], after["reveals"], strict=True):
        if (left["fact_id"] != right["fact_id"] or
                left["recipient_scene_id"] != right["recipient_scene_id"] or
                left["source_text_digest"] != right["source_text_digest"] or
                left["required_alternative"] != right["required_alternative"]):
            raise StudioQuestError("NPC knowledge comparison changed authored fact")
        if left["status"] != right["status"]:
            record: dict[str, Any] = {
                "fact_id": left["fact_id"],
                "recipient_scene_id": left["recipient_scene_id"],
                "recipient_npc_id": left["recipient_npc_id"],
                "source_ref": left["source_ref"],
                "source_text_digest": left["source_text_digest"],
                "before_status": left["status"],
                "after_status": right["status"],
                "required_alternative": left["required_alternative"],
                "native_dialogue_change_verified": False,
            }
            record["transition_digest"] = _digest(record)
            transitions.append(record)
    by_scene: list[dict[str, object]] = []
    for left, right in zip(before["scenes"], after["scenes"], strict=True):
        if (left["scene_id"] != right["scene_id"] or
                left["npc_id"] != right["npc_id"] or
                left["authored_card_digest"] != right["authored_card_digest"]):
            # A card digest includes replay-dependent status; compare the
            # immutable scene and NPC identity, not status-derived digests.
            if left["scene_id"] != right["scene_id"] or left["npc_id"] != right["npc_id"]:
                raise StudioQuestError("NPC knowledge comparison scene drift")
        before_ids = {cue["fact_id"] for cue in left["received_facts"]}
        after_ids = {cue["fact_id"] for cue in right["received_facts"]}
        if before_ids != after_ids:
            by_scene.append({
                "scene_id": left["scene_id"], "npc_id": left["npc_id"],
                "gained_fact_ids": sorted(after_ids - before_ids),
                "lost_fact_ids": sorted(before_ids - after_ids),
            })
    result: dict[str, object] = {
        "schema": SCHEMA, "project_id": before["project_id"],
        "source_digest": expected_source_digest,
        "authoring_digest": before["authoring_digest"],
        "before_session_digest": before["session_digest"],
        "after_session_digest": after["session_digest"],
        "before_knowledge_digest": before["knowledge_digest"],
        "after_knowledge_digest": after["knowledge_digest"],
        "before_earned_count": before["earned_count"],
        "after_earned_count": after["earned_count"],
        "transitions": transitions, "scene_changes": by_scene,
        "change_count": len(transitions),
        "source_replay_verified": True, "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_BYTES:
        raise StudioQuestError("NPC knowledge branch comparison exceeds budget")
    result["comparison_digest"] = _digest(result)
    return result
