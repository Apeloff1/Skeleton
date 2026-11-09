"""Original game NPC society: markets, shifts, faction standing and event replay.

This is a finite deterministic game economy: integer goods and coins never
materialize without a source-defined production/transfer event, and social
reactions depend on recorded player conduct. No external market claims.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Mapping
from .game_frontier_expedition import ExpeditionWorld,ExpeditionError,_digest
from .game_frontier_expedition_npcs import NPCDesign

@dataclass(frozen=True,slots=True)
class SocietyPolicy:
    ticks_per_day:int=24
    max_days:int=60
    units_per_craft:int=2
    cost_per_unit:int=3
    def __post_init__(self):
        for v,a,b in ((self.ticks_per_day,4,48),(self.max_days,1,365),
                      (self.units_per_craft,1,16),(self.cost_per_unit,1,500)):
            if type(v) is not int or not a<=v<=b:
                raise ExpeditionError("original NPC society economy budget invalid")

@dataclass(frozen=True,slots=True)
class SocialActor:
    npc_id:str
    faction:str
    workplace:str
    goods:str
    coins:int=40
    standing:int=0
    def __post_init__(self):
        for v in (self.npc_id,self.faction,self.workplace,self.goods):
            if not isinstance(v,str) or not v.isidentifier():
                raise ExpeditionError("society actor identity invalid")
        if type(self.coins) is not int or not 0<=self.coins<=100000:
            raise ExpeditionError("society starting coins invalid")
        if type(self.standing) is not int or not -100<=self.standing<=100:
            raise ExpeditionError("society reputation invalid")

class Society:
    def __init__(self,world:ExpeditionWorld,actors:tuple[SocialActor,...],
                 policy:SocietyPolicy=SocietyPolicy()):
        if (not isinstance(world,ExpeditionWorld) or type(actors) is not tuple
                or not 2<=len(actors)<=128 or not isinstance(policy,SocietyPolicy)):
            raise ExpeditionError("NPC society requires original world and bounded cast")
        if any(not isinstance(a,SocialActor) or a.workplace not in world.by_id for a in actors):
            raise ExpeditionError("society actor workplace does not exist")
        if len({a.npc_id for a in actors})!=len(actors):
            raise ExpeditionError("society duplicate actor")
        self.world=world
        self.actors=actors
        self.policy=policy
        self.goods={a.npc_id:0 for a in actors}
        self.coins={a.npc_id:a.coins for a in actors}
        self.standing={a.npc_id:a.standing for a in actors}
        self.shift={a.npc_id:"rest" for a in actors}
        self.events=[]
        self.head=_digest({"world":world.digest,"cast":[asdict(a) for a in actors],
                           "policy":asdict(policy)})

    def tick(self,clock:int,*,actor_id:str,kind:str,target:str="",
             conduct:int=0)->dict:
        if type(clock) is not int or clock!=len(self.events)+1 or clock>self.policy.ticks_per_day*self.policy.max_days*len(self.actors):
            raise ExpeditionError("society event clock out of canonical order")
        if actor_id not in self.goods or target and target not in self.goods:
            raise ExpeditionError("society event references unknown original actor")
        if kind not in {"work","rest","trade","praise","insult"}:
            raise ExpeditionError("unsupported original society event")
        if type(conduct) is not int or not -20<=conduct<=20:
            raise ExpeditionError("society conduct observation invalid")
        hour=(8+(clock-1)//len(self.actors))%self.policy.ticks_per_day
        actor=next(a for a in self.actors if a.npc_id==actor_id)
        prior=self.head
        produced=0
        transfer=0
        if kind=="work":
            if hour<6 or hour>=20:
                raise ExpeditionError("NPC shift disallows night work")
            produced=self.policy.units_per_craft
            self.goods[actor_id]+=produced
            self.shift[actor_id]="work"
        elif kind=="rest":
            self.shift[actor_id]="rest"
        elif kind=="trade":
            if not target or target==actor_id:
                raise ExpeditionError("NPC trade needs other original actor")
            price=self.policy.cost_per_unit
            if self.goods[actor_id]<1 or self.coins[target]<price:
                raise ExpeditionError("NPC trade cannot create goods or coins")
            self.goods[actor_id]-=1
            self.goods[target]+=1
            self.coins[actor_id]+=price
            self.coins[target]-=price
            transfer=1
        else:
            if conduct==0:
                raise ExpeditionError("NPC social action requires observed conduct")
            if kind=="praise" and conduct<0 or kind=="insult" and conduct>0:
                raise ExpeditionError("NPC reputation event contradicted by conduct")
            self.standing[actor_id]=max(-100,min(100,self.standing[actor_id]+conduct))
            # Faction peers change standing by half (toward zero), bounded.
            for peer in self.actors:
                if peer.npc_id!=actor_id and peer.faction==actor.faction:
                    delta=int(conduct/2)
                    self.standing[peer.npc_id]=max(-100,min(100,self.standing[peer.npc_id]+delta))
        row={"tick":clock,"hour":hour,"actor":actor_id,"kind":kind,
             "target":target,"conduct":conduct,"produced":produced,
             "transferred":transfer,
             "goods":dict(self.goods),"coins":dict(self.coins),
             "reputation":dict(self.standing),"shifts":dict(self.shift),
             "prior":prior,"world":self.world.digest}
        self.head=_digest(row)
        result={**row,"receipt":self.head}
        self.events.append(result)
        return result

    def snapshot(self):
        data={"schema":"skeleton.game.original_society.v1",
              "world":self.world.digest,"actors":[asdict(a) for a in self.actors],
              "policy":asdict(self.policy),"events":list(self.events),
              "goods":dict(self.goods),"coins":dict(self.coins),
              "standing":dict(self.standing),"shifts":dict(self.shift),
              "head":self.head}
        return {**data,"snapshot_digest":_digest(data)}

    @classmethod
    def restore(cls,world:ExpeditionWorld,actors:tuple[SocialActor,...],
                checkpoint:Mapping,policy:SocietyPolicy=SocietyPolicy()):
        if not isinstance(checkpoint,Mapping) or checkpoint.get("schema")!="skeleton.game.original_society.v1":
            raise ExpeditionError("NPC society restore checkpoint incomplete")
        data=dict(checkpoint)
        digest=data.pop("snapshot_digest",None)
        if digest!=_digest(data):
            raise ExpeditionError("NPC economy ledger checksum changed")
        session=cls(world,actors,policy)
        if checkpoint.get("world")!=world.digest or checkpoint.get("actors")!=[asdict(a) for a in actors]:
            raise ExpeditionError("NPC social source has changed")
        records=checkpoint.get("events")
        if not isinstance(records,list) or len(records)>100000:
            raise ExpeditionError("NPC economy replay budget invalid")
        for item in records:
            if not isinstance(item,dict):
                raise ExpeditionError("NPC social event invalid")
            actual=session.tick(item["tick"],actor_id=item["actor"],
                                kind=item["kind"],target=item["target"],
                                conduct=item["conduct"])
            if actual!=item:
                raise ExpeditionError("NPC society independent replay diverged")
        if session.snapshot()!=checkpoint:
            raise ExpeditionError("NPC society final state disagreed with source history")
        return session

def original_society(world:ExpeditionWorld,designs:tuple[NPCDesign,...])->Society:
    if not isinstance(world,ExpeditionWorld):
        raise ExpeditionError("society world missing")
    actors=tuple(SocialActor(
        npc.npc_id,npc.faction,npc.home,
        {"scout":"maps","courier":"letters","archivist":"chronicles",
         "trader":"goods","guardian":"tools"}[npc.role],
    ) for npc in designs)
    return Society(world,actors)

def simulate_original_society(world:ExpeditionWorld,designs:tuple[NPCDesign,...])->dict:
    sim=original_society(world,designs)
    for tick,(actor,event) in enumerate((
        (designs[0].npc_id,"rest"),
        (designs[1].npc_id,"rest"),
        (designs[2].npc_id,"rest"),
        (designs[0].npc_id,"praise"),
        (designs[1].npc_id,"rest"),
        (designs[2].npc_id,"rest"),
        (designs[0].npc_id,"work"),
        (designs[1].npc_id,"work"),
        (designs[2].npc_id,"work"),
        (designs[0].npc_id,"trade"),
    ),1):
        sim.tick(tick,actor_id=actor,kind=event,
                 target=designs[1].npc_id if event=="trade" else "",
                 conduct=12 if event=="praise" else 0)
    check=Society.restore(world,sim.actors,sim.snapshot())
    if check.snapshot()!=sim.snapshot():
        raise ExpeditionError("NPC economic production independently irreproducible")
    return sim.snapshot()
