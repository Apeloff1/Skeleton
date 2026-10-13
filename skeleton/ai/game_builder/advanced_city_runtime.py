"""Original advanced city-builder game: spatial utilities, zoning, traffic and civic solvency.

All rules operate on an authored 4x4 parcel map with deterministic road-graph
connectivity. Each action has a real cost and changes persistent civic state.
Original local power and finite aquifer water are independent of Python UI.
"""
from __future__ import annotations

from collections import deque

WIDTH = 4
PARCELS = WIDTH * WIDTH
TERRAINS = ("plain", "forest", "hill", "wetland", "water")
BUILDINGS = ("road", "bridge", "residential", "commercial", "industry", "park",
             "power", "waterworks", "firehouse", "clinic", "school")
DEVELOPED = tuple(t for t in BUILDINGS if t not in ("road", "bridge"))
COSTS = {
    "road": (5, 1, 2), "bridge": (15, 5, 8),
    "residential": (12, 4, 3), "commercial": (16, 4, 5),
    "industry": (18, 6, 5), "park": (8, 2, 1),
    "power": (32, 8, 9), "waterworks": (26, 6, 7),
    "firehouse": (19, 4, 5), "clinic": (21, 5, 5),
    "school": (23, 4, 6),
}
ACTIONS = (tuple(
    f"build:{name}:{i}" for name in BUILDINGS for i in range(PARCELS))
    + tuple(f"{command}:{i}" for command in ("upgrade","demolish","log","quarry")
            for i in range(PARCELS))
    + ("tick","tick:4","tax:low","tax:normal","tax:high",
       "policy:transit","policy:industrial","policy:ecology",
       "bond","pay_debt","import_materials")
)


class CityActionError(ValueError):
    """Invalid, out-of-budget or physically impossible urban development."""


def _integer(value, minimum, maximum, key):
    if type(value) is not int or not minimum <= value <= maximum:
        raise CityActionError("invalid bounded city " + key)
    return value


def neighbors(index):
    x, y = index % WIDTH, index // WIDTH
    return tuple(j for j in
                 (index - WIDTH, index - 1, index + 1, index + WIDTH)
                 if 0 <= j < PARCELS
                 and abs(j % WIDTH - x) + abs(j // WIDTH - y) == 1)


def default_layout(config, seed):
    terrain = ["plain"] * PARCELS
    # Two original terrain reserves exist without importing game maps.
    terrain[5] = "forest"
    terrain[6] = "hill"
    terrain[10] = "wetland"
    terrain[15] = "water"
    terrain[9] = "forest" if seed % 2 == 0 else "hill"
    return {
        "terrain": terrain,
        "road_hub": 0,
        "aquifer": 80 + (seed % 13),
        "timber_reserve": 48 + seed % 11,
        "stone_reserve": 42 + seed % 9,
        "flood_risk": seed % 4,
        "original_demand": 4 + seed % 5,
    }


def normalize_layout(config, layout):
    required = {"terrain","road_hub","aquifer","timber_reserve",
                "stone_reserve","flood_risk","original_demand"}
    if type(layout) is not dict or set(layout) != required:
        raise CityActionError("original city scene must declare exact typed geography")
    terrain = layout["terrain"]
    if type(terrain) is not list or len(terrain) != PARCELS or any(
        type(t) is not str or t not in TERRAINS for t in terrain
    ):
        raise CityActionError("city geography must be exactly sixteen registered cells")
    hub = _integer(layout["road_hub"], 0, PARCELS - 1, "road_hub")
    if terrain[hub] in ("water","wetland"):
        raise CityActionError("original city road hub cannot begin underwater")
    if sum(t not in ("water","wetland") for t in terrain) < 8:
        raise CityActionError("urban scene needs at least eight viable land parcels")
    amounts = (
        ("aquifer", 0, 100_000), ("timber_reserve", 0, 100_000),
        ("stone_reserve", 0, 100_000), ("flood_risk", 0, 8),
        ("original_demand", 1, 16),
    )
    for key, minimum, maximum in amounts:
        _integer(layout[key], minimum, maximum, key)
    return {"terrain": list(terrain), **{key:layout[key] for key in
        ("road_hub","aquifer","timber_reserve","stone_reserve",
         "flood_risk","original_demand")}}


def _parcel(index, terrain):
    return {"id":index,"terrain":terrain,"kind":"empty","level":0}


def start(config, seed):
    _integer(seed, 0, 2**31-1, "seed")
    return apply_scene({
        "seed":seed,"tick":0,"day":1,"population":0,"employment":0,
        "happiness":60,"health":100,"credits":config["opening_budget"],
        "debt":0,"wood":55,"stone":45,"aquifer":0,
        "timber_reserve":0,"stone_reserve":0,"flood_risk":0,
        "original_demand":0,"hub":0,"parcels":[],
        "power_capacity":0,"water_capacity":0,"powered":False,
        "watered":False,"congestion":0,"pollution":0,
        "tax":"normal","policy":config["policy"],
        "insolvency_days":0,"flood_losses":0,"citizen_satisfaction":0,
        "milestones":[],"events":[],"finished":False,"failed":False,
    }, config, default_layout(config, seed))


def apply_scene(state, config, layout):
    checked = normalize_layout(config,layout)
    state["parcels"] = [_parcel(i,t) for i,t in enumerate(checked["terrain"])]
    state["hub"] = checked["road_hub"]
    state["parcels"][state["hub"]]["kind"] = "road"
    state["parcels"][state["hub"]]["level"] = 1
    for name in ("aquifer","timber_reserve","stone_reserve",
                 "flood_risk","original_demand"):
        state[name] = checked[name]
    return state


def _connected_roads(state):
    hub = state["hub"]
    roads = {p["id"] for p in state["parcels"]
             if p["kind"] in ("road","bridge")}
    if hub not in roads:
        return set()
    found = {hub}
    pending = deque([hub])
    while pending:
        for nxt in neighbors(pending.popleft()):
            if nxt in roads and nxt not in found:
                found.add(nxt)
                pending.append(nxt)
    return found


def _connected_sites(state):
    roads = _connected_roads(state)
    return [p for p in state["parcels"]
            if p["kind"] in DEVELOPED
            and any(j in roads for j in neighbors(p["id"]))]


def _cost(state, credits, wood, stone):
    if state["credits"] < credits or state["wood"] < wood or state["stone"] < stone:
        raise CityActionError("urban construction requires real credits, timber and stone")
    state["credits"] -= credits
    state["wood"] -= wood
    state["stone"] -= stone


def _advance(state, config):
    state["tick"] += 1
    state["day"] += 1
    events = ["civic_day_advanced"]
    sites = _connected_sites(state)
    roads = _connected_roads(state)
    count = lambda kind: sum(p["level"] for p in sites if p["kind"] == kind)
    homes = count("residential")*config["housing_density"]
    jobs = count("commercial")*12 + count("industry")*16
    power = count("power")*config["power_output"]
    water = count("waterworks")*config["water_output"]
    capacity_water = min(water, state["aquifer"])
    state["power_capacity"] = power
    state["water_capacity"] = capacity_water
    state["powered"] = power > 0
    state["watered"] = capacity_water > 0
    state["employment"] = min(jobs,state["population"])
    old = state["population"]
    # Housing, employment, utilities and effective transport are required for
    # growth. A zoned home without a road/power/water is not inhabited.
    if homes and jobs and power and capacity_water and state["happiness"]>=30:
        potential = min(homes,config["citizens"],jobs*2,capacity_water,power)
        if old < potential:
            state["population"] += min(potential-old,state["original_demand"])
            events.append("connected_zones_attract_actual_residents")
    if state["population"] and (not power or not capacity_water):
        state["population"] = max(0,state["population"]-max(1,state["population"]//6))
        events.append("unserved_citizens_leave")
    state["employment"] = min(jobs,state["population"])
    # Actual water drawn from authored finite aquifer; no spontaneous replenishment.
    draw = min(state["aquifer"],(state["population"]+3)//4)
    state["aquifer"] -= draw
    if draw:
        events.append("finite_city_water_consumed")
    plants = count("industry")
    policy = state["policy"]
    raw_pollution = plants*config["industrial_emissions"]
    state["pollution"] = max(0,raw_pollution -
        count("park")*3 - (3 if policy=="ecology" else 0))
    roads_capacity = max(1,len(roads)*config["road_capacity"])
    rush = state["population"] + state["employment"]
    state["congestion"] = (max(0,rush-roads_capacity)
                           if config["traffic_simulation"] else 0)
    if policy == "transit":
        state["congestion"] //= 2
    tax_rate = {"low":1,"normal":2,"high":3}[state["tax"]]
    tax_policy = {"planned":1,"mixed":2,"market":3}[config["economic_model"]]
    income = state["population"]*tax_rate//4 + jobs*tax_policy//6
    overhead = sum(1+p["level"] for p in state["parcels"]
                   if p["kind"] != "empty")
    overhead += state["debt"]//20
    if policy == "industrial":
        income += plants*4
    if policy == "ecology":
        overhead += count("park")
    state["credits"] += income - overhead
    if income:
        events.append("actual_resident_and_employment_tax_revenue")
    risk = state["flood_risk"]
    if config["disasters"] and state["day"]%config["disaster_cycle"]==0 and risk:
        vulnerable = [p for p in sites if p["terrain"]=="wetland" or
                      p["id"]%WIDTH==3]
        if vulnerable:
            chosen = vulnerable[state["day"]%len(vulnerable)]
            state["credits"] -= min(20,risk*2)
            state["flood_losses"] += 1
            state["health"] = max(0,state["health"]-max(1,risk-count("firehouse")))
            events.append("urban_flood_damaged_unprotected_parcel")
    parks,clinics,schools,fire = (count(n) for n in
                                 ("park","clinic","school","firehouse"))
    wellness = 55 + parks*4 + clinics*3 + schools*3 + fire*2
    wellness -= state["congestion"]//3 + state["pollution"]*2
    wellness -= max(0, (state["population"]-state["employment"])//4)
    wellness -= 8 if state["tax"]=="high" else 0
    wellness += 3 if state["tax"]=="low" else 0
    state["happiness"] = max(0,min(100,wellness))
    state["citizen_satisfaction"] = state["happiness"]
    if state["population"] and state["happiness"]<20:
        state["population"] = max(0,state["population"]-1)
        events.append("unhappy_citizens_relocate")
    state["employment"] = min(jobs,state["population"])
    if state["credits"]<0:
        state["insolvency_days"] += 1
    else:
        state["insolvency_days"] = 0
    if state["insolvency_days"]>=6 or state["health"]==0:
        state["failed"]=True
        events.append("municipal_collapse")
    if (state["population"]>=12 and state["employment"]>=8
        and state["powered"] and state["watered"] and state["happiness"]>=50):
        if "functioning_original_city" not in state["milestones"]:
            state["milestones"].append("functioning_original_city")
            events.append("functional_civic_milestone")
    if (state["population"]>=32 and parks and clinics and schools
        and state["happiness"]>=65 and state["credits"]>=0):
        if "prosperous_civic_region" not in state["milestones"]:
            state["milestones"].append("prosperous_civic_region")
            events.append("resilient_city_milestone")
    if config["ending_policy"]=="campaign" and (
        "prosperous_civic_region" in state["milestones"]):
        state["finished"]=True
        events.append("optional_city_campaign_won")
    return events


def step(state, config, action):
    if action not in ACTIONS:
        raise CityActionError("unregistered original city action")
    if state["finished"] or state["failed"]:
        raise CityActionError("completed or collapsed city cannot accept commands")
    events = []
    parts = action.split(":")
    if action.startswith("build:"):
        kind,index = parts[1],int(parts[2])
        parcel = state["parcels"][index]
        if parcel["kind"]!="empty":
            raise CityActionError("parcel already contains a real structure")
        if kind=="bridge":
            if parcel["terrain"]!="water":
                raise CityActionError("bridge requires an authored river cell")
        elif parcel["terrain"]=="water":
            raise CityActionError("water parcel cannot be zoned without a bridge")
        if kind!="bridge" and parcel["terrain"]=="wetland" and kind in ("power","waterworks"):
            raise CityActionError("wetland utility plant is prohibited")
        if kind in ("power","waterworks") and sum(
                p["kind"] in ("power","waterworks") for p in state["parcels"]
                ) >= min(config["utility_nodes"],PARCELS):
            raise CityActionError("city has reached authored utility-node limit")
        if kind in ("residential","commercial","industry") and sum(
                p["kind"] in ("residential","commercial","industry")
                for p in state["parcels"]) >= min(config["zones"], PARCELS):
            raise CityActionError("authored zoning capacity exceeded")
        nearby=neighbors(index)
        roads=_connected_roads(state)
        if not any(n in roads for n in nearby):
            raise CityActionError("new development must connect to the real existing road graph")
        _cost(state,*COSTS[kind])
        parcel["kind"]=kind
        parcel["level"]=1
        events.append("connected_urban_asset_built")
    elif action.startswith("upgrade:"):
        parcel=state["parcels"][int(parts[1])]
        if parcel["kind"] not in DEVELOPED or parcel["level"]>=3:
            raise CityActionError("only existing active structures can be upgraded")
        cost=COSTS[parcel["kind"]]
        _cost(state,cost[0]*parcel["level"],cost[1],cost[2])
        parcel["level"]+=1
        events.append("urban_asset_upgraded")
    elif action.startswith("demolish:"):
        parcel=state["parcels"][int(parts[1])]
        if parcel["kind"]=="empty" or parcel["id"]==state["hub"]:
            raise CityActionError("cannot demolish empty parcel or originating road hub")
        kind=parcel["kind"]
        parcel["kind"]="empty"
        parcel["level"]=0
        state["wood"]+=COSTS[kind][1]//2
        state["stone"]+=COSTS[kind][2]//2
        events.append("original_zoning_demolished_and_salvaged")
    elif action.startswith("log:") or action.startswith("quarry:"):
        idx=int(parts[1]);p=state["parcels"][idx]
        kind="wood" if action.startswith("log:") else "stone"
        terrain="forest" if kind=="wood" else "hill"
        reserve="timber_reserve" if kind=="wood" else "stone_reserve"
        if p["terrain"]!=terrain or p["kind"]!="empty" or state[reserve]==0:
            raise CityActionError("resource requires a matching unused finite original terrain deposit")
        amount=min(6,state[reserve])
        state[reserve]-=amount
        state[kind]+=amount
        events.append("finite_original_civic_material_extracted")
    elif action in ("tick","tick:4"):
        for _ in range(4 if action=="tick:4" else 1):
            if state["finished"] or state["failed"]:
                break
            events.extend(_advance(state,config))
    elif action.startswith("tax:"):
        state["tax"]=parts[1]
        events.append("civic_tax_policy_changed")
    elif action.startswith("policy:"):
        state["policy"]=parts[1]
        events.append("urban_development_policy_changed")
    elif action=="bond":
        if state["debt"] >= 100:
            raise CityActionError("municipal bond ceiling reached")
        state["debt"]+=25
        state["credits"]+=25
        events.append("bounded_public_debt_issued")
    elif action=="pay_debt":
        if state["debt"]==0 or state["credits"]<25:
            raise CityActionError("debt repayment requires an outstanding bond and funds")
        state["credits"]-=25
        state["debt"]-=25
        events.append("municipal_debt_repaid")
    elif action=="import_materials":
        if state["credits"]<20:
            raise CityActionError("imported lumber and stone must be paid for")
        state["credits"]-=20
        state["wood"]+=5
        state["stone"]+=5
        events.append("priced_civic_materials_imported")
    state["events"]=events
    return events


__all__ = ["WIDTH","PARCELS","TERRAINS","BUILDINGS","ACTIONS","CityActionError",
           "neighbors","default_layout","normalize_layout","start","apply_scene","step"]
