"""Canonical multi-scene NPC itinerary with source-bound quest replay."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_dialogue_scene_route import plan_dialogue_scene_route
from .studio_ecosystem_quest import StudioQuestError, replay_quest, quest_progress

ITINERARY_SCHEMA = "skeleton.game_builder.studio_dialogue_itinerary.v1"
MAX_TARGETS = 8
MAX_ACTIONS = 64


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("noncanonical NPC itinerary") from exc


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def plan_dialogue_itinerary(
    documents: Mapping[str, Any], actions: list[list[str]], *,
    target_scene_ids: list[str], expected_source_digest: str,
    authorized: bool, expected_session_digest: str | None = None,
) -> dict[str, object]:
    """Visit ordered authored scenes by planning only missing prerequisites.

    Target scenes are NOT executed. Later targets may need earlier target
    stages as prerequisites. Every step and the final history are replayed.
    """
    if authorized is not True:
        raise PermissionError("NPC itinerary requires operator authorization")
    if (type(actions) is not list or len(actions) > MAX_ACTIONS
            or len(_canonical(actions)) > 16384):
        raise StudioQuestError("invalid NPC itinerary history")
    if (type(target_scene_ids) is not list or not 1 <= len(target_scene_ids) <= MAX_TARGETS
            or len(_canonical(target_scene_ids)) > 4096):
        raise StudioQuestError("invalid NPC itinerary targets")
    if (any(type(t) is not str or not 1 <= len(t) <= 512 for t in target_scene_ids)
            or len(set(target_scene_ids)) != len(target_scene_ids)):
        raise StudioQuestError("NPC itinerary targets must be unique authored scenes")
    if (type(expected_source_digest) is not str
            or len(expected_source_digest) != 64
            or any(c not in "0123456789abcdef" for c in expected_source_digest)):
        raise StudioQuestError("invalid NPC itinerary source lease")
    before = replay_quest(documents, actions, authorized=True)
    if expected_session_digest is not None and (
            type(expected_session_digest) is not str
            or expected_session_digest != before.digest):
        raise StudioQuestError("stale NPC itinerary session lease")
    planned = [list(pair) for pair in before.choices]
    hops: list[dict[str, object]] = []
    steps: list[dict[str, object]] = []
    digest = before.digest
    for target in target_scene_ids:
        route = plan_dialogue_scene_route(
            documents, planned, target_scene_id=target,
            expected_source_digest=expected_source_digest, authorized=True)
        if (route["original_session_digest"] != digest
                or route["source_digest"] != expected_source_digest):
            raise StudioQuestError("NPC itinerary source or session drift")
        new_actions = route["planned_quest_receipt"]["choices"]
        if (type(new_actions) is not list or len(new_actions) > MAX_ACTIONS
                or new_actions[:len(planned)] != planned):
            raise StudioQuestError("NPC itinerary did not extend canonical history")
        start = len(steps)
        for step in route["steps"]:
            if step["before_session_digest"] != digest:
                raise StudioQuestError("NPC itinerary broken step chain")
            digest = step["after_session_digest"]
            steps.append(step)
        if len(steps) > MAX_ACTIONS or digest != route["planned_session_digest"]:
            raise StudioQuestError("NPC itinerary step budget or digest mismatch")
        hops.append({
            "target_scene_id": target, "target_npc_id": route["target_npc_id"],
            "target_status": route["target_status"], "step_start": start,
            "step_count": len(steps) - start,
            "arrival_session_digest": digest,
            "route_digest": route["route_digest"],
            "scene_played_verified": False,
        })
        planned = [list(pair) for pair in new_actions]
    after = replay_quest(documents, planned, authorized=True)
    if (after.digest != digest or after.source_digest != before.source_digest
            or after.project_id != before.project_id):
        raise StudioQuestError("NPC itinerary final replay mismatch")
    if len({step["quest_stage"] for step in steps}) != len(steps):
        raise StudioQuestError("NPC itinerary duplicated a prerequisite")
    payload: dict[str, object] = {
        "schema": ITINERARY_SCHEMA, "project_id": before.project_id,
        "source_digest": expected_source_digest,
        "quest_source_digest": before.source_digest,
        "original_session_digest": before.digest,
        "planned_session_digest": after.digest,
        "target_scene_ids": list(target_scene_ids), "hops": hops,
        "steps": steps, "step_count": len(steps),
        "planned_quest_receipt": after.receipt(),
        "progress": quest_progress(after, documents),
        "replay_verified": True, "source_unchanged": True,
        "file_write_performed": False, "scene_played_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False, "release_certified": False,
    }
    payload["itinerary_digest"] = _digest(payload)
    return payload
