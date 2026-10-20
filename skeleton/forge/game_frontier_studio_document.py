"""Round-trip native Forge Studio project records in the existing project file tree.

This codec reconstructs typed project/quest/event/physics declarations before
accepting edits. It does not store a parallel state database or evaluate code.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .game_frontier_studio import (
    MapLayer, StudioError, StudioEvent, StudioPrefab, StudioPlacement,
    StudioProject, StudioQuest, StudioQuestStage, StudioTriggerVolume,
    StudioForceField, compile_studio_project,
)
from .game_frontier_rpg_events import EnvironmentalTrigger, RPGEventAction, RPGEventPage
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily


def create_authoring_project(project_id: str, *, width: int = 16,
                             height: int = 16) -> StudioProject:
    """Produce an editable original blank realm for an existing workspace."""
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 256 or not 1 <= height <= 256):
        raise StudioError("initial Studio realm requires bounded tile dimensions")
    return StudioProject(
        project_id=project_id, target_era="tile",
        projection=ProjectionMode.FULL_3D, world_family=WorldFamily.ORIGINAL,
        layers=(MapLayer("ground", width, height, ("ground", "stone", "water"),
                         (0,) * (width * height)),),
    )


def authored_document(project: StudioProject) -> str:
    """Emit deterministic UTF-8 JSON that can be stored as a canonical project file."""
    manifest = compile_studio_project(project)
    if manifest.get("virtual_game_map") is not None:
        raise StudioError("virtual map source requires its separate full-fidelity editor")
    try:
        content = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise StudioError("Forge Studio source must serialize into finite JSON") from exc
    if len(content.encode("utf-8")) > 128000:
        raise StudioError("Forge Studio source exceeds canonical project file budget")
    return content


def load_authored_document(source: str, *, project_id: str) -> StudioProject:
    """Reconstruct exact typed editable state, reject checksum drift and truncation."""
    if type(source) is not str or not 1 <= len(source.encode("utf-8")) <= 128000:
        raise StudioError("bounded original Studio JSON required")
    try:
        value = json.loads(source)
    except (ValueError, TypeError) as exc:
        raise StudioError("Forge Studio source JSON is invalid") from exc
    if (type(value) is not dict or value.get("schema") != "skeleton.forge.frontier_studio.v1"
            or value.get("project_id") != project_id
            or value.get("authority") != "candidate_not_executed"
            or value.get("virtual_game_map") is not None):
        raise StudioError("source does not belong to this canonical authoring project")
    try:
        layers = tuple(
            MapLayer(layer["id"], layer["w"], layer["h"],
                     tuple(layer["palette"]), tuple(layer["data"]),
                     layer["elevation"])
            for layer in value["layers"]
        )
        prefabs = tuple(StudioPrefab(**row) for row in value["prefabs"])
        placements = tuple(StudioPlacement(**row) for row in value["placements"])
        events = tuple(StudioEvent(**row) for row in value["events"])
        pages = tuple(
            RPGEventPage(
                page_id=page["id"], priority=page["priority"],
                conditions=tuple(EnvironmentalTrigger(**x) for x in page["conditions"]),
                actions=tuple(RPGEventAction(**x) for x in page["actions"]),
                required_flags=tuple(tuple(x) for x in page["flags"]),
                cooldown_ms=page["cooldown_ms"], enabled=page["enabled"],
                repeat=page["repeat"],
            ) for page in value["environmental_pages"]
        )
        volumes = tuple(
            StudioTriggerVolume(
                row["zone_id"], row["actor_entity_id"], row["event_page_id"],
                row["radius_m"], tuple(row["offset_xyz_m"]),
            ) for row in value["native_trigger_volumes"]
        )
        fields = tuple(
            StudioForceField(
                row["id"], row["actor_id"], row["kind"],
                row["radius_m"], row["acceleration_mps2"],
                tuple(row["offset_xyz_m"]),
            ) for row in value["native_gameplay_force_fields"]
        )
        quests = tuple(StudioQuest(
            quest["id"], quest["title"], quest["start"],
            tuple(StudioQuestStage(stage["id"], stage["objective"],
                                   tuple(stage["next"])) for stage in quest["stages"]),
        ) for quest in value["native_quests"])
        project = StudioProject(
            project_id, value["target_era"],
            ProjectionMode(value["projection"]), WorldFamily(value["world_family"]),
            layers=layers, prefabs=prefabs, placements=placements,
            events=events, environmental_pages=pages,
            soundtrack_ids=tuple(value["soundtrack"]),
            native_trigger_volumes=volumes,
            native_gameplay_force_fields=fields,
            native_quests=quests,
        )
    except (KeyError, IndexError, AttributeError, TypeError, ValueError) as exc:
        raise StudioError("authored original Studio source is incomplete or invalid") from exc
    if compile_studio_project(project) != value:
        raise StudioError("authoring file has inconsistent source receipt or unsupported fields")
    return project
