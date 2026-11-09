"""A deterministic, player-controlled original factory game with finite supplies.

Real manufacturing: ore -> plates -> components -> packed goods, energy
budget, configurable throughput, discrete player construction, pollution,
maintenance, mine depletion, contracts and bankruptcy. All integers.
"""
from __future__ import annotations


class FactoryActionError(ValueError):
    """Invalid action, impossible transition or resource overdraft."""


ROLES=("smelter","assembler","packer","generator")
SLOTS=4
ACTIONS=tuple(
    f"{verb}:{index}" for verb in ("build","upgrade","toggle","repair","sell")
    for index in range(SLOTS)
)+("mine","generate","buy_coal","tick","tick:4","ship",
  "scrub","priority:speed","priority:efficiency")


def default_layout(config,seed):
    count=min(SLOTS,config["machines"])
    return {
        "stations":[{"id":i,"role":ROLES[i]} for i in range(count)],
        "ore_deposit":24+seed%7,
        "coal_deposit":12+seed%5,
        "contract_target":8+(seed%3)*2,
        "market_price":3+seed%2,
    }


def normalize_layout(config,layout):
    keys={"stations","ore_deposit","coal_deposit","contract_target","market_price"}
    if type(layout) is not dict or set(layout)!=keys:
        raise FactoryActionError("authored factory needs stations, deposits, target and market")
    stations=layout["stations"]
    if type(stations) is not list or not 1<=len(stations)<=min(SLOTS,config["machines"]):
        raise FactoryActionError("factory needs one to four bounded machine slots")
    checked=[]
    for i,station in enumerate(stations):
        if type(station) is not dict or set(station)!={"id","role"}:
            raise FactoryActionError("invalid station fields")
        if type(station["id"]) is not int or station["id"]!=i:
            raise FactoryActionError("machine IDs must be sequential")
        if type(station["role"]) is not str or station["role"] not in ROLES:
            raise FactoryActionError("unsupported factory machine recipe")
        checked.append({"id":i,"role":station["role"]})
    if len({s["role"] for s in checked})!=len(checked):
        raise FactoryActionError("unique station roles prevent duplicate source loops")
    amounts=(("ore_deposit",1,100000),("coal_deposit",0,100000),
             ("contract_target",2,80),("market_price",1,10))
    for field,low,high in amounts:
        value=layout[field]
        if type(value) is not int or not low<=value<=high:
            raise FactoryActionError("invalid bounded factory "+field)
    return {**{k:layout[k] for k in ("ore_deposit","coal_deposit",
                                   "contract_target","market_price")},
            "stations":checked}


def start(config,seed):
    return apply_scene({
        "tick":0,"day":1,"ore":10,"coal":6,"plates":0,"components":0,
        "boxes":0,"shipped":0,"credits":90,"power":config["power_supply"],
        "power_cap":config["power_supply"],"pollution":0,
        "ore_deposit":0,"coal_deposit":0,"market_price":0,
        "contract_target":0,"contracts":0,"mode":"efficiency",
        "stations":[],"machines":[],"blocked_cycles":0,"maintenance":0,
        "events":[],"seed":seed,"finished":False,"failed":False,
    },config,default_layout(config,seed))


def apply_scene(state,config,layout):
    approved=normalize_layout(config,layout)
    state["stations"]=[dict(s) for s in approved["stations"]]
    state["ore_deposit"]=approved["ore_deposit"]
    state["coal_deposit"]=approved["coal_deposit"]
    state["contract_target"]=approved["contract_target"]
    state["market_price"]=approved["market_price"]
    return state


def _find(state,slot):
    return next((m for m in state["machines"] if m["id"]==slot),None)


def _tick(state,config):
    state["tick"]+=1
    if state["tick"]%5==0:
        state["day"]+=1
    events=["factory_tick"]
    for station in state["stations"]:
        m=_find(state,station["id"])
        if m is None or not m["enabled"] or m["health"]<=0:
            continue
        role=m["role"]
        cycle=min(config["belt_speed"],m["level"]+
                  (1 if state["mode"]=="speed" else 0))
        power_needed=cycle*(2 if role=="assembler" else 1)
        if role=="generator":
            if state["coal"]>=1 and state["power"]<state["power_cap"]:
                state["coal"]-=1
                state["power"]=min(state["power_cap"],state["power"]+cycle*6)
                events.append("local_grid_generated")
            else:
                state["blocked_cycles"]+=1
                events.append("machine_stalled")
            continue
        ingredient=("ore" if role=="smelter" else
                    "plates" if role=="assembler" else "components")
        cost=(2 if role in ("smelter","assembler") else 1)
        produced=min(cycle,state[ingredient]//cost,
                     state["power"]//(2 if role=="assembler" else 1))
        if produced<=0:
            state["blocked_cycles"]+=1
            events.append("machine_stalled")
            continue
        state[ingredient]-=produced*cost
        output=("plates" if role=="smelter" else
                "components" if role=="assembler" else "boxes")
        state[output]+=produced
        state["power"]-=produced*(2 if role=="assembler" else 1)
        if config["pollution"]:
            state["pollution"]+=produced*(2 if state["mode"]=="speed" else 1)
        if state["tick"]%4==0:
            m["health"]=max(0,m["health"]-1)
            events.append("wear_accumulated")
        events.append("machine_produced")
    if config["pollution"] and state["pollution"]>=70:
        state["failed"]=True
        events.append("pollution_shutdown")
    if (state["tick"]>=50 and state["credits"]<5 and state["ore"]==0
        and state["ore_deposit"]==0 and state["boxes"]==0):
        state["failed"]=True
        events.append("factory_bankrupt")
    return events


def step(state,config,action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise FactoryActionError("invalid or terminal factory order")
    events=[]
    if ":" in action and action.split(":")[0] in ("build","upgrade","toggle","repair","sell"):
        verb,raw=action.split(":")
        index=int(raw)
        if index>=len(state["stations"]):
            raise FactoryActionError("unavailable authored machine slot")
        machine=_find(state,index)
        if verb=="build":
            if machine is not None or state["credits"]<15:
                raise FactoryActionError("construction requires vacant slot and funds")
            state["credits"]-=15
            state["machines"].append({"id":index,"role":state["stations"][index]["role"],
                                       "level":1,"health":10,"enabled":True})
            state["machines"].sort(key=lambda m:m["id"])
            events.append("machine_constructed")
        elif verb=="upgrade":
            if machine is None or machine["level"]>=3 or state["credits"]<12*machine["level"]:
                raise FactoryActionError("upgrade requires machine, funds and level budget")
            state["credits"]-=12*machine["level"]
            machine["level"]+=1
            events.append("machine_upgraded")
        elif verb=="toggle":
            if machine is None:
                raise FactoryActionError("cannot toggle nonexistent machine")
            machine["enabled"]=not machine["enabled"]
            events.append("machine_switched")
        elif verb=="repair":
            if machine is None or machine["health"]>=10 or state["credits"]<5:
                raise FactoryActionError("repair requires damage and funds")
            state["credits"]-=5
            machine["health"]=min(10,machine["health"]+4)
            state["maintenance"]+=1
            events.append("machine_repaired")
        else:
            if machine is None:
                raise FactoryActionError("cannot liquidate nonexistent machine")
            state["credits"]+=7*machine["level"]
            state["machines"].remove(machine)
            events.append("machine_liquidated")
    elif action=="mine":
        if state["ore_deposit"]<1:
            raise FactoryActionError("no remaining ore in finite deposit")
        mined=min(config["belt_speed"],state["ore_deposit"])
        state["ore_deposit"]-=mined
        state["ore"]+=mined
        events.append("finite_ore_mined")
    elif action=="generate":
        if state["coal"]<1 or state["power"]>=state["power_cap"]:
            raise FactoryActionError("power generation requires coal and storage")
        state["coal"]-=1
        state["power"]=min(state["power_cap"],state["power"]+8)
        events.append("fuel_power_generated")
    elif action=="buy_coal":
        if state["credits"]<6 or state["coal_deposit"]<2:
            raise FactoryActionError("cannot acquire unavailable finite coal")
        state["credits"]-=6
        state["coal_deposit"]-=2
        state["coal"]+=2
        events.append("finite_coal_bought")
    elif action in ("tick","tick:4"):
        for _ in range(4 if action=="tick:4" else 1):
            if state["finished"] or state["failed"]:
                break
            events.extend(_tick(state,config))
    elif action=="ship":
        if state["boxes"]<2:
            raise FactoryActionError("shipping requires at least two finished products")
        shipped=min(state["boxes"],8)
        state["boxes"]-=shipped
        state["shipped"]+=shipped
        state["credits"]+=shipped*state["market_price"]
        state["contracts"]+=1
        events.append("manufacturing_contract_shipped")
    elif action=="scrub":
        if state["pollution"]<=0 or state["credits"]<5:
            raise FactoryActionError("scrubbing costs funds and requires polluted equipment")
        state["credits"]-=5
        state["pollution"]=max(0,state["pollution"]-15)
        events.append("pollution_scrubbed")
    elif action in ("priority:speed","priority:efficiency"):
        state["mode"]=action.split(":")[1]
        events.append("production_priority_changed")
    else:
        raise FactoryActionError("unregistered original factory control")
    if state["shipped"]>=state["contract_target"] and state["contracts"]>=2:
        state["finished"]=True
        events.append("sustainable_factory_operating")
    state["events"]=events
    return events


__all__=["FactoryActionError","ROLES","ACTIONS","default_layout",
         "normalize_layout","start","apply_scene","step"]
