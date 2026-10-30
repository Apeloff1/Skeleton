"""Deterministic short-patrol NPCs backed by original cast documents.

Produces actual world coordinates, on-map patrol actions and local knowledge
for a 2D source-authored prototype. These do not claim full sentient agent AI,
voice synthesis, independently validated dialogue or native genre behavior.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walkable import playable_world_source


def cast_patrols(documents: Mapping[str, Any]) -> dict[str,object]:
    world=playable_world_source(documents)
    cast=documents.get("cast")
    if (not isinstance(cast,dict) or cast.get("project_id")!=world["project_id"]
            or cast.get("release_certified") is not False):
        raise StudioQuestError("cast identity and release boundary required")
    support=cast.get("support")
    if not isinstance(support,list) or not support:
        raise StudioQuestError("missing original NPC cast")
    unique=set()
    actors=[]
    rows=world["maps"][0]
    reachable={tuple(world["spawn"])}
    queue=deque(reachable)
    while queue:
        x,y=queue.popleft()
        for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if (0<=nx<world["width"] and 0<=ny<world["height"] and
                    rows[ny][nx]=="." and (nx,ny) not in reachable):
                reachable.add((nx,ny));queue.append((nx,ny))
    tx,ty=world["target"]
    spawn=tuple(world["spawn"])
    candidates=sorted((x,y) for x,y in reachable
                      if (x,y)!=spawn and abs(x-tx)+abs(y-ty)>1)
    if len(candidates)<2:
        raise StudioQuestError("insufficient reachable NPC patrol surface")
    for actor in support:
        if not isinstance(actor,dict):
            raise StudioQuestError("invalid NPC cast entry")
        aid=actor.get("id")
        name=actor.get("name")
        knows=actor.get("knows")
        if (not isinstance(aid,str) or not aid or aid in unique
                or not isinstance(name,str) or not name
                or not isinstance(knows,str) or not knows
                or max(len(aid),len(name),len(knows))>1024):
            raise StudioQuestError("unqualified original NPC identity or knowledge")
        unique.add(aid)
        seed=sha256((world["source_digest"]+aid).encode("utf-8")).digest()
        start=candidates[int.from_bytes(seed[:4],"big")%len(candidates)]
        adjacent=sorted((nx,ny) for nx,ny in (
            (start[0]+1,start[1]),(start[0]-1,start[1]),
            (start[0],start[1]+1),(start[0],start[1]-1)
        ) if (nx,ny) in reachable)
        if not adjacent:
            raise StudioQuestError("NPC patrol cannot move between legal cells")
        end=adjacent[int.from_bytes(seed[4:8],"big")%len(adjacent)]
        actors.append({"id":aid,"name":name,"knows":knows,
                       "patrol":[list(start),list(end)]})
    return {"schema":"skeleton.game_builder.source_npc_patrol.v1",
            "project_id":world["project_id"],
            "source_digest":world["source_digest"],
            "actors":actors,"deterministic_local_patrol":True,
            "autonomous_agent_verified":False,
            "release_certified":False}


def inspect_npc_contact(documents: Mapping[str, Any], *,
                        npc_id: str, player_position: tuple[int,int],
                        accepted_moves: int, authorized: bool) -> dict[str,object]:
    if not authorized:
        raise PermissionError("NPC contact requires operator authorization")
    if (not isinstance(player_position,tuple) or len(player_position)!=2
            or any(type(c) is not int for c in player_position)
            or type(accepted_moves) is not int or accepted_moves<0):
        raise StudioQuestError("invalid NPC position/movement clock")
    actors=cast_patrols(documents)
    actor=next((x for x in actors["actors"] if x["id"]==npc_id),None)
    if actor is None:
        raise StudioQuestError("unregistered NPC")
    position=actor["patrol"][accepted_moves%2]
    if (abs(player_position[0]-position[0])+
            abs(player_position[1]-position[1])>1):
        raise StudioQuestError("NPC is not within conversation proximity")
    return {"schema":"skeleton.game_builder.local_npc_contact.v1",
            "project_id":actors["project_id"],"npc_id":npc_id,
            "patrol_position":position,"authored_knowledge":actor["knows"],
            "local_contact_available":True,"real_dialogue_performed":False,
            "release_certified":False}
