"""Actually simulate a complete collision-checked studio scene playthrough.

Uses shortest navigable routes and real source-authored choices, rather than
declaring scenes 'played' from a blueprint. This is offline synthetic QA.
"""
from __future__ import annotations

from typing import Any, Mapping

from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_navigation import shortest_scene_route
from .studio_ecosystem_walk_replay import replay_walk


def simulate_complete_walk(documents: Mapping[str, Any], *,
                           choice_by_stage: Mapping[str, str] | None = None,
                           authorized: bool) -> dict[str, object]:
    if not authorized:
        raise PermissionError("walk QA replay requires authorization")
    world = playable_world_source(documents)
    override = {} if choice_by_stage is None else dict(choice_by_stage)
    stages = world["stages"]
    if set(override) - {s["id"] for s in stages}:
        raise ValueError("override references unknown authored stage")
    actions: list[tuple[str, str]] = []
    routes = []
    for index, stage in enumerate(stages):
        route = shortest_scene_route(documents, scene_index=index, authorized=True)
        routes.append({"stage": stage["id"], "moves": route["accepted_steps"],
                       "route_sha256": route["route_sha256"]})
        actions.extend(("move", direction) for direction in route["directions"])
        selected = override.get(stage["id"], stage["alternatives"][0])
        actions.append(("choose", selected))
    session = replay_walk(documents, actions, authorized=True)
    if session.scene_index != len(stages):
        raise ValueError("synthetic playthrough stopped before final stage")
    return {"schema": "skeleton.game_builder.synthetic_walk_qa.v1",
            "project_id": world["project_id"],
            "source_digest": world["source_digest"],
            "walk_session_sha256": session.digest,
            "actions": [list(x) for x in session.events],
            "chosen": [list(x) for x in session.chosen],
            "stage_routes": routes, "movement_steps": session.accepted_moves,
            "all_authored_stages_reached": True,
            "synthetic_prototype_only": True,
            "real_playtester_verified": False,
            "release_certified": False}
