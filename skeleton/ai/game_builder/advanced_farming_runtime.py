"""Original, deterministic farming game, not an editor-only simulation.

Four bounded playable plots represent sectors of an authored farm. Crop growth
depends on daily weather, soil, moisture, pests and seasonal planning. A finite
economy connects seed purchases, harvest, livestock, market contracts and
bankruptcy. All actions are offline and replayable; no procedural frame claims.
"""
from __future__ import annotations


class FarmingActionError(ValueError):
    """An illegal farming command or exhausted finite resource."""


CROPS=("turnip","bean","sunflower")
ACTIONS=tuple(
    f"{verb}:{index}"
    for verb in ("plant","water","harvest","till","compost")
    for index in range(4)
)+("advance","advance:4","irrigate","buy_seeds","sell","feed","collect")


def default_layout(config,seed):
    count=min(4,config["field_tiles"])
    return {
        "plots":[{"id":i,"soil":2+(i+seed)%3,"moisture":1+(seed+i*2)%3}
                 for i in range(count)],
        "market_multiplier":1+seed%2,
        "starting_weather":("sun","rain","sun","drought")[seed%4],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={"plots","market_multiplier","starting_weather"}:
        raise FarmingActionError("original farm requires exactly plots, market multiplier and weather")
    plots=layout["plots"]
    if type(plots) is not list or not 1<=len(plots)<=min(4,config["field_tiles"]):
        raise FarmingActionError("original farm has one to four nonempty field sectors")
    checked=[]
    for idx,item in enumerate(plots):
        if type(item) is not dict or set(item)!={"id","soil","moisture"}:
            raise FarmingActionError("invalid authored farmland schema")
        if type(item["id"]) is not int or item["id"]!=idx:
            raise FarmingActionError("farm sector identity must be canonical")
        for key in ("soil","moisture"):
            if type(item[key]) is not int or not 0<=item[key]<=5:
                raise FarmingActionError("farm soil/water must be bounded integer values")
        checked.append(dict(item))
    m=layout["market_multiplier"]
    w=layout["starting_weather"]
    if type(m) is not int or not 1<=m<=3 or type(w) is not str or w not in ("sun","rain","drought"):
        raise FarmingActionError("authored market/weather profile invalid")
    return {"plots":checked,"market_multiplier":m,"starting_weather":w}


def start(config,seed):
    return apply_scene({
        "day":1,"season":0,"weather":"sun","plots":[],
        "coins":25,"seeds":8,"water":12,"fertilizer":2,
        "harvest_stock":0,"harvested":0,
        "livestock":2 if config["livestock"] else 0,
        "feed":6 if config["livestock"] else 0,
        "animal_health":10 if config["livestock"] else 0,
        "animal_products":0,"reputation":0,"contracts_completed":0,
        "market_multiplier":1,"seed":seed,
        "events":[],"finished":False,"failed":False,
    },config,default_layout(config,seed))


def apply_scene(state,config,layout):
    checked=normalize_layout(config,layout)
    state["plots"]=[
        {"id":item["id"],"soil":item["soil"],"moisture":item["moisture"],
         "crop":-1,"age":0,"pests":0} for item in checked["plots"]
    ]
    state["market_multiplier"]=checked["market_multiplier"]
    state["weather"]=checked["starting_weather"]
    return state


def _advance_day(state,config):
    state["day"]+=1
    events=["new_farm_day"]
    day=state["day"]
    if config["seasons"]:
        state["season"]=((day-1)//7)%4
    state["weather"]=("rain" if (day+state["seed"])%7 in (1,4)
                      else "drought" if (day+state["seed"])%7==6 else "sun")
    for plot in state["plots"]:
        if state["weather"]=="rain":
            plot["moisture"]=min(5,plot["moisture"]+2)
        else:
            plot["moisture"]=max(0,plot["moisture"]-(2 if state["weather"]=="drought" else 1))
        if plot["crop"]>=0:
            if plot["moisture"]>0 and plot["soil"]>0:
                plot["age"]+=1
                events.append("crop_grew")
            if day%11==0:
                plot["pests"]=min(3,plot["pests"]+1)
                events.append("seasonal_pests")
    if state["livestock"]>0:
        if state["feed"]>0:
            state["feed"]-=1
            if day%3==0 and state["animal_health"]>0:
                state["animal_products"]+=state["livestock"]
                events.append("livestock_produced")
        else:
            state["animal_health"]=max(0,state["animal_health"]-2)
            events.append("livestock_hungry")
    if day%7==0:
        state["coins"]=max(0,state["coins"]-2)
        events.append("market_upkeep")
    if (day>=40 and state["coins"]<3 and state["seeds"]==0
        and state["harvest_stock"]==0
        and not any(p["crop"]>=0 for p in state["plots"])):
        state["failed"]=True
        events.append("farm_bankrupt")
    return events


def step(state,config,action):
    if action not in ACTIONS:
        raise FarmingActionError("unrecognized original farming command")
    if state["finished"] or state["failed"]:
        raise FarmingActionError("farm cannot advance after terminal state")
    events=[]
    if ":" in action and action.split(":")[0] in {"plant","water","harvest","till","compost"}:
        verb,raw=action.split(":")
        idx=int(raw)
        if idx>=len(state["plots"]):
            raise FarmingActionError("unavailable farm sector")
        p=state["plots"][idx]
        if verb=="plant":
            if p["crop"]>=0 or state["seeds"]<1:
                raise FarmingActionError("occupied field or no finite seed")
            p.update(crop=idx%min(config["crop_types"],3),age=0,pests=0)
            state["seeds"]-=1
            events.append("crop_planted")
        elif verb=="water":
            if state["water"]<2 or p["moisture"]>=5:
                raise FarmingActionError("water unavailable or plot saturated")
            state["water"]-=2
            p["moisture"]=min(5,p["moisture"]+2)
            events.append("plot_watered")
        elif verb=="harvest":
            target=max(1,config["growth_days"]//(p["crop"]+2)) if p["crop"]>=0 else 0
            if p["crop"]<0 or p["age"]<target:
                raise FarmingActionError("crop has not actually matured")
            yield_count=max(1,2+p["crop"]+(1 if p["soil"]>=3 else 0)-p["pests"])
            state["harvest_stock"]+=yield_count
            state["harvested"]+=yield_count
            p.update(crop=-1,age=0,pests=0,soil=max(0,p["soil"]-1))
            events.append("mature_crop_harvested")
        elif verb=="till":
            if p["crop"]>=0 or state["coins"]<1 or p["soil"]>=5:
                raise FarmingActionError("tilling requires empty nonoptimal plot and funds")
            state["coins"]-=1
            p["soil"]+=1
            events.append("soil_cultivated")
        else:
            if state["fertilizer"]<1 or p["soil"]>=5:
                raise FarmingActionError("finite compost depleted or soil saturated")
            state["fertilizer"]-=1
            p["soil"]=min(5,p["soil"]+2)
            p["pests"]=max(0,p["pests"]-1)
            events.append("soil_composted")
    elif action in ("advance","advance:4"):
        for _ in range(4 if action=="advance:4" else 1):
            if state["finished"] or state["failed"]:
                break
            events.extend(_advance_day(state,config))
    elif action=="irrigate":
        active=[p for p in state["plots"] if p["crop"]>=0 and p["moisture"]<5]
        if not active or state["water"]<len(active):
            raise FarmingActionError("irrigation requires planted fields and finite stored water")
        for p in active:
            p["moisture"]=min(5,p["moisture"]+1)
        state["water"]-=len(active)
        events.append("field_irrigated")
    elif action=="buy_seeds":
        if state["coins"]<5:
            raise FarmingActionError("seeds require finite market funds")
        state["coins"]-=5
        state["seeds"]+=4
        events.append("seeds_purchased")
    elif action=="sell":
        if state["harvest_stock"]<1:
            raise FarmingActionError("cannot sell nonexistent harvest")
        batch=state["harvest_stock"]
        state["coins"]+=batch*(3+state["market_multiplier"]+(state["season"]==2))
        state["harvest_stock"]=0
        state["reputation"]+=1
        if batch>=3:
            state["contracts_completed"]+=1
            events.append("market_contract_fulfilled")
        events.append("genuine_harvest_sold")
    elif action=="feed":
        if state["livestock"]<1 or state["harvest_stock"]<2:
            raise FarmingActionError("feeding requires livestock and owned harvest")
        state["harvest_stock"]-=2
        state["feed"]+=4
        state["animal_health"]=min(10,state["animal_health"]+1)
        events.append("livestock_fed")
    elif action=="collect":
        if state["animal_products"]<1:
            raise FarmingActionError("no livestock products available")
        state["harvest_stock"]+=state["animal_products"]
        state["animal_products"]=0
        events.append("animal_products_collected")
    if state["coins"]>=80 and state["harvested"]>=8 and state["contracts_completed"]>=2:
        state["finished"]=True
        events.append("profitable_farm_established")
    state["events"]=events
    return events


__all__=["FarmingActionError","ACTIONS","CROPS","default_layout","normalize_layout","start","apply_scene","step"]
