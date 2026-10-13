"""Original deterministic open-world chunk streaming and authored exploration.

Integer-coordinate terrain comes from a portable mixer, not mutable RNG state.
Three persistence strategies differ in how they survive eviction. The world is
nonterminal after objectives, unless the player explicitly retires.
"""
from __future__ import annotations

ACTIONS=("north","south","east","west","sprint_north","sprint_south",
         "sprint_east","sprint_west","inspect","survey","harvest","mine",
         "plant","build","dismantle","rest","drink","craft","save","checkpoint",
         "retire")
MOVES={"north":(0,1),"south":(0,-1),"east":(1,0),"west":(-1,0),
       "sprint_north":(0,2),"sprint_south":(0,-2),
       "sprint_east":(2,0),"sprint_west":(-2,0)}
PERSISTENCE=("rebuild","save_deltas","snapshot")
BIOME_NAMES=("forest","grassland","desert","tundra","wetland","volcanic",
             "coastal","highland","woodland","savanna","alpine","ruins")


class ProceduralWorldActionError(ValueError):
    """Invalid authored world, finite resource transition or persistence command."""


def _int(v,lo,hi,name):
    if type(v) is not int or not lo<=v<=hi:
        raise ProceduralWorldActionError("invalid original world "+name)
    return v


def _mix(a):
    a=(a ^ (a>>16))*0x7feb352d & 0xffffffff
    a=(a ^ (a>>15))*0x846ca68b & 0xffffffff
    return (a ^ (a>>16))&0xffffffff


def _noise(seed,x,y):
    return _mix((seed*2654435761+x*374761393+y*668265263)&0xffffffff)


def _chunk_key(x,y,size):
    return str(x//size)+":"+str(y//size)


def _tile_key(x,y):
    return str(x)+":"+str(y)


def _source_tile(config,seed,x,y):
    # At most 12 biome archetypes in the reference renderer; a source with
    # 64 biome IDs maps them through the finite original ecological palette.
    world_seed=(config["seed"]^seed)&0xffffffff
    b=_noise(world_seed,x//config["chunk_size"],
             y//config["chunk_size"])%config["biomes"]
    kind=BIOME_NAMES[b%len(BIOME_NAMES)]
    n=_noise(world_seed^0x9e3779b9,x,y)
    material=("wood" if kind in ("forest","woodland","wetland") else
              "stone" if kind in ("volcanic","highland","alpine","ruins") else
              "food" if kind in ("grassland","savanna","coastal") else
              "water" if kind in ("desert","tundra") else "food")
    if n%13==0:material="ore"
    water=(kind in ("coastal","wetland") and n%5==0)
    return {
        "biome":b,"material":material,"units":1+n%config["resource_density"],
        "water":water,"structure":"none","planted":False,"height":n%7,
    }


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    return {
        "title":"Original Seeded Frontier "+str(seed%1000),
        "world_seed":config["seed"],
        "origin":[0,0],
        "landmarks":[
            {"id":0,"at":[3,0],"kind":"ruins"},
            {"id":1,"at":[-3,2],"kind":"observatory"},
        ],
        "climate":("temperate","dry","cold")[seed%3],
        "world_radius_chunks":config["world_radius_chunks"],
        "story_terminal":False,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","world_seed","origin","landmarks","climate",
        "world_radius_chunks","story_terminal"
    }:
        raise ProceduralWorldActionError("exact reviewed original frontier source required")
    title=layout["title"]
    if type(title) is not str or not 3<=len(title)<=64 or not all(
        c.isalnum() or c in " _-" for c in title
    ):
        raise ProceduralWorldActionError("unsafe original procedural world title")
    if _int(layout["world_seed"],0,2**31-1,"seed")!=config["seed"]:
        raise ProceduralWorldActionError("authored chunk seed cannot bypass editor custody")
    if type(layout["origin"]) is not list or layout["origin"]!=[0,0]:
        raise ProceduralWorldActionError("original world origin must be fixed")
    radius=_int(layout["world_radius_chunks"],1,config["world_radius_chunks"],"radius")
    if radius!=config["world_radius_chunks"]:
        raise ProceduralWorldActionError("source cannot enlarge world memory budget")
    if layout["story_terminal"] is not False:
        raise ProceduralWorldActionError("authored open worlds are intentionally nonterminal")
    if type(layout["climate"]) is not str or layout["climate"] not in (
        "temperate","dry","cold"
    ):
        raise ProceduralWorldActionError("unsupported original climate program")
    marks=layout["landmarks"]
    if type(marks) is not list or len(marks)!=2:
        raise ProceduralWorldActionError("two original spatial exploration goals required")
    landmarks=[]
    for i,mark in enumerate(marks):
        if type(mark) is not dict or set(mark)!={"id","at","kind"}:
            raise ProceduralWorldActionError("strict landmark identity/position/kind required")
        if type(mark["id"]) is not int or mark["id"]!=i:
            raise ProceduralWorldActionError("landmark identity must be stable")
        p=mark["at"]
        if type(p) is not list or len(p)!=2:
            raise ProceduralWorldActionError("landmark coordinates must be signed integers")
        coord=[_int(p[0],-12,12,"landmark x"),_int(p[1],-12,12,"landmark y")]
        if coord==[0,0] or any(m["at"]==coord for m in landmarks):
            raise ProceduralWorldActionError("landmarks must be distinct from home")
        kind=("ruins","observatory")[i]
        if mark["kind"]!=kind:
            raise ProceduralWorldActionError("landmark role cannot be forged")
        landmarks.append({"id":i,"at":coord,"kind":kind})
    return {
        "title":title,"world_seed":config["seed"],"origin":[0,0],
        "landmarks":landmarks,"climate":layout["climate"],
        "world_radius_chunks":radius,"story_terminal":False,
    }


def start(config,seed):
    scene=normalize_layout(config,default_layout(config,seed))
    state={
        "tick":0,"seed":seed,"title":scene["title"],"climate":scene["climate"],
        "position":[0,0],"landmarks":scene["landmarks"],"surveyed":[],
        "world_radius_chunks":scene["world_radius_chunks"],
        "chunks":[],"visited_chunks":[],"edits":{},"persisted":{},
        "evicted":[],"chunk_loads":0,"chunk_evictions":0,
        "inventory":{"wood":config["starting_wood"],"stone":config["starting_stone"],
                     "ore":0,"food":config["starting_food"],"water":config["starting_water"],
                     "seed":config["starting_seeds"],"tool":0},
        "health":config["health"],"energy":config["energy"],"thirst":0,
        "structures_built":0,"tiles_harvested":0,"craft_count":0,
        "save_count":0,"checkpoint_count":0,"expedition_complete":False,
        "retired":False,"score":0,"finished":False,"failed":False,"events":[],
    }
    _touch(state,config,0,0)
    return state


def apply_scene(state,config,layout):
    scene=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise ProceduralWorldActionError("original world cannot change while explored")
    state["title"]=scene["title"]
    state["climate"]=scene["climate"]
    state["position"]=list(scene["origin"])
    state["landmarks"]=[{"id":m["id"],"at":list(m["at"]),"kind":m["kind"]}
                        for m in scene["landmarks"]]


def _same_chunk(tile_key,chunk_key,size):
    x,y=map(int,tile_key.split(":"))
    return _chunk_key(x,y,size)==chunk_key


def _touch(state,config,x,y):
    key=_chunk_key(x,y,config["chunk_size"])
    if key not in state["chunks"]:
        if len(state["chunks"])>=config["active_chunks"]:
            oldest=state["chunks"].pop(0)
            state["chunk_evictions"]+=1
            state["evicted"].append(oldest)
            # Rebuild mode deliberately forgets edits. Save-deltas retains
            # explicitly committed edits, while snapshot auto-commits on unload.
            affected=[k for k in state["edits"] if
                      _same_chunk(k,oldest,config["chunk_size"])]
            for tile in affected:
                if config["persistence"]=="snapshot":
                    state["persisted"][tile]=dict(state["edits"][tile])
                del state["edits"][tile]
        state["chunks"].append(key)
        state["chunk_loads"]+=1
        if key not in state["visited_chunks"]:
            if len(state["visited_chunks"])<config["exploration_budget"]:
                state["visited_chunks"].append(key)
    else:
        state["chunks"].remove(key)
        state["chunks"].append(key)


def _read(state,config,x,y):
    key=_tile_key(x,y)
    return dict(state["edits"].get(key,state["persisted"].get(
        key,_source_tile(config,state["seed"],x,y)
    )))


def _write(state,config,x,y,tile):
    key=_tile_key(x,y)
    if key not in state["edits"] and len(state["edits"])>=config["max_edited_tiles"]:
        raise ProceduralWorldActionError("bounded active tile-change budget exhausted")
    state["edits"][key]=dict(tile)


def _spend(state,material,count):
    if state["inventory"][material]<count:
        raise ProceduralWorldActionError("finite original inventory cannot be forged")
    state["inventory"][material]-=count


def step(state,config,action):
    if action not in ACTIONS:
        raise ProceduralWorldActionError("unregistered original frontier input")
    if state["failed"] or state["finished"]:
        raise ProceduralWorldActionError("terminated original expedition cannot advance")
    events=[]
    x,y=state["position"]
    if action in MOVES:
        dx,dy=MOVES[action]
        if (abs(x+dx)>config["world_radius_chunks"]*config["chunk_size"] or
            abs(y+dy)>config["world_radius_chunks"]*config["chunk_size"]):
            events.append("authored_world_limit_reached")
        else:
            cost=2 if action.startswith("sprint") else 1
            if state["energy"]<cost:
                raise ProceduralWorldActionError("insufficient actual exploration stamina")
            state["energy"]-=cost
            state["position"]=[x+dx,y+dy]
            _touch(state,config,x+dx,y+dy)
            events.append("original_chunk_world_travel")
    elif action=="survey":
        marks=[m for m in state["landmarks"] if m["at"]==state["position"]]
        if not marks:
            raise ProceduralWorldActionError("cartography requires a physical landmark")
        target=marks[0]
        if target["id"] in state["surveyed"]:
            raise ProceduralWorldActionError("original survey reward already earned")
        state["surveyed"].append(target["id"])
        state["surveyed"].sort()
        state["score"]+=config["survey_reward"]
        events.append("physical_original_landmark_surveyed")
    elif action in ("harvest","mine"):
        tile=_read(state,config,x,y)
        resources=("wood","food","water") if action=="harvest" else ("stone","ore")
        if tile["material"] not in resources or tile["units"]<=0:
            raise ProceduralWorldActionError("resource extraction requires remaining biome material")
        material=tile["material"]
        state["inventory"][material]+=1
        tile["units"]-=1
        _write(state,config,x,y,tile)
        state["tiles_harvested"]+=1
        events.append("finite_biome_material_extracted")
    elif action=="plant":
        tile=_read(state,config,x,y)
        if tile["planted"] or tile["structure"]!="none":
            raise ProceduralWorldActionError("planting requires free unplanted world terrain")
        _spend(state,"seed",1)
        tile["planted"]=True
        _write(state,config,x,y,tile)
        events.append("original_terrain_planted")
    elif action=="build":
        tile=_read(state,config,x,y)
        if tile["structure"]!="none":
            raise ProceduralWorldActionError("a physical cell cannot hold duplicate structures")
        if (state["inventory"]["wood"]<config["shelter_wood"] or
            state["inventory"]["stone"]<config["shelter_stone"]):
            raise ProceduralWorldActionError("original structure requires conserved local resources")
        _spend(state,"wood",config["shelter_wood"])
        _spend(state,"stone",config["shelter_stone"])
        tile["structure"]="shelter"
        _write(state,config,x,y,tile)
        state["structures_built"]+=1
        events.append("material_conserving_original_shelter_built")
    elif action=="dismantle":
        tile=_read(state,config,x,y)
        if tile["structure"]!="shelter":
            raise ProceduralWorldActionError("can only dismantle a real original structure")
        tile["structure"]="none"
        _write(state,config,x,y,tile)
        state["inventory"]["wood"]+=config["shelter_wood"]//2
        state["inventory"]["stone"]+=config["shelter_stone"]//2
        events.append("lossy_original_structure_deconstruction")
    elif action=="drink":
        _spend(state,"water",1)
        state["thirst"]=max(0,state["thirst"]-config["hydration_gain"])
        events.append("finite_water_consumed")
    elif action=="rest":
        _spend(state,"food",1)
        state["energy"]=min(config["energy"],state["energy"]+config["rest_energy"])
        tile=_read(state,config,x,y)
        if tile["structure"]=="shelter":
            state["health"]=min(config["health"],state["health"]+config["shelter_healing"])
        events.append("finite_survival_rest")
    elif action=="craft":
        if (state["inventory"]["stone"]<config["tool_stone"] or
            state["inventory"]["ore"]<config["tool_ore"]):
            raise ProceduralWorldActionError("tool creation requires finite source minerals")
        _spend(state,"stone",config["tool_stone"])
        _spend(state,"ore",config["tool_ore"])
        state["inventory"]["tool"]+=1
        state["craft_count"]+=1
        events.append("original_finite_tool_crafted")
    elif action=="save":
        if config["persistence"]=="rebuild":
            raise ProceduralWorldActionError("regenerating worlds do not persist edited tiles")
        state["persisted"].update({k:dict(v) for k,v in state["edits"].items()})
        state["save_count"]+=1
        events.append("source_bound_world_delta_committed")
    elif action=="checkpoint":
        if len(state["surveyed"])<len(state["landmarks"]):
            raise ProceduralWorldActionError("original expedition requires actual landmark surveys")
        if state["expedition_complete"]:
            raise ProceduralWorldActionError("one expedition cannot mint duplicate rewards")
        state["expedition_complete"]=True
        state["checkpoint_count"]+=1
        state["score"]+=config["expedition_bonus"]
        events.append("nonterminal_original_world_checkpoint")
    elif action=="retire":
        if not state["expedition_complete"] or state["position"]!=[0,0]:
            raise ProceduralWorldActionError("retirement requires explored world and real home return")
        state["retired"]=state["finished"]=True
        events.append("voluntary_original_frontier_retirement")
    state["tick"]+=1
    if action.startswith("sprint"):
        state["thirst"]+=config["sprint_thirst"]
    if state["tick"]%config["thirst_period"]==0:
        state["thirst"]+=1
    if state["thirst"]>=config["thirst_limit"]:
        state["health"]=max(0,state["health"]-config["dehydration_damage"])
        events.append("environmental_dehydration")
    if state["health"]<=0 or state["tick"]>=config["turn_limit"]:
        state["failed"]=True
        events.append("frontier_survival_failed")
    state["events"]=events
    return events
