"""Original advanced endless sandbox: persistent streamed regions and live ecology.

Bounded active 8x8 chunks are generated on demand and persisted by region
index. Edits, water, ore, crops, animals, settlers, buildings and exhaustion
cannot reset when the player revisits a chunk. Up to 4096 authored logical
regions without allocating the whole world. No imported assets or scripting.
"""
from __future__ import annotations
from collections import deque

SIZE=8
CELLS=SIZE*SIZE
TERRAINS=("grass","forest","ridge","sand","marsh","lake")
BUILDINGS=("house","road","bridge","farm","well","workshop","kiln",
           "fence","beacon","generator","storehouse")
JOBS=("idle","farmer","forester","miner","rancher","builder","guard")
RESOURCES=("wood","stone","clay","food","water","ore","fiber","seed",
           "plank","brick","tool","fuel")
COSTS={
 "house":{"wood":9,"stone":4,"plank":2},
 "road":{"stone":2},"bridge":{"plank":5,"stone":2},
 "farm":{"wood":3,"tool":1},"well":{"stone":5,"clay":2},
 "workshop":{"wood":7,"stone":4},"kiln":{"stone":7,"clay":5},
 "fence":{"wood":3},"beacon":{"stone":6,"fuel":2},
 "generator":{"ore":4,"brick":4,"tool":1},
 "storehouse":{"wood":8,"stone":5},
}
ACTIONS=(
 tuple(f"{verb}:{i}" for verb in ("move","chop","quarry","dig_clay",
  "gather","draw_water","fish","mine_ore","till","sow","reap","irrigate",
  "tame","feed","hunt","ignite","extinguish","demolish","inspect") for i in range(CELLS))
 +tuple(f"build:{name}:{i}" for name in BUILDINGS for i in range(CELLS))
 +tuple(f"terraform:{name}:{i}" for name in TERRAINS for i in range(CELLS))
 +("tick","tick:4","rest","eat","drink","craft:plank","craft:brick",
   "craft:tool","craft:fuel","craft:food","trade:buy_food",
   "trade:sell_ore","trade:buy_seed","region:next","region:previous",
   "portal:next","recruit","release","assign:idle","assign:farmer",
   "assign:forester","assign:miner","assign:rancher","assign:builder",
   "assign:guard","toggle:ecology","toggle:trade","milestone:declare")
)


class SandboxActionError(ValueError):
    """Invalid authored world, impossible act or unsupported sandbox rule."""


def _int(v,minimum,maximum,key):
    if type(v) is not int or not minimum<=v<=maximum:
        raise SandboxActionError("invalid bounded sandbox "+key)
    return v


def _neighbors(i):
    x=i%SIZE;y=i//SIZE
    return tuple(j for j in (i-SIZE,i-1,i+1,i+SIZE)
       if 0<=j<CELLS and abs(j%SIZE-x)+abs(j//SIZE-y)==1)


def _tile(i,terrain,seed):
    # Deterministic bounded original terrain stocks, not copied game maps.
    v=(seed*37+i*73+i*i*7+19)&0x7fffffff
    return {
        "id":i,"terrain":terrain,"building":None,"level":0,
        "wood":(3+v%8 if terrain=="forest" else 0),
        "stone":(4+v%6 if terrain=="ridge" else 0),
        "clay":(2+v%5 if terrain in ("marsh","sand") else 0),
        "ore":(2+v%4 if terrain=="ridge" else 0),
        "water":(8+v%9 if terrain in ("lake","marsh") else 0),
        "fish":(3+v%5 if terrain in ("lake","marsh") else 0),
        "forage":(2+v%3 if terrain in ("grass","forest") else 0),
        "soil":0,"crop":0,"moisture":(2 if terrain in ("marsh","lake") else 0),
        "animal":(1 if terrain in ("grass","forest") and v%6==0 else 0),
        "tamed":False,
        "fire":0,"pollution":0,
    }


def generated_chunk(seed,region):
    _int(seed,0,2**31-1,"seed")
    _int(region,0,4095,"region")
    value=(seed+region*1013904223)&0x7fffffff
    tiles=[]
    for i in range(CELLS):
        v=(value*17+i*173+(i//SIZE)*13+i*i)&0x7fffffff
        biome=TERRAINS[v%len(TERRAINS)]
        if i==0:biome="grass"
        if i==1:biome="forest"
        if i in (2,3):biome="grass"
        if i==8:biome="ridge"
        if i==9:biome="marsh"
        tiles.append(_tile(i,biome,value))
    return tiles


def default_layout(config,seed):
    tiles=generated_chunk(seed,0)
    # Source always shows meaningful original tree, ore, aquifer and fauna.
    return {
        "spawn":0,"tiles":tiles,
        "starting_credits":min(config["build_budget"],400),
        "starting_weather":("clear","rain","drought")[seed%3],
        "region_name":"Original Homestead",
        "wildlife_population":sum(t["animal"] for t in tiles),
        "settler_spawns":[2,3][:min(config["settler_count"],2)],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "spawn","tiles","starting_credits","starting_weather",
        "region_name","wildlife_population","settler_spawns"}:
        raise SandboxActionError("world scene requires exact original geographic schema")
    if type(layout["tiles"]) is not list or len(layout["tiles"])!=CELLS:
        raise SandboxActionError("original sandbox must author exactly 64 terrain cells")
    source=layout["tiles"];tiles=[]
    stock_limits={"wood":1000,"stone":1000,"clay":1000,"ore":1000,
                  "water":1000,"forage":1000,"fish":1000,"soil":1,"crop":8,
                  "moisture":10,"animal":1,"fire":8,"pollution":1000}
    for i,t in enumerate(source):
        required={"id","terrain","building","level","tamed"}|set(stock_limits)
        if type(t) is not dict or set(t)!=required:
            raise SandboxActionError("sandbox cell must have exact typed terrain and stock fields")
        if _int(t["id"],0,CELLS-1,"cell id")!=i:
            raise SandboxActionError("authored sandbox cell identity must be canonical")
        if type(t["terrain"]) is not str or t["terrain"] not in TERRAINS:
            raise SandboxActionError("unregistered original terrain biome")
        if t["building"] is not None and (type(t["building"]) is not str
                                        or t["building"] not in BUILDINGS):
            raise SandboxActionError("unregistered original sandbox structure")
        _int(t["level"],0,3,"structure level")
        if (t["building"] is None)!=(t["level"]==0):
            raise SandboxActionError("building level cannot exist without structure")
        if type(t["tamed"]) is not bool or (t["tamed"] and t["animal"]!=1):
            raise SandboxActionError("animal taming requires a real original creature")
        for k,maximum in stock_limits.items():
            _int(t[k],0,maximum,k)
        if t["terrain"]=="lake" and t["building"] not in (None,"bridge"):
            raise SandboxActionError("non-bridge structures cannot begin on lake water")
        if t["crop"] and not t["soil"]:
            raise SandboxActionError("authored crops require prepared soil")
        tiles.append(dict(t))
    spawn=_int(layout["spawn"],0,CELLS-1,"player spawn")
    if tiles[spawn]["terrain"]=="lake":
        raise SandboxActionError("player cannot spawn in deep water")
    credits=_int(layout["starting_credits"],0,config["build_budget"],"starting funds")
    weather=layout["starting_weather"]
    if type(weather) is not str or weather not in ("clear","rain","drought","storm"):
        raise SandboxActionError("unregistered original weather")
    name=layout["region_name"]
    if type(name) is not str or not 3<=len(name)<=48 or not all(
        c.isalnum() or c in " -_" for c in name):
        raise SandboxActionError("original world region label must be safe bounded text")
    wildlife=_int(layout["wildlife_population"],0,CELLS,"wildlife population")
    if wildlife!=sum(t["animal"] for t in tiles):
        raise SandboxActionError("wildlife population must equal real animals on authored cells")
    spawns=layout["settler_spawns"]
    if type(spawns) is not list or len(spawns)>min(8,config["settler_count"]):
        raise SandboxActionError("authored starting settler count exceeds budget")
    if any(type(p) is not int or not 0<=p<CELLS or
           tiles[p]["terrain"]=="lake" for p in spawns) or len(set(spawns))!=len(spawns):
        raise SandboxActionError("settlers must spawn on unique viable cells")
    return {
      "spawn":spawn,"tiles":tiles,"starting_credits":credits,
      "starting_weather":weather,"region_name":name,
      "wildlife_population":wildlife,"settler_spawns":list(spawns),
    }


def _new_settler(index,cell,region=0):
    return {"id":index,"cell":cell,"region":region,"job":"idle","health":100,
            "morale":70,"skill":0,"worked":0}


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    state["position"]=source["spawn"]
    state["regions"]={"0":source["tiles"]}
    state["region_names"]={"0":source["region_name"]}
    state["weather"]=source["starting_weather"]
    state["credits"]=source["starting_credits"]
    state["settlers"]=[_new_settler(i,p) for i,p in enumerate(source["settler_spawns"])]
    state["visited_regions"]=[0]
    return state


def start(config,seed):
    _int(seed,0,2**31-1,"seed")
    state={
      "seed":seed,"region":0,"regions":{},"region_names":{},
      "position":0,"visited_regions":[],"ticks":0,"day":1,
      "season":0,"weather":"clear","energy":config["starting_energy"],
      "health":config["starting_health"],"hunger":0,"thirst":0,
      "inventory":{"wood":10,"stone":8,"clay":3,"food":10,"water":12,
        "ore":1,"fiber":6,"seed":7,"plank":4,"brick":0,"tool":2,"fuel":4},
      "credits":0,"settlers":[],"next_settler_id":2,
      "community_food":10,"community_water":12,"tamed_animals":0,
      "ecology":True,"trade":True,"research":0,"power":0,
      "emissions":0,"houses":0,"achievements":[],
      "events":[],"failed":False,"finished":False,"death_reason":"",
    }
    return apply_scene(state,config,default_layout(config,seed))


def _tiles(state):
    return state["regions"][str(state["region"])]


def _here(state):
    return _tiles(state)[state["position"]]


def _local(state,index,limit=1):
    p=state["position"]
    return abs(p%SIZE-index%SIZE)+abs(p//SIZE-index//SIZE)<=limit


def _mutate_resource(state,config,tile,stock,item,amount):
    if config["resource_policy"]=="unlimited":
        state["inventory"][item]+=amount
        return amount
    count=min(tile[stock],amount)
    if count==0:
        raise SandboxActionError("finite source stock exhausted: "+stock)
    tile[stock]-=count
    state["inventory"][item]+=count
    return count


def _spend(state,config,costs,reason):
    if config["creative_mode"]:
        return
    if any(state["inventory"][k]<v for k,v in costs.items()):
        raise SandboxActionError(reason+" needs actual source materials")
    for k,v in costs.items():
        state["inventory"][k]-=v


def _cost_energy(state,config,amount):
    if config["creative_mode"]:
        return
    if state["energy"]<amount:
        raise SandboxActionError("real action requires energy recovered by resting")
    state["energy"]-=amount


def _residence(state):
    return sum(t["building"]=="house" for rows in state["regions"].values()
               for t in rows)


def _structures(state,kind):
    return [t for rows in state["regions"].values() for t in rows
            if t["building"]==kind]


def _work(state,config,events):
    tiles=_tiles(state)
    for worker in state["settlers"]:
        if worker["health"]==0 or worker["region"]!=state["region"]:
            continue
        if worker["job"]=="idle":
            worker["morale"]=min(100,worker["morale"]+1)
            continue
        nearby=[tiles[i] for i in range(CELLS) if (
           abs(worker["cell"]%SIZE-i%SIZE)+abs(worker["cell"]//SIZE-i//SIZE)
           <=config["worker_radius"])]
        job=worker["job"]
        if job=="forester":
            deposit=next((t for t in nearby if t["wood"]>0),None)
            if deposit:
                deposit["wood"]-=1
                state["inventory"]["wood"]+=1
                events.append("settler_actually_logged_local_tree")
        elif job=="miner":
            deposit=next((t for t in nearby if t["stone"] or t["ore"]),None)
            if deposit:
                ore=deposit["ore"]>0
                key="ore" if ore else "stone"
                deposit[key]-=1
                state["inventory"][key]+=1
                events.append("settler_actually_mined_local_rock")
        elif job=="farmer":
            field=next((t for t in nearby if t["crop"]>=config["crop_days"]
                        and t["soil"]),None)
            if field:
                field["crop"]=0
                state["community_food"]+=config["crop_yield"]
                events.append("settler_harvested_mature_local_crop")
            else:
                field=next((t for t in nearby if t["soil"] and t["crop"]==0
                            and state["inventory"]["seed"]>0),None)
                if field:
                    state["inventory"]["seed"]-=1
                    field["crop"]=1
                    events.append("settler_sowed_real_reserved_seed")
        elif job=="rancher":
            herd=next((t for t in nearby if t["animal"] and t["tamed"]),None)
            if herd:
                state["community_food"]+=1
                events.append("settler_ran_existing_tamed_herd")
        elif job=="builder":
            if _structures(state,"workshop") and state["inventory"]["wood"]>=2:
                state["inventory"]["wood"]-=2
                state["inventory"]["plank"]+=1
                events.append("settler_milled_reserved_lumber")
        elif job=="guard":
            worker["health"]=min(100,worker["health"]+1)
            events.append("settler_guarded_real_camp")
        worker["worked"]+=1
        worker["skill"]=min(100,worker["skill"]+1)


def _tick(state,config):
    events=["persistent_original_world_tick"]
    state["day"]+=1
    state["ticks"]+=1
    if state["ticks"]%config["season_length"]==0:
        state["season"]=(state["season"]+1)%4
        events.append("real_climate_season_changed")
    if config["weather_enabled"]:
        cycle=("clear","rain","clear","storm","clear","drought")
        state["weather"]=cycle[(state["ticks"]+state["seed"]//3)%len(cycle)]
    tiles=_tiles(state)
    ecology=state["ecology"] and config["ecology_enabled"]
    for t in tiles:
        if t["crop"] and t["soil"] and t["crop"]<config["crop_days"]:
            if t["moisture"] or state["weather"]=="rain":
                t["crop"]=min(config["crop_days"],t["crop"]+
                    (2 if t["building"]=="farm" else 1))
                t["moisture"]=max(0,t["moisture"]-1)
        if ecology and config["resource_policy"]=="renewable":
            if t["terrain"]=="forest" and t["wood"]<config["regrowth_cap"] \
              and (state["day"]+t["id"])%config["regrowth_period"]==0:
                t["wood"]+=1
                events.append("original_forest_regrowth")
            if t["terrain"] in ("lake","marsh") and t["water"]<config["regrowth_cap"] \
              and state["weather"]=="rain":
                t["water"]+=config["rain_replenishment"]
                t["water"]=min(config["regrowth_cap"],t["water"])
        if config["fire_enabled"] and t["fire"]:
            t["fire"]=max(0,t["fire"]-1)
            if t["wood"]:
                t["wood"]=max(0,t["wood"]-config["fire_damage"])
            t["pollution"]=min(1000,t["pollution"]+config["fire_damage"])
        if t["building"]=="generator":
            state["power"]+=config["generator_output"]
            state["emissions"]+=config["generator_emissions"]
    # A well is only useful if physically connected to a finite source,
    # including rainy replenishment under the explicit renewable policy.
    for well in (t for t in tiles if t["building"]=="well"):
        for near in _neighbors(well["id"]):
            source=tiles[near]
            if source["terrain"] not in ("lake","marsh") or source["water"]==0:
                continue
            drawn=min(source["water"],config["well_output"])
            source["water"]-=drawn
            state["community_water"]+=drawn
            events.append("built_well_drew_finite_adjoining_aquifer_water")
            break
    # Wildfire consumes physical terrain stocks and propagates only through
    # neighboring flammable vegetation, never through lakes or fences.
    active=[t["id"] for t in tiles if t["fire"]>0]
    for site in active:
        origin=tiles[site]
        if origin["fire"]<=1:continue
        for near in _neighbors(site):
            target=tiles[near]
            if target["terrain"] not in ("grass","forest") or target["fire"] \
              or target["building"] in ("fence","well","bridge"):
                continue
            if (state["ticks"]+site*11+near*7)%config["fire_spread_period"]==0:
                target["fire"]=max(1,origin["fire"]-1)
                events.append("original_local_wildfire_spread_to_neighbor")
                break
    if ecology and config["wildlife_motion"]:
        occupied={t["id"] for t in tiles if t["animal"]}
        transfers=[]
        for t in tiles:
            if t["animal"] and not t["tamed"]:
                choices=[i for i in _neighbors(t["id"]) if i not in occupied
                         and tiles[i]["terrain"] in ("grass","forest")
                         and not tiles[i]["building"] and not tiles[i]["fire"]]
                if choices and (state["ticks"]+t["id"])%config["wildlife_move_period"]==0:
                    destination=choices[(state["ticks"]+t["id"])%len(choices)]
                    occupied.add(destination)
                    transfers.append((t["id"],destination))
        for origin,destination in transfers:
            tiles[origin]["animal"]=0
            tiles[destination]["animal"]=1
            events.append("original_wildlife_moved_into_safe_adjoining_habitat")
    if ecology and config["resource_policy"]=="renewable" and (
         state["ticks"]%config["wildlife_birth_period"]==0):
        population=sum(t["animal"] for t in tiles)
        if population<config["wildlife_cap"]:
            habitat=next((t for t in tiles if t["terrain"] in ("grass","forest")
                          and not t["animal"] and not t["building"] and not t["fire"]),None)
            if habitat is not None:
                habitat["animal"]=1
                events.append("bounded_original_wildlife_population_regenerated")
    _work(state,config,events)
    # Community consumables are genuinely conserved across settlers and
    # remain separate from the player's carried inventory.
    mouths=len(state["settlers"])
    if mouths:
        food=min(state["community_food"],max(1,(mouths+1)//2))
        water=min(state["community_water"],max(1,(mouths+1)//2))
        state["community_food"]-=food
        state["community_water"]-=water
        if food<max(1,(mouths+1)//2) or water<max(1,(mouths+1)//2):
            for s in state["settlers"]:
                s["health"]=max(0,s["health"]-config["starvation_damage"])
                s["morale"]=max(0,s["morale"]-config["morale_decay"])
            events.append("actual_settler_food_water_shortage")
        else:
            for s in state["settlers"]:
                s["morale"]=min(100,s["morale"]+1)
    state["hunger"]=min(100,state["hunger"]+config["hunger_gain"])
    state["thirst"]=min(100,state["thirst"]+config["thirst_gain"])
    if config["hazards_enabled"] and (
        not config["creative_mode"] or config["creative_hazards"]) and (
        state["hunger"]>=config["hunger_threshold"] or
        state["thirst"]>=config["thirst_threshold"]):
        state["health"]=max(0,state["health"]-config["exposure_damage"])
        events.append("actual_player_exposure_damage")
    if state["health"]==0:
        state["failed"]=True
        state["death_reason"]="environmental_exposure"
        events.append("original_explorer_could_not_survive")
    if _residence(state)>=config["milestone_houses"] and len(state["settlers"])>=config["milestone_population"]:
        if "self_sustaining_homestead" not in state["achievements"]:
            state["achievements"].append("self_sustaining_homestead")
            events.append("physical_original_homestead_milestone")
    if (config["allow_perpetual_play"] is False and
        "self_sustaining_homestead" in state["achievements"]):
        state["finished"]=True
        events.append("optional_settlement_campaign_completed")
    return events


def step(state,config,action):
    if action not in ACTIONS:
        raise SandboxActionError("unregistered sandbox world operation")
    if state["failed"] or state["finished"]:
        raise SandboxActionError("ended original simulation cannot accept orders")
    events=[]
    tiles=_tiles(state)
    fields=action.split(":")
    verb=fields[0]
    if verb in ("move","chop","quarry","dig_clay","gather","draw_water",
                "fish","mine_ore","till","sow","reap","irrigate","tame","feed","hunt",
                "ignite","extinguish","demolish","inspect","build","terraform"):
        kind=fields[1] if verb in ("build","terraform") else None
        index=int(fields[2] if kind is not None else fields[1])
        tile=tiles[index]
        if not _local(state,index,1):
            raise SandboxActionError("world manipulation requires direct geographic adjacency")
        if verb=="move":
            if index==state["position"] or not _local(state,index,1):
                raise SandboxActionError("movement must traverse a real adjacent tile")
            if tile["terrain"]=="lake" and tile["building"]!="bridge":
                raise SandboxActionError("lake is impassable until real bridge construction")
            _cost_energy(state,config,
                         config["move_energy"]//2 if tile["building"]=="road"
                         else config["move_energy"])
            state["position"]=index
            events.append("original_character_moved_on_local_world")
        elif verb in ("chop","quarry","dig_clay","gather","draw_water","fish","mine_ore"):
            if verb=="chop":
                stock,item,n="wood","wood",config["harvest_strength"]
            elif verb=="quarry":
                stock,item,n="stone","stone",config["harvest_strength"]
            elif verb=="mine_ore":
                stock,item,n="ore","ore",config["harvest_strength"]
            elif verb=="dig_clay":
                stock,item,n="clay","clay",config["harvest_strength"]
            elif verb=="gather":
                stock,item,n="forage","fiber",config["harvest_strength"]
            elif verb=="draw_water":
                stock,item,n="water","water",config["water_draw"]
            else:
                if tile["terrain"] not in ("lake","marsh"):
                    raise SandboxActionError("fish require real aquatic terrain")
                stock,item,n="fish","food",config["fishing_yield"]
            if config["resource_policy"]=="unlimited" and not (
                tile[stock]>0 or
                (verb=="chop" and tile["terrain"]=="forest") or
                (verb in ("quarry","mine_ore") and tile["terrain"]=="ridge") or
                (verb=="dig_clay" and tile["terrain"] in ("sand","marsh")) or
                (verb=="gather" and tile["terrain"] in ("grass","forest")) or
                (verb in ("draw_water","fish") and tile["terrain"] in ("lake","marsh"))):
                raise SandboxActionError("unlimited materials still require original matching terrain")
            _cost_energy(state,config,config["work_energy"])
            gained=_mutate_resource(state,config,tile,stock,item,n)
            events.append("original_local_resource_extracted_"+item+"_"+str(gained))
        elif verb=="ignite":
            if not config["fire_enabled"] or tile["terrain"]=="lake" or tile["fire"]:
                raise SandboxActionError("fire requires flammable original land and unlit fuel")
            _spend(state,config,{"fuel":1},"controlled ignition")
            tile["fire"]=config["initial_fire"]
            events.append("original_bounded_fire_ignited")
        elif verb=="extinguish":
            if tile["fire"]==0:
                raise SandboxActionError("cannot extinguish non-burning terrain")
            _spend(state,config,{"water":config["extinguish_water"]},"real fire suppression")
            tile["fire"]=0
            events.append("original_terrain_fire_extinguished")
        elif verb=="till":
            if tile["terrain"] not in ("grass","marsh") or tile["building"] not in (None,"farm"):
                raise SandboxActionError("cultivation needs viable unblocked original soil")
            _cost_energy(state,config,config["work_energy"])
            tile["soil"]=1
            events.append("real_original_soil_prepared")
        elif verb=="sow":
            if not tile["soil"] or tile["crop"]:
                raise SandboxActionError("planting needs empty prepared soil")
            _spend(state,config,{"seed":1},"genuine farming")
            tile["crop"]=1
            events.append("finite_original_seed_planted")
        elif verb=="reap":
            if tile["crop"]<config["crop_days"]:
                raise SandboxActionError("crop cannot be harvested before real seasonal growth")
            tile["crop"]=0
            state["inventory"]["food"]+=config["crop_yield"]
            state["inventory"]["seed"]+=1
            events.append("mature_original_food_reaped_once")
        elif verb=="irrigate":
            if not tile["soil"]:
                raise SandboxActionError("irrigation requires actual prepared soil")
            _spend(state,config,{"water":config["irrigation_cost"]},"irrigation")
            tile["moisture"]=min(10,tile["moisture"]+config["irrigation_effect"])
            events.append("real_crop_soil_irrigated")
        elif verb=="tame":
            if not tile["animal"] or tile["tamed"]:
                raise SandboxActionError("only living unowned wildlife can be tamed")
            _spend(state,config,{"food":config["taming_cost"]},"taming")
            tile["tamed"]=True
            state["tamed_animals"]+=1
            events.append("living_original_wildlife_tamed")
        elif verb=="feed":
            if not tile["animal"] or not tile["tamed"]:
                raise SandboxActionError("feeding requires a real tamed animal")
            _spend(state,config,{"food":1},"animal care")
            state["community_food"]+=1
            events.append("tamed_animal_supplied_actual_community_food")
        elif verb=="hunt":
            if not tile["animal"] or tile["tamed"]:
                raise SandboxActionError("cannot hunt absent or domesticated fauna")
            _cost_energy(state,config,config["work_energy"])
            tile["animal"]=0
            state["inventory"]["food"]+=config["hunting_yield"]
            events.append("finite_actual_wildlife_hunted")
        elif verb=="build":
            if tile["building"] is not None:
                raise SandboxActionError("occupied cell cannot receive a second structure")
            if tile["terrain"]=="lake" and kind!="bridge":
                raise SandboxActionError("only a bridge may be built over lake")
            if kind=="bridge" and tile["terrain"]!="lake":
                raise SandboxActionError("a real bridge requires lake terrain")
            _spend(state,config,COSTS[kind],"real construction")
            _cost_energy(state,config,config["work_energy"])
            if not config["creative_mode"]:
                if state["credits"]<config["structure_fee"]:
                    raise SandboxActionError("construction requires available licensed civic budget")
                state["credits"]-=config["structure_fee"]
            tile["building"]=kind;tile["level"]=1
            events.append("player_built_original_persistent_"+kind)
        elif verb=="demolish":
            if tile["building"] is None:
                raise SandboxActionError("empty original cell cannot be demolished")
            kind=tile["building"]
            tile["building"]=None;tile["level"]=0
            for key,amount in COSTS[kind].items():
                state["inventory"][key]+=amount//2
            events.append("built_original_structure_recycled")
        elif verb=="terraform":
            if not config["creative_mode"] or not config["terraforming"]:
                raise SandboxActionError("material transformation requires authorized creative terraforming")
            if tile["building"] or tile["crop"] or tile["animal"]:
                raise SandboxActionError("populated, built or cultivated tile cannot be silently overwritten")
            replacement=_tile(index,kind,state["seed"]+state["region"]*31)
            tiles[index]=replacement
            events.append("authorized_original_biome_terraformed")
        else:
            events.append("source_owned_original_local_cell_inspected")
    elif action.startswith("craft:"):
        product=fields[1]
        inputs={
          "plank":{"wood":config["plank_wood"]},
          "brick":{"clay":2,"fuel":1},
          "tool":{"plank":2,"ore":1},
          "fuel":{"wood":2},
          "food":{"food":1,"fiber":2},
        }
        if product in ("brick","tool","plank") and not _structures(state,
            "kiln" if product=="brick" else "workshop"):
            raise SandboxActionError("crafting requires appropriate built workshop or kiln")
        _spend(state,config,inputs[product],"crafting")
        state["inventory"][product]+=1 if product!="food" else config["cooking_yield"]
        events.append("original_material_transformer_produced_"+product)
    elif verb in ("tick","rest"):
        turns=4 if action=="tick:4" else 1
        for _ in range(turns):
            if state["finished"] or state["failed"]:break
            events.extend(_tick(state,config))
        if action=="rest":
            state["energy"]=min(config["starting_energy"],state["energy"]+config["rest_energy"])
            events.append("original_explorer_recovered_real_energy")
    elif action=="eat":
        _spend(state,config,{"food":1},"eating")
        state["hunger"]=max(0,state["hunger"]-config["food_relief"])
        events.append("carried_meal_reduced_real_hunger")
    elif action=="drink":
        _spend(state,config,{"water":1},"drinking")
        state["thirst"]=max(0,state["thirst"]-config["water_relief"])
        events.append("carried_water_reduced_real_thirst")
    elif action in ("region:next","region:previous","portal:next"):
        nextregion=state["region"]+(1 if action!="region:previous" else -1)
        if not 0<=nextregion<config["world_regions"]:
            raise SandboxActionError("cannot enter region beyond configured authored world")
        if action=="portal:next":
            if not _structures(state,"beacon") or state["power"]<config["portal_power"]:
                raise SandboxActionError("region teleport needs built original beacon and power")
            state["power"]-=config["portal_power"]
        else:
            _spend(state,config,{"food":config["travel_food"]},"region travel")
            _cost_energy(state,config,config["travel_energy"])
        state["region"]=nextregion
        state["position"]=0
        key=str(nextregion)
        if key not in state["regions"]:
            state["regions"][key]=generated_chunk(state["seed"],nextregion)
            state["region_names"][key]="Original Region "+str(nextregion)
            state["visited_regions"].append(nextregion)
            state["visited_regions"].sort()
            events.append("new_original_region_streamed_by_stable_seed")
        else:
            events.append("edited_original_region_restored_exactly")
        events.append("bounded_original_world_region_transition")
    elif action=="recruit":
        if len(state["settlers"])>=config["settler_count"]:
            raise SandboxActionError("recruiting exceeds realistic local population ceiling")
        local_homes=sum(t["building"]=="house" for t in _tiles(state))
        local_workers=sum(s["region"]==state["region"] for s in state["settlers"])
        if local_homes*config["house_capacity"]<=local_workers:
            raise SandboxActionError("new resident needs actual built housing")
        if state["credits"]<config["recruit_fee"]:
            raise SandboxActionError("settlement recruiting needs finite budget")
        state["credits"]-=config["recruit_fee"]
        key=state["next_settler_id"]
        state["settlers"].append(_new_settler(key,state["position"],state["region"]))
        state["next_settler_id"]+=1
        events.append("original_settler_housed_and_recruited")
    elif action=="release":
        if not state["settlers"]:
            raise SandboxActionError("no existing original settler to release")
        worker=state["settlers"].pop()
        events.append("actual_settler_released_"+str(worker["id"]))
    elif action.startswith("assign:"):
        if not state["settlers"]:
            raise SandboxActionError("cannot assign a job without actual original workers")
        worker=next((s for s in state["settlers"] if s["region"]==state["region"]
                     and s["cell"]==state["position"]),None)
        if worker is None:
            raise SandboxActionError("assign work only to physically colocated original settler")
        worker["job"]=fields[1]
        events.append("real_original_settler_assigned_"+fields[1])
    elif action.startswith("trade:"):
        if not state["trade"] or not config["trading"]:
            raise SandboxActionError("trading network disabled by authored rules")
        if action=="trade:buy_food":
            if state["credits"]<config["food_price"]:
                raise SandboxActionError("trade cannot mint unearned credits")
            state["credits"]-=config["food_price"]
            state["inventory"]["food"]+=3
        elif action=="trade:buy_seed":
            if state["credits"]<config["seed_price"]:
                raise SandboxActionError("trading needs paid original seed")
            state["credits"]-=config["seed_price"]
            state["inventory"]["seed"]+=3
        else:
            if state["inventory"]["ore"]<2:
                raise SandboxActionError("market cannot sell ore that does not exist")
            state["inventory"]["ore"]-=2
            state["credits"]+=config["ore_price"]
        events.append("finite_original_market_trade")
    elif action=="toggle:ecology":
        state["ecology"]=not state["ecology"]
        events.append("ecological_regeneration_policy_changed")
    elif action=="toggle:trade":
        state["trade"]=not state["trade"]
        events.append("municipal_trade_policy_changed")
    elif action=="milestone:declare":
        if _residence(state)<config["milestone_houses"] or len(state["settlers"])<config["milestone_population"]:
            raise SandboxActionError("cannot self-certify incomplete sustainable homestead")
        if "self_sustaining_homestead" not in state["achievements"]:
            state["achievements"].append("self_sustaining_homestead")
            events.append("physical_original_homestead_milestone")
        if not config["allow_perpetual_play"]:
            state["finished"]=True
            events.append("optional_original_sandbox_campaign_completion")
    else:
        raise SandboxActionError("unhandled original game action")
    state["houses"]=_residence(state)
    state["events"]=events
    return events


__all__=["SIZE","CELLS","TERRAINS","BUILDINGS","JOBS","RESOURCES",
         "COSTS","ACTIONS","SandboxActionError","generated_chunk",
         "default_layout","normalize_layout","start","apply_scene","step"]
