"""Source-verified authored scene transcript for offline walk sessions."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walk_replay import WalkSession, verify_walk
from .studio_ecosystem_walkable import playable_world_source

MAX_TRANSCRIPT_SCENES = 32
MAX_SOURCE_TEXT_BYTES = 512


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise StudioQuestError("invalid authored transcript text")
    try:
        size = len(value.encode("utf-8", "strict"))
    except UnicodeError as exc:
        raise StudioQuestError("invalid authored transcript encoding") from exc
    if size > MAX_SOURCE_TEXT_BYTES:
        raise StudioQuestError("authored transcript text exceeds bound")
    return value


def walk_story_transcript(
    session: WalkSession, documents: Mapping[str, Any], *,
    authorized: bool, max_scenes: int = MAX_TRANSCRIPT_SCENES,
) -> dict[str, object]:
    """Reconstruct played scenes; never trust client-supplied narrative claims."""
    if not authorized:
        raise PermissionError("story transcript requires operator authorization")
    if type(max_scenes) is not int or not 1 <= max_scenes <= MAX_TRANSCRIPT_SCENES:
        raise StudioQuestError("story transcript scene limit must be 1..32")
    verify_walk(session, documents)
    world = playable_world_source(documents)
    stages = world["stages"]
    if (world["project_id"] != session.project_id
            or world["source_digest"] != session.source_digest
            or session.scene_index != len(session.chosen)
            or session.scene_index > len(stages)):
        raise StudioQuestError("story transcript source or history mismatch")
    completed = []
    for index, (stage_id, choice) in enumerate(session.chosen[:max_scenes]):
        stage = stages[index]
        if stage_id != stage["id"] or choice not in stage["alternatives"]:
            raise StudioQuestError("story transcript choice is not authored")
        if not stage["objects"]:
            raise StudioQuestError("authored scene lacks interaction object")
        completed.append({
            "index": index, "stage_id": _text(stage_id),
            "scene_id": _text(stage["scene_id"]),
            "interaction_object": _text(stage["objects"][0]),
            "selected_alternative": _text(choice),
        })
    pending = None
    if session.scene_index < len(stages):
        stage = stages[session.scene_index]
        pending = {
            "index": session.scene_index,
            "stage_id": _text(stage["id"]),
            "scene_id": _text(stage["scene_id"]),
            "available_alternatives": [_text(x) for x in stage["alternatives"][:32]],
            "alternatives_omitted": max(0, len(stage["alternatives"]) - 32),
        }
    verify_walk(session, documents)
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_story_transcript.v1",
        "project_id": session.project_id,
        "source_digest": session.source_digest,
        "session_digest": session.digest,
        "status": "sandbox_complete" if pending is None else "in_progress",
        "completed_scene_count": session.scene_index,
        "displayed_scene_count": len(completed),
        "omitted_scene_count": session.scene_index - len(completed),
        "completed_scenes": completed, "pending_scene": pending,
        "position": list(session.position),
        "original_save_unchanged": True,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True,
                         allow_nan=False, separators=(",", ":")).encode("ascii")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise StudioQuestError("noncanonical authored transcript") from exc
    payload["transcript_digest"] = sha256(raw).hexdigest()
    return payload
