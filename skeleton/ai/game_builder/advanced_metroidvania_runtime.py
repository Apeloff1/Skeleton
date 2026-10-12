"""Original advanced interconnected-exploration reference game.

A bounded twelve-region authored world has persistent enemy injuries, finite
treasure and healing, collectible movement abilities, bidirectional locks,
sequence-breaking risks, fast travel and a real boss. No client-owned state,
external game assets, generative shell execution or native-game claims.
"""
from __future__ import annotations
from collections import deque

POWERS=("dash","grapple","phase","swim","resonance")
BIOMES=("moss","ruins","canopy","cavern","water","spire","ash")
ROOM_LIMIT=12
ACTIONS=(
    tuple(f"travel:{i}" for i in range(ROOM_LIMIT))+
    tuple(f"break:{i}" for i in range(ROOM_LIMIT))+
    tuple(f"fast:{i}" for i in range(ROOM_LIMIT))+
    ("attack","heavy","guard","evade","rest","claim",
     "search","heal","camp","craft","focus","inspect")
)


class ExplorationActionError(ValueError):
    """Invalid original map, out-of-budget move or impossible transition."""


def _integer(v,lo,hi,name):
    if type(v) is not int or not lo<=v<=hi:
        raise ExplorationActionError("invalid bounded exploration "+name)
    return v


def default_layout(config,seed):
    _integer(seed,0,2**31-1,"seed")
    count=max(2,min(ROOM_LIMIT,config["regions"]))
    power_count=min(len(POWERS),config["abilities"],count-2)
    anchors=[0]
    for i in range(1,count):
        if len(anchors)>=config["fast_travel_nodes"]:
            break
        if i%(max(1,(count-1)//max(1,config["fast_travel_nodes"]-1)))==0:
            anchors.append(i)
    if config["fast_travel_nodes"]==0:
        anchors=[]
    rooms=[]
    for i in range(count):
        rooms.append({
            "id":i,"biome":BIOMES[(i+seed)%len(BIOMES)],
            "foe":0 if i==0 or i==count-1 else
                   config["foe_health"]+(i+seed)%config["foe_variation"],
            "hazard":0 if i==0 else (i+seed)%4,
            "ability":POWERS[i-1] if 1<=i<=power_count else None,
            "cache":2+(i+seed)%config["cache_variation"] if i else 0,
            "anchor":i in anchors,
            "secret":bool(i%config["secret_interval"]==0 and i>0),
        })
    passages=[]
    gated_limit=min(config["gates"],count-2)
    for i in range(count-1):
        # To enter i+1, the player must have acquired room i's movement relic.
        gate=POWERS[min(i-1,power_count-1)] if 1<=i<=gated_limit and power_count else None
        passages.append({"a":i,"b":i+1,"gate":gate,"breakable":i>0,"hazard":0})
    if count>=4 and len(passages)<24:
        # A nonlinear shortcut provides high-skill routing and replay variety
        # without bypassing the only critical gate chain by default.
        passages.append({"a":0,"b":3,"gate":POWERS[min(2,power_count-1)]
                         if power_count else None,
                         "breakable":True,"hazard":2})
    return {"rooms":rooms,"passages":passages,"entry":0,
            "guardian":count-1,"guardian_health":config["boss_health"],
            "guardian_element":("storm","ember","void")[seed%3]}


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "rooms","passages","entry","guardian","guardian_health",
        "guardian_element"}:
        raise ExplorationActionError("authored world needs exact typed rooms and portals")
    source=layout["rooms"]
    if type(source) is not list or not 2<=len(source)<=min(ROOM_LIMIT,config["regions"]):
        raise ExplorationActionError("authored world must contain 2..12 bounded regions")
    n=len(source)
    rooms=[];powers=set()
    for i,r in enumerate(source):
        if type(r) is not dict or set(r)!={
            "id","biome","foe","hazard","ability","cache","anchor","secret"}:
            raise ExplorationActionError("original region has unknown or missing schema fields")
        if _integer(r["id"],0,n-1,"region identity")!=i:
            raise ExplorationActionError("region ordering and identity must be canonical")
        if type(r["biome"]) is not str or r["biome"] not in BIOMES:
            raise ExplorationActionError("original region biome is not registered")
        for key,maximum in (("foe",1000),("hazard",20),("cache",100)):
            _integer(r[key],0,maximum,key)
        if type(r["anchor"]) is not bool or type(r["secret"]) is not bool:
            raise ExplorationActionError("anchors and secrets must be typed booleans")
        if r["ability"] is not None:
            if type(r["ability"]) is not str or r["ability"] not in POWERS:
                raise ExplorationActionError("unregistered authored movement ability")
            if r["ability"] in powers:
                raise ExplorationActionError("an ability cannot be farmed from duplicate shrines")
            powers.add(r["ability"])
        rooms.append(dict(r))
    if len(powers)>config["abilities"]:
        raise ExplorationActionError("authored ability count exceeds editor budget")
    if sum(r["anchor"] for r in rooms)>config["fast_travel_nodes"]:
        raise ExplorationActionError("authored fast-travel network exceeds editor budget")
    passages=layout["passages"]
    if type(passages) is not list or not n-1<=len(passages)<=24:
        raise ExplorationActionError("world portals must form a bounded connected graph")
    edges=[];seen=set();gate_count=0
    for e in passages:
        if type(e) is not dict or set(e)!={"a","b","gate","breakable","hazard"}:
            raise ExplorationActionError("portal requires exactly five typed fields")
        a=_integer(e["a"],0,n-1,"portal origin")
        b=_integer(e["b"],0,n-1,"portal destination")
        if a>=b or (a,b) in seen:
            raise ExplorationActionError("portals must be unique, canonical undirected edges")
        seen.add((a,b))
        gate=e["gate"]
        if gate is not None:
            if type(gate) is not str or gate not in powers:
                raise ExplorationActionError("a gated route needs a collectible original movement ability")
            gate_count+=1
        if type(e["breakable"]) is not bool:
            raise ExplorationActionError("gate sequence-break flag must be boolean")
        hazard=_integer(e["hazard"],0,20,"portal environmental hazard")
        edges.append({"a":a,"b":b,"gate":gate,"breakable":e["breakable"],"hazard":hazard})
    if gate_count>config["gates"]:
        raise ExplorationActionError("authored gated routes exceed progression budget")
    entry=_integer(layout["entry"],0,n-1,"spawn region")
    guardian=_integer(layout["guardian"],0,n-1,"guardian region")
    if entry==guardian or rooms[entry]["foe"]!=0:
        raise ExplorationActionError("entry must be safe and distinct from finale")
    if rooms[entry]["ability"] is not None:
        raise ExplorationActionError("original entry must earn no free traversal ability")
    _integer(layout["guardian_health"],1,300,"guardian_health")
    if layout["guardian_element"] not in ("storm","ember","void"):
        raise ExplorationActionError("unregistered original guardian affinity")
    # Fixed point: a player can unlock one-time abilities from reachable rooms.
    # This prevents level designers from publishing impossible circular gates.
    reached={entry};acquired=set()
    for _ in range(2*n+2):
        acquired |= {rooms[i]["ability"] for i in reached if rooms[i]["ability"] is not None}
        expanded=set(reached)
        for e in edges:
            if e["gate"] is None or e["gate"] in acquired:
                if e["a"] in reached:expanded.add(e["b"])
                if e["b"] in reached:expanded.add(e["a"])
        if expanded==reached:break
        reached=expanded
    if guardian not in reached:
        raise ExplorationActionError("final guardian must be reachable without a sequence-break cheat")
    # World structure must be fully traversable for authored completion.
    if len(reached)!=n:
        raise ExplorationActionError("an authored region is permanently inaccessible")
    return {"rooms":rooms,"passages":edges,"entry":entry,
            "guardian":guardian,"guardian_health":layout["guardian_health"],
            "guardian_element":layout["guardian_element"]}


def apply_scene(state,config,layout):
    authored=normalize_layout(config,layout)
    state["rooms"]=[
        {**r,"visited":False,"claimed":False,"searched":False,
         "secret_found":False,"foe_max":r["foe"]} for r in authored["rooms"]
    ]
    state["passages"]=[dict(p) for p in authored["passages"]]
    state["region"]=authored["entry"]
    state["rooms"][authored["entry"]]["visited"]=True
    state["visited"]=[authored["entry"]]
    state["guardian"]=authored["guardian"]
    state["guardian_hp"]=authored["guardian_health"]
    state["guardian_max"]=authored["guardian_health"]
    state["guardian_element"]=authored["guardian_element"]
    state["boss_defeated"]=False
    return state


def start(config,seed):
    _integer(seed,0,2**31-1,"seed")
    state={
        "seed":seed,"turn":0,"region":0,
        "health":config["starting_health"],"max_health":config["starting_health"],
        "stamina":config["starting_stamina"],
        "max_stamina":config["starting_stamina"],"attack_power":config["attack_power"],
        "armor":config["armor"],"tonics":config["tonics"],
        "camp_supplies":config["camp_supplies"],
        "shards":config["opening_shards"],
        "abilities":[],"visited":[],"fast_unlocked":[],
        "sequence_breaks":0,"secrets_found":0,"foes_defeated":0,
        "guarding":False,"evading":False,"focus":0,
        "milestones":[],"events":[],"finished":False,"failed":False
    }
    return apply_scene(state,config,default_layout(config,seed))


def _current(state):
    return state["rooms"][state["region"]]


def _foe_health(state):
    r=_current(state)
    return r["foe"]+(state["guardian_hp"] if
                     state["region"]==state["guardian"] and
                     not state["boss_defeated"] else 0)


def _route(state,target):
    a=state["region"]
    for portal in state["passages"]:
        if (portal["a"]==a and portal["b"]==target or
            portal["b"]==a and portal["a"]==target):
            return portal
    raise ExplorationActionError("destination is not joined to current original world room")


def _environment(state,config,power=None):
    room=_current(state)
    h=room["hazard"]*config["hazard_damage"]//2
    if room["biome"]=="water" and "swim" in state["abilities"]:
        h//=2
    if room["biome"]=="cavern" and "phase" in state["abilities"]:
        h//=2
    if power=="phase":
        h//=2
    if h:
        state["health"]=max(0,state["health"]-h)
    return h


def _enemy_response(state,config,events):
    if _foe_health(state)<=0:
        state["guarding"]=False
        state["evading"]=False
        return
    room=_current(state)
    boss=state["region"]==state["guardian"] and not state["boss_defeated"]
    raw=(config["boss_damage"] if boss else config["foe_damage"])+(
         room["hazard"]//max(1,config["enemy_variance"]))
    armor=state["armor"]
    raw=max(0,raw-armor)
    if state["guarding"]:
        raw=max(0,raw-config["guard_block"])
        events.append("real_shield_stance_absorbed_damage")
    if state["evading"]:
        raw//=2
        events.append("stamina_funded_dodge_reduced_damage")
    if raw:
        state["health"]=max(0,state["health"]-raw)
        events.append("original_enemy_counterattacked")
    state["guarding"]=False
    state["evading"]=False


def _spend(state,key,amount,why):
    if state[key]<amount:
        raise ExplorationActionError(why+" requires finite "+key)
    state[key]-=amount


def _mark(state,label,events):
    if label not in state["milestones"]:
        state["milestones"].append(label)
        events.append(label)


def step(state,config,action):
    if action not in ACTIONS:
        raise ExplorationActionError("unsupported original traversal or battle command")
    if state["finished"] or state["failed"]:
        raise ExplorationActionError("terminal original world cannot accept another command")
    events=[]
    room=_current(state)
    battle=_foe_health(state)>0
    if action.startswith(("travel:","break:","fast:")):
        mode,index=action.split(":");target=int(index)
        if target>=len(state["rooms"]) or target==state["region"]:
            raise ExplorationActionError("original region destination missing or unchanged")
        if battle:
            raise ExplorationActionError("active enemies guard the only safe passage")
        if mode=="fast":
            if target not in state["visited"] or target not in state["fast_unlocked"] or (
                state["region"] not in state["fast_unlocked"]):
                raise ExplorationActionError("real fast travel requires both visited activated anchors")
            _spend(state,"stamina",config["fast_travel_cost"],"fast travel")
            events.append("visited_fast_travel_anchors_linked")
            passage=None
        else:
            passage=_route(state,target)
            gate=passage["gate"]
            if mode=="break":
                if gate is None or gate in state["abilities"] or not passage["breakable"]:
                    raise ExplorationActionError("cannot claim sequence break on an open normal edge")
                if not config["sequence_breaks"]:
                    raise ExplorationActionError("author disabled unintended progression breaks")
                _spend(state,"stamina",config["break_stamina"],"sequence break")
                state["sequence_breaks"]+=1
                _mark(state,"high_skill_sequence_break",events)
            elif gate is not None and gate not in state["abilities"]:
                raise ExplorationActionError("closed route requires an actually acquired movement relic")
            if passage["hazard"]:
                state["health"]=max(0,state["health"]-passage["hazard"])
                events.append("authored_passage_environment_damage")
        state["region"]=target
        if target not in state["visited"]:
            state["visited"].append(target)
            state["visited"].sort()
            events.append("new_connected_region_discovered")
        else:
            events.append("persistent_world_region_revisited")
        _current(state)["visited"]=True
        damage=_environment(state,config)
        if damage:events.append("authored_region_hazard_applied")
        if _current(state)["anchor"] and target not in state["fast_unlocked"]:
            state["fast_unlocked"].append(target)
            state["fast_unlocked"].sort()
            events.append("persistent_fast_travel_shrine_activated")
    elif action in ("attack","heavy"):
        if not battle:
            raise ExplorationActionError("cannot farm attacks without an active original enemy")
        strength=state["attack_power"]
        if action=="heavy":
            _spend(state,"stamina",config["heavy_stamina"],"heavy attack")
            strength=strength*config["heavy_multiplier"]//2
        strength+=state["focus"]
        state["focus"]=0
        if room["foe"]>0:
            room["foe"]=max(0,room["foe"]-strength)
            if room["foe"]==0:
                state["foes_defeated"]+=1
                state["shards"]+=config["foe_reward"]
                events.append("finite_authored_enemy_defeated")
            else:events.append("actual_local_enemy_damaged")
        else:
            state["guardian_hp"]=max(0,state["guardian_hp"]-strength)
            events.append("original_guardian_lost_hitpoints")
            if state["guardian_hp"]==0:
                state["boss_defeated"]=True
                state["shards"]+=config["boss_reward"]
                _mark(state,"original_guardian_defeated",events)
                if config["ending_policy"]=="campaign":
                    state["finished"]=True
                else:
                    _mark(state,"persistent_post_guardian_world_open",events)
    elif action=="guard":
        if not battle:raise ExplorationActionError("shield guarding requires actual combat")
        state["guarding"]=True
        state["stamina"]=min(state["max_stamina"],
                             state["stamina"]+config["stamina_regen"])
        events.append("defensive_stance_committed")
    elif action=="evade":
        if not battle:raise ExplorationActionError("evade requires actual combat")
        _spend(state,"stamina",config["evade_cost"],"evade")
        state["evading"]=True
        events.append("active_dodge_committed")
    elif action=="focus":
        if not battle:raise ExplorationActionError("focus requires actual combat")
        _spend(state,"stamina",config["focus_cost"],"focused strike")
        state["focus"]=min(10,state["focus"]+config["focus_power"])
        events.append("charged_original_strike")
    elif action=="rest":
        state["stamina"]=min(state["max_stamina"],
                             state["stamina"]+config["stamina_regen"])
        events.append("time_spent_recovering_stamina")
    elif action=="claim":
        ability=room["ability"]
        if ability is None or room["claimed"] or battle:
            raise ExplorationActionError("movement relic must be in an unclaimed cleared original shrine")
        if len(state["abilities"])>=config["abilities"]:
            raise ExplorationActionError("ability loadout capacity exhausted")
        room["claimed"]=True
        state["abilities"].append(ability)
        state["abilities"].sort()
        _mark(state,"ability_acquired_"+ability,events)
    elif action=="search":
        if room["searched"] or battle or room["cache"]==0:
            raise ExplorationActionError("room has no remaining reachable finite treasure")
        room["searched"]=True
        state["shards"]+=room["cache"]
        state["tonics"]+=config["cache_tonics"]
        events.append("authored_region_finite_supplies_claimed")
    elif action=="heal":
        if state["health"]>=state["max_health"]:
            raise ExplorationActionError("health potion cannot be consumed at full health")
        _spend(state,"tonics",1,"healing")
        state["health"]=min(state["max_health"],state["health"]+config["heal_power"])
        events.append("finite_tonic_restored_real_health")
    elif action=="camp":
        if battle or not room["anchor"]:
            raise ExplorationActionError("safe camp requires a cleared powered waystone")
        _spend(state,"camp_supplies",1,"camp")
        state["health"]=min(state["max_health"],state["health"]+config["camp_heal"])
        state["stamina"]=state["max_stamina"]
        if state["region"] not in state["fast_unlocked"]:
            state["fast_unlocked"].append(state["region"])
            state["fast_unlocked"].sort()
        events.append("finite_camp_supply_recovered_health_and_stamina")
    elif action=="craft":
        if battle:
            raise ExplorationActionError("cannot forge movement gear under direct attack")
        _spend(state,"shards",config["craft_cost"],"crafting")
        state["attack_power"]=min(config["max_attack"],state["attack_power"]+config["craft_gain"])
        events.append("finite_materials_reinforced_original_weapon")
    elif action=="inspect":
        # Inspect is a benign timed examination; danger still retaliates.
        events.append("authored_region_and_portals_examined")
    state["turn"]+=1
    if state["health"]>0 and not state["finished"]:
        _enemy_response(state,config,events)
    if state["health"]==0:
        state["failed"]=True
        events.append("original_explorer_defeated")
    state["events"]=events
    return events


__all__=["ACTIONS","POWERS","BIOMES","ROOM_LIMIT","ExplorationActionError",
         "default_layout","normalize_layout","start","apply_scene","step"]
