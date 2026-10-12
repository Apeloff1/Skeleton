"""Original deterministic sports simulation with four real rule variations.

Team, racket, arena and turn-based modes have separate eligible inputs,
possession/rally state transitions and earned scoring. All movement is bounded,
environment and roster resources are real. No licensed teams, leagues, players,
arenas, recordings, brands or assets are imported.
"""
from __future__ import annotations

MODES=("team","racket","arena","turn_based")
WEATHER=("clear","rain","wind")
ACTIONS=(
    "inspect","rest","substitute","tactic:balanced","tactic:press","tactic:hold",
    "advance","sprint","pass","shoot","block","intercept","dribble","cross",
    "serve","drive","slice","lob","smash","net",
    "carry","dash","sidestep","tackle","throw","guard","score",
    "move","switch_lane","end_turn",
)
MODE_ACTIONS={
    "team":frozenset(("advance","sprint","pass","shoot","block","intercept","dribble","cross")),
    "racket":frozenset(("serve","drive","slice","lob","smash","net")),
    "arena":frozenset(("carry","dash","sidestep","tackle","throw","guard","score")),
    "turn_based":frozenset(("move","dash","switch_lane","tackle","pass","shoot","end_turn")),
}
COMMON=frozenset(("inspect","rest","substitute","tactic:balanced",
                   "tactic:press","tactic:hold"))
ATTACK={"drive":5,"slice":4,"lob":3,"smash":13,"net":9}
STAMINA={
    "advance":3,"sprint":9,"pass":4,"shoot":8,"block":3,"intercept":5,
    "dribble":5,"cross":6,"serve":5,"drive":5,"slice":4,"lob":4,
    "smash":10,"net":7,"carry":5,"dash":9,"sidestep":3,"tackle":7,
    "throw":6,"guard":3,"score":5,"move":3,"switch_lane":3,"end_turn":0,
}


class SportsActionError(ValueError):
    """Invalid sport command, physically impossible scoring or forged source."""


def _int(v,lower,upper,name):
    if type(v) is not int or not lower<=v<=upper:
        raise SportsActionError("invalid original sports "+name)
    return v


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    length=config["field_length"]
    return {
        "title":"Original Stadium Series "+str(seed%1000),
        "weather":WEATHER[seed%3],
        "mode":config["rules"],
        "home_spawn":[2,1],
        "away_spawn":[length-5,1],
        "goal_x":length-2,
        "cover":[[length//2,0],[length//2,2]],
        "sideline_lanes":3,
        "target_score":config["target_score"],
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
        "title","weather","mode","home_spawn","away_spawn",
        "goal_x","cover","sideline_lanes","target_score"
    }:
        raise SportsActionError("strict original sports field source required")
    title=layout["title"]
    if type(title) is not str or not 3<=len(title)<=64 or not all(
        ch.isalnum() or ch in " -_" for ch in title
    ):
        raise SportsActionError("unsafe original sports level title")
    if type(layout["weather"]) is not str or layout["weather"] not in WEATHER:
        raise SportsActionError("unknown original weather variation")
    if layout["mode"]!=config["rules"] or type(layout["mode"]) is not str:
        raise SportsActionError("sporting rules cannot change outside reviewed editor")
    width=config["field_length"]
    occupied=[]
    for k in ("home_spawn","away_spawn"):
        v=layout[k]
        if type(v) is not list or len(v)!=2:
            raise SportsActionError("team spawn requires exact player coordinates")
        x=_int(v[0],1,width-3,k+".x")
        lane=_int(v[1],0,2,k+".lane")
        occupied.append([x,lane])
    if occupied[0]==occupied[1]:
        raise SportsActionError("home and away cannot spawn on same grid cell")
    goal=_int(layout["goal_x"],width-3,width-1,"goal")
    cover=layout["cover"]
    if type(cover) is not list or len(cover)>8:
        raise SportsActionError("arena cover budget exceeded")
    safe=[];seen=set()
    for cell in cover:
        if type(cell) is not list or len(cell)!=2:
            raise SportsActionError("exact terrain cell required")
        x=_int(cell[0],2,width-4,"cover x")
        lane=_int(cell[1],0,2,"cover lane")
        if (x,lane) in seen or [x,lane] in occupied:
            raise SportsActionError("cover overlaps a spawn or another cell")
        seen.add((x,lane));safe.append([x,lane])
    if _int(layout["sideline_lanes"],3,3,"lane count")!=3:
        raise SportsActionError("only reviewed three-lane stadium supported")
    target=_int(layout["target_score"],1,config["target_score"],"target score")
    if target!=config["target_score"]:
        raise SportsActionError("goal cannot be reduced by a level edit")
    return {
        "title":title,"weather":layout["weather"],"mode":config["rules"],
        "home_spawn":occupied[0],"away_spawn":occupied[1],
        "goal_x":goal,"cover":safe,"sideline_lanes":3,
        "target_score":config["target_score"],
    }


def start(config,seed):
    layout=default_layout(config,seed)
    mode=config["rules"]
    if mode not in MODES:
        raise SportsActionError("unregistered original sporting rules")
    return {
        "tick":0,"mode":mode,"weather":layout["weather"],
        "title":layout["title"],"width":config["field_length"],
        "home":list(layout["home_spawn"]),"away":list(layout["away_spawn"]),
        "teammate":[min(config["field_length"]-3,
                        layout["home_spawn"][0]+min(6,config["pass_distance"])),
                    layout["home_spawn"][1]],
        "ball":[2,1],"owner":"home","cover":[list(c) for c in layout["cover"]],
        "goal_x":layout["goal_x"],"target_score":layout["target_score"],
        "home_score":0,"away_score":0,
        "stamina":config["starting_stamina"],
        "max_stamina":config["starting_stamina"],
        "away_stamina":config["starting_stamina"],
        "ap_remaining":config["action_points"],"turns_committed":0,
        "subs_left":min(config["substitutions"],config["team_size"]-1),
        "fatigue":0,"injuries":0,"fouls":0,"passes":0,"interceptions":0,
        "shots":0,"misses":0,"goals":0,"blocks":0,
        "tempo":"balanced","rally":False,"rally_strokes":0,
        "opponent_readiness":config["opponent_skill"],
        "serve_home":True,"match_limit":config["match_turn_limit"],
        "finished":False,"failed":False,"victory":False,
        "score_reason":None,"events":[],
    }


def apply_scene(state,config,layout):
    source=normalize_layout(config,layout)
    if state["tick"]!=0:
        raise SportsActionError("cannot replace a live sporting arena")
    state["weather"]=source["weather"]
    state["title"]=source["title"]
    state["home"]=list(source["home_spawn"])
    state["away"]=list(source["away_spawn"])
    state["teammate"]=[
        min(config["field_length"]-3,
            source["home_spawn"][0]+min(6,config["pass_distance"])),
        source["home_spawn"][1],
    ]
    state["ball"]=list(source["home_spawn"])
    state["owner"]="home"
    state["cover"]=[list(v) for v in source["cover"]]
    state["goal_x"]=source["goal_x"]
    state["target_score"]=source["target_score"]


def _distance(a,b):
    return abs(a[0]-b[0])+abs(a[1]-b[1])


def _move(state,side,steps):
    origin=state[side]
    sign=1 if side=="home" else -1
    x=max(1,min(state["width"]-3,origin[0]+sign*steps))
    # Always resolve the NEAREST physical obstacle along the swept path,
    # regardless of authored JSON order. A farther wall cannot erase a
    # nearer collision or let high-speed athletes tunnel through cover.
    crossed=[
        cell[0] for cell in state["cover"]
        if cell[1]==origin[1]
        and 0<(cell[0]-origin[0])*sign<=abs(x-origin[0])
    ]
    if crossed:
        x=(min(crossed) if sign>0 else max(crossed))-sign
    state[side]=[x,origin[1]]
    # Roster support exists at a bounded chart location. Movement cannot
    # instantly transport that second athlete; if overtaken, they trail behind.
    if side=="home" and state["teammate"]==state["home"]:
        state["teammate"]=list(origin)
    if state["owner"]==side:
        state["ball"]=list(state[side])


def _point(state,side,reason):
    state[side+"_score"]+=1
    state["score_reason"]=reason
    state["rally"]=False
    state["rally_strokes"]=0
    state["owner"]="home" if side=="away" else "away"
    state["ball"]=list(state[state["owner"]])
    state["stamina"]=min(state["stamina"]+10,state["max_stamina"])
    return ["earned_"+side+"_point",reason]


def _opponent(state,config,action):
    events=[]
    if state["mode"]=="racket":
        if state["rally"]:
            # A real reply increases demand. Strong shots consume stamina,
            # slow defensive returns permit the player to reset position.
            state["opponent_readiness"]=min(
                config["opponent_skill"]+8,
                max(1,state["opponent_readiness"]+
                    (1 if state["rally_strokes"]%3==0 else -1)))
            state["rally_strokes"]+=1
            events.append("opponent_rally_return")
        return events
    if state["owner"]=="away":
        _move(state,"away",config["opponent_speed"])
        if state["away"][0]<=2:
            # A goal still requires the non-teleported opponent to reach its end.
            events+=_point(state,"away","away_field_goal")
        else:
            events.append("away_advances_with_ball")
    else:
        # Opposing athlete occupies real cells and can steal under spatial
        # pressure; a successful home action is not automatically a goal.
        _move(state,"away",min(config["opponent_speed"],
                               max(0,state["away"][0]-state["home"][0]-1)))
        radius=max(0,config["defense_radius"]+
                   (1 if state["tempo"]=="hold" else
                    -1 if state["tempo"]=="press" else 0))
        if (_distance(state["away"],state["home"])<=radius
            and state["tick"]%config["interception_period"]==0
            and action not in ("sprint","dash","sidestep","pass","cross","throw")):
            state["owner"]="away"
            state["ball"]=list(state["away"])
            state["interceptions"]+=1
            events.append("away_interception")
    return events


def step(state,config,action):
    mode=state["mode"]
    if action not in ACTIONS or (action not in COMMON and action not in MODE_ACTIONS[mode]):
        raise SportsActionError("action is not a legitimate rule-specific sporting control")
    if state["finished"] or state["failed"]:
        raise SportsActionError("cannot play after original match termination")
    if mode=="turn_based" and state["ap_remaining"]<=0 and action!="end_turn":
        raise SportsActionError("turn-based action points require a committed turn")
    if action=="substitute" and (
        state["subs_left"]<=0 or mode=="racket"
    ):
        raise SportsActionError("original substitutions require a finite team roster")
    if mode=="racket" and action=="serve" and state["rally"]:
        raise SportsActionError("cannot repeatedly serve into a live rally")
    if mode=="racket" and action in ATTACK and not state["rally"]:
        raise SportsActionError("return requires an actual preceding serve")
    if action=="shoot" and state["owner"]!="home":
        raise SportsActionError("unpossessed field ball cannot score")
    if action in ("score","throw","pass","cross") and state["owner"]!="home":
        raise SportsActionError("ball ownership is required for authored sports actions")
    cost=STAMINA.get(action,0)
    if mode=="arena" and action=="tackle":
        cost+=config["contact_cost"]
    if state["stamina"]<cost:
        raise SportsActionError("real sporting stamina cannot finance this action")
    state["stamina"]-=cost
    events=[]
    if action.startswith("tactic:"):
        state["tempo"]=action.split(":",1)[1]
        events.append("team_tactic_reconfigured")
    elif action=="rest":
        state["stamina"]=min(config["starting_stamina"],
                             state["stamina"]+config["recovery_per_turn"]*3)
        events.append("active_recovery")
    elif action=="substitute":
        state["subs_left"]-=1
        state["stamina"]=min(config["starting_stamina"],
                             state["stamina"]+config["substitution_energy"])
        state["fatigue"]=max(0,state["fatigue"]-12)
        events.append("registered_roster_substitution")
    elif mode=="racket":
        if action=="serve":
            state["rally"]=True
            state["rally_strokes"]=1
            state["opponent_readiness"]=config["opponent_skill"]
            state["owner"]="away"
            events.append("legal_original_serve")
        elif action in ATTACK:
            state["shots"]+=1
            state["rally_strokes"]+=1
            attack=ATTACK[action]+config["strike_precision"]+(
                2 if state["rally_strokes"]>=config["rally_combo"] else 0)
            defense=state["opponent_readiness"]+(
                3 if state["weather"]=="wind" and action=="lob" else 0)
            if attack>=defense and state["stamina"]>0:
                events+=_point(state,"home","legal_racket_winner")
            elif action=="smash" and state["stamina"]<config["racket_control"]:
                state["misses"]+=1
                events+=_point(state,"away","racket_unforced_error")
            else:
                events.append("racket_shot_returned")
    else:
        old=list(state["home"])
        if action in ("advance","dribble","carry","move"):
            speed=config["run_speed"]
            if state["weather"]=="rain":
                speed=max(1,speed-config["rain_stride_penalty"])
            _move(state,"home",speed)
        elif action in ("sprint","dash"):
            speed=config["sprint_speed"]
            if state["weather"]=="rain":
                speed=max(1,speed-config["rain_stride_penalty"])
            _move(state,"home",speed)
        elif action in ("pass","cross","throw"):
            # Switching control after a pass is legal only to an athlete who
            # already occupies a real, authored-position-bounded field cell.
            # Do not advance the ball carrier by the range of the pass.
            steps=config["throw_distance"] if action=="throw" else config["pass_distance"]
            receiver=state["teammate"]
            source=state["home"]
            distance=_distance(source,receiver)
            if config["team_size"]<2 or not 0<distance<=steps:
                raise SportsActionError("a real reachable teammate is required to pass")
            if any(cell[1]==source[1]==receiver[1] and
                   min(source[0],receiver[0])<cell[0]<max(source[0],receiver[0])
                   for cell in state["cover"]):
                raise SportsActionError("solid stadium cover blocks the ball trajectory")
            state["passes"]+=1
            if (source[1]==receiver[1]==state["away"][1] and
                min(source[0],receiver[0])<state["away"][0]<max(source[0],receiver[0])):
                state["owner"]="away"
                state["ball"]=list(state["away"])
                state["interceptions"]+=1
                events.append("defender_intercepted_swept_pass")
            else:
                state["home"]=list(receiver)
                state["teammate"]=list(source)
                state["ball"]=list(receiver)
                events.append("earned_ball_transfer_to_existing_teammate")
        elif action in ("sidestep","switch_lane"):
            state["home"][1]=(state["home"][1]+1)%3
            if state["owner"]=="home":
                state["ball"]=list(state["home"])
        elif action in ("intercept","tackle"):
            reach=config["tackle_range"]+(config["press_tackle_bonus"]
                                           if state["tempo"]=="press" else 0)
            if state["owner"]=="away" and _distance(state["home"],state["away"])<=reach:
                state["owner"]="home"
                state["ball"]=list(state["home"])
                state["interceptions"]+=1
                events.append("earned_live_ball_recovery")
            else:
                events.append("out_of_range_tackle")
        elif action in ("block","guard"):
            state["blocks"]+=1
            events.append("defensive_posture")
        elif action in ("shoot","score"):
            state["shots"]+=1
            within=state["home"][0]>=state["goal_x"]-config["shot_range"]
            lane=abs(state["home"][1]-1)<=config["goal_lane_tolerance"]
            defended=_distance(state["away"],state["home"])<=config["defense_radius"]
            shot_power=config["shot_power"]-(
                config["wind_shot_penalty"] if state["weather"]=="wind" else 0)
            shot_precision_ok=shot_power>=(
                config["opponent_skill"] if defended else
                max(1,config["opponent_skill"]//3))
            if within and lane and state["owner"]=="home" and shot_precision_ok:
                state["goals"]+=1
                events+=_point(state,"home","earned_original_field_goal")
            else:
                state["misses"]+=1
                state["owner"]="away"
                state["ball"]=list(state["away"])
                events.append("field_shot_missed_or_saved")
        if mode=="arena" and action in ("dash","carry","throw"):
            # Physical contact is constrained by actual opposing proximity.
            if _distance(state["home"],state["away"])<=config["contact_radius"]:
                state["fatigue"]+=config["collision_fatigue"]
                events.append("real_contact_collision")
        if mode=="turn_based" and action=="end_turn":
            state["turns_committed"]+=1
            state["ap_remaining"]=config["action_points"]
            events.append("tactical_turn_committed")
        if state["home"]!=old and state["owner"]=="home":
            events.append("player_field_position_changed")
    if mode=="turn_based" and action!="end_turn":
        state["ap_remaining"]-=1
    state["tick"]+=1
    if action!="rest":
        state["fatigue"]+=max(1,config["team_size"]//8)
        if state["tempo"]=="press" and action in ("sprint","dash","tackle"):
            state["fatigue"]+=2
    if state["fatigue"]>config["fatigue_limit"]:
        state["stamina"]=max(0,state["stamina"]-config["fatigue_tax"])
        events.append("real_player_fatigue")
    if action not in ("substitute","rest"):
        state["stamina"]=min(config["starting_stamina"],
                             state["stamina"]+config["recovery_per_turn"])
    # A won point resets possession before the next exchange. No AI response
    # can erase an already awarded point or fabricate a second result.
    if not any(e.startswith("earned_") and e.endswith("_point") for e in events):
        if mode!="turn_based" or action=="end_turn":
            events+=_opponent(state,config,action)
    target=state["target_score"]
    if (state["home_score"]>=target or state["away_score"]>=target
        or state["tick"]>=state["match_limit"]):
        state["finished"]=True
        state["victory"]=state["home_score"]>state["away_score"]
        events.append("match_ended_by_play_or_clock")
    state["events"]=events
    return events
