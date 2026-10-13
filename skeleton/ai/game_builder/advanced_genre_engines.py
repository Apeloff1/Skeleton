"""Three distinct advanced original-game simulation families.

Small, deterministic, finite integer worlds. Each step mutates only the
transient state reconstructed by advanced_gameplay_runtime. No runtime eval,
third-party assets, hidden RNG or native engine claims.
"""
from __future__ import annotations

from copy import deepcopy

from .system_editors import SystemEditorError


class GenreActionError(SystemEditorError):
    """An invalid player command or an impossible game-world transition."""


SHOOTER_ACTIONS=(
    "north","south","west","east","dash:north","dash:south",
    "dash:west","dash:east","fire","reload","cover","medkit",
    "extract","wait",
)
DECK_ACTIONS=("play:0","play:1","play:2","play:3","play:4",
              "end_turn","potion")
PUZZLE_ACTIONS=("north","south","west","east","interact",
                "undo","rewind","wait")
GENRE_ACTIONS={
    "shooter":SHOOTER_ACTIONS,
    "deck_battler":DECK_ACTIONS,
    "puzzle":PUZZLE_ACTIONS,
}

CARDS={
    "strike":(1,"attack"),
    "guard":(1,"defend"),
    "pierce":(2,"pierce"),
    "drain":(2,"drain"),
    "rally":(1,"strength"),
    "scry":(0,"draw"),
    "ward":(1,"ward"),
    "spark":(1,"poison"),
}
DEFAULT_DECK=[
    "strike","guard","strike","scry","pierce","guard",
    "rally","strike","ward","drain","spark","guard",
]


def _valid_location(point,width,height):
    return 0<=point[0]<width and 0<=point[1]<height


def _next(pos, direction):
    delta={"north":(0,-1),"south":(0,1),"east":(1,0),"west":(-1,0)}[direction]
    return [pos[0]+delta[0],pos[1]+delta[1]]


def _distance(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


def _line_clear(a,b,walls):
    """Integer Bresenham LOS: cover blocks bullets, not just movement."""
    x,y=a;tx,ty=b
    dx=abs(tx-x);dy=abs(ty-y)
    sx=1 if x<tx else -1
    sy=1 if y<ty else -1
    err=dx-dy
    blocked={tuple(w) for w in walls}
    while [x,y]!=list(b):
        twice=2*err
        if twice>-dy:
            err-=dy;x+=sx
        if twice<dx:
            err+=dx;y+=sy
        if [x,y]!=list(b) and (x,y) in blocked:
            return False
    return True


def shooter_start(cfg,seed):
    width,height=14,9
    state={
        "tick":0,"width":width,"height":height,"player":[1,4],
        "hp":cfg["player_health"],"max_hp":cfg["player_health"],
        "ammo":cfg["ammo"],"magazine":cfg["ammo"],
        "dashes":cfg["dodge_charges"],"dodge_limit":cfg["dodge_charges"],
        "medkits":1,"covered":False,"cover":[[4,3],[4,5],[9,3],[9,5]],
        "spawns":[[12,2],[12,4],[12,6]],
        "extraction":[13,4],"pickups":[[7,4]],
        "enemies":[],"enemy_total":cfg["enemy_count"],
        "spawned":0,"defeated":0,"wave":0,"damage_taken":0,
        "score":0,"events":[],"finished":False,"failed":False,
    }
    _spawn_wave(state,seed)
    return state


def _spawn_wave(state,seed):
    if state["enemies"] or state["spawned"]>=state["enemy_total"]:
        return
    state["wave"]+=1
    count=min(3,state["enemy_total"]-state["spawned"])
    for index in range(count):
        ident=state["spawned"]
        pos=state["spawns"][(ident+seed)%len(state["spawns"])]
        state["enemies"].append({
            "id":ident,"pos":pos[:],"hp":4+ident//3,
            "armor":1 if ident%4==3 else 0,
            "behavior":"flank" if ident%3==2 else "advance",
        })
        state["spawned"]+=1


def shooter_step(state,cfg,action):
    if action not in SHOOTER_ACTIONS:
        raise GenreActionError("unknown arena combat command")
    ev=[]
    state["tick"]+=1
    dodging=False
    if action in {"north","south","east","west"} or action.startswith("dash:"):
        dodging=action.startswith("dash:")
        direction=action.split(":")[-1]
        if dodging and state["dashes"]<=0:
            raise GenreActionError("no remaining dodge charge")
        steps=2 if dodging else 1
        for _ in range(steps):
            next_pos=_next(state["player"],direction)
            if (not _valid_location(next_pos,state["width"],state["height"])
                or next_pos in state["cover"] or any(
                    e["pos"]==next_pos for e in state["enemies"]
                )):
                break
            state["player"]=next_pos
        if dodging:
            state["dashes"]-=1
            ev.append("evasive_movement")
        else:
            ev.append("arena_movement")
    elif action=="fire":
        if state["ammo"]<=0:
            raise GenreActionError("magazine is empty")
        targets=[enemy for enemy in state["enemies"]
                 if _distance(state["player"],enemy["pos"])<=8
                 and _line_clear(state["player"],enemy["pos"],state["cover"])]
        if not targets:
            raise GenreActionError("no target is visible within effective range")
        target=min(targets,key=lambda e:(_distance(state["player"],e["pos"]),e["id"]))
        state["ammo"]-=1
        damage=max(1,cfg["weapon_damage"]-target["armor"])
        target["hp"]-=damage
        ev.append("weapon_hit")
        if target["hp"]<=0:
            state["enemies"].remove(target)
            state["defeated"]+=1
            state["score"]+=100
            ev.append("enemy_defeated")
    elif action=="reload":
        if state["ammo"]==state["magazine"]:
            raise GenreActionError("magazine already full")
        state["ammo"]=state["magazine"]
        ev.append("magazine_reloaded")
    elif action=="cover":
        state["covered"]=True
        ev.append("cover_stance")
    elif action=="medkit":
        if state["medkits"]<=0 or state["hp"]==state["max_hp"]:
            raise GenreActionError("medkit unavailable or player health full")
        state["medkits"]-=1
        state["hp"]=min(state["max_hp"],state["hp"]+6)
        ev.append("medkit_used")
    elif action=="extract":
        if state["enemies"] or state["spawned"]<state["enemy_total"]:
            raise GenreActionError("evacuation locked until all waves defeated")
        if state["player"]!=state["extraction"]:
            raise GenreActionError("player must reach the authored extraction tile")
        state["finished"]=True
        ev.append("mission_extracted")
        return ev
    else:
        ev.append("arena_wait")
    for pickup in list(state["pickups"]):
        if pickup==state["player"]:
            state["pickups"].remove(pickup)
            state["medkits"]=min(3,state["medkits"]+1)
            ev.append("medical_supply_collected")
    if not state["enemies"] and state["spawned"]<state["enemy_total"]:
        _spawn_wave(state,state["wave"])
        ev.append("enemy_reinforcement_wave")
    # Deterministic enemy AI: bounded movement, cover LOS, staggered attacks,
    # player dodges nullify a turn; cover stance mitigates but never grants
    # invulnerability or free recharge.
    occupied={tuple(e["pos"]) for e in state["enemies"]}
    for enemy in state["enemies"]:
        if state["hp"]<=0:
            break
        if (_distance(enemy["pos"],state["player"])<=3
            and _line_clear(enemy["pos"],state["player"],state["cover"])):
            amount=0 if dodging else max(0,2-(1 if state["covered"] else 0))
            state["hp"]=max(0,state["hp"]-amount)
            state["damage_taken"]+=amount
            if amount:
                ev.append("enemy_fire")
        else:
            for direction in (
                ("east" if state["player"][0]>enemy["pos"][0] else "west"),
                ("south" if state["player"][1]>enemy["pos"][1] else "north"),
            ):
                candidate=_next(enemy["pos"],direction)
                if (candidate==state["player"]
                    or not _valid_location(candidate,state["width"],state["height"])
                    or candidate in state["cover"]
                    or tuple(candidate) in occupied):
                    continue
                occupied.remove(tuple(enemy["pos"]))
                enemy["pos"]=candidate
                occupied.add(tuple(candidate))
                ev.append("enemy_patrolled")
                break
    if not state["finished"] and state["hp"]==0:
        state["failed"]=True
        ev.append("player_defeated")
    state["covered"]=False
    return ev


def _shuffle(cards,seed):
    values=list(cards)
    rng=(seed^0xA5B35705)&0x7fffffff
    for i in range(len(values)-1,0,-1):
        rng=(1103515245*rng+12345)&0x7fffffff
        j=rng%(i+1)
        values[i],values[j]=values[j],values[i]
    return values


def _draw_cards(state,count):
    for _ in range(count):
        if len(state["hand"])>=state["hand_limit"]:
            break
        if not state["draw_pile"]:
            if not state["discard"]:
                break
            state["draw_pile"]=_shuffle(state["discard"],state["seed"]+state["round"])
            state["discard"]=[]
        state["hand"].append(state["draw_pile"].pop())


def deck_start(cfg,seed):
    hand_limit=4
    state={
        "round":1,"seed":seed,"hand_limit":hand_limit,
        "max_hp":cfg["starting_health"],"hp":cfg["starting_health"],
        "enemy_hp":cfg["enemy_health"],"enemy_max_hp":cfg["enemy_health"],
        "energy":cfg["energy_per_turn"],"energy_limit":cfg["energy_per_turn"],
        "block":0,"enemy_block":0,"strength":0,"weak":0,"poison":0,
        "enemy_strength":0,"enemy_poison":0,"potions":2,
        "hand":[],"draw_pile":_shuffle(DEFAULT_DECK,seed),
        "discard":[],"exhaust":[],"deck_origin":list(DEFAULT_DECK),
        "enemy_pattern":["attack","defend","poison","charge"],
        "enemy_intent":"attack","damage_dealt":0,
        "score":0,"events":[],"finished":False,"failed":False,
    }
    _draw_cards(state,hand_limit)
    return state


def _damage_enemy(state,amount,piercing=False):
    dmg=max(0,amount)
    armor=0 if piercing else min(state["enemy_block"],dmg)
    state["enemy_block"]-=armor
    dealt=min(state["enemy_hp"],dmg-armor)
    state["enemy_hp"]-=dealt
    state["damage_dealt"]+=dealt
    return dealt


def _damage_player(state,amount):
    blocked=min(state["block"],amount)
    state["block"]-=blocked
    state["hp"]=max(0,state["hp"]-(amount-blocked))


def deck_step(state,cfg,action):
    if action not in DECK_ACTIONS:
        raise GenreActionError("unknown original card-battle action")
    ev=[]
    if action.startswith("play:"):
        idx=int(action.split(":")[1])
        if idx>=len(state["hand"]):
            raise GenreActionError("card index absent from current hand")
        card=state["hand"][idx]
        cost,kind=CARDS[card]
        if state["energy"]<cost:
            raise GenreActionError("not enough turn energy for that card")
        state["energy"]-=cost
        state["hand"].pop(idx)
        state["discard"].append(card)
        if kind=="attack":
            _damage_enemy(state,cfg["attack_damage"]+state["strength"])
        elif kind=="defend":
            state["block"]+=cfg["block_value"]
        elif kind=="pierce":
            _damage_enemy(state,cfg["attack_damage"]+3+state["strength"],True)
        elif kind=="drain":
            hit=_damage_enemy(state,max(1,cfg["attack_damage"]//2+state["strength"]))
            state["hp"]=min(state["max_hp"],state["hp"]+hit)
        elif kind=="strength":
            state["strength"]+=2
        elif kind=="draw":
            _draw_cards(state,2)
        elif kind=="ward":
            state["block"]+=max(2,cfg["block_value"]//2)
            state["poison"]=max(0,state["poison"]-2)
        elif kind=="poison":
            state["enemy_poison"]+=3
        ev.append("card_"+card+"_played")
    elif action=="potion":
        if not state["potions"] or state["hp"]==state["max_hp"]:
            raise GenreActionError("potion cannot be used without missing health")
        state["potions"]-=1
        state["hp"]=min(state["max_hp"],state["hp"]+8)
        ev.append("potion_consumed")
    else:
        intent=state["enemy_intent"]
        if state["enemy_poison"]:
            state["enemy_hp"]=max(0,state["enemy_hp"]-state["enemy_poison"])
            state["enemy_poison"]-=1
            ev.append("enemy_poison_tick")
        if state["enemy_hp"]>0:
            if intent=="attack":
                _damage_player(state,4+state["enemy_strength"])
                ev.append("enemy_attacked")
            elif intent=="defend":
                state["enemy_block"]+=5
                ev.append("enemy_guarded")
            elif intent=="poison":
                state["poison"]+=2
                ev.append("player_poisoned")
            elif intent=="charge":
                state["enemy_strength"]+=2
                ev.append("enemy_enraged")
        if state["poison"]:
            state["hp"]=max(0,state["hp"]-state["poison"])
            state["poison"]-=1
            ev.append("player_poison_tick")
        state["discard"].extend(state["hand"])
        state["hand"]=[]
        state["round"]+=1
        state["block"]=0
        state["energy"]=state["energy_limit"]
        state["enemy_intent"]=state["enemy_pattern"][
            (state["round"]-1)%len(state["enemy_pattern"])]
        _draw_cards(state,state["hand_limit"])
        ev.append("new_turn")
    if state["enemy_hp"]<=0:
        state["enemy_hp"]=0
        state["finished"]=True
        state["score"]=max(1,1000+state["hp"]*3-state["round"]*10)
        ev.append("enemy_boss_defeated")
    if state["hp"]<=0:
        state["hp"]=0
        state["failed"]=True
        state["finished"]=False
        ev.append("player_battle_lost")
    return ev


def _puzzle_snapshot(state):
    return {key:deepcopy(state[key]) for key in (
        "player","crates","switches_on","powered_nodes","phase",
        "portal_visited",
    )}


def puzzle_default_layout(cfg):
    """Small boards use only objects relevant to the selected puzzle logic."""
    w,h=cfg["board_width"],cfg["board_height"]
    mode=cfg["logic"]
    scene={
        "spawn":[0,0],"exit":[w-1,h-1],
        "walls":[],"doors":[],"switches":[],"crates":[],
        "targets":[],"nodes":[],"portals":[],"phase_gates":[],
    }
    if mode=="switches":
        scene["switches"]=[[1,0]]
        scene["doors"]=[[1,h-1]]
    elif mode=="push_blocks":
        scene["crates"]=[[1,1]]
        scene["targets"]=[[min(w-1,2),1]]
    elif mode=="circuits":
        scene["nodes"]=[[1,0],[1,1]]
        scene["doors"]=[[1,h-1]]
    elif mode=="time":
        scene["phase_gates"]=[[1,1]]
    elif mode=="non_euclidean":
        scene["portals"]=[[[1,0],[w-2,h-1]]]
    return scene


def puzzle_start(cfg,seed):
    w,h=cfg["board_width"],cfg["board_height"]
    layout=puzzle_default_layout(cfg)
    state={
        "tick":0,"mode":cfg["logic"],"width":w,"height":h,
        "player":list(layout["spawn"]),"exit":list(layout["exit"]),
        "walls":layout["walls"],"doors":layout["doors"],
        "switches":layout["switches"],"crates":layout["crates"],
        "targets":layout["targets"],"nodes":layout["nodes"],
        "portals":layout["portals"],"phase_gates":layout["phase_gates"],
        "switches_on":[],"powered_nodes":[],"phase":seed%2,
        "portal_visited":False,
        "undo_available":min(cfg["undo_depth"],128),
        "history":[],"move_count":0,
        "events":[],"finished":False,"failed":False,
    }
    return state

def _puzzle_valid(state,point):
    if not _valid_location(point,state["width"],state["height"]):
        return False
    if point in state["walls"]:
        return False
    if point in state["doors"] and (
        state["mode"]=="switches" and len(state["switches_on"])<len(state["switches"])
        or state["mode"]=="circuits" and len(state["powered_nodes"])<len(state["nodes"])
    ):
        return False
    if point in state["phase_gates"] and state["mode"]=="time" and state["phase"]%2:
        return False
    return True


def puzzle_step(state,cfg,action):
    if action not in PUZZLE_ACTIONS:
        raise GenreActionError("unrecognized puzzle command")
    ev=[]
    if action in ("undo","rewind"):
        if not state["history"] or not state["undo_available"]:
            raise GenreActionError("no previous puzzle state or available rewind")
        prior=state["history"].pop()
        for key,value in prior.items():
            state[key]=value
        state["undo_available"]-=1
        state["tick"]+=1
        ev.append("causal_rewind")
        return ev
    before=_puzzle_snapshot(state)
    if action in ("north","south","west","east"):
        next_pos=_next(state["player"],action)
        if not _puzzle_valid(state,next_pos):
            raise GenreActionError("wall, closed gate or outside board")
        if next_pos in state["crates"]:
            push=_next(next_pos,action)
            if (not _puzzle_valid(state,push) or push in state["crates"]
                or state["mode"]!="push_blocks"):
                raise GenreActionError("crate cannot move to blocked or incompatible cell")
            state["crates"][state["crates"].index(next_pos)]=push
            ev.append("crate_pushed")
        state["player"]=next_pos
        state["move_count"]+=1
        ev.append("puzzle_player_moved")
        if state["mode"]=="non_euclidean":
            for a,b in state["portals"]:
                if state["player"]==a:
                    state["player"]=list(b)
                    state["portal_visited"]=True
                    ev.append("portal_traversed")
                    break
                if state["player"]==b:
                    state["player"]=list(a)
                    state["portal_visited"]=True
                    ev.append("portal_traversed")
                    break
    elif action=="interact":
        if state["mode"]=="switches" and state["player"] in state["switches"]:
            if state["player"] not in state["switches_on"]:
                state["switches_on"].append(list(state["player"]))
            ev.append("switch_activated")
        elif state["mode"]=="circuits" and state["player"] in state["nodes"]:
            if state["player"] not in state["powered_nodes"]:
                state["powered_nodes"].append(list(state["player"]))
            ev.append("circuit_node_activated")
        else:
            raise GenreActionError("no compatible object to interact with here")
    elif action=="wait":
        ev.append("puzzle_time_advanced")
    state["tick"]+=1
    if state["mode"]=="time":
        state["phase"]=1-state["phase"]
        ev.append("phase_shift")
    if cfg["undo_depth"]>0:
        state["history"].append(before)
        state["history"]=state["history"][-min(cfg["undo_depth"],128):]
    requirements={
        "switches":len(state["switches_on"])==len(state["switches"]),
        "push_blocks":sorted(state["crates"])==sorted(state["targets"]),
        "circuits":len(state["powered_nodes"])==len(state["nodes"]),
        "time":state["phase"]==0,
        "non_euclidean":state["portal_visited"],
    }
    if state["player"]==state["exit"] and (
        requirements[state["mode"]] or not cfg["solution_required"]
    ):
        state["finished"]=True
        ev.append("puzzle_completed")
    return ev


def apply_genre_scene(editor,state,layout):
    """Mutate initial state only after the caller validated source/checksum."""
    if editor=="shooter":
        state.update(width=layout["width"],height=layout["height"],
                     player=list(layout["player_spawn"]),
                     cover=[list(c) for c in layout["cover"]],
                     spawns=[list(c) for c in layout["enemy_spawns"]],
                     extraction=list(layout["extraction"]),
                     pickups=[list(c) for c in layout["medkits"]])
        # Runtime generated enemies must be respawned at authored positions,
        # not left at default seed-only positions.
        for i,enemy in enumerate(state["enemies"]):
            enemy["pos"]=list(state["spawns"][i%len(state["spawns"])])
    elif editor=="deck_battler":
        state["hand_limit"]=layout["hand_size"]
        state["deck_origin"]=list(layout["cards"])
        state["draw_pile"]=_shuffle(layout["cards"],state["seed"])
        state["discard"]=[];state["exhaust"]=[];state["hand"]=[]
        state["enemy_pattern"]=list(layout["enemy_pattern"])
        state["enemy_intent"]=layout["enemy_pattern"][0]
        state["enemy_block"]=layout["enemy_armor"]
        state["potions"]=layout["potions"]
        _draw_cards(state,state["hand_limit"])
    elif editor=="puzzle":
        state.update(player=list(layout["spawn"]),exit=list(layout["exit"]),
            walls=[list(x) for x in layout["walls"]],
            doors=[list(x) for x in layout["doors"]],
            switches=[list(x) for x in layout["switches"]],
            crates=[list(x) for x in layout["crates"]],
            targets=[list(x) for x in layout["targets"]],
            nodes=[list(x) for x in layout["nodes"]],
            portals=[[list(a),list(b)] for a,b in layout["portals"]],
            phase_gates=[list(x) for x in layout["phase_gates"]])
    else:
        raise GenreActionError("unknown advanced scene genre")


STARTS={"shooter":shooter_start,"deck_battler":deck_start,"puzzle":puzzle_start}
STEPS={"shooter":shooter_step,"deck_battler":deck_step,"puzzle":puzzle_step}
__all__=["GenreActionError","GENRE_ACTIONS","CARDS","DEFAULT_DECK",
         "STARTS","STEPS","apply_genre_scene","puzzle_default_layout"]
