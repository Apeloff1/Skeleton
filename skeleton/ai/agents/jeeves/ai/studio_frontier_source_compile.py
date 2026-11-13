"""Compile actual Jeeves-authored records into the existing typed Forge Studio.

This bridge does not invent a second game engine. It consumes revision-pinned
creator records and reconstructs real skeleton.forge.game_frontier_studio types,
then calls that compiler with the project's explicitly authored era/projection
and world family. Unhandled game facets are reported, never silently marked
compiled or substituted with default generated gameplay.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skeleton.forge.game_frontier_studio import (
    MapLayer, StudioEvent, StudioPlacement, StudioPrefab, StudioProject,
    StudioQuest, StudioQuestStage, compile_studio_project,
)
from skeleton.jeeves.game_frontier_worlds import ProjectionMode, WorldFamily
from .studio_interaction_contract import digest

SCHEMA = "skeleton.jeeves.frontier_source_compiler.v1"


class FrontierSourceError(ValueError):
    """Authoring record cannot become the canonical typed Forge project."""


def _exact(document: Mapping[str, Any], required: set[str],
           optional: set[str] = frozenset()) -> None:
    if not isinstance(document, Mapping):
        raise FrontierSourceError("source document must be a reviewed object")
    actual = set(document)
    if not required <= actual or not actual <= required | set(optional):
        raise FrontierSourceError(
            "source authoring fields differ from the selected Forge type"
        )


def _record_doc(record: Mapping[str, Any]) -> Mapping[str, Any]:
    item = record.get("document")
    if not isinstance(item, Mapping):
        raise FrontierSourceError("authored record has no document")
    return item


def materialize_persisted_frontier_source(
    project_id: str,
    records: Mapping[str, Mapping[str, Any]],
    *, source_head_sha256: str | None,
) -> tuple[StudioProject, dict[str, Any]]:
    """Compile real typed world, map, sprites, actors, RPG events and quests.

    A 'studio_settings' record and at least one map_layer are mandatory;
    other creator documents remain clearly uncompiled design material.
    """
    if not isinstance(records, Mapping) or not 1 <= len(records) <= 10000:
        raise FrontierSourceError("at least one real game source record required")
    if any(not isinstance(item, Mapping) for item in records.values()):
        raise FrontierSourceError("creator source contains an invalid record")

    settings: list[Mapping[str, Any]] = []
    layers = []
    prefabs = []
    placements = []
    events = []
    quests = []
    uncompiled: list[str] = []
    compiled: list[str] = []

    for record_id in sorted(records):
        record = records[record_id]
        doc = _record_doc(record)
        kind = doc.get("kind")
        if record.get("record_id") != record_id:
            raise FrontierSourceError("record id changed during typed compilation")
        try:
            if kind == "studio_settings":
                _exact(doc, {"kind", "target_era", "projection", "world_family"})
                if record.get("facet") not in ("engine", "platform", "scope"):
                    raise FrontierSourceError("studio settings require an engine facet")
                settings.append(doc)
            elif kind == "map_layer":
                _exact(doc, {"kind", "layer_id", "width", "height", "palette", "data"},
                       {"elevation_m"})
                if record.get("facet") not in ("map", "world"):
                    raise FrontierSourceError("map source belongs to map/world editor")
                layers.append(MapLayer(
                    doc["layer_id"], doc["width"], doc["height"],
                    tuple(doc["palette"]), tuple(doc["data"]),
                    doc.get("elevation_m", 0.0),
                ))
            elif kind == "prefab":
                _exact(doc, {"kind", "prefab_id", "prefab_kind", "era", "asset_digest"},
                       {"interaction_type"})
                if record.get("facet") not in ("asset_forge", "sprite_forge", "cast", "npc"):
                    raise FrontierSourceError("prefab requires a real Forge asset facet")
                prefabs.append(StudioPrefab(
                    doc["prefab_id"], doc["prefab_kind"], doc["era"],
                    doc["asset_digest"], doc.get("interaction_type", "none"),
                ))
            elif kind == "placement":
                _exact(doc, {"kind", "prefab_id", "x", "y", "z"}, {"facing_deg"})
                if record.get("facet") not in ("scene_forge", "world", "map"):
                    raise FrontierSourceError("placement requires an actual scene editor")
                placements.append(StudioPlacement(
                    doc["prefab_id"], doc["x"], doc["y"], doc["z"],
                    doc.get("facing_deg", 0.0),
                ))
            elif kind == "event":
                _exact(doc, {"kind", "event_id", "trigger", "condition_flag",
                             "condition_value", "action", "target", "value"})
                if record.get("facet") not in ("scene_forge", "dialogue", "quests"):
                    raise FrontierSourceError("event needs event or dialogue owner")
                events.append(StudioEvent(
                    doc["event_id"], doc["trigger"], doc["condition_flag"],
                    doc["condition_value"], doc["action"], doc["target"], doc["value"],
                ))
            elif kind == "quest":
                _exact(doc, {"kind", "quest_id", "title", "first_stage_id", "stages"})
                if record.get("facet") != "quests":
                    raise FrontierSourceError("quest graph requires quest editor")
                stages = []
                if not isinstance(doc["stages"], list):
                    raise FrontierSourceError("quest stage graph must be an array")
                for stage in doc["stages"]:
                    _exact(stage, {"stage_id", "objective", "next_stage_ids"})
                    stages.append(StudioQuestStage(
                        stage["stage_id"], stage["objective"],
                        tuple(stage["next_stage_ids"]),
                    ))
                quests.append(StudioQuest(
                    doc["quest_id"], doc["title"], doc["first_stage_id"],
                    tuple(stages),
                ))
            else:
                # This is an original design document outside the currently
                # installed typed Forge compiler. Keep its source provenance
                # visible; never claim it appeared in a playable build.
                uncompiled.append(record_id)
                continue
            compiled.append(record_id)
        except (TypeError, KeyError, ValueError, AttributeError) as exc:
            raise FrontierSourceError(
                "typed Forge schema rejected source record " + record_id
            ) from exc

    if len(settings) != 1 or not layers:
        raise FrontierSourceError(
            "typed original game needs exactly one authored setting and a map layer"
        )
    chosen = settings[0]
    try:
        project = StudioProject(
            project_id=project_id,
            target_era=chosen["target_era"],
            projection=ProjectionMode(chosen["projection"]),
            world_family=WorldFamily(chosen["world_family"]),
            layers=tuple(layers), prefabs=tuple(prefabs),
            placements=tuple(placements), events=tuple(events),
            native_quests=tuple(quests),
        )
        manifest = compile_studio_project(project)
    except (ValueError, TypeError, KeyError) as exc:
        raise FrontierSourceError(
            "existing Forge Studio compiler rejected game project graph"
        ) from exc
    result = {
        "schema_version": SCHEMA,
        "project_id": project_id,
        "source_head_sha256": source_head_sha256,
        "typed_compiler": "skeleton.forge.game_frontier_studio.compile_studio_project",
        "typed_manifest": manifest,
        "compiled_record_ids": compiled,
        "non_compilable_record_ids": uncompiled,
        "typed_forge_coverage_complete": not uncompiled,
        "native_engine_runtime_executed": False,
        "commercial_game_complete": False,
    }
    result["receipt_sha256"] = digest(result)
    return project, result


def compile_persisted_frontier_source(
    project_id: str,
    records: Mapping[str, Mapping[str, Any]],
    *, source_head_sha256: str | None,
) -> dict[str, Any]:
    """Return the exact serializable approved typed Forge candidate."""
    _, receipt = materialize_persisted_frontier_source(
        project_id, records, source_head_sha256=source_head_sha256,
    )
    return receipt


__all__ = [
    "FrontierSourceError", "materialize_persisted_frontier_source",
    "compile_persisted_frontier_source",
]
