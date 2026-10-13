"""Original spatial arena-fighting game with actual frames, lanes and ringouts.

No external fighters, likenesses, trademarks, movements, animation data or
imported assets. Deterministic turn-frame simulation, real guard/parry,
fatigue, knockback, combo windows, hazards, active opposing AI and rounds.
"""
from __future__ import annotations

WIDTH_MAX=16
LANES=3
ATTACKS={
    "jab":(1,4,3,"high",0),
    "cross":(1,7,5,"high",0),
    "kick":(2,6,6,"mid",0),
    "sweep":(1,5,6,"low",0),
    "uppercut":(1,9,8,"mid",0),
    "grapple":(1,8,9,"grapple",0),
    "projectile":(4,8,5,"mid",1),
    "special":(2,14,8,"high",2),
}
ACTIONS=(
    "approach","retreat","dash","backdash","sidestep_up","sidestep_down",
    "jump","crouch","stand","guard_high","guard_low","parry","dodge",
    "feint","charge","recover","inspect","wait:60","wait:240",
    *ATTACKS,
)


class FightingActionError(ValueError):
    """Unsafe arena, unreachable physical hit or fabricated combat command."""


def _int(v,lo,hi,k):
    if type(v) is not int or not lo<=v<=hi:
        raise FightingActionError("invalid original fighting "+k)
    return v


def _fighter(side,x,lane,config):
    hp=config["player_health"] if side=="blue" else config["enemy_health"]
    return {
       "side":side,"x":x,"lane":lane,"hp":hp,"max_hp":hp,
       "stamina":config["starting_stamina"],
       "max_stamina":config["starting_stamina"],
       "meter":config["starting_meter"],"guard":config["guard_meter"],
       "guard_high":False,"guard_low":False,"parry":False,"crouching":False,
       "airborne":0,"stun":0,"recovery":0,"combo":0,"best_combo":0,
       "last_attack":None,"last_hit_frame":None,"hits":0,"misses":0,"damage_done":0,
       "defended":0,"parried":0,"whiffs":0,"ringouts":0,
    }


def default_layout(config,seed):
    _int(seed,0,2**31-1,"seed")
    width=config["arena_width"]
    hazards=(
        [{"x":width//2,"lane":1,"damage":config["hazard_damage"]}]
        if config["hazards_enabled"] and config["hazard_count"]>0 else []
    )
    cover=[{"x":max(3,width//2),"lane":2,"hp":config["cover_health"]}] if (
        config["cover_enabled"] and config["cover_count"]>0 and width>=8) else []
    return {
        "width":width,"lanes":LANES,"player_spawn":[1,1],
        "enemy_spawn":[width-2,1],
        "hazards":hazards,"cover":cover,
        "theme":("tournament","sky_garden","industrial","mountain")[
                    seed%4],
        "weather":("clear","rain","fog")[seed%3],
        "round_limit_frames":config["round_seconds"]*60,
    }


def normalize_layout(config,layout):
    if type(layout) is not dict or set(layout)!={
       "width","lanes","player_spawn","enemy_spawn",
       "hazards","cover","theme","weather","round_limit_frames"}:
        raise FightingActionError("original arena demands exact scene schema")
    if (_int(layout["width"],8,WIDTH_MAX,"width")!=config["arena_width"] or
        _int(layout["lanes"],LANES,LANES,"lane count")!=LANES):
        raise FightingActionError("authored arena topology cannot bypass editor budget")
    occupied=set()
    for kind in ("player_spawn","enemy_spawn"):
        p=layout[kind]
        if type(p) is not list or len(p)!=2:
            raise FightingActionError("real fighter spawn must have two grid coordinates")
        _int(p[0],1,config["arena_width"]-2,kind+" x")
        _int(p[1],0,LANES-1,kind+" lane")
        if tuple(p) in occupied:
            raise FightingActionError("fighters may not occupy the same real cell")
        occupied.add(tuple(p))
    for kind,maximum,shape in (
        ("hazards",config["hazard_count"],{"x","lane","damage"}),
        ("cover",config["cover_count"],{"x","lane","hp"}),
    ):
        values=layout[kind]
        if type(values) is not list or len(values)>maximum:
            raise FightingActionError("authored arena component exceeds budget")
        if (kind=="hazards" and not config["hazards_enabled"] and values) or (
            kind=="cover" and not config["cover_enabled"] and values):
            raise FightingActionError("disabled authored arena objects cannot be introduced")
        seen=set()
        for part in values:
            if type(part) is not dict or set(part)!=shape:
                raise FightingActionError("strict original arena component keys required")
            x=_int(part["x"],1,config["arena_width"]-2,"object x")
            lane=_int(part["lane"],0,LANES-1,"object lane")
            if (x,lane) in occupied or (x,lane) in seen:
                raise FightingActionError("signed fighters, obstacles and hazards must not overlap")
            seen.add((x,lane))
            _int(part["damage"] if kind=="hazards" else part["hp"],0,
                 config["hazard_damage"] if kind=="hazards" else
                 config["cover_health"],"bounded original environmental durability")
        occupied.update(seen)
    if layout["theme"] not in ("tournament","sky_garden","industrial","mountain"):
        raise FightingActionError("unregistered original thematic arena")
    if layout["weather"] not in ("clear","rain","fog"):
        raise FightingActionError("unregistered original physical weather")
    if _int(layout["round_limit_frames"],1,18000,"time limit")!=config["round_seconds"]*60:
        raise FightingActionError("authoring cannot fake unlimited match time")
    return {
        **dict(layout),"player_spawn":list(layout["player_spawn"]),
        "enemy_spawn":list(layout["enemy_spawn"]),
        "hazards":[dict(h) for h in layout["hazards"]],
        "cover":[dict(o) for o in layout["cover"]],
    }


def apply_scene(state,config,layout):
    arena=normalize_layout(config,layout)
    state["arena"]=arena
    state["player"]=_fighter("blue",*arena["player_spawn"],config)
    state["opponent"]=_fighter("red",*arena["enemy_spawn"],config)
    state["clock_frames"]=0
    state["attacks_observed"]={}
    return state


def start(config,seed):
    _int(seed,0,2**31-1,"seed")
    if config["starting_meter"]>config["meter_cap"]:
        raise FightingActionError("original fighter cannot begin above authored special meter capacity")
    state={
       "seed":seed,"arena":{},"player":{},"opponent":{},
       "turn":0,"clock_frames":0,"round":1,
       "blue_rounds":0,"red_rounds":0,"round_winners":[],
       "attacks_observed":{},"combos_won":0,"ringouts":0,
       "events":[],"finished":False,"failed":False,
       "victory":False,"reason":"",
    }
    return apply_scene(state,config,default_layout(config,seed))


def _facing(fighter,target):
    return 1 if fighter["x"]<=target["x"] else -1


def _distance(a,b):
    return abs(a["x"]-b["x"])+abs(a["lane"]-b["lane"])


def _occupied(state,x,lane,actor):
    other=state["opponent"] if actor is state["player"] else state["player"]
    if other["x"]==x and other["lane"]==lane:return True
    return any(p["hp"]>0 and p["x"]==x and p["lane"]==lane
               for p in state["arena"]["cover"])


def _move(state,config,actor,dx,dlane,events):
    if actor["stun"]>0:
        events.append("stunned_original_fighter_could_not_move")
        return False
    if actor["stamina"]<config["move_stamina"]:
        events.append("exhausted_fighter_lacks_real_footwork_energy")
        return False
    x=actor["x"];lane=actor["lane"]
    for _ in range(max(abs(dx),abs(dlane))):
        nx=x+(1 if dx>0 else -1 if dx<0 else 0)
        nl=lane+(1 if dlane>0 else -1 if dlane<0 else 0)
        if not 0<=nl<LANES or not 0<=nx<state["arena"]["width"] or (
           _occupied(state,nx,nl,actor)):
            events.append("real_arena_obstacle_or_opponent_blocked_footwork")
            return False
        x=nx;lane=nl
        dx-=1 if dx>0 else -1 if dx<0 else 0
        dlane-=1 if dlane>0 else -1 if dlane<0 else 0
    actor["x"]=x;actor["lane"]=lane
    actor["stamina"]-=config["move_stamina"]
    events.append("original_fighter_moved_one_or_more_real_arena_cells")
    return True


def _hit(state,config,attacker,defender,name,events):
    distance=_distance(attacker,defender)
    reach,raw,stamina,zone,special=ATTACKS[name]
    if (attacker["last_hit_frame"] is not None and
        state["clock_frames"]-attacker["last_hit_frame"]>config["combo_window_frames"]):
        attacker["combo"]=0
        events.append("original_combo_expired_after_real_frame_window")
    if distance>reach or (name not in ("grapple","uppercut")
                           and attacker["lane"]!=defender["lane"]):
        attacker["whiffs"]+=1
        attacker["combo"]=0
        events.append("original_attack_whiffed_outside_real_physical_range")
        return False
    if name=="projectile" and state["arena"]["weather"]=="fog" and distance>max(
          1,reach-config["fog_projectile_penalty"]):
        attacker["whiffs"]+=1
        events.append("original_mist_occluded_ranged_fighter_attack")
        return False
    if name=="projectile" and any(c["hp"]>0 and
            c["lane"]==attacker["lane"] and
            min(attacker["x"],defender["x"])<c["x"]<max(attacker["x"],defender["x"])
            for c in state["arena"]["cover"]):
        attacker["whiffs"]+=1
        events.append("real_projectile_intercepted_by_authored_arena_cover")
        return False
    if defender["crouching"] and zone=="high" and name!="special":
        attacker["whiffs"]+=1
        attacker["combo"]=0
        events.append("physical_grounded_crouch_avoided_actual_high_strike")
        return False
    if defender["airborne"] and zone=="low":
        attacker["whiffs"]+=1
        events.append("grounded_original_sweep_passed_beneath_actual_jumping_opponent")
        return False
    if defender["parry"] and name!="grapple":
        defender["parried"]+=1
        attacker["stun"]+=config["parry_stun_frames"]
        defender["meter"]=min(config["meter_cap"],
                              defender["meter"]+config["parry_meter_gain"])
        defender["parry"]=False
        events.append("precisely_timed_original_defense_parried_real_attack")
        return False
    guard=(zone!="grapple" and (defender["guard_high"] and zone in ("high","mid")
               or defender["guard_low"] and zone=="low"
               or config["accessibility_auto_guard"] and zone!="grapple"))
    damage=raw+config["attack_bonus"]
    if attacker["combo"] and attacker["combo"]<config["combo_limit"]:
        damage+=min(config["combo_damage_cap"],attacker["combo"]*
                    config["combo_damage_bonus"])
    if guard:
        guard_hit=max(1,config["guard_chip"])
        defender["guard"]=max(0,defender["guard"]-
                             config["guard_damage"]-max(1,damage//2))
        defender["hp"]=max(0,defender["hp"]-guard_hit)
        defender["defended"]+=1
        attacker["combo"]=0
        if defender["guard"]==0:
            defender["stun"]+=config["guard_break_stun"]
            events.append("real_original_guard_meter_broke_under_pressure")
        else:
            events.append("legitimate_original_guard_prevented_major_hit")
        damage=guard_hit
    else:
        defender["hp"]=max(0,defender["hp"]-damage)
        attacker["hits"]+=1
        attacker["combo"]=min(config["combo_limit"],attacker["combo"]+1)
        attacker["last_hit_frame"]=state["clock_frames"]
        attacker["best_combo"]=max(attacker["best_combo"],attacker["combo"])
        defender["stun"]+=config["hitstun_frames"]
        events.append("actual_original_hitbox_resolved_combat_damage")
        if config["knockback"] and name in ("cross","kick","uppercut","special"):
            # Push the target cell by cell: intermediate cover and the
            # opposing fighter are solid, so momentum cannot tunnel through.
            direction=_facing(attacker,defender)
            for _ in range(config["knockback"]):
                destination=defender["x"]+direction
                if destination<0 or destination>=state["arena"]["width"]:
                    if config["ring_outs"]:
                        defender["hp"]=0
                        attacker["ringouts"]+=1
                        state["ringouts"]+=1
                        events.append("true_original_arena_edge_ringout")
                    else:
                        events.append("original_arena_boundary_stopped_knockback")
                    break
                if _occupied(state,destination,defender["lane"],defender):
                    events.append("physical_original_stage_cover_blocked_knockback")
                    break
                defender["x"]=destination
                events.append("original_contact_knockback_changed_real_location")
    attacker["damage_done"]+=damage
    attacker["meter"]=min(config["meter_cap"],
                         attacker["meter"]+config["meter_gain_per_hit"])
    return True


def _attack(state,config,attacker,defender,name,events):
    _,_,stamina,_,tier=ATTACKS[name]
    cost=stamina+config["attack_stamina"]
    if attacker["stamina"]<cost:
        raise FightingActionError("fighter lacks actual stamina to issue that attack")
    meter=(config["projectile_meter_cost"] if tier==1
           else config["special_meter_cost"] if tier==2 else 0)
    if attacker["meter"]<meter:
        raise FightingActionError("special and ranged attacks require earned finite meter")
    if attacker["stun"]>0:
        raise FightingActionError("stunned fighter cannot bypass hitstun")
    if attacker["recovery"]>0 and not (
        attacker["combo"] and attacker["recovery"]<=config["input_buffer"]):
        raise FightingActionError("committed attack must complete real recovery frames")
    attacker["stamina"]-=cost
    attacker["meter"]-=meter
    attacker["last_attack"]=name
    attacker["recovery"]=config["recovery_frames"]
    return _hit(state,config,attacker,defender,name,events)


def _hazards(state,config,events):
    if not config["hazards_enabled"]:return
    if state["clock_frames"]%config["hazard_period_frames"]>=config["frames_per_turn"]:
        return
    for f in (state["player"],state["opponent"]):
        if f["airborne"]:continue
        if any(h["x"]==f["x"] and h["lane"]==f["lane"]
               for h in state["arena"]["hazards"]):
            dmg=next(h["damage"] for h in state["arena"]["hazards"]
                     if h["x"]==f["x"] and h["lane"]==f["lane"])
            f["hp"]=max(0,f["hp"]-dmg)
            events.append("original_canonical_arena_hazard_applied_real_damage")


def _round(state,config,events):
    # step() checks round completion after the player, the AI and elapsed
    # frames. Terminal scores must never be awarded twice in one step.
    if state["finished"] or state["failed"]:
        return
    player=state["player"];enemy=state["opponent"]
    timeout=state["clock_frames"]>=state["arena"]["round_limit_frames"]
    if player["hp"]>0 and enemy["hp"]>0 and not timeout:return
    if player["hp"]>enemy["hp"]:
        winner="blue"
    elif enemy["hp"]>player["hp"]:
        winner="red"
    else:
        winner="blue" if player["damage_done"]>enemy["damage_done"] else "red"
    state[winner+"_rounds"]+=1
    state["round_winners"].append(winner)
    events.append("real_original_fighting_round_completed_"+winner)
    if state[winner+"_rounds"]>=config["rounds_to_win"]:
        state["finished"]=True
        state["victory"]=winner=="blue"
        state["failed"]=winner=="red"
        state["reason"]=("legitimate_arena_champion" if winner=="blue"
                         else "legitimate_arena_match_defeat")
        events.append("original_fighting_match_genuinely_finished")
        return
    state["round"]+=1
    source=state["arena"]
    state["player"]=_fighter("blue",*source["player_spawn"],config)
    state["opponent"]=_fighter("red",*source["enemy_spawn"],config)
    state["clock_frames"]=0
    events.append("new_original_fighting_round_loaded_with_real_health")


def _ai(state,config,events):
    enemy=state["opponent"];hero=state["player"]
    if enemy["hp"]==0 or enemy["stun"]>0:return
    distance=_distance(enemy,hero)
    style=config["ai_style"]
    if style=="adaptive" and state["attacks_observed"].get("grapple",0)>config["ai_adaptation_threshold"]:
        style="aggressive"
    if (distance<=1 and hero["last_attack"] in ("jab","cross","kick") and
        style=="defensive" and (state["turn"]%4)<config["ai_defense_frequency"]):
        enemy["guard_high"]=True;enemy["guard_low"]=False
        events.append("adaptive_original_opponent_chose_real_guard")
        return
    if enemy["recovery"]>config["input_buffer"]:
        enemy["stamina"]=min(enemy["max_stamina"],enemy["stamina"]+config["stamina_regen"])
        events.append("original_opponent_observed_actual_attack_recovery")
        return
    if distance<=2 and enemy["stamina"]>=config["attack_stamina"]+6:
        kind="kick" if distance>1 else (
            "sweep" if hero["guard_high"] else "jab")
        _attack(state,config,enemy,hero,kind,events)
        events.append("actual_original_opponent_selected_spatial_counterattack")
    elif distance>1:
        towards=_facing(enemy,hero)
        _move(state,config,enemy,towards,0,events)
    else:
        enemy["stamina"]=min(enemy["max_stamina"],enemy["stamina"]+
                            config["stamina_regen"])
        events.append("opponent_conserved_real_stamina")


def _turn(state,config,events,advance_frames):
    # Frame durations are discrete fixed steps, rather than browser frame
    # times. The same replay yields byte-identical gameplay under any OS.
    for f in (state["player"],state["opponent"]):
        f["stun"]=max(0,f["stun"]-advance_frames)
        f["recovery"]=max(0,f["recovery"]-advance_frames)
        f["airborne"]=max(0,f["airborne"]-advance_frames)
        f["stamina"]=min(f["max_stamina"],f["stamina"]+
                         config["stamina_regen"])
        f["guard"]=min(config["guard_meter"],f["guard"]+
                       config["guard_regen"])
        # An unused parry is a brief timed posture, not a permanent shield.
        f["parry"]=False
    state["clock_frames"]+=advance_frames
    _hazards(state,config,events)
    _round(state,config,events)


def step(state,config,action):
    if action not in ACTIONS:
        raise FightingActionError("unregistered original spatial fighting action")
    if state["finished"] or state["failed"]:
        raise FightingActionError("ended match cannot be replayed as an active fight")
    events=[]
    hero=state["player"];enemy=state["opponent"]
    if action in ATTACKS:
        _attack(state,config,hero,enemy,action,events)
        state["attacks_observed"][action]=state["attacks_observed"].get(action,0)+1
        hero["guard_high"]=False;hero["guard_low"]=False;hero["parry"]=False
    elif action in ("approach","retreat","dash","backdash","sidestep_up","sidestep_down"):
        toward=_facing(hero,enemy)
        delta=2 if action in ("dash","backdash") else 1
        if action in ("retreat","backdash"):delta=-delta
        dx=0 if action in ("sidestep_up","sidestep_down") else toward*delta
        dlane=1 if action=="sidestep_down" else -1 if action=="sidestep_up" else 0
        if action in ("dash","backdash") and (
            hero["stamina"]<config["move_stamina"]+config["dash_stamina_cost"]):
            raise FightingActionError("dash needs additional real committed stamina")
        moved=_move(state,config,hero,dx,dlane,events)
        if moved and action in ("dash","backdash"):
            hero["stamina"]-=config["dash_stamina_cost"]
            events.append("original_two_cell_dash_paid_extra_finite_stamina")
    elif action in ("guard_high","guard_low"):
        hero["guard_high"]=action=="guard_high"
        hero["guard_low"]=action=="guard_low"
        hero["parry"]=False
        events.append("original_human_authorized_high_or_low_guard")
    elif action=="parry":
        if hero["stamina"]<config["parry_stamina"]:
            raise FightingActionError("parry needs actually available stamina")
        hero["stamina"]-=config["parry_stamina"]
        hero["parry"]=True
        events.append("original_fighter_set_actual_one_turn_parry")
    elif action=="jump":
        if hero["stamina"]<config["jump_stamina"]:
            raise FightingActionError("airborne movement costs physical stamina")
        hero["stamina"]-=config["jump_stamina"]
        hero["airborne"]=config["jump_duration_frames"]
        hero["guard_low"]=False
        events.append("actual_original_airborne_low_attack_evasion")
    elif action=="crouch":
        hero["crouching"]=True;hero["airborne"]=0
        events.append("original_fighter_became_grounded")
    elif action=="stand":
        hero["crouching"]=False
        events.append("original_fighter_stood_back_up")
    elif action=="dodge":
        hero["parry"]=False
        if _distance(hero,enemy)<=2:
            _move(state,config,hero,-_facing(hero,enemy),0,events)
        events.append("original_character_attempted_physical_evasion")
    elif action=="charge":
        hero["meter"]=min(config["meter_cap"],
                           hero["meter"]+config["charge_meter"])
        events.append("legitimate_original_nonattacking_meter_charge")
    elif action=="recover":
        hero["stamina"]=min(hero["max_stamina"],
                            hero["stamina"]+config["recover_stamina"])
        events.append("actual_original_fighter_spent_turn_recovering_stamina")
    elif action=="feint":
        if hero["stamina"]<config["feint_stamina"]:
            raise FightingActionError("feint requires paid stance commitment")
        hero["stamina"]-=config["feint_stamina"]
        if _distance(hero,enemy)<=config["feint_range"]:
            enemy["guard_high"]=False;enemy["guard_low"]=False
            events.append("original_close_range_paid_feint_disrupted_real_guard")
        else:
            events.append("original_distant_feint_failed_to_change_enemy_guard")
    elif action in ("wait:60","wait:240","inspect"):
        events.append("original_fighting_simulation_clock_or_replay_observed")
    else:
        raise FightingActionError("action missing physical fighting behavior")
    # A hit that completes the round cannot be answered by a dead fighter.
    _round(state,config,events)
    if not state["finished"] and not state["failed"] and (
       state["player"] is hero):
        _ai(state,config,events)
    _round(state,config,events)
    if not state["finished"] and not state["failed"] and (
        state["player"] is hero):
        advance=(int(action.split(":")[1]) if action.startswith("wait:")
                 else config["frames_per_turn"])
        _turn(state,config,events,advance)
    state["turn"]+=1;state["events"]=events
    return events


__all__=["LANES","ACTIONS","ATTACKS","FightingActionError",
         "default_layout","normalize_layout","start","apply_scene","step"]
