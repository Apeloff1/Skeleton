"""Recompute untrusted browser movement against authoritative Python collision."""
from __future__ import annotations
import json
from typing import Any, Mapping
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walk_replay import replay_walk
from .studio_ecosystem_encounters import replay_hazard_health

FIELDS = {"schema", "project_id", "source_digest", "events",
          "external_evidence_verified", "native_genre_runtime_verified",
          "release_certified"}


def review_walk_events(raw: bytes, documents: Mapping[str, Any], *,
                       authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("walk review requires operator authorization")
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 4*1024*1024:
        raise StudioQuestError("oversized or invalid untrusted walk log")
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        found: dict[str, object] = {}
        for key, value in pairs:
            if key in found:
                raise StudioQuestError("repeated walk JSON field")
            found[key] = value
        return found
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"),
                             object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite walk record")))
    except (UnicodeError, ValueError) as exc:
        raise StudioQuestError("invalid walk JSON") from exc
    if (not isinstance(payload, dict) or set(payload) != FIELDS
            or payload["schema"] != "skeleton.game_builder.offline_walk_events.v1"
            or any(payload[k] is not False for k in (
                "external_evidence_verified", "native_genre_runtime_verified",
                "release_certified"))):
        raise StudioQuestError("invalid or certified browser claims")
    session = replay_walk(documents, payload["events"], authorized=True)
    encounter = replay_hazard_health(documents, session.events, authorized=True)
    if (payload["project_id"] != session.project_id
            or payload["source_digest"] != session.source_digest):
        raise StudioQuestError("stale or foreign authored source")
    return {"schema": "skeleton.game_builder.authoritative_walk_review.v1",
            "project_id": session.project_id,
            "walk_session_digest": session.digest,
            "scene_index": session.scene_index,
            "position": list(session.position),
            "authored_decisions": [list(e) for e in session.chosen],
            "accepted_moves": session.accepted_moves,
            "remaining_health": encounter["remaining_health"],
            "hazard_contacts": encounter["hazard_contacts"],
            "character_defeated": encounter["character_defeated"],
            "local_physics_replay_verified": True,
            "external_input_authenticity_verified": False,
            "native_genre_runtime_verified": False,
            "release_certified": False}
