"""Original bounded labyrinth game with five genuine spatial topologies.

Includes guarded grid, angular wrap, braided diagonal paths, timed shifting
barriers, and authored non-Euclidean portals. Every action is integer
deterministic; level data are exact source, never executable or external IP.
This is a reference engine, not a native console or platform certification.
"""
from __future__ import annotations

TOPOLOGIES=("grid","circular","braided","moving","non_euclidean")
ACTIONS=("north","south","east","west","northeast","northwest",
         "southeast","southwest","ascend","descend","wait",
         "warp","open","light_torch","rest","inspect","finish")
CARDINAL={"north":(0,1),"south":(0,-1),"east":(1,0),"west":(-1,0)}
DIAGONAL={"northeast":(1,1),"northwest":(-1,1),
          "southeast":(1,-1),"southwest":(-1,-1)}


class MazeActionError(ValueError):
    """Malformed labyrinth, illegal action, or unearned original exit."""


def _int(value,lo,hi,field):
    if type(value) is not int or not lo<=value<=hi:
        raise MazeActionError("invalid original labyrinth "+field)
    return value


def _point(value,config,name):
    if type(value) is not list or len(value)!=3:
        raise MazeActionError("strict three-dimensional maze coordinate required: "+name)
    return [
        _int(value[0],1,config["width"]-2,name+".x"),
        _int(value[1],1,config["height"]-2,name+".y"),
        _int(value[2],0,config["levels"]-1,name+".level"),
    ]


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    w,h,lv=config["width"],config["height"],config["levels"]
    stairs=[[w-3,1,z] for z in range(lv)]
    key_points=[]
    reserved={(1,1,0),(w-2,h-2,lv-1),(w-2,h-3,lv-1),
              *(tuple(p) for p in stairs)}
    # Deterministic, finite enumeration: stop after the authored budget.
    for z in range(lv):
        for y in range(1,h-1):
            for x in range(1,w-1):
                p=(x,y,z)
                if p in reserved:continue
                if len(key_points)<config["key_count"]:
                    key_points.append(list(p));reserved.add(p)
                if len(key_points)==config["key_count"]:break
            if len(key_points)==config["key_count"]:break
        if len(key_points)==config["key_count"]:break
    walls=[]
    for y in range(2,h-1):
        for x in range(2,w-1):
            p=(x,y,0)
            if p not in reserved and (x+y+seed)%4==0:
                walls.append({"at":list(p),"phase":len(walls)%2})
                reserved.add(p)
            if len(walls)>=min(config["wall_budget"],16):break
        if len(walls)>=min(config["wall_budget"],16):break
    hazards=[]
    for z in range(lv):
        for y in range(1,h-1):
            for x in range(1,w-1):
                p=(x,y,z)
                if p in reserved:continue
                hazards.append(list(p));reserved.add(p)
                if len(hazards)>=config["hazards"]:break
            if len(hazards)>=config["hazards"]:break
        if len(hazards)>=config["hazards"]:break
    if config["hazards"]==0:hazards=[]
    portals=([
        {"entry":[1,h-3,0],"destination":[w-3,h-3,lv-1]}
    ] if config["topology"]=="non_euclidean" else [])
    # Portals are not privileged shortcuts to the exit: entering their
    # authored source cell and paying a finite action is compulsory.
    return {
        "title":"Original Living Labyrinth "+str(seed%1000),
        "topology":config["topology"],
        "start":[1,1,0],
        "exit":[w-2,h-2,lv-1],
        "keys":key_points,
        "door":[w-2,h-3,lv-1],
        "stairs":stairs,
        "walls":walls,"hazards":hazards,"portals":portals,
        "phase_offset":seed%2,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","topology","start","exit","keys","door","stairs",
        "walls","hazards","portals","phase_offset"
    }:
        raise MazeActionError("original maze requires exact authored topology schema")
    name=layout["title"]
    if type(name) is not str or not 3<=len(name)<=64 or not all(
        ch.isalnum() or ch in " _-" for ch in name
    ):
        raise MazeActionError("unsafe original level title")
    topology=layout["topology"]
    if type(topology) is not str or topology!=config["topology"] or topology not in TOPOLOGIES:
        raise MazeActionError("topology cannot bypass reviewed original engine rules")
    start=_point(layout["start"],config,"start")
    end=_point(layout["exit"],config,"exit")
    door=_point(layout["door"],config,"locked door")
    if start!=[1,1,0] or end!=[config["width"]-2,config["height"]-2,config["levels"]-1]:
        raise MazeActionError("authored maze cannot move its origin or full-route destination")
    if door==start or door==end:
        raise MazeActionError("door cannot overwrite spawn or exit")
    stairs=layout["stairs"]
    if type(stairs) is not list or len(stairs)!=config["levels"]:
        raise MazeActionError("one authored stair must exist on every traversable floor")
    safe_stairs=[_point(v,config,"stair") for v in stairs]
    if any(p[2]!=i for i,p in enumerate(safe_stairs)):
        raise MazeActionError("stairs must retain ordered level traversal")
    if any(p in (start,end,door) for p in safe_stairs):
        raise MazeActionError("stairs overlap a source-fixed objective")
    keys=layout["keys"]
    if type(keys) is not list or len(keys)!=config["key_count"]:
        raise MazeActionError("keys must match original finite puzzle budget")
    safe_keys=[_point(k,config,"key") for k in keys]
    if len({tuple(k) for k in safe_keys})!=len(safe_keys) or any(
        k in (start,end,door) or k in safe_stairs for k in safe_keys
    ):
        raise MazeActionError("keys must be distinct, reachable physical tiles")
    walls=layout["walls"]
    if type(walls) is not list or len(walls)>config["wall_budget"]:
        raise MazeActionError("maze wall budget exceeded")
    safe_walls=[]
    used={tuple(start),tuple(end),tuple(door),
          *(tuple(k) for k in safe_keys),*(tuple(k) for k in safe_stairs)}
    for wall in walls:
        if type(wall) is not dict or set(wall)!={"at","phase"}:
            raise MazeActionError("exact phased wall schema required")
        p=_point(wall["at"],config,"wall")
        phase=_int(wall["phase"],0,1,"wall phase")
        if tuple(p) in used:
            raise MazeActionError("walls cannot overwrite objectives or overlap")
        if topology!="moving" and phase!=0:
            # Static walls are phase independent outside moving labyrinths.
            phase=0
        safe_walls.append({"at":p,"phase":phase})
        used.add(tuple(p))
    safe_hazards=[]
    hazards=layout["hazards"]
    if type(hazards) is not list or len(hazards)!=config["hazards"]:
        raise MazeActionError("exact bounded hazard budget required")
    for item in hazards:
        p=_point(item,config,"hazard")
        if tuple(p) in used:
            raise MazeActionError("hazard overlaps authored objective or another object")
        safe_hazards.append(p);used.add(tuple(p))
    portals=layout["portals"]
    if type(portals) is not list or len(portals)!=(1 if topology=="non_euclidean" else 0):
        raise MazeActionError("portals only exist in authored non-Euclidean worlds")
    safe_portals=[]
    for portal in portals:
        if type(portal) is not dict or set(portal)!={"entry","destination"}:
            raise MazeActionError("portal pair requires exact source and destination")
        entry=_point(portal["entry"],config,"portal entry")
        target=_point(portal["destination"],config,"portal destination")
        if entry==target or entry in (start,end,door) or target in (start,end,door):
            raise MazeActionError("portals cannot mint destination or override locked gate")
        if entry in safe_keys or target in safe_keys or entry in safe_hazards or target in safe_hazards:
            raise MazeActionError("portal cannot overlap finite puzzle resources")
        if any(entry==w["at"] or target==w["at"] for w in safe_walls):
            raise MazeActionError("portals cannot bypass solid wall collision")
        safe_portals.append({"entry":entry,"destination":target})
    if any(portal["entry"] in safe_stairs or portal["destination"] in safe_stairs
           for portal in safe_portals):
        raise MazeActionError("portals cannot become arbitrary inter-floor stairways")
    offset=_int(layout["phase_offset"],0,1,"phase offset")
    return {
        "title":name,"topology":topology,"start":start,"exit":end,
        "keys":safe_keys,"door":door,"stairs":safe_stairs,
        "walls":safe_walls,"hazards":safe_hazards,"portals":safe_portals,
        "phase_offset":offset,
    }


def start(config,seed):
    source=normalize_layout(config,default_layout(config,seed))
    return {
        "tick":0,"position":list(source["start"]),"exit":list(source["exit"]),
        "door":list(source["door"]),"keys":source["keys"],"collected_keys":[],
        "stairs":source["stairs"],"walls":source["walls"],
        "hazards":source["hazards"],"portals":source["portals"],
        "topology":source["topology"],"title":source["title"],
        "phase_offset":source["phase_offset"],"phase":source["phase_offset"],
        "health":config["health"],"stamina":config["stamina"],
        "torches":config["torches"],"light":0,
        "score":0,"collisions":0,"hazard_hits":0,
        "floor_visits":[0],"portal_uses":0,"door_open":False,
        "explored":[list(source["start"])],"events":[],
        "finished":False,"failed":False,
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise MazeActionError("maze source cannot mutate an active run")
    for name,value in source.items():
        if name=="start":state["position"]=list(value)
        elif name=="phase_offset":
            state["phase_offset"]=value;state["phase"]=value
        elif name in ("title","topology","exit","door","keys","stairs",
                      "walls","hazards","portals"):
            state[name]=([dict(v) for v in value] if name in ("walls","portals")
                         else [list(v) for v in value] if name in ("keys","stairs","hazards")
                         else list(value) if name in ("exit","door") else value)
    state["explored"]=[list(state["position"])]


def _blocked(state,config,point):
    if point==state["door"] and not state["door_open"]:
        return "locked_gate"
    for wall in state["walls"]:
        if point==wall["at"] and (
            state["topology"]!="moving" or wall["phase"]==state["phase"]
        ):
            return "solid_dynamic_wall"
    return None


def step(state,config,action):
    if action not in ACTIONS:
        raise MazeActionError("unregistered original labyrinth traversal")
    if state["finished"] or state["failed"]:
        raise MazeActionError("terminated maze cannot continue")
    if action=="finish":
        if (state["position"]!=state["exit"] or not state["door_open"] or
            len(state["collected_keys"])!=len(state["keys"])):
            raise MazeActionError("physical exit, door and all keys required")
        state["tick"]+=1
        state["finished"]=True
        state["score"]+=config["completion_bonus"]+state["health"]
        state["events"]=["earned_original_labyrinth_exit"]
        return state["events"]
    if action in DIAGONAL and state["topology"]!="braided":
        raise MazeActionError("diagonal connections require actual braided topology")
    events=[]
    position=list(state["position"])
    destination=list(position)
    cost=0
    if action in CARDINAL or action in DIAGONAL:
        dx,dy=(CARDINAL if action in CARDINAL else DIAGONAL)[action]
        nx=position[0]+dx
        ny=position[1]+dy
        if state["topology"]=="circular":
            nx=1+(nx-1)%(config["width"]-2)
        elif not 1<=nx<=config["width"]-2:
            events.append("bounded_x_collision");nx=position[0]
        if not 1<=ny<=config["height"]-2:
            events.append("bounded_y_collision");ny=position[1]
        destination=[nx,ny,position[2]]
        cost=config["move_cost"]+(config["diagonal_cost"] if action in DIAGONAL else 0)
    elif action in ("ascend","descend"):
        delta=1 if action=="ascend" else -1
        if position not in state["stairs"] or not 0<=position[2]+delta<config["levels"]:
            raise MazeActionError("floor transitions require physical authored stairs")
        destination=[position[0],position[1],position[2]+delta]
        cost=config["stair_cost"]
    elif action=="warp":
        pair=next((x for x in state["portals"] if x["entry"]==position),None)
        if state["topology"]!="non_euclidean" or pair is None:
            raise MazeActionError("non-Euclidean jump requires occupied authored portal")
        destination=list(pair["destination"])
        cost=config["portal_cost"]
    elif action=="open":
        if len(state["collected_keys"])!=len(state["keys"]):
            raise MazeActionError("all actual keys required to open source-bound door")
        if sum(abs(a-b) for a,b in zip(position,state["door"]))!=1:
            raise MazeActionError("locked gate must be approached physically")
        state["door_open"]=True;events.append("original_key_gate_opened")
    elif action=="light_torch":
        if state["torches"]<=0:
            raise MazeActionError("finite original light source depleted")
        state["torches"]-=1;state["light"]=config["torch_duration"]
        events.append("finite_torch_lit")
    elif action=="rest":
        state["stamina"]=min(config["stamina"],state["stamina"]+config["rest_recovery"])
        events.append("labyrinth_rest")
    if cost>state["stamina"]:
        raise MazeActionError("exhausted runner cannot pay movement cost")
    if cost:
        state["stamina"]-=cost
        if destination!=position:
            # Braided diagonals cannot slip through two blocked adjacent cells.
            if action in DIAGONAL:
                a=[destination[0],position[1],position[2]]
                b=[position[0],destination[1],position[2]]
                if _blocked(state,config,a) and _blocked(state,config,b):
                    destination=position;events.append("diagonal_corner_blocked")
            blocked=_blocked(state,config,destination)
            if blocked:
                destination=position;state["collisions"]+=1;events.append(blocked)
            else:
                state["position"]=destination
                if destination[2] not in state["floor_visits"]:
                    state["floor_visits"].append(destination[2])
                if destination not in state["explored"]:
                    if len(state["explored"])<config["exploration_budget"]:
                        state["explored"].append(list(destination))
                if destination in state["keys"] and destination not in state["collected_keys"]:
                    state["collected_keys"].append(list(destination))
                    state["score"]+=config["key_reward"]
                    events.append("physical_key_collected")
                if action=="warp":
                    state["portal_uses"]+=1
                    events.append("authored_portal_traversal")
                if destination in state["hazards"]:
                    state["health"]=max(0,state["health"]-config["hazard_damage"])
                    state["hazard_hits"]+=1
                    events.append("maze_hazard_damage")
    state["tick"]+=1
    if state["light"]>0:state["light"]-=1
    if state["topology"]=="moving":
        phase=(state["tick"]//config["phase_period"]+state["phase_offset"])%2
        if phase!=state["phase"]:
            state["phase"]=phase;events.append("dynamic_wall_phase_shift")
            if _blocked(state,config,state["position"]):
                state["health"]=max(0,state["health"]-config["crush_damage"])
                events.append("moving_labyrinth_crush")
    if action=="wait" and state["light"]==0 and state["topology"]=="moving":
        events.append("waited_for_wall_phase")
    if state["health"]<=0 or state["tick"]>=config["turn_limit"]:
        state["failed"]=True;events.append("labyrinth_run_failed")
    state["events"]=events
    return events
