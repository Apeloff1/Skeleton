"""Inventory, crafting, equipment, trading and economies: capabilities 031–040.

All actions return updated state; no implicit side effects or negative-stock
bugs. Resources are integers so repeated transactions cannot mint value via
floating point drift.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
import random

@dataclass(frozen=True)
class Item:
    key: str
    category: str
    value: int
    weight: int = 1
    stack: int = 99
    power: int = 0

@dataclass(frozen=True)
class Inventory:
    stacks: tuple[tuple[str,int],...] = ()
    capacity: int = 40
    max_weight: int = 100
    coins: int = 0

@dataclass(frozen=True)
class Recipe:
    output: str
    quantity: int
    materials: tuple[tuple[str,int],...]
    station: str = "hand"

@dataclass(frozen=True)
class TradingPost:
    stock: tuple[tuple[str,int],...]
    markup_percent: int = 125

def _stock(inventory: Inventory) -> dict[str,int]:
    return dict(inventory.stacks)

def _pack(items:dict[str,int],inv:Inventory, *, coins:int|None=None)->Inventory:
    return replace(inv,stacks=tuple(sorted((key,n) for key,n in items.items() if n>0)),
                   coins=inv.coins if coins is None else coins)

# 031 Construct bounded, meaningful resource and equipment definitions.
def define_game_item(key:str, *, category:str,value:int,
                     weight:int=1,stack:int=99,power:int=0)->Item:
    if not isinstance(key,str) or not 1<=len(key)<=100 or category not in (
        "material","consumable","weapon","armor","quest","currency"
    ) or not 0<=value<=1_000_000 or not 0<=weight<=10000 or not 1<=stack<=99999:
        raise ValueError("invalid item")
    return Item(key,category,value,weight,stack,power)

# 032 Add physically affordable items with stack/weight/capacity enforcement.
def inventory_add(inv:Inventory,item:Item,quantity:int, *,
                  catalog:dict[str,Item])->Inventory:
    if item.key not in catalog or not 1<=quantity<=100000:
        raise ValueError("unknown or invalid incoming item")
    stocks=_stock(inv);updated=stocks.get(item.key,0)+quantity
    if updated>item.stack:raise ValueError("stack limit exceeded")
    stocks[item.key]=updated
    if len(stocks)>inv.capacity:raise ValueError("inventory slots full")
    if sum(catalog[name].weight*count for name,count in stocks.items())>inv.max_weight:
        raise ValueError("inventory overweight")
    return _pack(stocks,inv)

# 033 Remove exact quantities without creating negative stacks.
def inventory_remove(inv:Inventory,key:str,quantity:int)->Inventory:
    if not 1<=quantity<=100000:raise ValueError("invalid item quantity")
    stocks=_stock(inv)
    if stocks.get(key,0)<quantity:raise ValueError("insufficient stock")
    stocks[key]-=quantity
    return _pack(stocks,inv)

# 034 Transfer items between entities atomically, never duplicating them.
def trade_inventory_item(a:Inventory,b:Inventory,item:Item,quantity:int, *,
                         catalog:dict[str,Item])->tuple[Inventory,Inventory]:
    after_a=inventory_remove(a,item.key,quantity)
    after_b=inventory_add(b,item,quantity,catalog=catalog)
    return after_a,after_b

# 035 Craft recipe output if station and each ingredient is available.
def craft_item(inv:Inventory,recipe:Recipe, *, station:str,
               catalog:dict[str,Item],times:int=1)->Inventory:
    if station!=recipe.station or not 1<=times<=1000:
        raise ValueError("crafting station or batch invalid")
    if not recipe.materials or recipe.output not in catalog:
        raise ValueError("recipe not executable")
    state=inv
    for key,amount in recipe.materials:
        if not 1<=amount<=10000:raise ValueError("invalid recipe quantity")
        state=inventory_remove(state,key,amount*times)
    return inventory_add(state,catalog[recipe.output],recipe.quantity*times,catalog=catalog)

# 036 Equip items into player slots by category and compute resulting power.
def equip_character(equipment:dict[str,str],slot:str,item:Item,
                    *, catalog:dict[str,Item])->tuple[tuple[str,str],...]:
    correct={"main_hand":"weapon","body":"armor","quick":"consumable"}
    if slot not in correct or item.category!=correct[slot] or item.key not in catalog:
        raise ValueError("item cannot be equipped")
    state={**equipment,slot:item.key}
    return tuple(sorted(state.items()))

# 037 Consume a potion or consumable, mutating inventory only after validation.
def use_consumable(inv:Inventory,item:Item, *,
                   health:int,maximum_health:int)->tuple[Inventory,int]:
    if item.category!="consumable" or not 0<=health<=maximum_health:
        raise ValueError("invalid consumable use")
    after=inventory_remove(inv,item.key,1)
    return after,min(maximum_health,health+max(0,item.power))

# 038 Price vendor goods with finite markup and stock constraints.
def merchant_purchase(inv:Inventory,merchant:TradingPost,
                      item:Item, *, quantity:int,
                      catalog:dict[str,Item])->tuple[Inventory,TradingPost]:
    if not 1<=quantity<=10000 or not 100<=merchant.markup_percent<=1000:
        raise ValueError("invalid merchant transaction")
    available=dict(merchant.stock)
    if available.get(item.key,0)<quantity:raise ValueError("merchant out of stock")
    unit=(item.value*merchant.markup_percent+99)//100
    price=unit*quantity
    if inv.coins<price:raise ValueError("insufficient currency")
    bought=inventory_add(inv,item,quantity,catalog=catalog)
    available[item.key]-=quantity
    return replace(bought,coins=inv.coins-price),replace(
        merchant,stock=tuple(sorted((k,v) for k,v in available.items() if v>0))
    )

# 039 Tune loot rarity without generating items not in the supplied catalog.
def roll_loot_table(entries:tuple[tuple[str,int],...], *,
                    seed:int,rolls:int=1)->tuple[str,...]:
    if not 1<=len(entries)<=1000 or not 1<=rolls<=10000:
        raise ValueError("invalid loot table")
    if any(not name or not 1<=weight<=100000 for name,weight in entries):
        raise ValueError("invalid loot weight")
    rng=random.Random(seed);names=[x[0] for x in entries];weights=[x[1] for x in entries]
    return tuple(rng.choices(names,weights=weights,k=rolls))

# 040 Simulate supply/sinks in a closed currency economy over a time step.
def simulate_game_economy(coins:int, *, earned:int,spent:int,
                          tax_percent:int=0,cap:int=2**31-1)->tuple[int,int]:
    if min(coins,earned,spent)<0 or not 0<=tax_percent<=100 or cap<=0:
        raise ValueError("invalid economy transaction")
    tax=spent*tax_percent//100
    if spent>coins+earned:raise ValueError("currency overspend")
    balance=coins+earned-spent-tax
    if balance<0:raise ValueError("tax exceeds available currency")
    return min(cap,balance),tax
