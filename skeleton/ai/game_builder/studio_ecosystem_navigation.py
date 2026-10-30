"""Deterministic shortest-path navigation for source-owned 2D scenes."""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from typing import Any, Mapping

from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_walk_replay import DIRECTIONS, replay_walk
from .studio_ecosystem_quest import StudioQuestError

_NEIGHBORS = tuple(DIRECTIONS.items())


def shortest_scene_route(documents: Mapping[str, Any], *, scene_index: int,
                         start: tuple[int, int] = (1, 1),
                         authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("authored navigation needs operator authorization")
    world = playable_world_source(documents)
    if type(scene_index) is not int or not 0 <= scene_index < len(world["maps"]):
        raise StudioQuestError("unknown scene route")
    if (not isinstance(start, tuple) or len(start) != 2
            or any(type(x) is not int for x in start)):
        raise StudioQuestError("invalid grid coordinate")
    sx, sy = start
    rows = world["maps"][scene_index]
    if not (0 <= sx < world["width"] and 0 <= sy < world["height"]
            and rows[sy][sx] != "#"):
        raise StudioQuestError("navigation starts outside playable grid")
    tx, ty = world["target"]
    target_cells = {(x, y) for x, y in (
        (tx, ty), (tx - 1, ty), (tx + 1, ty), (tx, ty - 1), (tx, ty + 1)
    ) if (0 <= x < world["width"] and 0 <= y < world["height"]
           and rows[y][x] != "#")}
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
    destination = None
    while queue:
        here = queue.popleft()
        if here in target_cells:
            destination = here
            break
        for name, (dx, dy) in _NEIGHBORS:
            point = (here[0] + dx, here[1] + dy)
            x, y = point
            if (0 <= x < world["width"] and 0 <= y < world["height"]
                    and rows[y][x] != "#" and point not in previous):
                previous[point] = (here, name)
                queue.append(point)
    if destination is None:
        raise StudioQuestError("authored marker has no reachable interaction cell")
    actions: list[str] = []
    current = destination
    while previous[current] is not None:
        back, name = previous[current]
        actions.append(name)
        current = back
    actions.reverse()
    payload = {"project": world["project_id"], "source": world["source_digest"],
               "scene_index": scene_index, "start": start,
               "finish": destination, "directions": actions}
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("ascii")).hexdigest()
    return {"schema": "skeleton.game_builder.scene_shortest_route.v1",
            "project_id": world["project_id"],
            "source_digest": world["source_digest"],
            "scene_index": scene_index,
            "start": list(start), "finish": list(destination),
            "directions": actions, "accepted_steps": len(actions),
            "route_sha256": digest, "collision_checked": True,
            "physical_world_qualified": False, "release_certified": False}
