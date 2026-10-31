"""Deterministic source-bounded local 2D encounter/hazard simulation.

Hazards occupy ordinary navigable cells away from guaranteed authored quest
route. Traps cause actual simulated health loss when walked into, without
pretending to implement every original game's combat or physics systems.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .studio_ecosystem_walkable import playable_world_source
from .studio_ecosystem_navigation import shortest_scene_route
from .studio_ecosystem_walk_replay import DIRECTIONS
from .studio_ecosystem_quest import StudioQuestError


def authored_hazards(documents: Mapping[str, Any]) -> dict[str, object]:
    world=playable_world_source(documents)
    intent=documents.get("intent")
    if not isinstance(intent,dict) or intent.get("project_id")!=world["project_id"]:
        raise StudioQuestError("encounter intent/source mismatch")
    count=intent.get("hazards_per_level")
    health=intent.get("starting_health")
    if (type(count) is not int or count<0 or
            type(health) is not int or health<1):
        raise StudioQuestError("invalid authored hazard budget or health")
    arranged=[]
    for scene,rows in enumerate(world["maps"]):
        route=shortest_scene_route(documents,scene_index=scene,authorized=True)
        safe={tuple(world["spawn"]),tuple(world["target"])}
        x,y=world["spawn"]
        safe.add((x,y))
        for command in route["directions"]:
            dx,dy=DIRECTIONS[command]
            x+=dx;y+=dy;safe.add((x,y))
        reachable={tuple(world["spawn"])}
        queue=deque(reachable)
        while queue:
            px,py=queue.popleft()
            for nx,ny in ((px+1,py),(px-1,py),(px,py+1),(px,py-1)):
                if (0<=nx<world["width"] and 0<=ny<world["height"] and
                        rows[ny][nx]=="." and (nx,ny) not in reachable):
                    reachable.add((nx,ny))
                    queue.append((nx,ny))
        choices=[]
        for y,row in enumerate(rows):
            for x,value in enumerate(row):
                if value=="." and (x,y) in reachable and (x,y) not in safe:
                    token=sha256((world["source_digest"]+":"+str(scene)+
                                  ":"+str(x)+":"+str(y)).encode("ascii")).digest()
                    choices.append((token,x,y))
        choices.sort()
        hazards=[(x,y) for _,x,y in choices[:min(count,len(choices))]]
        arranged.append([list(coord) for coord in hazards])
    return {"schema":"skeleton.game_builder.offline_encounters.v1",
            "project_id":world["project_id"],"source_digest":world["source_digest"],
            "starting_health":health,"hazards_by_stage":arranged,
            "hazard_damage":1,"hazards_externally_observed":False,
            "native_combat_implemented":False,"release_certified":False}


def replay_hazard_health(documents: Mapping[str, Any],
                         events: Sequence[tuple[str,str]], *,
                         authorized: bool) -> dict[str,object]:
    if not authorized:
        raise PermissionError("hazard replay requires operator authorization")
    from .studio_ecosystem_walk_replay import replay_walk
    session=replay_walk(documents,events,authorized=True)
    world=playable_world_source(documents)
    hazards=authored_hazards(documents)
    health=hazards["starting_health"]
    x,y=world["spawn"]
    scene=0
    hit_events=[]
    for index,event in enumerate(events):
        if health<=0:
            raise StudioQuestError("player cannot act after defeat")
        if len(event)!=2:
            raise StudioQuestError("invalid encounter event")
        kind,value=event
        if kind=="move":
            dx,dy=DIRECTIONS.get(value,(0,0))
            x+=dx;y+=dy
            if [x,y] in hazards["hazards_by_stage"][scene]:
                health-=hazards["hazard_damage"]
                hit_events.append({"event":index,"scene_index":scene,"position":[x,y]})
                health=max(0,health)
        elif kind=="choose":
            scene+=1
            x,y=world["spawn"]
    return {"schema":"skeleton.game_builder.offline_hazard_replay.v1",
            "project_id":session.project_id,"walk_session_sha256":session.digest,
            "remaining_health":health,"hazard_contacts":hit_events,
            "character_defeated":health==0,
            "local_physics_checked":True,"native_combat_qualified":False,
            "release_certified":False}
