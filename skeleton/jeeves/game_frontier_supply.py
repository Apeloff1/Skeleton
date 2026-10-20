"""NPC production-chain inventory, cargo delivery and double-entry coin ledger.

All supply items are manufactured by explicit recipes from sourced finite
starting stock. Every transfer debits the sender and credits the recipient,
and replay independently reconstructs all inventory/coin effects.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Mapping
from .game_frontier_expedition import ExpeditionWorld,ExpeditionError,_digest
from .game_frontier_expedition_npcs import NPCDesign

@dataclass(frozen=True,slots=True)
class Recipe:
    name:str
    inputs:tuple[tuple[str,int],...]
    output:str
    quantity:int
    coins_cost:int=0
    def __post_init__(self):
        if not isinstance(self.name,str) or not self.name.isidentifier():
            raise ExpeditionError("production chain recipe identity invalid")
        if (not isinstance(self.output,str) or not self.output.isidentifier()
                or not self.inputs or len(self.inputs)>12
                or any(not isinstance(k,str) or not k.isidentifier() or type(n) is not int or not 1<=n<=100
                       for k,n in self.inputs)
                or len({k for k,n in self.inputs})!=len(self.inputs)):
            raise ExpeditionError("supply recipe material inputs invalid")
        if type(self.quantity) is not int or not 1<=self.quantity<=100:
            raise ExpeditionError("supply recipe produced quantity invalid")
        if type(self.coins_cost) is not int or not 0<=self.coins_cost<=1000:
            raise ExpeditionError("supply recipe manufacturing cost invalid")

class SupplyNetwork:
    def __init__(self,world:ExpeditionWorld,actors:tuple[NPCDesign,...],
                 recipes:tuple[Recipe,...],*,initial:Mapping[str,int]|None=None):
        if (not isinstance(world,ExpeditionWorld) or type(actors) is not tuple
                or not 2<=len(actors)<=64 or type(recipes) is not tuple
                or not 1<=len(recipes)<=64):
            raise ExpeditionError("NPC production network requires bounded original cast")
        if any(not isinstance(x,NPCDesign) or x.home not in world.by_id for x in actors):
            raise ExpeditionError("supply node has foreign original game location")
        if any(not isinstance(r,Recipe) for r in recipes):
            raise ExpeditionError("supply factory requires original typed recipe")
        if len({r.name for r in recipes})!=len(recipes):
            raise ExpeditionError("production chain duplicates recipe identity")
        self.world=world
        self.actors=actors
        self.recipes={r.name:r for r in recipes}
        self.stock={x.npc_id:{} for x in actors}
        self.coins={x.npc_id:200 for x in actors}
        self.treasury=0
        self.initial=dict(initial or {"ore":8,"fiber":10})
        if any(not isinstance(k,str) or not k.isidentifier() or type(v) is not int or not 0<=v<=10000
               for k,v in self.initial.items()):
            raise ExpeditionError("supply network cannot invent unbounded starting goods")
        self.stock[actors[0].npc_id]=dict(self.initial)
        self.events=[]
        self.head=_digest({"world":world.digest,"actors":[asdict(x) for x in actors],
                           "recipes":[asdict(r) for r in recipes],"initial":self.initial})
    def execute(self,kind:str,*,actor:str,target:str="",item:str="",quantity:int=1,recipe:str="",price:int=0)->dict:
        if len(self.events)>=5000 or actor not in self.stock:
            raise ExpeditionError("supply game event budget or actor invalid")
        if type(quantity) is not int or not 1<=quantity<=1000 or type(price) is not int or not 0<=price<=10000:
            raise ExpeditionError("supply trade quantity or price invalid")
        previous=self.head
        if kind=="craft":
            if recipe not in self.recipes:
                raise ExpeditionError("unknown original supply recipe")
            r=self.recipes[recipe]
            for key,amount in r.inputs:
                if self.stock[actor].get(key,0)<amount:
                    raise ExpeditionError("supply manufacturing lacks actual inputs")
            if self.coins[actor]<r.coins_cost:
                raise ExpeditionError("supply manufacturing has insufficient coins")
            for key,amount in r.inputs:
                self.stock[actor][key]-=amount
            self.stock[actor][r.output]=self.stock[actor].get(r.output,0)+r.quantity
            self.coins[actor]-=r.coins_cost
            self.treasury+=r.coins_cost
            quantity=r.quantity
            item=r.output
        elif kind=="transfer":
            if target not in self.stock or target==actor or not item or not item.isidentifier():
                raise ExpeditionError("supply transport needs valid destination and cargo")
            if self.stock[actor].get(item,0)<quantity or self.coins[target]<price:
                raise ExpeditionError("supply cannot double-spend stock or coins")
            self.stock[actor][item]-=quantity
            self.stock[target][item]=self.stock[target].get(item,0)+quantity
            self.coins[actor]+=price
            self.coins[target]-=price
        else:
            raise ExpeditionError("supply ledger only supports real craft/transfer events")
        row={"schema":"skeleton.game.original_supply_event.v1","sequence":len(self.events)+1,
             "kind":kind,"actor":actor,"target":target,"item":item,"quantity":quantity,
             "recipe":recipe,"price":price,"inventory":{k:dict(v) for k,v in self.stock.items()},
             "coins":dict(self.coins),"treasury":self.treasury,
             "prior":previous,"world":self.world.digest}
        self.head=_digest(row)
        result={**row,"receipt_digest":self.head}
        self.events.append(result)
        return result
    def snapshot(self):
        data={"schema":"skeleton.game.original_supply_network.v1",
              "world":self.world.digest,"actors":[asdict(a) for a in self.actors],
              "recipes":[asdict(r) for r in self.recipes.values()],
              "initial":self.initial,"events":list(self.events),
              "stock":{k:dict(v) for k,v in self.stock.items()},
              "coins":dict(self.coins),"treasury":self.treasury,"head":self.head}
        return {**data,"snapshot_digest":_digest(data)}
    @classmethod
    def restore(cls,world,actors,recipes,checkpoint):
        if not isinstance(checkpoint,Mapping) or checkpoint.get("schema")!="skeleton.game.original_supply_network.v1":
            raise ExpeditionError("supply checkpoint missing source")
        data=dict(checkpoint)
        if data.pop("snapshot_digest",None)!=_digest(data):
            raise ExpeditionError("supply ledger checksum invalid")
        obj=cls(world,actors,recipes,initial=checkpoint["initial"])
        if checkpoint["world"]!=world.digest or checkpoint["actors"]!=[asdict(x) for x in actors]:
            raise ExpeditionError("supply checkpoint references foreign game")
        if not isinstance(checkpoint.get("events"),list) or len(checkpoint["events"])>5000:
            raise ExpeditionError("supply replay budget exceeded")
        for e in checkpoint["events"]:
            if not isinstance(e,dict):
                raise ExpeditionError("supply event row malformed")
            checked=obj.execute(e["kind"],actor=e["actor"],target=e["target"],
                                item=e["item"],quantity=e["quantity"],
                                recipe=e["recipe"],price=e["price"])
            if checked!=e:
                raise ExpeditionError("supply event diverged after source replay")
        if obj.snapshot()!=checkpoint:
            raise ExpeditionError("supply source replay disagrees with goods/coins")
        return obj

def original_supply_network(world:ExpeditionWorld,cast:tuple[NPCDesign,...])->dict:
    recipes=(Recipe("forge_tools",(("ore",2),("fiber",1)),"tools",1,2),
             Recipe("sew_gliders",(("fiber",3),),"glider_cloth",1,1))
    network=SupplyNetwork(world,cast,recipes)
    network.execute("craft",actor=cast[0].npc_id,recipe="forge_tools")
    network.execute("craft",actor=cast[0].npc_id,recipe="sew_gliders")
    network.execute("transfer",actor=cast[0].npc_id,target=cast[1].npc_id,item="tools",price=8)
    if SupplyNetwork.restore(world,cast,recipes,network.snapshot()).snapshot()!=network.snapshot():
        raise ExpeditionError("supply source independent replay failed")
    return network.snapshot()
