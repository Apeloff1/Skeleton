"""Optimistic source-leased commitment of one authored NPC quest alternative.

No filesystem writes or model-generated speech. The resulting canonical quest
receipt is suitable for explicit private persistence and later replay.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_choice_preview import preview_dialogue_choices
from .studio_ecosystem_dialogue_staging import compile_dialogue_staging
from .studio_ecosystem_quest import StudioQuestError, quest_progress, replay_quest

COMMIT_SCHEMA = "skeleton.game_builder.studio_dialogue_choice_commit.v1"


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical dialogue choice commit") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _identifier(value: object) -> bool:
    return (type(value) is str and 1 <= len(value) <= 256
            and value == value.strip()
            and all(ord(ch) >= 32 for ch in value))


def commit_dialogue_choice(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    stage_id: str, alternative: str, expected_preview_digest: str,
    authorized: bool, expected_source_digest: str | None = None,
    scene_id: str | None = None,
) -> dict[str, object]:
    """Commit only a current, exact previewed choice through canonical replay."""
    if authorized is not True:
        raise PermissionError("dialogue choice commitment requires operator authorization")
    if (not _identifier(stage_id) or not _identifier(alternative)
            or type(expected_preview_digest) is not str
            or len(expected_preview_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_preview_digest)):
        raise StudioQuestError("invalid dialogue choice commit lease")
    preview = preview_dialogue_choices(
        documents, actions, authorized=True, scene_id=scene_id,
        expected_source_digest=expected_source_digest)
    candidates = [
        item for item in preview["previews"]
        if item["quest_stage"] == stage_id and item["alternative"] == alternative
    ]
    if len(candidates) != 1:
        raise StudioQuestError("dialogue choice unavailable, locked or ambiguous")
    chosen = candidates[0]
    if chosen["preview_digest"] != expected_preview_digest:
        raise StudioQuestError("stale or forged dialogue choice preview digest")
    following = replay_quest(
        documents, actions + [[stage_id, alternative]], authorized=True)
    if following.digest != chosen["after_session_digest"]:
        raise StudioQuestError("dialogue choice changed since preview")
    staged = compile_dialogue_staging(
        documents, actions + [[stage_id, alternative]], authorized=True,
        scene_id=scene_id, expected_source_digest=preview["source_digest"])
    progress = quest_progress(following, documents)
    if (staged["session_digest"] != following.digest
            or progress["session_digest"] != following.digest
            or staged["source_digest"] != preview["source_digest"]):
        raise StudioQuestError("dialogue choice commit verification failed")
    payload: dict[str, object] = {
        "schema": COMMIT_SCHEMA,
        "project_id": following.project_id,
        "source_digest": preview["source_digest"],
        "quest_source_digest": following.source_digest,
        "previous_session_digest": chosen["before_session_digest"],
        "session_digest": following.digest,
        "preview_digest": expected_preview_digest,
        "scene_id": chosen["scene_id"],
        "npc_id": chosen["npc_id"],
        "stage_id": stage_id,
        "alternative": alternative,
        "quest_receipt": following.receipt(),
        "progress": progress,
        "staging_after": staged,
        "choice_committed_to_receipt": True,
        "file_write_performed": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["commit_digest"] = _digest(payload)
    return payload
