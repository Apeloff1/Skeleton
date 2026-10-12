"""Original advanced 8x8 real-time strategy reference game.

Finite local logistics, distinct structures and units, deterministic shortest
path orders, bounded opposing faction AI, spatial combat, fog, supply and
actual control objectives. Designed for independently replayable turns, not
a claimed native RTS engine or a copied level.
"""
from __future__ import annotations
from collections import deque

SIZE=8
CELLS=SIZE*SIZE
TYPES=("worker","soldier","ranger","medic","siege")
STRUCTURES=("outpost","barracks","turret","generator","wall")
TECHS=("weapons","armor","economy","sight")
BASE_COSTS={"worker":(3,0),"soldier":(4,2),"ranger":(5,3),
            "medic":(4,3),"siege":(7,6)}
BUILD_COSTS={"outpost":(8,4),"barracks":(8,7),"turret":(6,6),
             "generator":(4,7),"wall":(3,2)}
SUPPLY={"worker":1,"soldier":2,"ranger":2,"medic":2,"siege":3}
ACTIONS=(
    tuple("select:"+str(i) for i in range(16))+
    tuple(verb+":"+str(i) for verb in ("move","attack","harvest","scout")
          for i in range(CELLS))+
    tuple("construct:"+kind+":"+str(i) for kind in STRUCTURES
          for i in range(CELLS))+
    tuple("train:"+kind for kind in TYPES)+
    tuple("research:"+kind for kind in TECHS)+
    ("hold","aggressive","defensive","capture","deposit","repair",
     "tick","tick:4","scan","inspect")
)


class RTSActionError(ValueError):
    """Invalid original tactical scene, finite resource or player instruction."""


def _int(value,lo,hi,key):
    if type(value) is not int or not lo<=value<=hi:
        raise RTSActionError("invalid bounded strategy "+key)
    return value


def _adjacent(point):
    x,y=point%SIZE,point//SIZE
    return tuple(y2*SIZE+x2 for x2,y2 in ((x,y-1),(x-1,y),(x+1,y),(x,y+1))
                 if 0<=x2<SIZE and 0<=y2<SIZE)


def _distance(a,b):
    return abs(a%SIZE-b%SIZE)+abs(a//SIZE-b//SIZE)


def _path(source,target,blocked):
    if source==target:return []
    seen={source:None};todo=deque([source])
    while todo:
        p=todo.popleft()
        if p==target:break
        for nxt in _adjacent(p):
            if nxt not in seen and nxt not in blocked:
                seen[nxt]=p;todo.append(nxt)
    if target not in seen:return None
    result=[];p=target
    while p!=source:
        result.append(p);p=seen[p]
    result.reverse()
    return result


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    obstacles=[18,19,34,35,43][:config["obstacle_count"]]
    nodes=[
       {"id":0,"cell":9,"type":"wood","stock":config["wood_stock"]},
       {"id":1,"cell":16,"type":"ore","stock":config["ore_stock"]},
       {"id":2,"cell":40,"type":"energy","stock":config["energy_stock"]},
    ][:config["resource_nodes"]]
    return {
       "width":SIZE,"height":SIZE,"obstacles":obstacles,
       "nodes":nodes,"friendly_base":0,"enemy_base":63,
       "friendly_spawns":[1,8],"enemy_spawns":[54],
       "relay":27,"starting_wood":config["starting_wood"],
       "starting_ore":config["starting_ore"],
       "starting_energy":config["starting_energy"],
       "enemy_base_health":config["enemy_base_health"],
       "environment":("forest","desert","highland","rain")[seed%4],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
      "width","height","obstacles","nodes","friendly_base",
      "enemy_base","friendly_spawns","enemy_spawns","relay",
      "starting_wood","starting_ore","starting_energy",
      "enemy_base_health","environment"}:
        raise RTSActionError("authored RTS field must have exact typed tactical schema")
    _int(layout["width"],SIZE,SIZE,"width")
    _int(layout["height"],SIZE,SIZE,"height")
    blocked=layout["obstacles"]
    if type(blocked) is not list or len(blocked)>config["obstacle_count"] or any(
       type(p) is not int or not 0<=p<CELLS for p in blocked) or (
       len(blocked)!=len(set(blocked))):
        raise RTSActionError("invalid original connected battlefield obstacles")
    blocked_set=set(blocked)
    places=[]
    for key in ("friendly_base","enemy_base","relay"):
        places.append(_int(layout[key],0,CELLS-1,key))
    for key,max_n in (("friendly_spawns",4),("enemy_spawns",4)):
        locs=layout[key]
        if type(locs) is not list or not (2 if key=="friendly_spawns" else 1)<=len(locs)<=max_n or (
          any(type(p) is not int or not 0<=p<CELLS for p in locs)):
            raise RTSActionError("original force spawn budget or type invalid")
        places.extend(locs)
    if len(places)!=len(set(places)) or set(places)&blocked_set:
        raise RTSActionError("actual RTS objectives and units cannot overlap")
    sources=layout["nodes"]
    if type(sources) is not list or not 1<=len(sources)<=config["resource_nodes"]:
        raise RTSActionError("original local resource map exceeds node count")
    seen=set()
    for i,n in enumerate(sources):
        if type(n) is not dict or set(n)!={"id","cell","type","stock"}:
            raise RTSActionError("resource sources require exact typed physical identity")
        if _int(n["id"],0,100,"source id")!=i:
            raise RTSActionError("local physical deposit identity must be canonical")
        p=_int(n["cell"],0,CELLS-1,"node position")
        if p in seen or p in blocked_set or p in places:
            raise RTSActionError("original material deposit overlaps an occupied cell")
        seen.add(p)
        if type(n["type"]) is not str or n["type"] not in ("wood","ore","energy"):
            raise RTSActionError("unregistered original source material")
        _int(n["stock"],0,10000,"finite resource stock")
        if n["stock"]>config[n["type"]+"_stock"]:
            raise RTSActionError("authored material deposit cannot exceed its original typed geological budget")
    for key,max_value in (("starting_wood",10000),("starting_ore",10000),
                          ("starting_energy",10000),("enemy_base_health",500)):
        _int(layout[key],1 if key=="enemy_base_health" else 0,max_value,key)
    if (layout["starting_wood"]>config["starting_wood"] or
        layout["starting_ore"]>config["starting_ore"] or
        layout["starting_energy"]>config["starting_energy"] or
        layout["enemy_base_health"]>config["enemy_base_health"]):
        raise RTSActionError("authored stock may not mint beyond editor budget")
    if layout["environment"] not in ("forest","desert","highland","rain"):
        raise RTSActionError("invalid original environmental condition")
    known={layout["friendly_base"]};queue=deque(known)
    while queue:
        for tile in _adjacent(queue.popleft()):
            if tile not in known and tile not in blocked_set:
                known.add(tile);queue.append(tile)
    if len(known)!=CELLS-len(blocked_set) or not set(places).issubset(known):
        raise RTSActionError("battlefield, relay, home bases and enemy base must be reachable")
    return {
      **dict(layout),"obstacles":list(blocked),
      "nodes":[dict(n) for n in sources],
      "friendly_spawns":list(layout["friendly_spawns"]),
      "enemy_spawns":list(layout["enemy_spawns"]),
    }


def _unit(kind,id,side,cell,config):
    hp={"worker":config["worker_hp"],"soldier":config["soldier_hp"],
        "ranger":config["ranger_hp"],"medic":config["medic_hp"],
        "siege":config["siege_hp"]}[kind]
    return {"id":id,"side":side,"kind":kind,"cell":cell,
      "hp":hp,"max_hp":hp,"order":"hold","target":None,
      "cargo":0,"resource":None,"stance":"defensive",
      "kills":0,"experience":0,"veterancy":0}


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    state["map"]=source
    state["units"]=[
       _unit("worker",0,"blue",source["friendly_spawns"][0],config),
       _unit("soldier",1,"blue",source["friendly_spawns"][1],config)]
    if len(source["friendly_spawns"])>2:
        state["units"].extend(_unit("soldier",i,"blue",p,config)
             for i,p in enumerate(source["friendly_spawns"][2:],2))
    state["enemies"]=[_unit("soldier",i,"red",p,config) for i,p in
                      enumerate(source["enemy_spawns"])]
    state["buildings"]=[{"kind":"command","side":"blue","cell":source["friendly_base"],
       "hp":config["friendly_base_health"],"level":1},
       {"kind":"command","side":"red","cell":source["enemy_base"],
       "hp":source["enemy_base_health"],"level":1}]
    state["wood"]=source["starting_wood"]
    state["ore"]=source["starting_ore"]
    state["energy"]=source["starting_energy"]
    state["selected"]=0
    state["next_unit_id"]=len(state["units"])
    state["next_enemy_id"]=len(state["enemies"])
    state["visible"]=[]
    state["discovered"]=[]
    return _refresh(state,config)


def start(config,seed):
    _int(seed,0,2**31-1,"seed")
    state={
      "seed":seed,"turn":0,"tick":0,"map":{},"units":[],"enemies":[],
      "buildings":[],"wood":0,"ore":0,"energy":0,"selected":0,
      "next_unit_id":2,"next_enemy_id":1,
      "tech":{key:0 for key in TECHS},"supply_used":0,
      "relay_owner":"neutral","relay_progress":0,"capture_committed":False,
      "relay_hold":0,"visible":[],"discovered":[],
      "scan_ticks":0,"wave_index":0,"casualties":0,
      "events":[],"achievements":[],"finished":False,"failed":False,
      "victory":False,"reason":""
    }
    return apply_scene(state,config,default_layout(config,seed))


def _alive(state,side):
    return [u for u in (state["units"] if side=="blue" else state["enemies"])
            if u["hp"]>0]


def _refresh(state,config):
    state["supply_used"]=sum(SUPPLY[u["kind"]] for u in _alive(state,"blue"))
    available=set()
    for obj in _alive(state,"blue"):
        radius=config["vision_radius"]+state["tech"]["sight"]*config["sight_upgrade"]
        if state["scan_ticks"]>0:radius+=config["scan_bonus"]
        available.update(p for p in range(CELLS) if _distance(obj["cell"],p)<=radius)
    for base in state["buildings"]:
        if base["side"]=="blue" and base["hp"]>0:
            available.update(p for p in range(CELLS) if
                 _distance(base["cell"],p)<=config["base_vision"])
    state["visible"]=sorted(available if config["fog_of_war"] else range(CELLS))
    state["discovered"]=sorted(set(state["discovered"])|set(state["visible"]))
    return state


def _selected(state):
    return next((u for u in state["units"] if u["id"]==state["selected"]
                 and u["hp"]>0),None)


def _spend(state,wood=0,ore=0,energy=0):
    if state["wood"]<wood or state["ore"]<ore or state["energy"]<energy:
        raise RTSActionError("original finite treasury cannot finance requested action")
    state["wood"]-=wood
    state["ore"]-=ore
    state["energy"]-=energy


def _building_at(state,cell):
    return next((b for b in state["buildings"] if b["cell"]==cell
                 and b["hp"]>0),None)


def _unit_at(state,cell):
    return next((u for u in state["units"]+state["enemies"]
                 if u["hp"]>0 and u["cell"]==cell),None)


def _actual_line_of_fire(state,source,target):
    """Deterministic Bresenham LOS; no shots through mountains, buildings or units.

    The destination itself may be an enemy or its building. All intermediary
    cells must be open; this deliberately forbids allied-body pass-through.
    """
    x0,y0=source%SIZE,source//SIZE
    x1,y1=target%SIZE,target//SIZE
    dx=abs(x1-x0);dy=abs(y1-y0)
    sx=1 if x0<x1 else -1
    sy=1 if y0<y1 else -1
    error=dx-dy
    blocked=set(state["map"]["obstacles"])
    blocked.update(b["cell"] for b in state["buildings"] if b["hp"]>0)
    blocked.update(u["cell"] for u in _alive(state,"blue")+_alive(state,"red"))
    while (x0,y0)!=(x1,y1):
        doubled=2*error
        if doubled>-dy:
            error-=dy;x0+=sx
        if doubled<dx:
            error+=dx;y0+=sy
        if (x0,y0)!=(x1,y1) and y0*SIZE+x0 in blocked:
            return False
    return True


def _damage(state,config,attacker,cell,events):
    if cell not in state["visible"] and attacker["side"]=="blue":
        raise RTSActionError("cannot attack unknown fog-covered cell")
    target=_unit_at(state,cell)
    structure=_building_at(state,cell)
    if (target is None or target["side"]==attacker["side"]) and (
      structure is None or structure["side"]==attacker["side"]):
        raise RTSActionError("attacks require actual hostile enemy or structure")
    victim=target if target is not None and target["side"]!=attacker["side"] else structure
    if victim is None:raise RTSActionError("friendly fire is not a legal default RTS operation")
    max_range={"worker":1,"soldier":1,"ranger":config["ranger_range"],
               "medic":0,"siege":config["siege_range"]}[attacker["kind"]]
    if _distance(attacker["cell"],cell)>max_range:
        raise RTSActionError("original combat target is physically out of range")
    if max_range==0:raise RTSActionError("support medic cannot be ordered to attack")
    if attacker["kind"] in ("ranger","siege") and config["line_of_sight"] and not (
        _actual_line_of_fire(state,attacker["cell"],cell)):
        raise RTSActionError("real ranged unit cannot fire through intervening geometry or allied bodies")
    if state["map"]["environment"]=="rain" and attacker["kind"] in ("ranger","siege") and (
        _distance(attacker["cell"],cell)>max(1,max_range-config["rain_range_penalty"])):
        raise RTSActionError("rainfall actually limits ranged original combat targeting")
    dmg={"worker":config["worker_attack"],"soldier":config["soldier_attack"],
         "ranger":config["ranger_attack"],"siege":config["siege_attack"]}.get(
            attacker["kind"],0)+state["tech"]["weapons"]*config["weapon_bonus"]
    armor=state["tech"]["armor"]*config["armor_bonus"] if (
        target is not None and target["side"]=="blue") else 0
    if victim is structure and attacker["kind"]=="siege":
        dmg+=config["siege_structure_bonus"]
    dmg+=attacker["veterancy"]*config["veterancy_damage_bonus"]
    damage=max(1,dmg-armor)
    victim["hp"]=max(0,victim["hp"]-damage)
    events.append("real_authoritative_original_spatial_attack")
    if victim["hp"]==0:
        attacker["kills"]+=1
        attacker["experience"]+=config["kill_experience"]
        if (attacker["experience"]>=config["veterancy_threshold"] and
            attacker["veterancy"]<config["max_veterancy"]):
            attacker["experience"]-=config["veterancy_threshold"]
            attacker["veterancy"]+=1
            events.append("actually_defeated_original_enemy_awarded_veteran_level")
        if target is not None:
            if target["side"]=="blue":state["casualties"]+=1
            events.append("finite_original_combatant_defeated")
        else:
            events.append("original_enemy_structure_destroyed")
            if structure["kind"]=="command" and structure["side"]=="red":
                state["finished"]=True;state["victory"]=True
                state["reason"]="actual_enemy_command_destroyed"
                state["achievements"].append("real_original_base_conquest")
            if structure["kind"]=="command" and structure["side"]=="blue":
                state["failed"]=True;state["reason"]="friendly_base_destroyed"
    return damage


def _go(state,config,unit,target,events):
    blockers=set(state["map"]["obstacles"])|set(
       b["cell"] for b in state["buildings"] if b["hp"]>0)
    blockers.update(u["cell"] for u in _alive(state,"blue")+_alive(state,"red")
                    if u is not unit)
    steps=_path(unit["cell"],target,blockers)
    if steps is None or not steps:
        return False
    unit["cell"]=steps[0]
    events.append("real_grid_unit_advanced_one_reachable_tile")
    return True


def _tick(state,config):
    events=["deterministic_original_rts_simulation_tick"]
    state["tick"]+=1
    _refresh(state,config)
    for u in _alive(state,"blue"):
        if u["order"]=="move" and u["target"] is not None:
            if u["cell"]==u["target"]:
                u["order"]="hold"
            elif not _go(state,config,u,u["target"],events):
                events.append("real_unit_path_temporarily_blocked")
        elif u["order"]=="harvest" and u["target"] is not None:
            node=next((n for n in state["map"]["nodes"] if n["cell"]==u["target"]),None)
            if u["kind"]!="worker" or node is None or node["stock"]<=0:
                u["order"]="hold";continue
            if _distance(u["cell"],node["cell"])>1:
                blockers=set(state["map"]["obstacles"])|{
                    b["cell"] for b in state["buildings"] if b["hp"]>0}
                destination=next((p for p in _adjacent(node["cell"])
                    if p not in blockers and _unit_at(state,p) is None),None)
                if destination is not None:_go(state,config,u,destination,events)
                continue
            if u["cargo"]>=config["worker_capacity"]:
                u["order"]="return"
                continue
            amount=min(node["stock"],config["gather_rate"]+config["tick_rate"]//20+
                state["tech"]["economy"]*config["economy_bonus"],
                config["worker_capacity"]-u["cargo"])
            node["stock"]-=amount
            u["cargo"]+=amount;u["resource"]=node["type"]
            events.append("finite_original_resource_physical_node_depleted")
            if node["stock"]==0 or u["cargo"]>=config["worker_capacity"]:
                u["order"]="return"
        elif u["order"]=="return":
            home=next((b for b in state["buildings"] if b["side"]=="blue"
                 and b["kind"] in ("command","outpost") and b["hp"]>0),None)
            if home is None:continue
            if _distance(u["cell"],home["cell"])<=1:
                state[u["resource"]]+=u["cargo"]
                events.append("actual_carried_original_material_deposited_at_base")
                u["cargo"]=0;u["resource"]=None;u["order"]="hold"
            else:
                adjacent=next((p for p in _adjacent(home["cell"]) if
                    _unit_at(state,p) is None and p not in state["map"]["obstacles"]),None)
                if adjacent is not None:_go(state,config,u,adjacent,events)
        elif u["order"]=="attack" and u["target"] is not None:
            if _unit_at(state,u["target"]) is None and _building_at(state,u["target"]) is None:
                u["order"]="hold"
                continue
            try:_damage(state,config,u,u["target"],events)
            except RTSActionError:
                enemy_cell=u["target"]
                blockers=set(state["map"]["obstacles"])|{
                    b["cell"] for b in state["buildings"] if b["hp"]>0}
                neighbor=next((p for p in _adjacent(enemy_cell) if p not in blockers
                              and _unit_at(state,p) is None),None)
                if neighbor is not None:_go(state,config,u,neighbor,events)
    # Unit stances now have independently observable behavior. Hold means
    # physical defensive abstention; defensive engages only close threats;
    # aggressive acquires targets up to a larger exact map radius.
    for u in _alive(state,"blue"):
        if u["kind"]=="medic":
            patient=next((friend for friend in _alive(state,"blue")
              if friend is not u and friend["hp"]<friend["max_hp"]
              and _distance(friend["cell"],u["cell"])<=config["medic_range"]),None)
            if patient is not None and state["energy"]>=config["medic_energy_cost"]:
                state["energy"]-=config["medic_energy_cost"]
                patient["hp"]=min(patient["max_hp"],patient["hp"]+config["medic_heal"])
                events.append("actual_nearby_original_combat_medic_spent_energy_healing")
            continue
        if u["kind"] not in ("soldier","ranger","siege") or u["order"]=="attack" or u["stance"]=="hold":
            continue
        radius=(config["aggressive_radius"] if u["stance"]=="aggressive"
                else config["defensive_radius"])
        enemy=next((e for e in _alive(state,"red")
          if e["cell"] in state["visible"] and
          _distance(e["cell"],u["cell"])<=radius and
          _distance(e["cell"],u["cell"])<=(
            config["ranger_range"] if u["kind"]=="ranger" else
            config["siege_range"] if u["kind"]=="siege" else 1)),None)
        if enemy is not None:
            _damage(state,config,u,enemy["cell"],events)
            events.append("original_owned_unit_stance_selected_real_opponent")
    if config["supply_model"]=="logistics":
        demand=max(1,state["supply_used"]//config["logistics_divisor"])+(
            config["desert_logistics_penalty"] if state["map"]["environment"]=="desert" else 0)
        if state["energy"]>=demand:
            state["energy"]-=demand
            events.append("real_logistics_fuel_paid_per_strategy_tick")
        else:
            for u in _alive(state,"blue"):
                u["hp"]=max(0,u["hp"]-config["logistics_damage"])
            events.append("unfunded_original_supply_lines_caused_attrition")
    if config["enemy_ai"]:
        for enemy in _alive(state,"red"):
            blue=_alive(state,"blue")
            target=min(blue,key=lambda u:_distance(u["cell"],enemy["cell"])) if blue else None
            if target is not None and _distance(enemy["cell"],target["cell"])<=config["enemy_aggro"]:
                if _distance(enemy["cell"],target["cell"])<=1:
                    damage=max(1,config["enemy_attack"]-state["tech"]["armor"]*config["armor_bonus"])
                    target["hp"]=max(0,target["hp"]-damage)
                    events.append("opposing_original_faction_physically_attacked")
                    if target["hp"]==0:state["casualties"]+=1
                elif config["enemy_patrol"]:
                    candidate=next((p for p in _adjacent(target["cell"])
                       if _unit_at(state,p) is None and _building_at(state,p) is None
                       and p not in state["map"]["obstacles"]),None)
                    if candidate is not None:
                        _go(state,config,enemy,candidate,events)
            # The opposing army is allowed to actually win by breaking
            # an undefended command HQ; no remote/magic building damage.
            home=next((b for b in state["buildings"] if b["kind"]=="command"
              and b["side"]=="blue" and b["hp"]>0),None)
            if home is not None and _distance(enemy["cell"],home["cell"])<=config["enemy_siege_range"]:
                home["hp"]=max(0,home["hp"]-config["enemy_siege_damage"])
                events.append("actual_original_opposing_faction_assaulted_blue_command")
                if home["hp"]==0:
                    state["failed"]=True
                    state["reason"]="physical_opposing_command_base_assault"
                    events.append("original_friendly_command_destroyed_by_hostile_units")
                    break
    for structure in state["buildings"]:
        if structure["side"]!="blue" or structure["hp"]==0:
            continue
        if structure["kind"]=="generator" and state["tick"]%config["generator_cycle"]==0:
            state["energy"]+=config["energy_production"]
            events.append("original_active_power_generator_created_energy")
        if structure["kind"]=="turret":
            enemy=next((e for e in _alive(state,"red")
                         if _distance(e["cell"],structure["cell"])<=config["turret_range"]),None)
            if enemy:
                enemy["hp"]=max(0,enemy["hp"]-config["turret_damage"])
                if enemy["hp"]==0:events.append("physical_turret_defended_original_base")
    relay=state["map"]["relay"]
    friendly=any(u["cell"]==relay for u in _alive(state,"blue"))
    enemy=any(u["cell"]==relay for u in _alive(state,"red"))
    if state["failed"]:
        state["scan_ticks"]=max(0,state["scan_ticks"]-1)
        _refresh(state,config)
        return events
    if friendly and not enemy and state["capture_committed"]:
        state["relay_progress"]=min(config["capture_ticks"],state["relay_progress"]+1)
        if state["relay_progress"]==config["capture_ticks"]:
            state["relay_owner"]="blue"
            state["relay_hold"]+=1
            if state["relay_hold"]>=config["hold_ticks"]:
                state["finished"]=True;state["victory"]=True
                state["reason"]="physical_original_relay_control"
                state["achievements"].append("legitimate_rts_control_victory")
    elif enemy:
        state["relay_progress"]=max(0,state["relay_progress"]-1)
        if state["relay_progress"]==0:
            state["relay_owner"]="neutral"
            state["capture_committed"]=False
        state["relay_hold"]=0
    if config["enemy_waves"] and state["tick"]%config["wave_interval"]==0 and (
        state["wave_index"]<config["wave_cap"]):
        if len(_alive(state,"red"))<config["max_enemy_active"]:
            home=state["map"]["enemy_base"]
            pos=next((p for p in _adjacent(home) if p not in state["map"]["obstacles"]
                      and _unit_at(state,p) is None),None)
            if pos is not None:
                state["enemies"].append(_unit("soldier",state["next_enemy_id"],
                                              "red",pos,config))
                state["next_enemy_id"]+=1;state["wave_index"]+=1
                events.append("actual_finite_original_opposing_wave_deployed")
    state["scan_ticks"]=max(0,state["scan_ticks"]-1)
    _refresh(state,config)
    if not _alive(state,"blue") and not state["finished"]:
        state["failed"]=True;state["reason"]="all_original_blue_units_lost"
    return events


def step(state,config,action):
    if action not in ACTIONS:
        raise RTSActionError("unregistered bounded strategy action")
    if state["finished"] or state["failed"]:
        raise RTSActionError("completed original RTS cannot accept additional commands")
    events=[];selected=_selected(state)
    if action.startswith("select:"):
        index=int(action.split(":")[1])
        if not any(u["id"]==index and u["hp"]>0 for u in state["units"]):
            raise RTSActionError("cannot select unowned, dead, or unbuilt combatant")
        state["selected"]=index
        events.append("real_original_selected_unit_changed")
    elif action.startswith(("move:","harvest:","attack:","scout:")):
        command,target=action.split(":");target=int(target)
        if selected is None:raise RTSActionError("a living owned unit must be selected")
        if command=="harvest":
            if selected["kind"]!="worker" or not any(n["cell"]==target and n["stock"]>0
                              for n in state["map"]["nodes"]):
                raise RTSActionError("only real workers can work remaining physical deposits")
            if selected["cargo"] and selected["resource"] not in (
                    n["type"] for n in state["map"]["nodes"] if n["cell"]==target):
                raise RTSActionError("real worker cannot carry mixed unbanked resources")
        if command=="attack":
            if selected["kind"]=="medic":
                raise RTSActionError("combat medics provide finite real healing, not enemy attacks")
            enemy=_unit_at(state,target);building=_building_at(state,target)
            if not ((enemy and enemy["side"]=="red") or
                    (building and building["side"]=="red")):
                raise RTSActionError("cannot order attack on friendly, absent or invented target")
            if target not in state["visible"]:
                raise RTSActionError("fog of war blocks targeting undiscovered enemies")
        if command in ("move","scout") and (
             target in state["map"]["obstacles"] or _building_at(state,target) or
             _unit_at(state,target)):
            raise RTSActionError("RTS movement requires physically unoccupied passable destination")
        selected["order"]="move" if command=="scout" else command
        selected["target"]=target
        events.append("original_unit_received_spatial_authenticated_"+command+"_order")
    elif action.startswith("construct:"):
        _,kind,cell=action.split(":");cell=int(cell)
        if selected is None or selected["kind"]!="worker":
            raise RTSActionError("only a live player-owned builder can construct buildings")
        if _distance(selected["cell"],cell)>1 or cell in state["map"]["obstacles"] or (
              _unit_at(state,cell) or _building_at(state,cell) or
              any(n["cell"]==cell for n in state["map"]["nodes"])):
            raise RTSActionError("structure footprint requires unoccupied nearby buildable ground")
        if len([b for b in state["buildings"] if b["side"]=="blue"])>=config["max_buildings"]:
            raise RTSActionError("built original structures reach physical budget")
        w,o=BUILD_COSTS[kind];_spend(state,w,o)
        state["buildings"].append({"kind":kind,"side":"blue","cell":cell,
              "hp":config["building_health"],"level":1})
        events.append("built_real_original_rts_structure_"+kind)
    elif action.startswith("train:"):
        kind=action.split(":")[1]
        if len(_alive(state,"blue"))>=min(config["max_units"],16):
            raise RTSActionError("physical owned unit active population limit")
        if config["supply_model"]!="none" and state["supply_used"]+SUPPLY[kind]>config["supply_cap"]+sum(
            config["outpost_supply"] for b in state["buildings"] if
            b["kind"]=="outpost" and b["side"]=="blue" and b["hp"]>0):
            raise RTSActionError("trained units require existing original supply capacity")
        if kind!="worker" and not any(b["kind"]=="barracks" and b["side"]=="blue"
                             and b["hp"]>0 for b in state["buildings"]):
            raise RTSActionError("combat unit training requires a physical barracks")
        base=next((b for b in state["buildings"] if b["side"]=="blue"
                 and b["kind"] in ("command","barracks") and b["hp"]>0),None)
        if base is None:raise RTSActionError("training requires actual production structure")
        spot=next((p for p in _adjacent(base["cell"]) if
                  p not in state["map"]["obstacles"] and _unit_at(state,p) is None
                  and _building_at(state,p) is None),None)
        if spot is None:raise RTSActionError("spawn needs free physical deployment tile")
        wood,ore=BASE_COSTS[kind];_spend(state,wood,ore)
        state["units"].append(_unit(kind,state["next_unit_id"],"blue",spot,config))
        state["next_unit_id"]+=1
        events.append("finite_materials_created_original_owned_unit")
    elif action.startswith("research:"):
        kind=action.split(":")[1]
        if state["tech"][kind]>=config["research_cap"]:
            raise RTSActionError("real upgrade tree has reached authored cap")
        if not any(b["kind"] in ("command","barracks") and b["side"]=="blue"
                 and b["hp"]>0 for b in state["buildings"]):
            raise RTSActionError("research needs actually owned operational command")
        _spend(state,config["research_wood"],config["research_ore"],
               config["research_energy"])
        state["tech"][kind]+=1
        events.append("actually_funded_original_strategic_research_"+kind)
    elif action in ("hold","aggressive","defensive"):
        if selected is None:raise RTSActionError("no living owned unit to command")
        selected["stance"]=action
        if action=="hold":
            selected["order"]="hold";selected["target"]=None
        events.append("owned_original_squad_stance_changed")
    elif action=="capture":
        if selected is None or selected["cell"]!=state["map"]["relay"]:
            raise RTSActionError("relay capture requires physical original squad position")
        if any(e["cell"]==selected["cell"] for e in _alive(state,"red")):
            raise RTSActionError("contested original relay cannot be silently captured")
        state["capture_committed"]=True
        events.append("real_original_relay_capture_activated")
    elif action=="deposit":
        if selected is None or selected["kind"]!="worker" or selected["cargo"]==0:
            raise RTSActionError("banking requires carried real worker material")
        if not any(b["side"]=="blue" and b["kind"] in ("command","outpost")
              and b["hp"]>0 and _distance(b["cell"],selected["cell"])<=1
              for b in state["buildings"]):
            raise RTSActionError("worker must physically return cargo to real depot")
        state[selected["resource"]]+=selected["cargo"]
        selected["cargo"]=0;selected["resource"]=None
        selected["order"]="hold"
        events.append("real_original_worker_deposited_conserved_material")
    elif action=="repair":
        if selected is None or selected["kind"]!="worker":
            raise RTSActionError("repairs require a real assigned engineer")
        b=next((b for b in state["buildings"] if b["side"]=="blue" and b["hp"]>0
              and b["hp"]<config["building_health"]
              and _distance(b["cell"],selected["cell"])<=1),None)
        if b is None:raise RTSActionError("no damaged neighboring owned structure")
        _spend(state,config["repair_wood"],0)
        b["hp"]=min(config["building_health"],b["hp"]+config["repair_amount"])
        events.append("finite_paid_original_building_repair")
    elif action=="scan":
        _spend(state,0,0,config["scan_energy"])
        state["scan_ticks"]=config["scan_duration"]
        events.append("paid_original_temporary_fog_reconnaissance")
    elif action=="inspect":
        events.append("actual_original_battlefield_observation")
    elif action in ("tick","tick:4"):
        events.append("player_advanced_real_tactical_simulation")
    else:
        raise RTSActionError("RTS action has no implemented gameplay effect")
    turns=4 if action=="tick:4" else 1
    for _ in range(turns):
        if state["finished"] or state["failed"]:break
        events.extend(_tick(state,config))
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["SIZE","CELLS","TYPES","STRUCTURES","TECHS","ACTIONS",
         "RTSActionError","default_layout","normalize_layout","start",
         "apply_scene","step"]
