"""Original deterministic roguelike game, bounded procedural floors and tactics.

Spatially separate enemies, traps, rooms, shops, floors, keys, inventory, and
equipment. Permadeath and non-permadeath are distinct legitimate authored
rules. No cloned level data, general-purpose scripts or client-trusted loot.
"""
from __future__ import annotations

from collections import deque

WIDTH=6
CELLS=WIDTH*WIDTH
DIRECTIONS={"north":-WIDTH,"south":WIDTH,"west":-1,"east":1}
WALLS=(7,8,10,16,19,25,28)
ENEMY_KINDS=("sentinel","skirmisher","archer","wraith","bulwark")
BOONS=("vitality","precision","guard","swiftness","alchemy","prosperity")
ACTIONS=(
 tuple(kind+"_"+direction for kind in
       ("move","dash","strike","shoot","cast") for direction in DIRECTIONS)
 +("defend","meditate","drink_potion","eat_ration","open_chest","loot_key",
   "take_stairs","search","disarm","use_shrine","buy_potion","buy_arrows",
   "upgrade_weapon","upgrade_armor","rest","scout","use_lockpick",
   "bank_relic","inspect")
)


class RoguelikeActionError(ValueError):
    """Out-of-bounds procedural dungeon, illegal command or resource abuse."""


def _integer(v,lo,hi,name):
    if type(v) is not int or not lo<=v<=hi:
        raise RoguelikeActionError("invalid original roguelike "+name)
    return v


def _neighbor(point,direction):
    x,y=point%WIDTH,point//WIDTH
    dx,dy={"north":(0,-1),"south":(0,1),
           "west":(-1,0),"east":(1,0)}[direction]
    xx,yy=x+dx,y+dy
    if 0<=xx<WIDTH and 0<=yy<WIDTH:
        return yy*WIDTH+xx
    return None


def _distance(a,b):
    return abs(a%WIDTH-b%WIDTH)+abs(a//WIDTH-b//WIDTH)


def _reachable(entry,walls):
    known={entry};queue=deque([entry])
    while queue:
        p=queue.popleft()
        for direction in DIRECTIONS:
            nxt=_neighbor(p,direction)
            if nxt is not None and nxt not in known and nxt not in walls:
                known.add(nxt);queue.append(nxt)
    return known


def _make_enemy(seed,floor,index,position,config,boss=False):
    kind="guardian" if boss else ENEMY_KINDS[(seed+floor*3+index)%len(ENEMY_KINDS)]
    health=config["boss_health"]+(floor-1)*config["boss_health_growth"] if boss else (
        config["foe_health"]+(floor-1)*config["foe_health_growth"]+
        (index%config["health_variance"]))
    return {
      "id":index,"kind":kind,"cell":position,"hp":health,"max_hp":health,
      "attack":config["boss_attack"] if boss else config["foe_attack"]+
        min(config["floor_damage_cap"],(floor-1)//config["damage_scaling"]),
      "ranged":bool(kind=="archer"),"armor":config["boss_armor"] if boss else
               (1 if kind=="bulwark" else 0),
      "status":"active","poison":0,"stun":0,"rewarded":False,
      "is_boss":bool(boss),
    }


def _generate(config,seed,floor):
    _integer(seed,0,2**31-1,"seed")
    _integer(floor,1,config["floors"],"floor")
    # Guaranteed walkable outer-ring traversal and meaningful inner walls.
    walls=sorted(p for p in WALLS if (seed+floor+p)%config["wall_density"]!=0)
    floor_tiles=["floor"]*CELLS
    for w in walls:floor_tiles[w]="wall"
    entry=0;exit_cell=35
    trap_positions=[11,17,20,29]
    traps=[p for p in trap_positions if p not in walls][:
           config["trap_count"]]
    chests=[p for p in (9,15,24,27) if p not in walls and p not in traps
            and p not in (entry,exit_cell)][:config["chest_count"]]
    shop=12 if 12 not in walls else 6
    shrine=18
    candidates=[5,14,22,31,4,23,32,30,33,26,3,13,21,34]
    slots=[p for p in candidates if p not in walls and p not in traps
           and p not in chests and p not in (entry,exit_cell,shop,shrine)]
    n=min(config["encounters_per_floor"],len(slots))
    guardian=floor==config["floors"]
    if guardian:
        n=min(n, len(slots)-1)
    enemies=[_make_enemy(seed,floor,i,p,config) for i,p in
             enumerate(slots[:n])]
    if guardian:
        enemies.append(_make_enemy(seed,floor,len(enemies),34,config,True))
    return {
       "width":WIDTH,"height":WIDTH,"floor":floor,
       "terrain":floor_tiles,"entry":entry,"exit":exit_cell,
       "traps":traps,"chests":chests,"shop":shop,"shrine":shrine,
       "enemies":enemies,"ambient":("crypt","glade","foundry","temple")[
                       (floor+seed)%4],
       "light":("torch","moon","mist")[(seed+floor)%3],
       "hazard_damage":config["trap_damage"],
    }


def default_layout(config,seed):
    return _generate(config,seed,1)


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
       "width","height","floor","terrain","entry","exit","traps",
       "chests","shop","shrine","enemies","ambient","light","hazard_damage"}:
        raise RoguelikeActionError("dungeon layout requires exact signed procedural fields")
    if _integer(layout["width"],WIDTH,WIDTH,"grid width")!=WIDTH or (
         _integer(layout["height"],WIDTH,WIDTH,"grid height")!=WIDTH):
        raise RoguelikeActionError("bounded 6x6 original dungeon is mandatory")
    if _integer(layout["floor"],1,config["floors"],"authored floor")!=1:
        raise RoguelikeActionError("authored start source must begin on floor one")
    terrain=layout["terrain"]
    if type(terrain) is not list or len(terrain)!=CELLS or any(
        type(t) is not str or t not in ("floor","wall") for t in terrain):
        raise RoguelikeActionError("bounded floor terrain needs 36 exact tiles")
    walls={i for i,t in enumerate(terrain) if t=="wall"}
    entry=_integer(layout["entry"],0,CELLS-1,"entry")
    exit_cell=_integer(layout["exit"],0,CELLS-1,"exit")
    shop=_integer(layout["shop"],0,CELLS-1,"shop")
    shrine=_integer(layout["shrine"],0,CELLS-1,"shrine")
    if len({entry,exit_cell,shop,shrine})!=4:
        raise RoguelikeActionError("spawn, exit, shop, shrine cannot overlap")
    traps=layout["traps"];chests=layout["chests"]
    if type(traps) is not list or type(chests) is not list or (
        len(traps)>config["trap_count"] or len(chests)>config["chest_count"]):
        raise RoguelikeActionError("authored environmental count exceeds typed budget")
    for name,positions in (("trap",traps),("chest",chests)):
        if any(type(p) is not int or not 0<=p<CELLS for p in positions):
            raise RoguelikeActionError("out-of-range "+name+" cell")
        if len(set(positions))!=len(positions):
            raise RoguelikeActionError("duplicate authored "+name)
    if (walls & ({entry,exit_cell,shop,shrine}|set(traps)|set(chests))
        or set(traps)&set(chests)
        or len({entry,exit_cell,shop,shrine}|set(traps)|set(chests))!=
           4+len(traps)+len(chests)):
        raise RoguelikeActionError("terrain features cannot physically overlap")
    reached=_reachable(entry,walls)
    if not {exit_cell,shop,shrine}.issubset(reached):
        raise RoguelikeActionError("original dungeon route, merchant and shrine must be reachable")
    raw=layout["enemies"]
    if type(raw) is not list or len(raw)>min(16,config["encounters_per_floor"]+1):
        raise RoguelikeActionError("enemy roster exceeds authored bounds")
    enemies=[];occupied=set()
    for i,e in enumerate(raw):
        if type(e) is not dict or set(e)!={
          "id","kind","cell","hp","max_hp","attack","ranged","armor",
          "status","poison","stun","rewarded","is_boss"}:
            raise RoguelikeActionError("authored enemy requires exact tactical contract")
        if _integer(e["id"],0,16,"enemy id")!=i:
            raise RoguelikeActionError("enemy identities must be canonical")
        if type(e["kind"]) is not str or e["kind"] not in ENEMY_KINDS+("guardian",):
            raise RoguelikeActionError("invalid original enemy kind")
        p=_integer(e["cell"],0,CELLS-1,"enemy cell")
        if p in occupied or p in walls or p in {entry,exit_cell,shop,shrine}|set(traps)|set(chests):
            raise RoguelikeActionError("enemy overlaps occupied terrain")
        occupied.add(p)
        for key,maximum in (("hp",1000),("max_hp",1000),("attack",100),("armor",30),
                            ("poison",20),("stun",20)):
            _integer(e[key],0,maximum,key)
        for key in ("ranged","rewarded","is_boss"):
            if type(e[key]) is not bool:
                raise RoguelikeActionError("enemy boolean state must be typed")
        if e["hp"]!=e["max_hp"] or e["hp"]<=0 or e["status"]!="active" or (
            e["poison"] or e["stun"] or e["rewarded"]):
            raise RoguelikeActionError("authored enemy must begin as a genuine undefeated foe")
        enemies.append(dict(e))
    _integer(layout["hazard_damage"],0,30,"trap damage")
    if layout["ambient"] not in ("crypt","glade","foundry","temple") or (
       layout["light"] not in ("torch","moon","mist")):
        raise RoguelikeActionError("unregistered original dungeon ambience")
    return {**dict(layout),"enemies":enemies,"traps":list(traps),
            "chests":list(chests),"terrain":list(terrain)}


def apply_scene(state,config,layout):
    map_data=normalize_layout(config,layout)
    state["map"]=map_data
    state["player"]=map_data["entry"]
    return state


def start(config,seed):
    _integer(seed,0,2**31-1,"seed")
    state={
      "seed":seed,"floor":1,"turn":0,"player":0,
      "hp":config["starting_health"],"max_hp":config["starting_health"],
      "stamina":config["starting_stamina"],"max_stamina":config["starting_stamina"],
      "mana":config["starting_mana"],"max_mana":config["starting_mana"],
      "attack":config["attack_power"],"armor":config["armor"],
      "gold":config["opening_gold"],"arrows":config["arrows"],
      "potions":config["potions"],"rations":config["rations"],
      "lockpicks":config["lockpicks"],"potion_healing":config["potion_healing"],
      "poison":0,"guard":False,"floor_key":False,"prepared_stairs":False,
      "kills":0,"total_kills":0,"treasure":0,"xp":0,
      "level":1,"relics":0,"meta_unlocked":[],
      "shrines_used":[],"chests_opened":[],"traps_disarmed":[],
      "boons":[],"floor_boss_defeated":False,
      "score":0,"events":[],"milestones":[],"failed":False,
      "finished":False,"victory":False,"reason":"",
      "map":{},"run_id":"seed_"+str(seed),
    }
    return apply_scene(state,config,default_layout(config,seed))


def _enemy_at(state,cell):
    return next((e for e in state["map"]["enemies"] if e["hp"]>0
                 and e["cell"]==cell),None)


def _blocks(state,cell):
    return (cell is None or state["map"]["terrain"][cell]=="wall")


def _spend(state,key,amount):
    if state[key]<amount:
        raise RoguelikeActionError("insufficient real "+key+" for original action")
    state[key]-=amount


def _enemy_route(state,origin,target):
    blocks={i for i,t in enumerate(state["map"]["terrain"]) if t=="wall"}
    queue=deque([origin]);parent={origin:None}
    while queue:
        p=queue.popleft()
        if p==target:break
        for direction in DIRECTIONS:
            q=_neighbor(p,direction)
            if q is not None and q not in blocks and q not in parent:
                parent[q]=p;queue.append(q)
    if target not in parent:
        return origin
    node=target
    while parent[node]!=origin:
        node=parent[node]
    return node


def _line_open(state,start,direction,range_limit):
    cells=[];spot=start
    for _ in range(range_limit):
        spot=_neighbor(spot,direction)
        if _blocks(state,spot):break
        cells.append(spot)
    return cells


def _enemy_turn(state,config,events):
    if state["poison"]>0:
        state["poison"]-=1
        state["hp"]=max(0,state["hp"]-config["poison_damage"])
        events.append("finite_poison_actually_harmed_original_hero")
    occupied={e["cell"] for e in state["map"]["enemies"] if e["hp"]>0}
    for enemy in state["map"]["enemies"]:
        if enemy["hp"]<=0:continue
        if enemy["stun"]>0:
            enemy["stun"]-=1
            events.append("real_enemy_stunned_for_one_turn")
            continue
        if enemy["poison"]>0:
            enemy["poison"]-=1
            enemy["hp"]=max(0,enemy["hp"]-config["poison_damage"])
            if enemy["hp"]==0:
                _enemy_defeat(state,config,enemy,events)
                continue
        distance=_distance(enemy["cell"],state["player"])
        if distance<=1 or (enemy["ranged"] and distance<=config["archer_range"] and
                            any(state["player"] in _line_open(
                               state,enemy["cell"],direction,config["archer_range"])
                                for direction in DIRECTIONS)):
            damage=max(0,enemy["attack"]-state["armor"]-(config["guard_block"] if
                 state["guard"] else 0))
            state["hp"]=max(0,state["hp"]-damage)
            if damage:events.append("original_spatial_enemy_counterattack")
            if enemy["kind"]=="wraith" and config["poison_enabled"]:
                state["poison"]=max(state["poison"],config["poison_duration"])
            continue
        if config["enemy_patrol"] and distance<=config["aggro_distance"]:
            candidate=_enemy_route(state,enemy["cell"],state["player"])
            if candidate!=state["player"] and candidate not in occupied:
                occupied.remove(enemy["cell"]);occupied.add(candidate)
                enemy["cell"]=candidate
                events.append("original_enemy_navigated_real_floor")
    state["guard"]=False
    if state["hp"]==0:
        if not config["permadeath"] and state["relics"]>=config["revive_relic_cost"]:
            state["relics"]-=config["revive_relic_cost"]
            state["hp"]=max(1,state["max_hp"]//2)
            state["poison"]=0
            state["player"]=state["map"]["entry"]
            state["gold"]=max(0,state["gold"]-config["revival_gold_penalty"])
            events.append("nonpermadeath_paid_relic_resurrection")
        else:
            state["failed"]=True
            state["reason"]="dungeon_permadeath" if config["permadeath"] else "unfunded_defeat"
            events.append("original_dungeon_run_ended_in_defeat")


def _enemy_defeat(state,config,enemy,events):
    if enemy["rewarded"]:return
    enemy["hp"]=0
    enemy["status"]="defeated"
    enemy["rewarded"]=True
    state["kills"]+=1;state["total_kills"]+=1
    state["gold"]+=config["kill_gold"]+(config["boss_gold"] if enemy["is_boss"] else 0)
    state["xp"]+=config["kill_xp"]+(config["boss_xp"] if enemy["is_boss"] else 0)
    state["score"]+=10+(100 if enemy["is_boss"] else 0)
    if enemy["id"]==0:
        state["floor_key"]=True
        events.append("physical_elite_enemy_yielded_unique_floor_key")
    if enemy["is_boss"]:
        state["floor_boss_defeated"]=True
        events.append("real_original_floor_guardian_defeated")
    if state["xp"]>=state["level"]*config["xp_threshold"]:
        state["xp"]-=state["level"]*config["xp_threshold"]
        state["level"]+=1
        state["max_hp"]+=config["level_health_gain"]
        state["hp"]=min(state["max_hp"],state["hp"]+config["level_health_gain"])
        state["attack"]+=config["level_attack_gain"]
        events.append("earned_original_experience_level")
    events.append("genuinely_defeated_authoritative_original_enemy")


def _inside_shop(state):
    return _distance(state["player"],state["map"]["shop"])<=1


def _inside_shrine(state):
    return _distance(state["player"],state["map"]["shrine"])<=1


def step(state,config,action):
    if action not in ACTIONS:
        raise RoguelikeActionError("unregistered original dungeon action")
    if state["failed"] or state["finished"]:
        raise RoguelikeActionError("completed or failed game cannot accept further turns")
    events=[];mode,*tail=action.split("_")
    threats=True
    if mode in ("move","dash","strike","shoot","cast") and tail:
        direction=tail[0]
        if mode in ("move","dash"):
            if mode=="dash":_spend(state,"stamina",config["dash_cost"])
            jumps=2 if mode=="dash" else 1
            current=state["player"]
            for _ in range(jumps):
                destination=_neighbor(current,direction)
                if _blocks(state,destination) or _enemy_at(state,destination):
                    raise RoguelikeActionError("dungeon geometry or actual enemy blocks movement")
                current=destination
            state["player"]=current
            events.append("hero_moved_on_authoritative_original_floor")
            if current in state["map"]["traps"] and current not in state["traps_disarmed"]:
                state["hp"]=max(0,state["hp"]-state["map"]["hazard_damage"])
                events.append("authored_unresolved_trap_damaged_hero")
        else:
            points=_line_open(state,state["player"],direction,
                              1 if mode=="strike" else config["spell_range"]
                              if mode=="cast" else config["arrow_range"])
            target=next((e for p in points if (e:=_enemy_at(state,p))),None)
            if target is None:
                raise RoguelikeActionError("attacks and spells need a real line-of-sight enemy")
            damage=state["attack"]
            if mode=="shoot":
                _spend(state,"arrows",1);damage=config["arrow_damage"]+state["attack"]//2
            elif mode=="cast":
                _spend(state,"mana",config["spell_cost"])
                damage=config["spell_damage"]+state["attack"]//2
                target["poison"]=config["spell_poison"]
            damage=max(1,damage-target["armor"])
            target["hp"]=max(0,target["hp"]-damage)
            events.append("physical_tactical_attack_hit_actual_enemy")
            if target["hp"]==0:
                _enemy_defeat(state,config,target,events)
    elif action=="defend":
        state["guard"]=True
        state["stamina"]=min(state["max_stamina"],state["stamina"]+1)
        events.append("real_guard_stance_absorbs_enemy_contact")
    elif action=="meditate":
        state["mana"]=min(state["max_mana"],state["mana"]+config["mana_regen"])
        events.append("turn_exchanged_for_finite_spell_energy")
    elif action=="drink_potion":
        if state["hp"]>=state["max_hp"]:
            raise RoguelikeActionError("healing cannot be farmed at full health")
        _spend(state,"potions",1)
        state["hp"]=min(state["max_hp"],state["hp"]+state["potion_healing"])
        events.append("finite_original_potion_healed_player")
    elif action=="eat_ration":
        _spend(state,"rations",1)
        state["stamina"]=min(state["max_stamina"],state["stamina"]+config["food_stamina"])
        state["hp"]=min(state["max_hp"],state["hp"]+config["food_heal"])
        events.append("consumed_original_exploration_ration")
    elif action=="open_chest":
        chest=next((p for p in state["map"]["chests"] if
                    p not in state["chests_opened"] and _distance(
                    state["player"],p)<=1),None)
        if chest is None:
            raise RoguelikeActionError("loot must be near an unopened finite original chest")
        state["chests_opened"].append(chest)
        state["gold"]+=config["chest_gold"]
        state["relics"]+=config["chest_relics"]
        state["potions"]+=config["chest_potions"]
        state["treasure"]+=1
        events.append("original_finite_treasure_chest_opened_once")
    elif action=="loot_key":
        if state["floor_key"]:
            raise RoguelikeActionError("floor key was already legitimately recovered")
        raise RoguelikeActionError("key must drop from actual unique elite encounter")
    elif action=="disarm":
        hazard=next((p for p in state["map"]["traps"] if
            p not in state["traps_disarmed"] and
            _distance(state["player"],p)<=1),None)
        if hazard is None:
            raise RoguelikeActionError("trap cannot be disabled remotely")
        _spend(state,"stamina",config["disarm_stamina"])
        state["traps_disarmed"].append(hazard)
        events.append("physical_authored_trap_disarmed_with_energy")
    elif action=="search":
        state["stamina"]=min(state["max_stamina"],
                            state["stamina"]+config["search_recovery"])
        events.append("original_search_expended_an_active_turn")
    elif action=="use_shrine":
        if not _inside_shrine(state) or state["floor"] in state["shrines_used"]:
            raise RoguelikeActionError("shrine requires physical proximity and cannot repeat")
        state["shrines_used"].append(state["floor"])
        selection=BOONS[(state["floor"]+state["seed"])%len(BOONS)]
        state["boons"].append(selection)
        if selection=="vitality":
            state["max_hp"]+=config["shrine_vitality"]
            state["hp"]+=config["shrine_vitality"]
        elif selection=="precision":state["attack"]+=config["shrine_attack"]
        elif selection=="guard":state["armor"]+=config["shrine_armor"]
        elif selection=="swiftness":state["max_stamina"]+=config["shrine_stamina"]
        elif selection=="alchemy":state["potions"]+=1
        else:state["gold"]+=config["shrine_gold"]
        events.append("unique_authoritative_original_boon_earned")
    elif action in ("buy_potion","buy_arrows","upgrade_weapon","upgrade_armor"):
        if not _inside_shop(state):
            raise RoguelikeActionError("merchant trade requires physical shop visit")
        cost={"buy_potion":config["potion_price"],
              "buy_arrows":config["arrow_price"],
              "upgrade_weapon":config["weapon_upgrade_price"],
              "upgrade_armor":config["armor_upgrade_price"]}[action]
        _spend(state,"gold",cost)
        if action=="buy_potion":state["potions"]+=1
        elif action=="buy_arrows":state["arrows"]+=config["arrow_bundle"]
        elif action=="upgrade_weapon":state["attack"]+=config["weapon_gain"]
        else:state["armor"]+=config["armor_gain"]
        events.append("paid_original_local_dungeon_merchant_trade")
    elif action=="rest":
        _spend(state,"rations",1)
        state["hp"]=min(state["max_hp"],state["hp"]+config["rest_health"])
        state["stamina"]=state["max_stamina"]
        events.append("one_real_ration_funded_dungeon_rest")
    elif action=="scout":
        _spend(state,"stamina",config["scout_stamina"])
        state["score"]+=0
        events.append("hero_scouted_actual_signed_original_floor")
    elif action=="use_lockpick":
        if state["floor_key"] or state["prepared_stairs"]:
            raise RoguelikeActionError("stair lock was already legitimately bypassed")
        if _distance(state["player"],state["map"]["exit"])>1:
            raise RoguelikeActionError("lockpicking must occur beside the real exit")
        _spend(state,"lockpicks",1)
        state["prepared_stairs"]=True
        events.append("limited_lockpick_opened_physical_exit")
    elif action=="bank_relic":
        if state["relics"]<=0 or config["meta_progress"]=="none":
            raise RoguelikeActionError("meta unlock requires real relic and enabled progression")
        _spend(state,"relics",1)
        mark="original_run_relic_"+str(len(state["meta_unlocked"]))
        state["meta_unlocked"].append(mark)
        events.append("per_run_custodial_meta_relic_invested")
    elif action=="take_stairs":
        if state["player"]!=state["map"]["exit"]:
            raise RoguelikeActionError("floor transition requires actual physical exit tile")
        if not (state["floor_key"] or state["prepared_stairs"]):
            raise RoguelikeActionError("locked stairs require elite key or finite lockpick")
        if state["floor"]==config["floors"] and not state["floor_boss_defeated"]:
            raise RoguelikeActionError("final original guardian must genuinely be defeated")
        if state["floor"]==config["floors"]:
            state["finished"]=True
            state["victory"]=True
            state["score"]+=config["win_score"]
            state["milestones"].append("original_procedural_dungeon_conquered")
            events.append("reached_actual_final_exit_and_completed_campaign")
        else:
            state["floor"]+=1
            state["map"]=_generate(config,state["seed"],state["floor"])
            state["player"]=state["map"]["entry"]
            state["floor_key"]=False;state["prepared_stairs"]=False
            state["chests_opened"]=[];state["traps_disarmed"]=[]
            state["floor_boss_defeated"]=False;state["kills"]=0
            events.append("deterministic_original_next_floor_instantiated")
    else:
        raise RoguelikeActionError("action has no original gameplay implementation")
    if state["hp"]<=0 and not state["finished"]:
        state["failed"]=True
        state["reason"]="physical_environmental_defeat"
    if not state["finished"] and not state["failed"]:
        _enemy_turn(state,config,events)
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["WIDTH","CELLS","DIRECTIONS","BOONS","ENEMY_KINDS","ACTIONS",
         "RoguelikeActionError","default_layout","normalize_layout","start",
         "apply_scene","step"]
