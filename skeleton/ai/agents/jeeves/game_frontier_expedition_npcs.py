"""Original NPC route decisions with needs, faction, reputation and receipts.

This is a deterministic *game* AI using real authored graph movement. It
cannot secretly change the player's game physics or invent world locations.
NPCs observe positions and reputation through a finite, replayable episode.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from .game_frontier_expedition import (
    ExpeditionWorld,Traveler,ExpeditionError,find_route,_digest,
)

@dataclass(frozen=True,slots=True)
class NPCDesign:
    npc_id:str
    role:str
    faction:str
    home:str
    preferred_goal:str
    courage:float=.5
    loyalty:float=.5
    curiosity:float=.5

    def __post_init__(self):
        if not isinstance(self.npc_id,str) or not self.npc_id.isidentifier():
            raise ExpeditionError("NPC canonical identity required")
        if self.role not in {"scout","trader","guardian","archivist","courier"}:
            raise ExpeditionError("NPC role must use supported original behavior")
        if not isinstance(self.faction,str) or not self.faction.isidentifier():
            raise ExpeditionError("NPC faction id invalid")
        for item in (self.home,self.preferred_goal):
            if not isinstance(item,str) or not item.isidentifier():
                raise ExpeditionError("NPC source waypoint id invalid")
        for val in (self.courage,self.loyalty,self.curiosity):
            if type(val) not in (float,int) or not 0<=val<=1:
                raise ExpeditionError("NPC personality parameter nonfinite")


class NPCEpisode:
    def __init__(self,world:ExpeditionWorld,traveler:Traveler,design:NPCDesign):
        if not isinstance(world,ExpeditionWorld) or not isinstance(traveler,Traveler) or not isinstance(design,NPCDesign):
            raise ExpeditionError("NPC requires original typed source")
        if design.home not in world.by_id or design.preferred_goal not in world.by_id:
            raise ExpeditionError("NPC spawn/goal cannot be outside original game")
        self.world=world
        self.traveler=traveler
        self.design=design
        self.position=design.home
        self.history=[]
        self.reputation=0
        self.fatigue=0
        self.memory:set[str]={design.home}
        self.head=_digest({"world":world.digest,"design":asdict(design),
                           "traveler":_digest(sorted(traveler.permitted_modes))})

    def choose(self,*,player_at:str,player_reputation:int,
               tick:int)->dict:
        if player_at not in self.world.by_id:
            raise ExpeditionError("NPC cannot observe foreign player location")
        if type(player_reputation) is not int or not -100<=player_reputation<=100:
            raise ExpeditionError("NPC reputation outside game bound")
        if type(tick) is not int or tick!=len(self.history)+1 or tick>10000:
            raise ExpeditionError("NPC decisions require unique monotonic game ticks")
        old=self.head
        # Select intent from needs and source-bound role. All movement is
        # still subject to the actual game's pathfinding/ability gates.
        if self.position==self.design.preferred_goal:
            goal=self.design.home
        else:
            goal=self.design.preferred_goal
        decision="patrol"
        if player_at==self.position:
            decision=("assist" if player_reputation>=25 else
                      "warn" if player_reputation<-25 else "greet")
        if self.fatigue>=70 and self.world.by_id[self.position].safe_rest:
            decision="rest"
        proposed=""
        previous_position=self.position
        if decision=="rest":
            self.fatigue=max(0,self.fatigue-30)
        elif decision in {"patrol","assist"}:
            try:
                route=find_route(self.world,self.traveler,goal,start=self.position)
            except ExpeditionError as exc:
                if "no traversable route" not in str(exc):
                    raise
                decision="blocked"
            else:
                if route.edge_ids:
                    edge=self.world.by_edge[route.edge_ids[0]]
                    if edge.source!=self.position:
                        raise ExpeditionError("NPC path disconnected from original world")
                    proposed=edge.edge_id
                    self.position=edge.target
                    self.memory.add(self.position)
                    self.fatigue=min(100,self.fatigue+6)
        self.reputation=player_reputation
        record={
            "schema":"skeleton.game.npc_action.v1",
            "tick":tick,"npc":self.design.npc_id,
            "faction":self.design.faction,"role":self.design.role,
            "world":self.world.digest,"intent":decision,
            "old":previous_position,"new":self.position,
            "edge":proposed,"fatigue":self.fatigue,
            "player_at":player_at,"player_reputation":player_reputation,
            "memory":sorted(self.memory),"prior":old,
        }
        self.head=_digest(record)
        result={**record,"receipt":self.head}
        self.history.append(result)
        return result

    def snapshot(self)->dict:
        data={
            "schema":"skeleton.game.npc_simulation_v1",
            "design":asdict(self.design),
            "world":self.world.digest,
            "steps":list(self.history),"head":self.head,
            "position":self.position,"fatigue":self.fatigue,
            "memory":sorted(self.memory),"reputation":self.reputation,
        }
        return {**data,"snapshot_digest":_digest(data)}

    @classmethod
    def restore(cls,world:ExpeditionWorld,traveler:Traveler,
                design:NPCDesign,snapshot:dict)->"NPCEpisode":
        if not isinstance(snapshot,dict) or snapshot.get("schema")!="skeleton.game.npc_simulation_v1":
            raise ExpeditionError("NPC checkpoint missing canonical schema")
        prior={k:v for k,v in snapshot.items() if k!="snapshot_digest"}
        if snapshot.get("snapshot_digest")!=_digest(prior):
            raise ExpeditionError("NPC snapshot checksum mismatch")
        instance=cls(world,traveler,design)
        if (snapshot.get("world")!=world.digest
                or snapshot.get("design")!=asdict(design)
                or not isinstance(snapshot.get("steps"),list)
                or len(snapshot["steps"])>10000):
            raise ExpeditionError("NPC checkpoint belongs to another original game")
        for record in snapshot["steps"]:
            if type(record) is not dict:
                raise ExpeditionError("NPC action history malformed")
            replay=instance.choose(
                tick=record["tick"],player_at=record["player_at"],
                player_reputation=record["player_reputation"],
            )
            if replay!=record:
                raise ExpeditionError("NPC decisions diverged from original game")
        if instance.snapshot()!=snapshot:
            raise ExpeditionError("NPC replay failed continuity verification")
        return instance


def original_world_npcs(world:ExpeditionWorld)->tuple[NPCDesign,...]:
    if not isinstance(world,ExpeditionWorld) or len(world.waypoints)<3:
        raise ExpeditionError("NPC population requires original connected locations")
    node=world.waypoints[1].waypoint_id
    return (
        NPCDesign("sky_scout","scout","free_mariners",world.arrival,node,.8,.6,.9),
        NPCDesign("island_courier","courier","cloud_post",node,world.arrival,.6,.8,.7),
        NPCDesign("wind_archivist","archivist","sky_archive",world.destinations[0],
                  world.arrival,.3,.9,.7),
    )
