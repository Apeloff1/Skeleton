"""Original advanced parkour game: deterministic traversal and earned rooftop delivery.

Arcade movement is frame-bounded and integer-only. A selected physical technique
must clear every swept obstacle. Momentum, stamina, grip, weather, load, health,
grounded recovery, spatial routes and source-bound checkpoints all change play.
No borrowed levels, brands, movement animations or third-party executable assets.
"""
from __future__ import annotations

KINDS=("gap","wall","rail","low_bar","hazard","ledge")
COURSES=("rooftops","industrial","highland")
WEATHER=("dry","rain","wind")
ACTIONS=(
    "run","sprint","brake","jump","double_jump","vault","slide","wall_run",
    "grapple","swing","climb","mantle","roll","recover","rest",
    "lane_left","lane_right","inspect","finish",
)
MOBILITY={
    "run":1,"sprint":2,"jump":2,"double_jump":2,"vault":2,
    "slide":2,"wall_run":3,"grapple":4,"swing":3,"climb":1,"mantle":1,
    "roll":2,
}
COMPATIBLE={
    "gap":frozenset(("jump","double_jump","wall_run","grapple","swing")),
    "wall":frozenset(("vault","climb","mantle","wall_run","grapple")),
    "rail":frozenset(("vault","jump","double_jump","grapple")),
    "low_bar":frozenset(("slide","roll","grapple")),
    "hazard":frozenset(("jump","double_jump","vault","wall_run","grapple")),
    "ledge":frozenset(("climb","mantle","grapple","wall_run")),
}

class ParkourActionError(ValueError):
    """Illegal parkour movement, forged geometry or unearned finish."""


def _int(value,minimum,maximum,name):
    if type(value) is not int or not minimum<=value<=maximum:
        raise ParkourActionError("invalid original parkour "+name)
    return value


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    length=config["course_length"]
    xs=[max(5,length*i//9) for i in range(1,9)]
    kinds=("gap","wall","rail","low_bar","hazard","ledge","gap","wall")
    obstacles=[
        {"x":x,"lane":(1 if i%3!=2 else (seed%2)*2),
         "kind":kinds[i],"height":min(4,1+i%3)}
        for i,x in enumerate(xs)
    ]
    # Medals may be reached by genuine lane switching; a route does not
    # silently inherit a victory because it reached the end of the map.
    return {
        "title":"Original Freeflow Course "+str(seed%1000),
        "style":COURSES[seed%len(COURSES)],
        "weather":WEATHER[(seed//2)%len(WEATHER)],
        "start":[0,1],
        "exit_x":length-1,
        "obstacles":obstacles,
        "medals":[{"x":length//3,"lane":1},
                  {"x":2*length//3,"lane":1}],
        "checkpoints":[length//4,length//2,3*length//4],
        "wind_direction":(-1,1)[seed%2],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","style","weather","start","exit_x","obstacles","medals",
        "checkpoints","wind_direction"
    }:
        raise ParkourActionError("exact original rooftop course source required")
    title=layout["title"]
    if type(title) is not str or not 3<=len(title)<=64 or not all(
        c.isalnum() or c in " _-" for c in title
    ):
        raise ParkourActionError("unsafe authored course title")
    if (type(layout["style"]) is not str or layout["style"] not in COURSES
        or type(layout["weather"]) is not str or layout["weather"] not in WEATHER):
        raise ParkourActionError("unrecognized physical course or weather style")
    if type(layout["start"]) is not list or layout["start"]!=[0,1]:
        raise ParkourActionError("course must start in the safe central original lane")
    exit_x=_int(layout["exit_x"],config["course_length"]-1,
                config["course_length"]-1,"finish position")
    marks=layout["checkpoints"]
    if type(marks) is not list or not 1<=len(marks)<=8:
        raise ParkourActionError("bounded real saveable checkpoint geometry required")
    checkpoints=[]
    for mark in marks:
        x=_int(mark,1,exit_x-1,"checkpoint")
        if checkpoints and x<=checkpoints[-1]:
            raise ParkourActionError("checkpoints must be unique and ordered")
        checkpoints.append(x)
    medals=layout["medals"]
    if type(medals) is not list or len(medals)!=config["medals_required"]:
        raise ParkourActionError("required course collectibles cannot be fabricated")
    medals_out=[]; seen=set()
    for medal in medals:
        if type(medal) is not dict or set(medal)!={"x","lane"}:
            raise ParkourActionError("medal must have exact physical location")
        x=_int(medal["x"],1,exit_x-1,"medal x")
        lane=_int(medal["lane"],0,2,"medal lane")
        if (x,lane) in seen or any(m["x"]==x for m in medals_out):
            raise ParkourActionError("earned medal positions must have unique course columns")
        seen.add((x,lane));medals_out.append({"x":x,"lane":lane})
    hazards=layout["obstacles"]
    if type(hazards) is not list or not 2<=len(hazards)<=24:
        raise ParkourActionError("bounded authored obstacle course required")
    obstacles=[];seen=set()
    for part in hazards:
        if type(part) is not dict or set(part)!={"x","lane","kind","height"}:
            raise ParkourActionError("physical obstacle needs exact geometry")
        x=_int(part["x"],2,exit_x-2,"obstacle x")
        lane=_int(part["lane"],0,2,"obstacle lane")
        kind=part["kind"]
        if type(kind) is not str or kind not in KINDS:
            raise ParkourActionError("unregistered original obstacle")
        height=_int(part["height"],1,4,"obstacle height")
        if (x,lane) in seen:
            raise ParkourActionError("overlapping course obstacles cannot create free routes")
        seen.add((x,lane))
        obstacles.append({"x":x,"lane":lane,"kind":kind,"height":height})
    obstacles.sort(key=lambda item:(item["x"],item["lane"]))
    wind=_int(layout["wind_direction"],-1,1,"wind direction")
    if wind==0:
        raise ParkourActionError("wind direction must be signed")
    return {
        "title":title,"style":layout["style"],"weather":layout["weather"],
        "start":[0,1],"exit_x":exit_x,"obstacles":obstacles,
        "medals":medals_out,"checkpoints":checkpoints,"wind_direction":wind,
    }


def start(config,seed):
    scene=default_layout(config,seed)
    return {
        "tick":0,"x":0,"lane":1,"height":0,"vertical_speed":0,
        "momentum":0,"stamina":config["stamina"],"max_stamina":config["stamina"],
        "health":config["max_health"],"max_health":config["max_health"],
        "grip":config["grip_strength"],"grapple_charges":config["grapple_charges"],
        "wall_run_remaining":config["wall_run_ticks"],
        "cooldown":0,"flow_chain":0,"best_chain":0,"score":0,"falls":0,
        "medals_collected":[],"checkpoint":0,"checkpoint_lane":1,
        "weather":scene["weather"],"style":scene["style"],"title":scene["title"],
        "exit_x":scene["exit_x"],"obstacles":scene["obstacles"],
        "medals":scene["medals"],"checkpoints":scene["checkpoints"],
        "wind_direction":scene["wind_direction"],"events":[],
        "finished":False,"failed":False,
    }


def apply_scene(state,config,layout):
    level=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise ParkourActionError("authored course cannot overwrite an active run")
    for key in ("title","style","weather","exit_x","obstacles","medals",
                "checkpoints","wind_direction"):
        v=level[key]
        state[key]=[dict(item) for item in v] if key in ("obstacles","medals") else (
            list(v) if key=="checkpoints" else v)
    state["x"],state["lane"]=level["start"]


def _required_stamina(config,action):
    return {
        "run":1,"sprint":config["sprint_cost"],
        "jump":config["jump_cost"],"double_jump":config["jump_cost"]+3,
        "vault":config["vault_cost"],"slide":config["slide_cost"],
        "wall_run":config["wall_run_cost"],"grapple":config["grapple_cost"],
        "swing":config["grapple_cost"]//2+1,"climb":config["climb_cost"],
        "mantle":config["climb_cost"]+2,"roll":config["slide_cost"],
    }.get(action,0)


def step(state,config,action):
    if action not in ACTIONS:
        raise ParkourActionError("unregistered original spatial traversal")
    if state["finished"] or state["failed"]:
        raise ParkourActionError("terminal parkour session cannot advance")
    if action=="finish" and (
        state["x"]!=state["exit_x"] or
        len(state["medals_collected"])!=len(state["medals"]) or state["health"]<=0
    ):
        raise ParkourActionError("physical exit and source medals are required to finish")
    events=[]
    # No client-supplied x, score, medals, coordinates or damage is authoritative.
    cost=_required_stamina(config,action)
    if cost>state["stamina"]:
        raise ParkourActionError("actual runner stamina cannot pay traversal cost")
    if action=="double_jump" and (not config["double_jump"] or state["cooldown"]>0):
        raise ParkourActionError("double jump requires earned ability and cooldown")
    if action in ("grapple","swing") and (
        config["grapple_reach"]<=0 or state["grapple_charges"]<=0
    ):
        raise ParkourActionError("grapple needs real source-enabled finite gear")
    if action=="wall_run" and state["wall_run_remaining"]<=0:
        raise ParkourActionError("wall-running requires available kinetic window")
    if action=="mantle" and not config["mantling"]:
        raise ParkourActionError("mantling must be enabled by source")
    state["stamina"]-=cost
    if action=="finish":
        state["tick"]+=1;state["finished"]=True
        state["score"]+=config["completion_bonus"]+state["health"]
        state["events"]=["earned_course_completion"]
        return state["events"]
    if action=="lane_left":
        state["lane"]=max(0,state["lane"]-1)
    elif action=="lane_right":
        state["lane"]=min(2,state["lane"]+1)
    elif action=="rest":
        state["stamina"]=min(state["max_stamina"],
                             state["stamina"]+config["stamina_recovery"]*3)
        state["flow_chain"]=0
    elif action=="recover":
        state["stamina"]=min(state["max_stamina"],
                             state["stamina"]+config["stamina_recovery"])
    elif action=="brake":
        state["momentum"]=max(0,state["momentum"]-config["momentum_decay"]*2)
        state["flow_chain"]=0
    elif action in ("grapple","swing"):
        state["grapple_charges"]-=1
        state["height"]=min(config["jump_power"]*2,config["grapple_reach"])
        events.append("rope_traversal")
    if action=="wall_run":
        state["wall_run_remaining"]=max(0,state["wall_run_remaining"]-1)
        events.append("wall_run")
    if action in ("jump","double_jump"):
        state["vertical_speed"]=(config["jump_power"]*(
            2 if action=="double_jump" else 1))
        state["height"]+=state["vertical_speed"]
        state["cooldown"]=config["jump_cooldown"]
    elif action in ("climb","mantle"):
        state["height"]+=config["climb_power"]
    elif action in ("slide","roll"):
        state["height"]=0
    old_x=state["x"]
    if action in MOBILITY:
        multiplier=MOBILITY[action]
        # 3 style envelopes alter actual longitudinal acceleration.
        accel={"rooftops":2,"industrial":1,"highland":1}[state["style"]]
        momentum=(state["momentum"]+
                  (config["sprint_gain"] if action=="sprint" else accel))
        state["momentum"]=min(config["max_velocity"],momentum)
        stride=min(config["max_stride"],multiplier+state["momentum"]//config["stride_divisor"])
        if state["weather"]=="rain" and action=="sprint":
            stride=max(1,stride-config["surface_friction"])
        state["x"]=min(state["exit_x"],state["x"]+max(1,stride))
    else:
        state["momentum"]=max(0,state["momentum"]-config["momentum_decay"])
    if state["weather"]=="wind" and state["tick"]%config["wind_period"]==0:
        if state["momentum"]>config["wind_resistance"]:
            state["lane"]=max(0,min(2,state["lane"]+state["wind_direction"]))
            events.append("lateral_wind_drift")
    crossed=[part for part in state["obstacles"]
             if old_x<part["x"]<=state["x"] and part["lane"]==state["lane"]]
    for part in crossed:
        kind=part["kind"]
        enough=action in COMPATIBLE[kind]
        if kind=="wall" and action=="vault":
            enough=enough and part["height"]<=config["vault_clearance"]
        if action in ("jump","double_jump") and kind in ("gap","rail","hazard"):
            enough=enough and state["height"]>=part["height"]
        if action=="grapple" and part["height"]>config["grapple_reach"]:
            enough=False
        if action=="wall_run" and part["height"]>config["wall_run_height"]:
            enough=False
        if not enough:
            damage=config["collision_damage"]+(
                config["hardcore_damage"] if config["difficulty"]=="hardcore" else 0
            )
            state["health"]=max(0,state["health"]-damage)
            state["falls"]+=1
            state["flow_chain"]=0
            state["x"]=state["checkpoint"]
            state["lane"]=state["checkpoint_lane"]
            state["height"]=0;state["vertical_speed"]=0;state["momentum"]=0
            events.extend(("obstacle_collision","checkpoint_respawn"))
            break
        state["flow_chain"]+=1
        state["best_chain"]=max(state["best_chain"],state["flow_chain"])
        state["score"]+=config["trick_reward"]*state["flow_chain"]
        events.append("technique_cleared_"+kind)
    else:
        for medal in state["medals"]:
            if (old_x<medal["x"]<=state["x"] and medal["lane"]==state["lane"]
                and medal["x"] not in state["medals_collected"]):
                state["medals_collected"].append(medal["x"])
                state["score"]+=config["medal_bonus"]
                events.append("real_course_medal_collected")
        state["medals_collected"].sort()
        for checkpoint in state["checkpoints"]:
            if old_x<checkpoint<=state["x"] and checkpoint>state["checkpoint"]:
                state["checkpoint"]=checkpoint
                state["checkpoint_lane"]=state["lane"]
                state["wall_run_remaining"]=config["wall_run_ticks"]
                events.append("safe_checkpoint_activated")
    if action not in ("jump","double_jump","grapple","swing","climb","mantle"):
        state["vertical_speed"]=max(-config["gravity"],state["vertical_speed"]-config["gravity"])
        state["height"]=max(0,state["height"]+state["vertical_speed"])
    if state["cooldown"]>0 and action!="double_jump":
        state["cooldown"]-=1
    if action not in ("rest","recover"):
        state["stamina"]=min(state["max_stamina"],
                             state["stamina"]+config["stamina_regen_per_turn"])
    state["tick"]+=1
    if state["health"]<=0 or state["tick"]>=config["time_limit"]:
        state["failed"]=True
        events.append("parkour_run_failed")
    if state["x"]==state["exit_x"] and len(state["medals_collected"])==len(state["medals"]):
        events.append("real_exit_ready")
    state["events"]=events
    return events
