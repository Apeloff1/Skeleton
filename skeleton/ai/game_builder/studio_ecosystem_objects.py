"""Immutable authored interactive-object index for director and editor tools."""
from __future__ import annotations

from typing import Any, Mapping

from .studio_ecosystem_quest import compile_quest_program, StudioQuestError
from .studio_ecosystem_scene import scene_catalog


def object_inventory(documents: Mapping[str, Any]) -> dict[str, object]:
    program = compile_quest_program(documents)
    scenes = scene_catalog(documents)
    mapping: dict[str, list[str]] = {}
    stages: dict[str, list[str]] = {}
    for scene in scenes:
        for item in scene["objects"]:
            mapping.setdefault(item, []).append(scene["scene_id"])
            stages.setdefault(item, []).append(scene["quest_stage"])
    return {
        "schema": "skeleton.game_builder.studio_object_catalog.v1",
        "project_id": program.project_id,
        "source_digest": program.source_digest,
        "unique_object_count": len(mapping),
        "objects": [{"id": key, "scenes": mapping[key], "stages": stages[key]}
                    for key in sorted(mapping)],
        "scene_objects_materialized": False,
        "native_interaction_qualified": False,
        "release_certified": False,
    }


def resolve_object(documents: Mapping[str, Any], object_id: str) -> dict[str, object]:
    if not isinstance(object_id, str) or not object_id:
        raise StudioQuestError("invalid object lookup")
    inventory = object_inventory(documents)
    value = next((obj for obj in inventory["objects"] if obj["id"] == object_id), None)
    if value is None:
        raise StudioQuestError("unknown authored interactive object")
    return {"project_id": inventory["project_id"],
            "source_digest": inventory["source_digest"], **value,
            "assets_generated": False}
