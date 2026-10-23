"""Ten new quest graph rewrites and five substantive procedural terrain tools.

Quest operations modify executable native stage paths and are rechecked by
the canonical parser. Terrain commands update the actual MapLayer pixel grid.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from typing import Any, Mapping

from .game_frontier_studio import (
    StudioError, StudioProject, StudioQuest, StudioQuestStage,
)
from .game_frontier_studio_map_edit import (
    _name, _integer, _layer, _rectangle, _tile, _replace_layer,
)

QUEST_ACTIONS = (
    "quest_stage_remove", "quest_stage_link", "quest_stage_unlink",
    "quest_stage_split", "quest_stage_rename", "quest_start_change",
    "quest_stage_swap_objectives", "quest_duplicate",
    "quest_stage_reorder", "quest_rewrite_objectives",
)
TERRAIN_ACTIONS = (
    "terrain_noise", "terrain_smooth", "terrain_terrace",
    "terrain_outline", "terrain_erode",
)


def _quest(project: StudioProject, args: Mapping[str, Any]):
    quest_id = _name(args, "quest_id")
    for i, quest in enumerate(project.native_quests):
        if quest.quest_id == quest_id:
            return i, quest
    raise StudioError("native quest not found")


def _stage(quest: StudioQuest, ident: str):
    for i, stage in enumerate(quest.stages):
        if stage.stage_id == ident:
            return i, stage
    raise StudioError("requested quest stage does not exist")


def _replace(items: tuple, i: int, value: object):
    return items[:i] + (value,) + items[i + 1:]


def _objective(args: Mapping[str, Any], key: str = "objective") -> str:
    value = args.get(key)
    if type(value) is not str or not 1 <= len(value.strip()) <= 512:
        raise StudioError("narrative objective must have meaningful bounded text")
    return value


def edit_quest_structure(project: StudioProject, operation: str,
                         args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or operation not in QUEST_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("unsupported quest branch rewrite")
    i, quest = _quest(project, args)
    if operation == "quest_duplicate":
        name = _name(args, "new_quest_id")
        if any(q.quest_id == name for q in project.native_quests):
            raise StudioError("duplicate quest id")
        title = args.get("title", quest.title)
        if type(title) is not str or not 1 <= len(title) <= 256:
            raise StudioError("copy requires a valid native quest title")
        new = replace(quest, quest_id=name, title=title)
        return replace(project, native_quests=project.native_quests + (new,))
    stages = list(quest.stages)
    if operation == "quest_stage_remove":
        sid = _name(args, "stage_id")
        if sid == quest.first_stage_id or len(stages) < 2:
            raise StudioError("cannot remove the native quest entry/last stage")
        position, _ = _stage(quest, sid)
        stages.pop(position)
        stages = [replace(stage, next_stage_ids=tuple(
            edge for edge in stage.next_stage_ids if edge != sid))
                  for stage in stages]
    elif operation in ("quest_stage_link", "quest_stage_unlink"):
        source = _name(args, "from_stage_id")
        destination = _name(args, "to_stage_id")
        pos, stage = _stage(quest, source)
        _stage(quest, destination)
        if source == destination:
            raise StudioError("self-loop quest edge forbidden")
        if operation == "quest_stage_link":
            if destination in stage.next_stage_ids or len(stage.next_stage_ids) >= 32:
                raise StudioError("duplicate or excessive branch")
            edges = stage.next_stage_ids + (destination,)
        else:
            if destination not in stage.next_stage_ids:
                raise StudioError("branch edge does not exist")
            edges = tuple(e for e in stage.next_stage_ids if e != destination)
        stages[pos] = replace(stage, next_stage_ids=edges)
    elif operation == "quest_stage_split":
        source = _name(args, "from_stage_id")
        destination = _name(args, "to_stage_id")
        new = _name(args, "new_stage_id")
        if any(stage.stage_id == new for stage in stages):
            raise StudioError("intermediate quest stage identity already exists")
        i_source, stage = _stage(quest, source)
        _stage(quest, destination)
        if destination not in stage.next_stage_ids:
            raise StudioError("can only split an existing authored edge")
        stages[i_source] = replace(stage, next_stage_ids=tuple(
            new if edge == destination else edge for edge in stage.next_stage_ids))
        stages.insert(i_source + 1, StudioQuestStage(new, _objective(args), (destination,)))
    elif operation == "quest_stage_rename":
        old, new = _name(args, "stage_id"), _name(args, "new_stage_id")
        if any(s.stage_id == new for s in stages):
            raise StudioError("target stage name already exists")
        position, stage = _stage(quest, old)
        stages[position] = replace(stage, stage_id=new)
        stages = [replace(s, next_stage_ids=tuple(
            new if destination == old else destination
            for destination in s.next_stage_ids)) for s in stages]
        if quest.first_stage_id == old:
            quest = replace(quest, first_stage_id=new)
    elif operation == "quest_start_change":
        start = _name(args, "stage_id")
        _stage(quest, start)
        quest = replace(quest, first_stage_id=start)
    elif operation == "quest_stage_swap_objectives":
        first = _name(args, "stage_a")
        second = _name(args, "stage_b")
        ia, a = _stage(quest, first)
        ib, b = _stage(quest, second)
        if ia == ib:
            raise StudioError("swap requires two different stages")
        stages[ia], stages[ib] = (replace(a, objective=b.objective),
                                   replace(b, objective=a.objective))
    elif operation == "quest_stage_reorder":
        sid = _name(args, "stage_id")
        pos, stage = _stage(quest, sid)
        target = _integer(args, "position", 0, len(stages) - 1)
        stages.pop(pos)
        stages.insert(target, stage)
    elif operation == "quest_rewrite_objectives":
        payload = args.get("objectives")
        if (type(payload) is not dict or not payload or len(payload) > 128
                or any(type(k) is not str or type(v) is not str for k, v in payload.items())):
            raise StudioError("rewrite requires bounded id-objective object")
        existing = {s.stage_id for s in stages}
        if not set(payload) <= existing:
            raise StudioError("objective rewrite contains foreign native stages")
        stages = [replace(stage, objective=_objective(
            {"objective": payload[stage.stage_id]}))
            if stage.stage_id in payload else stage for stage in stages]
    else:
        raise StudioError("unrecognized quest graph transformation")
    changed = replace(quest, stages=tuple(stages))
    return replace(project, native_quests=_replace(
        project.native_quests, i, changed))


def _cells(project: StudioProject, args: Mapping[str, Any]):
    index, layer = _layer(project, args)
    x, y, width, height = _rectangle(layer, args)
    return index, layer, x, y, width, height


def _noise(seed: int, x: int, y: int) -> int:
    return int.from_bytes(sha256(
        f"{seed}:{x}:{y}".encode("ascii")).digest()[:8], "big")


def edit_terrain(project: StudioProject, operation: str,
                 args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or operation not in TERRAIN_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("invalid terrain authoring command")
    index, layer, left, top, width, height = _cells(project, args)
    old = layer.data
    cells = list(old)
    if operation == "terrain_noise":
        seed = _integer(args, "seed", 0, 2**63 - 1)
        tile_a = _tile(layer, args, "a")
        tile_b = _tile(layer, args, "b")
        percent = _integer(args, "percent_b", 0, 100)
        for y in range(top, top + height):
            for x in range(left, left + width):
                cells[y * layer.width + x] = (
                    tile_b if _noise(seed, x, y) % 100 < percent else tile_a)
    elif operation == "terrain_smooth":
        passes = _integer(args, "passes", 1, 8)
        for _ in range(passes):
            previous = tuple(cells)
            for y in range(top, top + height):
                for x in range(left, left + width):
                    neighborhood = [
                        previous[yy * layer.width + xx]
                        for yy in range(max(0, y - 1), min(layer.height, y + 2))
                        for xx in range(max(0, x - 1), min(layer.width, x + 2))
                    ]
                    frequency = Counter(neighborhood)
                    best = sorted(frequency, key=lambda tile: (
                        -frequency[tile], tile != previous[y * layer.width + x], tile))[0]
                    cells[y * layer.width + x] = best
    elif operation == "terrain_terrace":
        bands = _integer(args, "bands", 1, len(layer.palette))
        if bands == 1:
            levels = (0,)
        else:
            levels = tuple(round(i * (len(layer.palette) - 1) / (bands - 1))
                           for i in range(bands))
        for y in range(top, top + height):
            for x in range(left, left + width):
                pos = y * layer.width + x
                if cells[pos] != -1:
                    cells[pos] = min(levels, key=lambda v: (abs(v - cells[pos]), v))
    elif operation in ("terrain_outline", "terrain_erode"):
        target = _tile(layer, args, "target")
        replacement = _tile(layer, args, "replacement")
        for y in range(top, top + height):
            for x in range(left, left + width):
                pos = y * layer.width + x
                neighbors = [
                    old[ny * layer.width + nx]
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                    if 0 <= nx < layer.width and 0 <= ny < layer.height
                ]
                if operation == "terrain_outline":
                    if old[pos] != target and target in neighbors:
                        cells[pos] = replacement
                elif old[pos] == target and (
                        len(neighbors) < 4 or any(v != target for v in neighbors)):
                    cells[pos] = replacement
    else:
        raise StudioError("unknown procedural terrain operation")
    return _replace_layer(project, index, replace(layer, data=tuple(cells)))
