"""Immutable prefab, placement, event, quest and soundtrack creation/editing.

Twenty-five functional operations over existing canonical Forge Studio fields.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Any
import math

from .game_frontier_studio import (
    StudioError, StudioEvent, StudioPrefab, StudioPlacement, StudioQuest,
    StudioQuestStage, StudioProject,
)
from .game_frontier_studio_map_edit import _integer, _name

OBJECT_ACTIONS = (
    "prefab_add", "prefab_remove", "prefab_clone", "prefab_retarget",
    "prefab_interaction", "placement_add", "placement_remove",
    "placement_move", "placement_rotate", "placement_duplicate",
    "placement_mirror", "placement_grid",
    "event_add", "event_remove", "event_condition", "event_action",
    "event_trigger", "quest_add", "quest_remove", "quest_stage_append",
    "quest_objective", "quest_title", "soundtrack_add",
    "soundtrack_remove", "soundtrack_reorder",
)


def _text(args: Mapping, key: str, maximum: int = 512) -> str:
    value = args.get(key)
    if type(value) is not str or not 1 <= len(value) <= maximum or not value.strip():
        raise StudioError(f"{key} must contain bounded text")
    return value


def _finite(args: Mapping, key: str, maximum: float = 1e7) -> float:
    value = args.get(key)
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > maximum:
        raise StudioError(f"{key} must be finite and bounded")
    return float(value)


def _digest(args: Mapping) -> str:
    v = args.get("asset_digest")
    if type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise StudioError("asset digest must be lowercase SHA-256")
    return v


def _locate(items: tuple, identity: str, attribute: str):
    for i, item in enumerate(items):
        if getattr(item, attribute) == identity:
            return i, item
    raise StudioError("source object identity not found")


def _at(items: tuple, i: int, value: object) -> tuple:
    return items[:i] + (value,) + items[i + 1:]


def _xyz(args: Mapping) -> dict[str, float]:
    return {axis: _finite(args, axis) for axis in ("x", "y", "z")}


def edit_objects(project: StudioProject, action: str, args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or action not in OBJECT_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("invalid original game editor operation")
    if action == "prefab_add":
        prefab = StudioPrefab(
            _name(args, "prefab_id"), _text(args, "kind", 32),
            _text(args, "era", 64), _digest(args),
            args.get("interaction_type", "none"),
        )
        if any(p.prefab_id == prefab.prefab_id for p in project.prefabs):
            raise StudioError("duplicate prefab")
        return replace(project, prefabs=project.prefabs + (prefab,))
    if action in ("prefab_remove", "prefab_clone", "prefab_retarget", "prefab_interaction"):
        i, prefab = _locate(project.prefabs, _name(args, "prefab_id"), "prefab_id")
        if action == "prefab_remove":
            if any(p.prefab_id == prefab.prefab_id for p in project.placements):
                raise StudioError("placed prefab cannot be removed")
            return replace(project, prefabs=project.prefabs[:i] + project.prefabs[i + 1:])
        if action == "prefab_clone":
            name = _name(args, "new_prefab_id")
            if any(p.prefab_id == name for p in project.prefabs):
                raise StudioError("prefab clone conflicts with existing")
            return replace(project, prefabs=project.prefabs + (replace(prefab, prefab_id=name),))
        change = ({"asset_digest": _digest(args)} if action == "prefab_retarget"
                  else {"interaction_type": _text(args, "interaction_type", 32)})
        return replace(project, prefabs=_at(project.prefabs, i, replace(prefab, **change)))
    if action == "placement_add":
        name = _name(args, "prefab_id")
        if not any(p.prefab_id == name for p in project.prefabs):
            raise StudioError("placement requires real prefab")
        placement = StudioPlacement(name, **_xyz(args),
                                    facing_deg=_finite(args, "facing_deg", 36000)
                                    if "facing_deg" in args else 0.)
        return replace(project, placements=project.placements + (placement,))
    if action == "placement_grid":
        name = _name(args, "prefab_id")
        if not any(p.prefab_id == name for p in project.prefabs):
            raise StudioError("grid requires real prefab")
        columns, rows = _integer(args, "columns", 1, 128), _integer(args, "rows", 1, 128)
        if columns * rows > 1024:
            raise StudioError("placement grid exceeds batch limit")
        start = _xyz(args)
        dx, dy = _finite(args, "dx", 10000), _finite(args, "dy", 10000)
        instances = tuple(StudioPlacement(name, start["x"] + x * dx,
                                          start["y"] + y * dy, start["z"])
                          for y in range(rows) for x in range(columns))
        return replace(project, placements=project.placements + instances)
    if action in ("placement_remove", "placement_move", "placement_rotate",
                  "placement_duplicate", "placement_mirror"):
        i = _integer(args, "index", 0, len(project.placements) - 1)
        p = project.placements[i]
        if action == "placement_remove":
            # Prevent changing actor index bindings used by native zones/fields.
            for binding in (*project.native_trigger_volumes,
                            *project.native_gameplay_force_fields):
                part = binding.actor_entity_id.rsplit(":", 1)
                if len(part) == 2 and part[1].isdigit() and int(part[1]) >= i:
                    raise StudioError("removal would reindex bound actor")
            return replace(project, placements=project.placements[:i] + project.placements[i + 1:])
        if action == "placement_move":
            p = replace(p, **_xyz(args))
        elif action == "placement_rotate":
            p = replace(p, facing_deg=(p.facing_deg + _finite(args, "degrees", 36000)) % 360)
        elif action == "placement_mirror":
            axis = _text(args, "axis", 1)
            if axis not in ("x", "y"):
                raise StudioError("mirror requires x or y axis")
            pivot = _finite(args, "pivot")
            p = replace(p, **{axis: 2 * pivot - getattr(p, axis)},
                        facing_deg=(180 - p.facing_deg if axis == "x" else -p.facing_deg) % 360)
        else:
            offsets = {axis: _finite(args, "d" + axis) for axis in ("x", "y", "z")}
            copy = replace(p, **{axis: getattr(p, axis) + delta for axis, delta in offsets.items()})
            return replace(project, placements=project.placements + (copy,))
        return replace(project, placements=_at(project.placements, i, p))
    if action == "event_add":
        condition = args.get("condition_value", True)
        if type(condition) is not bool:
            raise StudioError("typed event condition required")
        flag = args.get("condition_flag", "")
        value = args.get("value", "")
        if type(flag) is not str or type(value) is not str:
            raise StudioError("event flag and value must be strings")
        event = StudioEvent(_name(args, "event_id"), _text(args, "trigger", 32),
                            flag, condition, _text(args, "action", 32),
                            _text(args, "target", 128), value)
        if any(e.event_id == event.event_id for e in project.events):
            raise StudioError("duplicate authored event")
        return replace(project, events=project.events + (event,))
    if action in ("event_remove", "event_condition", "event_action", "event_trigger"):
        i, event = _locate(project.events, _name(args, "event_id"), "event_id")
        if action == "event_remove":
            if any(z.event_page_id == event.event_id for z in project.native_trigger_volumes):
                raise StudioError("cannot remove native-bound event")
            return replace(project, events=project.events[:i] + project.events[i + 1:])
        if action == "event_condition":
            flag, value = args.get("condition_flag", ""), args.get("condition_value")
            if type(flag) is not str or type(value) is not bool:
                raise StudioError("event conditions must be typed")
            event = replace(event, condition_flag=flag, condition_value=value)
        elif action == "event_action":
            v = args.get("value", "")
            if type(v) is not str:
                raise StudioError("event action value must be string")
            event = replace(event, action=_text(args, "action", 32),
                            target=_text(args, "target", 128), value=v)
        else:
            event = replace(event, trigger=_text(args, "trigger", 32))
        return replace(project, events=_at(project.events, i, event))
    if action == "quest_add":
        qid, sid = _name(args, "quest_id"), _name(args, "stage_id")
        if any(q.quest_id == qid for q in project.native_quests):
            raise StudioError("duplicate quest")
        q = StudioQuest(qid, _text(args, "title", 256), sid,
                        (StudioQuestStage(sid, _text(args, "objective")),))
        return replace(project, native_quests=project.native_quests + (q,))
    if action in ("quest_remove", "quest_stage_append", "quest_objective", "quest_title"):
        i, q = _locate(project.native_quests, _name(args, "quest_id"), "quest_id")
        if action == "quest_remove":
            if any(e.action == "start_quest" and e.value == q.quest_id for e in project.events):
                raise StudioError("cannot remove quest referenced by event")
            return replace(project, native_quests=project.native_quests[:i] + project.native_quests[i + 1:])
        if action == "quest_title":
            q = replace(q, title=_text(args, "title", 256))
        elif action == "quest_objective":
            j, stage = _locate(q.stages, _name(args, "stage_id"), "stage_id")
            q = replace(q, stages=_at(q.stages, j, replace(stage, objective=_text(args, "objective"))))
        else:
            parent, new = _name(args, "from_stage_id"), _name(args, "stage_id")
            if any(s.stage_id == new for s in q.stages):
                raise StudioError("stage identity already exists")
            j, stage = _locate(q.stages, parent, "stage_id")
            if len(stage.next_stage_ids) >= 32:
                raise StudioError("quest stage has reached branch limit")
            existing = _at(q.stages, j, replace(stage, next_stage_ids=stage.next_stage_ids + (new,)))
            q = replace(q, stages=existing + (StudioQuestStage(new, _text(args, "objective")),))
        return replace(project, native_quests=_at(project.native_quests, i, q))
    if action == "soundtrack_add":
        song = _name(args, "soundtrack_id")
        if song in project.soundtrack_ids or len(project.soundtrack_ids) >= 4096:
            raise StudioError("duplicate or excessive soundtrack cue")
        return replace(project, soundtrack_ids=project.soundtrack_ids + (song,))
    if action in ("soundtrack_remove", "soundtrack_reorder"):
        song = _name(args, "soundtrack_id")
        if song not in project.soundtrack_ids:
            raise StudioError("soundtrack identity not present")
        cues = list(project.soundtrack_ids)
        cues.remove(song)
        if action == "soundtrack_reorder":
            position = _integer(args, "position", 0, len(cues))
            cues.insert(position, song)
        return replace(project, soundtrack_ids=tuple(cues))
    raise StudioError("unsupported object authoring action")
