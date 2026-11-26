"""Read-only, source-bound NPC dialogue alternatives and quest consequence previews.

The authored dialogue is a staging cue, not verified speech. Every counterfactual
is replayed through the canonical quest engine; no branch is persisted.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest

PREVIEW_SCHEMA = "skeleton.game_builder.studio_dialogue_choice_preview.v1"
MAX_PREVIEWS = 32
MAX_SOURCE_BYTES = 512 * 1024


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue preview input") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def preview_dialogue_choices(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    authorized: bool, expected_source_digest: str | None = None,
    scene_id: str | None = None,
) -> dict[str, object]:
    """Show available original choices with authoritative one-step quest proofs.

    Locked and completed scenes remain visible as holds. Every alternative
    is independently replayed and bounded; a preview cannot grant a reward.
    """
    if authorized is not True:
        raise PermissionError("dialogue choice preview requires operator authorization")
    if not isinstance(documents, Mapping):
        raise StudioQuestError("missing dialogue source")
    original = _canonical(documents)
    if len(original) > MAX_SOURCE_BYTES:
        raise StudioQuestError("dialogue preview source exceeds byte budget")
    staged = compile_dialogue_staging(
        documents, actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest)
    before = replay_quest(documents, actions, authorized=True)
    if before.digest != staged["session_digest"]:
        raise StudioQuestError("dialogue preview session mismatch")
    previews: list[dict[str, object]] = []
    cards: list[dict[str, object]] = []
    for card in staged["cards"]:
        status = card["status"]
        alternatives = card["authored_alternatives"]
        if status == "available" and len(previews) + len(alternatives) > MAX_PREVIEWS:
            raise StudioQuestError("dialogue preview branch budget exceeded")
        item: dict[str, object] = {
            "scene_id": card["scene_id"], "npc_id": card["npc_id"],
            "quest_stage": card["quest_stage"], "status": status,
            "card_digest": card["card_digest"],
            "available_alternatives": list(alternatives) if status == "available" else [],
            "selected_alternative": card["selected_alternative"],
            "dialogue_spoken_verified": False,
        }
        cards.append(item)
        if status != "available":
            continue
        for alternative in alternatives:
            following = replay_quest(
                documents, actions + [[card["quest_stage"], alternative]],
                authorized=True)
            if (following.project_id != before.project_id
                    or following.source_digest != before.source_digest
                    or len(following.choices) != len(before.choices) + 1):
                raise StudioQuestError("dialogue preview source or replay drift")
            progress = quest_progress(following, documents)
            preview = {
                "scene_id": card["scene_id"],
                "npc_id": card["npc_id"],
                "quest_stage": card["quest_stage"],
                "alternative": alternative,
                "before_session_digest": before.digest,
                "after_session_digest": following.digest,
                "available_after": progress["available"],
                "sandbox_endings_eligible": progress["sandbox_endings_eligible"],
                "unmet_ending_predicates": progress["unmet_ending_predicates"],
                "card_digest": card["card_digest"],
                "choice_committed": False,
                "external_evidence_verified": False,
            }
            preview["preview_digest"] = _digest(preview)
            previews.append(preview)
    if _canonical(documents) != original:
        raise StudioQuestError("dialogue source changed during preview")
    payload: dict[str, object] = {
        "schema": PREVIEW_SCHEMA,
        "project_id": staged["project_id"],
        "source_digest": staged["source_digest"],
        "quest_source_digest": staged["quest_source_digest"],
        "session_digest": before.digest,
        "staging_digest": staged["staging_digest"],
        "scene_filter": scene_id,
        "cards": cards,
        "previews": previews,
        "preview_count": len(previews),
        "source_unchanged": True,
        "choice_committed": False,
        "file_write_performed": False,
        "dialogue_spoken_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["receipt_digest"] = _digest(payload)
    return payload
