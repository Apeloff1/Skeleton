"""Read-only executable binding of authored studio scenes to quest replay.

Scene views and object intent events never assert physical interactions, world
physics, actual equipment, or native genre execution.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    QuestSession, StudioQuestError, available_stages,
    compile_quest_program, verify_quest_session,
)


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def scene_catalog(documents: Mapping[str, Any]) -> tuple[dict[str, object], ...]:
    program = compile_quest_program(documents)
    scene = documents.get("scene")
    if not isinstance(scene, dict) or scene.get("project_id") != program.project_id:
        raise StudioQuestError("scene and quest source identity mismatch")
    episodes = scene.get("episode_plan")
    if not isinstance(episodes, list) or len(episodes) != len(program.stages):
        raise StudioQuestError("scene/quest length mismatch")
    result: list[dict[str, object]] = []
    names: set[str] = set()
    for i, item in enumerate(episodes):
        if not isinstance(item, dict):
            raise StudioQuestError("invalid authored scene")
        old = "quest" in item or "objects" in item
        if old and ("quest_stage" in item or "interactive_objects" in item):
            raise StudioQuestError("ambiguous scene schema")
        stage = item.get("quest" if old else "quest_stage")
        objects = item.get("objects" if old else "interactive_objects")
        sid = item.get("id")
        if (not isinstance(sid, str) or not sid or sid in names
                or stage != program.stages[i].key
                or not isinstance(objects, list) or not objects
                or any(not isinstance(x, str) or not x for x in objects)
                or len(objects) != len(set(objects))):
            raise StudioQuestError("scene stage, identity or objects are invalid")
        names.add(sid)
        result.append({"scene_id": sid, "quest_stage": stage,
                       "objects": tuple(objects)})
    return tuple(result)


def inspect_scene(session: QuestSession, documents: Mapping[str, Any], *,
                  scene_id: str, authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("scene inspection requires operator authorization")
    verify_quest_session(session, documents)
    entry = next((s for s in scene_catalog(documents) if s["scene_id"] == scene_id), None)
    if entry is None:
        raise StudioQuestError("unregistered scene")
    unlocked = entry["quest_stage"] in available_stages(session, documents)
    return {
        "schema": "skeleton.game_builder.studio_scene_inspection.v1",
        "project_id": session.project_id, "source_digest": session.source_digest,
        "session_digest": session.digest, "scene_id": scene_id,
        "quest_stage": entry["quest_stage"], "unlocked": unlocked,
        "authored_object_ids": list(entry["objects"]) if unlocked else [],
        "scene_executed_natively": False, "release_certified": False,
    }


def inspect_object_intent(session: QuestSession, documents: Mapping[str, Any], *,
                          scene_id: str, object_id: str,
                          authorized: bool) -> dict[str, object]:
    view = inspect_scene(session, documents, scene_id=scene_id, authorized=authorized)
    if not view["unlocked"] or object_id not in view["authored_object_ids"]:
        raise StudioQuestError("object is not currently accessible")
    payload = {"project_id": session.project_id, "source": session.source_digest,
               "quest_session": session.digest, "scene": scene_id, "object": object_id}
    return {
        "schema": "skeleton.game_builder.studio_object_intent.v1",
        **payload, "intent_digest": _hash(payload), "object_interaction_performed": False,
        "external_evidence_verified": False, "release_certified": False,
    }
