"""Executable 50-action authoring controller over canonical Forge Studio projects.

All changes are copy-on-write, immediately revalidated as real StudioProject
instances. A batch fails atomically, preserves source and emits a receipt.
Actual native game compilation remains in the existing Forge Studio compiler.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .game_frontier_studio import (
    StudioError, StudioProject, compile_studio_project,
)
from .game_frontier_studio_map_edit import MAP_ACTIONS, edit_map
from .game_frontier_studio_object_edit import OBJECT_ACTIONS, edit_objects
from .game_frontier_studio_environment_edit import ENV_ACTIONS, edit_environment
from .game_frontier_studio_physics_edit import PHYSICAL_ACTIONS, edit_physical
from .game_frontier_studio_procedural_edit import PROCEDURAL_ACTIONS, edit_procedural
from .game_frontier_studio_population_edit import POPULATION_ACTIONS, edit_population
from .game_frontier_studio_narrative_edit import STORY_ACTIONS, edit_story
from .game_frontier_studio_topology_edit import TERRAIN_TOPOLOGY_ACTIONS, edit_topology
from .game_frontier_studio_actor_layout_edit import ACTOR_LAYOUT_ACTIONS, edit_actor_layout
from .game_frontier_studio_story_production_edit import STORY_PRODUCTION_ACTIONS, edit_story_production
from .game_frontier_studio_environment_composer import ENVIRONMENT_COMPOSER_ACTIONS, edit_environment_composer
from .game_frontier_studio_biome_factory import BIOME_ACTIONS, edit_biome
from .game_frontier_studio_structure_factory import STRUCTURE_ACTIONS, edit_structure
from .game_frontier_studio_encounter_factory import ENCOUNTER_ACTIONS, edit_encounter
from .game_frontier_studio_quest_blueprint_factory import QUEST_BLUEPRINT_ACTIONS, edit_quest_blueprint
from .game_frontier_studio_reactive_scene_factory import REACTIVE_SCENE_ACTIONS, edit_reactive_scene
from .game_frontier_studio_quest_terrain_edit import (
    QUEST_ACTIONS, TERRAIN_ACTIONS, edit_quest_structure, edit_terrain,
)

AUTHORING_ACTIONS = (MAP_ACTIONS + OBJECT_ACTIONS + ENV_ACTIONS + PHYSICAL_ACTIONS +
                     QUEST_ACTIONS + TERRAIN_ACTIONS + PROCEDURAL_ACTIONS +
                     POPULATION_ACTIONS + STORY_ACTIONS +
                     TERRAIN_TOPOLOGY_ACTIONS + ACTOR_LAYOUT_ACTIONS +
                     STORY_PRODUCTION_ACTIONS + ENVIRONMENT_COMPOSER_ACTIONS +
                     BIOME_ACTIONS + STRUCTURE_ACTIONS + ENCOUNTER_ACTIONS +
                     QUEST_BLUEPRINT_ACTIONS + REACTIVE_SCENE_ACTIONS)
if len(AUTHORING_ACTIONS) != 500 or len(set(AUTHORING_ACTIONS)) != 500:
    raise RuntimeError("Forge Studio must expose 500 implemented, distinct operations")


def _bytes(value: object, *, maximum: int = 512_000) -> bytes:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise StudioError("authoring operation must contain finite JSON") from exc
    if len(result) > maximum:
        raise StudioError("authoring payload exceeds permitted budget")
    return result


def _digest(value: object) -> str:
    return sha256(_bytes(value, maximum=8_000_000)).hexdigest()


def snapshot(project: StudioProject) -> dict[str, Any]:
    """Actual stable content snapshot produced by the existing Studio compiler."""
    if not isinstance(project, StudioProject):
        raise StudioError("project must use existing typed Forge Studio")
    return compile_studio_project(project)


def project_digest(project: StudioProject) -> str:
    return snapshot(project)["content_sha256"]


def execute_authoring(project: StudioProject, operation: str,
                      payload: Mapping[str, Any]) -> StudioProject:
    """Execute exactly one operation; never consume unrecognized tool names."""
    if type(operation) is not str or not isinstance(payload, Mapping):
        raise StudioError("typed operation and parameters are required")
    if len(payload) > 32 or len(_bytes(dict(payload))) > 128_000:
        raise StudioError("authoring payload exceeds bounded edit request")
    if operation in MAP_ACTIONS:
        return edit_map(project, operation, payload)
    if operation in OBJECT_ACTIONS:
        return edit_objects(project, operation, payload)
    if operation in ENV_ACTIONS:
        return edit_environment(project, operation, payload)
    if operation in PHYSICAL_ACTIONS:
        return edit_physical(project, operation, payload)
    if operation in QUEST_ACTIONS:
        return edit_quest_structure(project, operation, payload)
    if operation in TERRAIN_ACTIONS:
        return edit_terrain(project, operation, payload)
    if operation in PROCEDURAL_ACTIONS:
        return edit_procedural(project, operation, payload)
    if operation in POPULATION_ACTIONS:
        return edit_population(project, operation, payload)
    if operation in STORY_ACTIONS:
        return edit_story(project, operation, payload)
    if operation in TERRAIN_TOPOLOGY_ACTIONS:
        return edit_topology(project, operation, payload)
    if operation in ACTOR_LAYOUT_ACTIONS:
        return edit_actor_layout(project, operation, payload)
    if operation in STORY_PRODUCTION_ACTIONS:
        return edit_story_production(project, operation, payload)
    if operation in ENVIRONMENT_COMPOSER_ACTIONS:
        return edit_environment_composer(project, operation, payload)
    if operation in BIOME_ACTIONS:
        return edit_biome(project, operation, payload)
    if operation in STRUCTURE_ACTIONS:
        return edit_structure(project, operation, payload)
    if operation in ENCOUNTER_ACTIONS:
        return edit_encounter(project, operation, payload)
    if operation in QUEST_BLUEPRINT_ACTIONS:
        return edit_quest_blueprint(project, operation, payload)
    if operation in REACTIVE_SCENE_ACTIONS:
        return edit_reactive_scene(project, operation, payload)
    raise StudioError("unknown executable Studio editor action")


def apply_authoring_batch(project: StudioProject,
                          steps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Fully transactional immutable edit batch with source and final receipts.

    No source mutation and no persistent write is performed here. The existing
    authorized host decides whether to persist the resulting typed project.
    """
    if not isinstance(project, StudioProject) or type(steps) not in (tuple, list) or (
            not 1 <= len(steps) <= 64):
        raise StudioError("bounded existing Studio project and edit steps required")
    initial = project_digest(project)
    draft = project
    changes: list[dict[str, Any]] = []
    for index, command in enumerate(steps):
        if type(command) is not dict or set(command) != {"action", "parameters"}:
            raise StudioError("authoring step requires action and parameters only")
        name = command["action"]
        params = command["parameters"]
        old = project_digest(draft)
        draft = execute_authoring(draft, name, params)
        updated = project_digest(draft)
        changes.append({
            "index": index, "operation": name,
            "before_sha256": old, "after_sha256": updated,
            "changed": old != updated,
        })
    final = project_digest(draft)
    receipt = {
        "schema": "skeleton.forge.frontier_authoring_batch.v1",
        "project_id": project.project_id,
        "source_sha256": initial,
        "candidate_sha256": final,
        "action_count": len(changes),
        "changes": changes,
        "actually_changed": initial != final,
        "persisted": False,
    }
    return {
        "project": draft,
        "receipt": {**receipt, "receipt_sha256": _digest(receipt)},
    }


def authored_summary(project: StudioProject) -> dict[str, Any]:
    """Compact, source-backed counts and layer statistics for Jeeves UI."""
    digest = project_digest(project)
    output = {
        "schema": "skeleton.forge.frontier_authoring_summary.v1",
        "project_id": project.project_id,
        "source_sha256": digest,
        "target_era": project.target_era,
        "projection": project.projection.value,
        "world_family": project.world_family.value,
        "layers": [
            {"id": layer.layer_id, "size": [layer.width, layer.height],
             "tile_count": sum(v != -1 for v in layer.data),
             "palette_size": len(layer.palette), "elevation_m": layer.elevation_m}
            for layer in project.layers
        ],
        "prefab_catalog": [
            {"id": p.prefab_id, "kind": p.kind, "era": p.era,
             "interaction": p.interaction_type}
            for p in project.prefabs[:128]
        ],
        "actor_catalog": [
            {"index": i, "prefab_id": p.prefab_id,
             "position": [p.x, p.y, p.z], "facing_deg": p.facing_deg}
            for i, p in enumerate(project.placements[:128])
        ],
        "quest_catalog": [
            {"id": q.quest_id, "title": q.title, "stage_count": len(q.stages)}
            for q in project.native_quests[:128]
        ],
        "prefab_count": len(project.prefabs),
        "placed_actor_count": len(project.placements),
        "authored_event_count": len(project.events),
        "quest_count": len(project.native_quests),
        "music_cue_count": len(project.soundtrack_ids),
        "environment_page_count": len(project.environmental_pages),
        "native_zone_count": len(project.native_trigger_volumes),
        "native_force_field_count": len(project.native_gameplay_force_fields),
        "quest_stage_count": sum(len(q.stages) for q in project.native_quests),
        "action_catalog": AUTHORING_ACTIONS,
        "candidate_only": True,
    }
    return {**output, "receipt_sha256": _digest(output)}


def authored_tile_region(project: StudioProject, layer_id: str, *, x: int, y: int,
                         width: int, height: int) -> dict[str, Any]:
    """Read actual authored tile pixels for editor clipboard / viewport."""
    layer = next((item for item in project.layers if item.layer_id == layer_id), None)
    if layer is None or any(type(v) is not int for v in (x, y, width, height)):
        raise StudioError("tile region requires existing layer and bounded integers")
    if (width <= 0 or height <= 0 or width * height > 65536 or
            x < 0 or y < 0 or x + width > layer.width or y + height > layer.height):
        raise StudioError("tile copy is outside actual authored map")
    tiles = [layer.data[row * layer.width + col]
             for row in range(y, y + height) for col in range(x, x + width)]
    output = {
        "schema": "skeleton.forge.frontier_tile_region.v1",
        "project_sha256": project_digest(project),
        "layer": layer_id,
        "x": x, "y": y, "width": width, "height": height,
        "palette": list(layer.palette),
        "tiles": tiles,
    }
    return {**output, "receipt_sha256": _digest(output)}
