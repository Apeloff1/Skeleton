"""Original supervised stealth game: spatial visibility, patrols, security and escape.

Reference-only bounded turn-based game. Original geometry and player actions
deterministically recreate every state transition; no client-owned reward,
script, asset, mutable RNG or guessed native-execution assurance.
"""
from __future__ import annotations

from collections import deque

WIDTH, HEIGHT = 10, 8
DIRECTIONS = {"north":(0,-1),"south":(0,1),"west":(-1,0),"east":(1,0)}
SECURITY_ACTIONS = ("hide","emerge","wait","rest","disguise",
                    "hack_terminal","hack_door","collect_keycard","steal","disable_camera",
                    "neutralize","deploy_smoke","deploy_emp","collect_intel",
                    "extract","use_medkit")
ACTIONS = (SECURITY_ACTIONS
           + tuple(name for prefix in ("move","crouch","sprint","decoy")
                   for name in (prefix+"_"+d for d in DIRECTIONS)))


class StealthActionError(ValueError):
    """Illegal original player command, scene, or impossible state transition."""


def _integer(v,lo,hi,key):
    if type(v) is not int or not lo<=v<=hi:
        raise StealthActionError("invalid bounded infiltration "+key)
    return v


def _xy(v,name):
    if (type(v) is not list or len(v)!=2
        or any(type(x) is not int for x in v)
        or not 0<=v[0]<WIDTH or not 0<=v[1]<HEIGHT):
        raise StealthActionError("invalid grid coordinate for "+name)
    return list(v)


def _points(v,minimum,maximum,name):
    if type(v) is not list or not minimum<=len(v)<=maximum:
        raise StealthActionError("invalid count for authored "+name)
    result=[_xy(c,name) for c in v]
    if len({tuple(c) for c in result})!=len(result):
        raise StealthActionError("duplicate authored "+name+" coordinates")
    return result


def default_layout(config,seed):
    walls=[[3,1],[3,2],[3,3],[3,5],[6,2],[6,3],[6,4],
           [6,6],[1,5],[8,5],[1,2]]
    return {
        "spawn":[0,0],"extraction":[9,7],
        "walls":walls,
        "shadows":[[1,1],[2,4],[4,3],[5,6],[8,6],[7,2]],
        "vents":[[3,7],[6,1]],
        "doors":[[3,4],[6,5]],
        "guard_routes":[
            [[5,4],[5,5]],[[2,6],[2,7]],[[8,4],[9,4]],
            [[8,2],[9,2]],[[4,1],[5,1]],[[7,6],[7,7]],
            [[2,3],[2,4]],[[5,0],[6,0]],
        ],
        "cameras":[[4,4],[8,3]],
        "keycards":[[2,0]],
        "intel":[[5,1],[7,7]],
        "objective":[8,1],
        "terminal":[7,5],
        "lighting":("day","night","storm")[seed%3],
        "alarm_budget":5+(seed%3),
    }


def _reachable(origin,blocks):
    explored={tuple(origin)}
    pending=deque([origin])
    while pending:
        x,y=pending.popleft()
        for dx,dy in DIRECTIONS.values():
            p=(x+dx,y+dy)
            if (0<=p[0]<WIDTH and 0<=p[1]<HEIGHT
                and p not in blocks and p not in explored):
                explored.add(p)
                pending.append(p)
    return explored


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "spawn","extraction","walls","shadows","vents","doors","guard_routes",
        "cameras","keycards","intel","objective","terminal","lighting",
        "alarm_budget"}:
        raise StealthActionError("infiltration requires exact authored scene geography")
    spawn=_xy(layout["spawn"],"spawn")
    exit_at=_xy(layout["extraction"],"extraction")
    objective=_xy(layout["objective"],"objective")
    terminal=_xy(layout["terminal"],"terminal")
    walls=_points(layout["walls"],0,40,"walls")
    shadows=_points(layout["shadows"],0,32,"shadows")
    vents=_points(layout["vents"],0,12,"vents")
    doors=_points(layout["doors"],0,8,"doors")
    cameras=_points(layout["cameras"],0,12,"cameras")
    keycards=_points(layout["keycards"],0,10,"keycards")
    intel=_points(layout["intel"],0,10,"intel")
    routes=layout["guard_routes"]
    if type(routes) is not list or len(routes)>16:
        raise StealthActionError("guards must have sixteen or fewer authored patrol circuits")
    checked=[]
    for i,route in enumerate(routes):
        points=_points(route,2,8,"guard patrol "+str(i))
        checked.append(points)
    wallset={tuple(p) for p in walls}
    doorset={tuple(p) for p in doors}
    important=[spawn,exit_at,objective,terminal]+vents+doors+cameras+keycards+intel
    if any(tuple(p) in wallset for p in important):
        raise StealthActionError("critical authored infiltration features occupy walls")
    if wallset & doorset:
        raise StealthActionError("door cannot be placed inside an impassable wall")
    if any(tuple(p) in doorset for p in (spawn,exit_at,objective,terminal)):
        raise StealthActionError("spawn/mission/exit cannot be a closed security door")
    if spawn==exit_at or spawn==objective or exit_at==objective:
        raise StealthActionError("mission needs distinct entry, objective and extraction")
    for route in checked:
        if any(tuple(p) in wallset or tuple(p) in doorset for p in route):
            raise StealthActionError("patrol circuits must not run through blocked terrain")
        for a,b in zip(route,route[1:]):
            if abs(a[0]-b[0])+abs(a[1]-b[1])>5:
                raise StealthActionError("patrol waypoints cannot jump across the map")
    reached=_reachable(spawn,wallset)
    if any(tuple(p) not in reached for p in (exit_at,objective,terminal)):
        raise StealthActionError("authored mission objective, terminal and extraction require physical routes")
    if config["mission"]=="sabotage" and not cameras:
        raise StealthActionError("sabotage requires a real camera security target")
    if config["mission"]=="intelligence" and len(intel)<config["intel_target"]:
        raise StealthActionError("authored intelligence mission requires enough finite caches")
    if config["mission"]=="archive" and not keycards and config["hacking_charges"]==0:
        raise StealthActionError("archive needs at least one genuine unlock path")
    if layout["lighting"] not in ("day","night","storm"):
        raise StealthActionError("unregistered original stealth lighting")
    _integer(layout["alarm_budget"],1,30,"alarm_budget")
    return {"spawn":spawn,"extraction":exit_at,"objective":objective,
            "terminal":terminal,"walls":walls,"shadows":shadows,
            "vents":vents,"doors":doors,"guard_routes":checked,
            "cameras":cameras,"keycards":keycards,"intel":intel,
            "lighting":layout["lighting"],"alarm_budget":layout["alarm_budget"]}


def apply_scene(state,config,layout):
    geo=normalize_layout(config,layout)
    state.update({
        "spawn":geo["spawn"],"player":list(geo["spawn"]),
        "extraction":geo["extraction"],"objective":geo["objective"],
        "terminal":geo["terminal"],"walls":geo["walls"],
        "shadows":geo["shadows"],"vents":geo["vents"],
        "doors":geo["doors"],"open_doors":[],
        "guards":[{"id":i,"position":list(route[0]),"route":route,
                   "waypoint":1,"suspicion":0,"disabled":0,"facing":"south",
                   "last_known":list(route[0])} for i,route in
                  enumerate(geo["guard_routes"][:min(16,config["guard_count"])])],
        "cameras":[{"position":list(p),"active":True} for p in geo["cameras"]],
        "keycards":geo["keycards"],"intel":geo["intel"],
        "lighting":geo["lighting"],"alarm_budget":geo["alarm_budget"],
    })
    return state


def start(config,seed):
    _integer(seed,0,2**31-1,"seed")
    state={
        "seed":seed,"turn":0,"hp":config["health"],"max_hp":config["health"],
        "stamina":config["stamina"],"max_stamina":config["stamina"],
        "stun_charges":config["stun_charges"],"smoke_charges":config["smoke_charges"],
        "emp_charges":config["emp_charges"],"medkits":config["medkits"],
        "hacking":config["hacking_charges"],"keycards_owned":0,
        "disguised":False,"crouched":False,"hidden":False,"smoke_turns":0,
        "alarm":0,"terminal_hacked":False,"archive":False,
        "intel_collected":0,"cameras_disabled":0,"guards_neutralized":0,
        "score":0,"failed":False,"finished":False,"events":[],
        "milestones":[],"extracted":False,"reason":"",
    }
    return apply_scene(state,config,default_layout(config,seed))


def _distance(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


def _blocks(state):
    return {tuple(p) for p in state["walls"]} | (
        {tuple(p) for p in state["doors"]}-{tuple(p) for p in state["open_doors"]})


def _passable(state,p,crouched):
    if not(0<=p[0]<WIDTH and 0<=p[1]<HEIGHT):
        return False
    if tuple(p) in _blocks(state):
        return False
    if list(p) in state["vents"] and not crouched:
        return False
    return True


def _line_of_sight(state,a,b):
    # Integer supercover ray. Exact authored walls/doors block all security rays.
    x0,y0=a
    x1,y1=b
    dx=x1-x0;dy=y1-y0
    nx=abs(dx);ny=abs(dy)
    sx=1 if dx>0 else -1
    sy=1 if dy>0 else -1
    x=x0;y=y0;ix=iy=0
    blocked=_blocks(state)
    while ix<nx or iy<ny:
        decision=(1+2*ix)*ny-(1+2*iy)*nx
        if decision==0:
            x+=sx;y+=sy;ix+=1;iy+=1
        elif decision<0:
            x+=sx;ix+=1
        else:
            y+=sy;iy+=1
        if (x,y) in blocked:
            return False
    return True


def _see(state,config,observer,player,facing):
    distance=_distance(observer,player)
    if distance==0:
        return True
    # 90-degree directed field, except immediately adjacent threats.
    if distance>1:
        dx,dy=DIRECTIONS[facing]
        vx=player[0]-observer[0]
        vy=player[1]-observer[1]
        if vx*dx+vy*dy < max(abs(vx),abs(vy)):
            return False
    radius=min(config["visibility_range"],10)
    radius=max(1,radius-(2 if state["lighting"]=="night" else
                         1 if state["lighting"]=="storm" else 0))
    if state["crouched"]:
        radius=max(1,radius-config["crouch_visibility_reduction"])
    if state["disguised"]:
        radius=max(1,radius-1)
    if state["smoke_turns"]:
        radius=min(radius,1)
    if player in state["shadows"]:
        radius=max(1,radius-config["shadow_bonus"])
    if state["hidden"] or distance>radius:
        return False
    return not config["line_of_sight"] or _line_of_sight(state,observer,player)


def _shortest_step(state,origin,target):
    if origin==target:
        return list(origin)
    start=tuple(origin);goal=tuple(target)
    blocks=_blocks(state)
    pending=deque([start]);previous={start:None}
    while pending:
        x,y=pending.popleft()
        if (x,y)==goal:
            break
        for dx,dy in DIRECTIONS.values():
            nxt=(x+dx,y+dy)
            if (0<=nxt[0]<WIDTH and 0<=nxt[1]<HEIGHT
                and nxt not in blocks and nxt not in previous):
                previous[nxt]=(x,y)
                pending.append(nxt)
    if goal not in previous:
        return list(origin)
    while previous[goal]!=start:
        goal=previous[goal]
    return list(goal)


def _security_update(state,config,noise,origin):
    events=[]
    state["turn"]+=1
    player=state["player"]
    sensed=False
    for guard in state["guards"]:
        if guard["disabled"]:
            guard["disabled"]-=1
            continue
        if guard["suspicion"]>=config["suspicion_threshold"]:
            destination=guard["last_known"]
        else:
            destination=guard["route"][guard["waypoint"]]
        here=guard["position"]
        moved=_shortest_step(state,here,destination)
        if moved!=here:
            dx=moved[0]-here[0];dy=moved[1]-here[1]
            guard["facing"]=next(k for k,v in DIRECTIONS.items() if v==(dx,dy))
            guard["position"]=moved
        if moved==guard["route"][guard["waypoint"]]:
            guard["waypoint"]=(guard["waypoint"]+1)%len(guard["route"])
        visible=_see(state,config,moved,player,guard["facing"])
        heard=(noise>0 and _distance(moved,origin)<=min(12,config["hearing_range"]+noise)
               and (not state["crouched"] or noise>=config["crouch_noise_threshold"]))
        if visible:
            guard["suspicion"]=min(100,guard["suspicion"]+
                                  config["detection_gain"]*(1 if state["disguised"] else 2))
            guard["last_known"]=list(player)
            events.append("patrol_observed_player")
        elif heard:
            guard["suspicion"]=min(100,guard["suspicion"]+noise*config["noise_gain"])
            guard["last_known"]=list(origin)
            events.append("patrol_investigating_noise")
        else:
            guard["suspicion"]=max(0,guard["suspicion"]-config["noise_decay"])
        if guard["suspicion"]>=config["suspicion_threshold"]:
            sensed=True
            if visible and _distance(moved,player)<=1:
                state["hp"]=max(0,state["hp"]-config["contact_damage"])
                events.append("guard_close_contact_damage")
    # Powered cameras provide genuinely different coverage to patrol cones.
    for camera in state["cameras"]:
        if (camera["active"] and state["smoke_turns"]==0 and not state["hidden"]
            and _distance(camera["position"],player)<=config["camera_range"]
            and (not config["line_of_sight"] or
                 _line_of_sight(state,camera["position"],player))):
            sensed=True
            events.append("active_camera_alert")
    if state["smoke_turns"]:
        state["smoke_turns"]-=1
    if sensed:
        state["alarm"]=min(100,state["alarm"]+config["alarm_gain"])
        events.append("security_alarm_escalated")
    else:
        state["alarm"]=max(0,state["alarm"]-config["alarm_cooldown"])
    if state["alarm"]>=state["alarm_budget"]*10:
        state["hp"]=max(0,state["hp"]-config["alarm_damage"])
        events.append("facility_lockdown_damage")
    if state["hp"]==0:
        state["failed"]=True
        state["reason"]="captured"
        events.append("player_captured")
    if (config["fail_on_alarm"] and state["alarm"]>=100
        and not state["finished"]):
        state["failed"]=True
        state["reason"]="maximum_alarm"
        events.append("facility_automated_lockdown")
    return events


def _consume(state,key,amount=1):
    if state[key]<amount:
        raise StealthActionError("no remaining "+key+" for original stealth action")
    state[key]-=amount


def _nearby(state,target):
    return _distance(state["player"],target)<=1


def _move(state,config,direction,mode):
    delta=DIRECTIONS[direction]
    steps=2 if mode=="sprint" else 1
    if mode=="sprint":
        _consume(state,"stamina",config["sprint_stamina"])
    current=list(state["player"])
    crouch=mode=="crouch"
    for _ in range(steps):
        dest=[current[0]+delta[0],current[1]+delta[1]]
        if not _passable(state,dest,crouch):
            raise StealthActionError("blocked original map or vent requires crouched entry")
        current=dest
    state["player"]=current
    state["crouched"]=crouch
    state["hidden"]=False
    # Noise emerges from actual movement style and terrain, not a filler flag.
    sound={"move":2,"crouch":0,"sprint":6}[mode]
    if current in state["shadows"] and crouch:
        sound=0
    return ["player_moved_on_original_grid"],sound


def step(state,config,action):
    if action not in ACTIONS:
        raise StealthActionError("unregistered original stealth command")
    if state["finished"] or state["failed"]:
        raise StealthActionError("infiltration terminal outcome cannot take another action")
    previous=list(state["player"])
    events=[];noise=0
    if action.startswith(("move_","crouch_","sprint_")):
        mode,direction=action.split("_")
        events,noise=_move(state,config,direction,mode)
    elif action.startswith("decoy_"):
        _consume(state,"stun_charges")
        dx,dy=DIRECTIONS[action.split("_")[1]]
        previous=[max(0,min(WIDTH-1,state["player"][0]+3*dx)),
                  max(0,min(HEIGHT-1,state["player"][1]+3*dy))]
        noise=7
        events.append("directional_decoy_sound")
    elif action=="hide":
        if (state["player"] not in state["shadows"]
            and state["player"] not in state["vents"]):
            raise StealthActionError("hiding requires authored cover, not empty floor")
        state["hidden"]=True
        state["crouched"]=True
        events.append("player_hidden_in_real_cover")
    elif action=="emerge":
        state["hidden"]=False
        events.append("player_left_cover")
    elif action in ("wait","rest"):
        state["stamina"]=min(state["max_stamina"],state["stamina"]+
                             (config["stamina_regen"]*(2 if action=="rest" else 1)))
        events.append("turn_spent_and_stamina_recovered")
    elif action=="disguise":
        if not config["disguises"] or state["disguised"]:
            raise StealthActionError("disguises disabled or already worn")
        if state["guards_neutralized"]==0:
            raise StealthActionError("disguise requires actual neutralized security uniform")
        state["disguised"]=True
        events.append("uniform_disguise_acquired_from_guard")
    elif action=="hack_terminal":
        if not _nearby(state,state["terminal"]) or state["terminal_hacked"]:
            raise StealthActionError("must be adjacent to unhacked physical terminal")
        _consume(state,"hacking")
        state["terminal_hacked"]=True
        state["score"]+=20
        events.append("authoritative_security_terminal_hacked")
        noise=1
    elif action=="hack_door":
        available=[p for p in state["doors"] if p not in state["open_doors"]
                   and _nearby(state,p)]
        if not available:
            raise StealthActionError("no reachable closed security door")
        if state["keycards_owned"]==0:
            _consume(state,"hacking")
        state["open_doors"].append(available[0])
        state["open_doors"].sort()
        events.append("spatial_security_door_unlocked")
        noise=1
    elif action=="collect_keycard":
        target=next((p for p in state["keycards"] if _nearby(state,p)),None)
        if target is None:
            raise StealthActionError("security keycard must be physically recovered once")
        state["keycards"].remove(target)
        state["keycards_owned"]+=1
        events.append("finite_keycard_recovered_from_authored_scene")
    elif action=="steal":
        if not _nearby(state,state["objective"]) or state["archive"]:
            raise StealthActionError("archive must be physically reached once")
        if not state["terminal_hacked"] and not state["keycards_owned"]:
            raise StealthActionError("secure archive needs real hacking or keycard access")
        state["archive"]=True
        state["score"]+=30
        events.append("original_facility_archive_seized")
        noise=2
    elif action=="disable_camera":
        target=next((c for c in state["cameras"] if c["active"] and
                     _nearby(state,c["position"])),None)
        if not target:
            raise StealthActionError("must reach a live camera to disable it")
        target["active"]=False
        state["cameras_disabled"]+=1
        events.append("powered_camera_physically_disabled")
        noise=2
    elif action=="neutralize":
        target=next((g for g in state["guards"] if g["disabled"]==0 and
                     _nearby(state,g["position"])),None)
        if not target:
            raise StealthActionError("cannot neutralize a distant or already-disabled guard")
        _consume(state,"stun_charges")
        target["disabled"]=config["stun_duration"]
        target["suspicion"]=0
        state["guards_neutralized"]+=1
        events.append("nearby_patrol_temporarily_stunned")
        noise=2
    elif action=="deploy_smoke":
        _consume(state,"smoke_charges")
        state["smoke_turns"]=config["smoke_duration"]
        events.append("finite_smoke_gadget_deployed")
    elif action=="deploy_emp":
        _consume(state,"emp_charges")
        disabled=0
        for c in state["cameras"]:
            if c["active"] and _distance(c["position"],state["player"])<=config["emp_radius"]:
                c["active"]=False
                disabled+=1
        state["cameras_disabled"]+=disabled
        events.append("finite_emp_disabled_"+str(disabled)+"_spatial_cameras")
        noise=3
    elif action=="collect_intel":
        picked=next((p for p in state["intel"] if _nearby(state,p)),None)
        if picked is None:
            raise StealthActionError("intel cannot be collected remotely or twice")
        state["intel"].remove(picked)
        state["intel_collected"]+=1
        state["score"]+=10
        events.append("original_intelligence_evidence_collected")
    elif action=="extract":
        if not _nearby(state,state["extraction"]):
            raise StealthActionError("infiltration extraction requires reaching exit")
        completed={"archive":state["archive"],
                   "sabotage":state["terminal_hacked"] and state["cameras_disabled"]>0,
                   "intelligence":state["intel_collected"]>=config["intel_target"]}
        if not completed[config["mission"]]:
            raise StealthActionError("current mission objective was not achieved")
        state["extracted"]=True
        state["finished"]=True
        state["score"]+=max(0,100-state["alarm"])+state["hp"]
        state["milestones"].append("authoritative_original_infiltration_complete")
        events.append("actual_mission_extraction_success")
    elif action=="use_medkit":
        if state["hp"]>=state["max_hp"]:
            raise StealthActionError("full health cannot consume a field medkit")
        _consume(state,"medkits")
        state["hp"]=min(state["max_hp"],state["hp"]+config["medkit_heal"])
        events.append("paid_medical_supply_restored_actual_health")
    else:
        raise StealthActionError("unexpected original infiltration command")
    if not state["finished"]:
        events.extend(_security_update(state,config,noise,previous))
    state["events"]=events
    return events


__all__=["WIDTH","HEIGHT","ACTIONS","StealthActionError","default_layout",
         "normalize_layout","start","apply_scene","step"]
