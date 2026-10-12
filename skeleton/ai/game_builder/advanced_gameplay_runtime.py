"""Advanced-floor replayable sessions for eight original game families.

Runs entirely offline, integer-only, content-addressed and stateless. Gameplay
is reconstructed from a bounded command transcript, so client-controlled state
cannot award itself money, HP, equipment or victory. This is a reference game
runtime, not a native-engine, publication, or hardware certification.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping, Sequence

from .system_editors import make_editor_document, SystemEditorError
from .advanced_npc_society_runtime import (
    ACTIONS as SOCIETY_ACTIONS, SocietyActionError,
    start as society_start, step as society_step,
    apply_scene as apply_society_scene,
)
from .advanced_ecosystem_runtime import (
    ACTIONS as ECOSYSTEM_ACTIONS, EcosystemActionError,
    start as ecosystem_start, step as ecosystem_step,
    apply_scene as apply_ecosystem_scene,
)
from .advanced_rpg_runtime import (
    ACTIONS as RPG_ACTIONS, RPGActionError,
    start as rpg_start, step as rpg_step, apply_scene as apply_rpg_scene,
)
from .advanced_procedural_world_runtime import (
    ACTIONS as PROC_ACTIONS, ProceduralWorldActionError,
    start as proc_start, step as proc_step, apply_scene as apply_proc_scene,
)
from .advanced_maze_runtime import (
    ACTIONS as MAZE_ACTIONS, MazeActionError,
    start as maze_start, step as maze_step, apply_scene as apply_maze_scene,
)
from .advanced_sports_runtime import (
    ACTIONS as SPORTS_ACTIONS, SportsActionError,
    start as sports_start, step as sports_step, apply_scene as apply_sports_scene,
)
from .advanced_parkour_runtime import (
    ACTIONS as PARKOUR_ACTIONS, ParkourActionError,
    start as parkour_start, step as parkour_step, apply_scene as apply_parkour_scene,
)
from .advanced_sailing_runtime import (
    ACTIONS as SAIL_ACTIONS, SailingActionError,
    start as sail_start, step as sail_step, apply_scene as apply_sail_scene,
)
from .advanced_flight_runtime import (
    ACTIONS as FLIGHT_ACTIONS, FlightActionError,
    start as flight_start, step as flight_step, apply_scene as apply_flight_scene,
)
from .advanced_quest_director_runtime import (ACTIONS as QUEST_ACTIONS,
        QuestDirectorError,start as quest_start,step as quest_step,
        apply_scene as apply_quest_scene)
from .advanced_fighting_runtime import (ACTIONS as FIGHT_ACTIONS, FightingActionError,
                                        start as fight_start, step as fight_step,
                                        apply_scene as apply_fight_scene)
from .advanced_rhythm_runtime import (ACTIONS as RHYTHM_ACTIONS, RhythmActionError,
                                      start as rhythm_start, step as rhythm_step,
                                      apply_scene as apply_rhythm_scene)
from .advanced_rts_runtime import (ACTIONS as RTS_ACTIONS, RTSActionError,
                                   start as rts_start, step as rts_step,
                                   apply_scene as apply_rts_scene)
from .advanced_roguelike_runtime import (ACTIONS as ROGUE_ACTIONS, RoguelikeActionError,
                                         start as rogue_start, step as rogue_step,
                                         apply_scene as apply_rogue_scene)
from .advanced_sandbox_runtime import (ACTIONS as SANDBOX_ACTIONS, SandboxActionError,
                                       start as sandbox_start, step as sandbox_step,
                                       apply_scene as apply_sandbox_scene)
from .advanced_metroidvania_runtime import (ACTIONS as EXPLORE_ACTIONS, ExplorationActionError,
                                          start as explore_start, step as explore_step,
                                          apply_scene as apply_explore_scene)
from .advanced_stealth_runtime import (ACTIONS as STEALTH_ACTIONS, StealthActionError,
                                      start as stealth_start, step as stealth_step,
                                      apply_scene as apply_stealth_scene)
from .advanced_city_runtime import (ACTIONS as CITY_ACTIONS, CityActionError,
                                    start as city_start, step as city_step,
                                    apply_scene as apply_city_scene)
from .advanced_colony_runtime import (ACTIONS as COLONY_ACTIONS, ColonyActionError,
                                      start as colony_start, step as colony_step,
                                      apply_scene as apply_colony_scene)
from .advanced_factory_runtime import (ACTIONS as FACTORY_ACTIONS, FactoryActionError,
                                        start as factory_start, step as factory_step,
                                        apply_scene as apply_factory_scene)
from .advanced_farming_runtime import (ACTIONS as FARM_ACTIONS, FarmingActionError,
                                        start as farming_start, step as farming_step,
                                        apply_scene as apply_farm_scene)
from .advanced_genre_engines import (
    GENRE_ACTIONS, STARTS as GENRE_STARTS, STEPS as GENRE_STEPS,
    GenreActionError, apply_genre_scene,
)

SCHEMA = "skeleton.game_builder.advanced_session.v1"
ENGINES = ("platformer", "tactics", "tower_defense", "racing", "survival", "shooter", "deck_battler", "puzzle", "farming", "factory", "colony", "city_builder", "stealth", "metroidvania", "sandbox", "roguelike", "rts", "rhythm", "fighting", "quest_director", "flight", "sailing", "parkour", "sports", "maze", "rpg", "procedural_world", "npc_society", "ecosystem")
MAX_TURNS = 128
MAX_SEED = 2**31 - 1

ACTION_HELP = {
    "platformer": ("left", "right", "jump", "jump_left", "jump_right",
                   "wait", "dash_left", "dash_right"),
    "tactics": ("north", "south", "west", "east", "attack:0",
               "attack:1", "guard", "overwatch", "heal", "switch", "end_turn"),
    "tower_defense": ("tick", "tick:4", "build:0", "build:1", "build:2",
                      "upgrade:0", "upgrade:1", "upgrade:2", "sell:0",
                      "sell:1", "sell:2", "priority:first", "priority:strong"),
    "racing": ("accelerate", "brake", "coast", "steer_left", "steer_right",
               "boost", "pit"),
    "survival": ("forage", "gather_wood", "mine_stone", "drink", "hunt",
                 "cook", "craft_tool", "light_fire", "build_shelter",
                 "trade", "travel", "rest"),
    "farming": FARM_ACTIONS,
    "factory": FACTORY_ACTIONS,
    "colony": COLONY_ACTIONS,
    "city_builder": CITY_ACTIONS,
    "stealth": STEALTH_ACTIONS,
    "metroidvania": EXPLORE_ACTIONS,
    "sandbox": SANDBOX_ACTIONS,
    "roguelike": ROGUE_ACTIONS,
    "rts": RTS_ACTIONS,
    "rhythm": RHYTHM_ACTIONS,
    "fighting": FIGHT_ACTIONS,
    "quest_director": QUEST_ACTIONS,
    "flight": FLIGHT_ACTIONS,
    "sailing": SAIL_ACTIONS,
    "parkour": PARKOUR_ACTIONS,
    "sports": SPORTS_ACTIONS,
    "maze": MAZE_ACTIONS,
    "rpg": RPG_ACTIONS,
    "procedural_world": PROC_ACTIONS,
    "npc_society": SOCIETY_ACTIONS,
    "ecosystem": ECOSYSTEM_ACTIONS,
    **GENRE_ACTIONS,
}


class AdvancedRuntimeError(SystemEditorError):
    """Rejected illegal game move, mismatched proof or unsupported family."""


def _serialize(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(payload):
    return sha256(_serialize(payload).encode("utf-8")).hexdigest()


def _bounded(seed, actions):
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise AdvancedRuntimeError("game seed must be a bounded unsigned integer")
    if type(actions) not in (tuple, list) or len(actions) > MAX_TURNS:
        raise AdvancedRuntimeError("session commands exceed bounded replay budget")
    if any(type(action) is not str or not 1 <= len(action) <= 30
           for action in actions):
        raise AdvancedRuntimeError("session commands must be bounded strings")


def _layout(seed, width):
    # Stable, original layouts whose hazards may be avoided using height or
    # dashed through with finite cooldown. This is not imported copyrighted map data.
    positions = [max(4, width // 6), max(7, width // 2),
                 max(10, width - 7)]
    hazards = sorted(set(min(width - 2, x + seed % 3) for x in positions))
    pickups = sorted(set(min(width - 2, max(1, x - 2)) for x in positions))
    checkpoints = sorted(set(x for x in (max(2, width // 3), max(3, 2*width // 3))
                             if x < width-1))
    return hazards, pickups, checkpoints


def _platform_start(config, seed):
    width = config["level_width"]
    spikes, crystals, checkpoints = _layout(seed, width)
    return {
        "tick": 0, "x": 0, "y": 0, "vy": 0, "air_jumps": 0,
        "health": 5, "checkpoint": 0, "dash_cooldown": 0,
        "crystals": [], "spikes": spikes, "collectibles": crystals,
        "checkpoints": checkpoints, "exit_x": width - 1,
        "events": [], "finished": False, "failed": False,
    }


def _platform_step(state, config, action):
    if action not in ACTION_HELP["platformer"]:
        raise AdvancedRuntimeError("unsupported platform traversal control")
    state["tick"] += 1
    events = []
    grounded = state["y"] == 0
    jump = action.startswith("jump")
    if jump and (grounded or
                 (config["double_jump"] and state["air_jumps"] < 2)):
        state["vy"] = config["jump_impulse"]
        state["air_jumps"] += 1
        events.append("jump")
    direction = (-1 if action in ("left", "jump_left", "dash_left")
                 else 1 if action in ("right", "jump_right", "dash_right")
                 else 0)
    dash = action.startswith("dash")
    if dash and state["dash_cooldown"] > 0:
        raise AdvancedRuntimeError("dash ability is cooling down")
    speed = config["run_speed"] * (2 if dash else 1)
    old_x = state["x"]
    new_x = max(0, min(config["level_width"] - 1, old_x + direction * speed))
    old_y = state["y"]
    state["y"] = max(0, old_y + state["vy"])
    state["vy"] = max(-config["gravity"] * 3, state["vy"] - config["gravity"])
    if state["y"] == 0:
        state["vy"] = 0
        state["air_jumps"] = 0
    state["x"] = new_x
    if dash:
        state["dash_cooldown"] = 3
        events.append("dash")
    elif state["dash_cooldown"]:
        state["dash_cooldown"] -= 1
    interval = range(min(old_x, new_x), max(old_x, new_x) + 1)
    for crystal in state["collectibles"]:
        if crystal in interval and crystal not in state["crystals"]:
            state["crystals"].append(crystal)
            events.append("crystal_collected")
    state["crystals"].sort()
    for checkpoint in state["checkpoints"]:
        if checkpoint in interval and checkpoint > state["checkpoint"]:
            state["checkpoint"] = checkpoint
            events.append("checkpoint_activated")
    # Swept traversal: crossing a spike in a ground-level movement is a hit
    # even when movement skips over the hazard tile at high speed.
    exposed = (old_y <= 2 and state["y"] <= 2 and not dash)
    if exposed and any(spike in interval for spike in state["spikes"]):
        state["health"] -= 1
        state["x"] = state["checkpoint"]
        state["y"] = 0
        state["vy"] = 0
        state["air_jumps"] = 0
        events.append("hazard_respawn")
    if state["health"] <= 0:
        state["health"] = 0
        state["failed"] = True
        events.append("run_failed")
    if state["x"] >= state["exit_x"] and len(state["crystals"]) == len(state["collectibles"]) and not state["failed"]:
        state["finished"] = True
        events.append("exit_unlocked")
    elif state["x"] >= state["exit_x"]:
        events.append("exit_locked")
    return events


def _tactics_start(config, seed):
    w, h = config["board_width"], config["board_height"]
    # Keep reproducible cover/obstruction away from origin and enemy spawns.
    obstacles = [[w//2, i] for i in range(2, max(2, h-2))
                 if (i + seed) % 3 == 0]
    return {
        "round": 1, "active_unit": 0, "action_points": config["action_points"],
        "units": [
            {"x":0, "y":0, "hp":config["unit_health"], "guard":False,
             "overwatch":False, "medkits":2},
            {"x":0, "y":min(1,h-1), "hp":config["unit_health"], "guard":False,
             "overwatch":False, "medkits":1},
        ],
        "enemies": [
            {"x":w-1, "y":h-1, "hp":config["unit_health"], "id":0},
            {"x":w-2, "y":h-1, "hp":config["unit_health"], "id":1},
        ],
        "obstacles":obstacles, "objective":[w-1,0], "events":[],
        "finished":False, "failed":False, "score":0,
    }


def _line_clear(x1, y1, x2, y2, blocking):
    # An exact integer grid ray avoids graphics-dependent float rounding.
    dx = abs(x2-x1); dy = abs(y2-y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx-dy
    x,y=x1,y1
    while (x,y)!=(x2,y2):
        error=2*err
        if error > -dy:
            err -= dy; x += sx
        if error < dx:
            err += dx; y += sy
        if (x,y)!=(x2,y2) and [x,y] in blocking:
            return False
    return True


def _tactics_enemy_round(state, config):
    report=[]
    for enemy in state["enemies"]:
        viable = [unit for unit in state["units"] if unit["hp"] > 0]
        if not viable:
            break
        unit=min(viable, key=lambda u:(abs(enemy["x"]-u["x"])+abs(enemy["y"]-u["y"]),u["y"],u["x"]))
        distance=abs(unit["x"]-enemy["x"])+abs(unit["y"]-enemy["y"])
        if distance <= 2 and _line_clear(enemy["x"],enemy["y"],unit["x"],unit["y"],state["obstacles"]):
            damage = max(0, 3 - (2 if unit["guard"] else 0))
            unit["hp"] = max(0, unit["hp"]-damage)
            report.append("enemy_fired")
        else:
            for axis in ("x","y"):
                delta = (1 if unit[axis] > enemy[axis] else -1 if unit[axis] < enemy[axis] else 0)
                spot=[enemy["x"] + (delta if axis=="x" else 0),
                      enemy["y"] + (delta if axis=="y" else 0)]
                if delta and spot not in state["obstacles"] and not any(
                    [u["x"], u["y"]] == spot and u["hp"] > 0 for u in state["units"]
                ) and not any(
                    e is not enemy and [e["x"],e["y"]] == spot for e in state["enemies"]
                ):
                    enemy[axis]+=delta
                    report.append("enemy_advanced")
                    break
    for unit in state["units"]:
        if unit["hp"] > 0 and unit["overwatch"]:
            target=next((e for e in state["enemies"] if abs(e["x"]-unit["x"])+abs(e["y"]-unit["y"]) <= config["attack_range"]
                         and _line_clear(unit["x"],unit["y"],e["x"],e["y"],state["obstacles"])),None)
            if target:
                target["hp"] = max(0, target["hp"] - 2)
                report.append("overwatch_hit")
        unit["overwatch"]=False
        unit["guard"]=False
    state["enemies"]=[e for e in state["enemies"] if e["hp"] > 0]
    state["round"]+=1
    state["action_points"]=config["action_points"]
    return report


def _tactics_step(state, config, action):
    if action not in ACTION_HELP["tactics"]:
        raise AdvancedRuntimeError("invalid tactics order")
    events=[]
    unit=state["units"][state["active_unit"]]
    ap=state["action_points"]
    if action=="end_turn":
        events.extend(_tactics_enemy_round(state,config))
    elif action=="switch":
        other=1-state["active_unit"]
        if state["units"][other]["hp"] <= 0:
            raise AdvancedRuntimeError("cannot command a defeated squad member")
        state["active_unit"]=other
    elif action in {"north","south","west","east"}:
        if ap == 0: raise AdvancedRuntimeError("no action points left")
        dx,dy={"north":(0,-1),"south":(0,1),"west":(-1,0),"east":(1,0)}[action]
        x=unit["x"]+dx;y=unit["y"]+dy
        if not (0 <= x < config["board_width"] and 0 <= y < config["board_height"]):
            raise AdvancedRuntimeError("unit cannot move beyond map")
        if [x,y] in state["obstacles"] or any([o["x"],o["y"]]==[x,y] for o in state["units"]+state["enemies"] if o is not unit and o["hp"]>0):
            raise AdvancedRuntimeError("target tile is occupied or blocked")
        unit["x"]=x;unit["y"]=y
        state["action_points"]-=1
        events.append("unit_moved")
    elif action.startswith("attack:"):
        if ap == 0: raise AdvancedRuntimeError("no action points left")
        target_id=int(action.split(":")[1])
        enemy=next((e for e in state["enemies"] if e["id"]==target_id),None)
        if enemy is None: raise AdvancedRuntimeError("target was already defeated")
        distance=abs(enemy["x"]-unit["x"])+abs(enemy["y"]-unit["y"])
        if distance > config["attack_range"] or not _line_clear(
            unit["x"],unit["y"],enemy["x"],enemy["y"],state["obstacles"]
        ):
            raise AdvancedRuntimeError("target is beyond range or occluded")
        enemy["hp"]=max(0,enemy["hp"]-4)
        state["action_points"]-=1
        events.append("direct_attack")
        if enemy["hp"]==0:
            state["score"]+=100
            events.append("enemy_defeated")
        state["enemies"]=[e for e in state["enemies"] if e["hp"] > 0]
    else:
        if ap == 0: raise AdvancedRuntimeError("no action points left")
        if action=="guard": unit["guard"]=True
        elif action=="overwatch":unit["overwatch"]=True
        elif action=="heal":
            if not unit["medkits"]:
                raise AdvancedRuntimeError("no first-aid charges remain")
            unit["medkits"]-=1
            unit["hp"]=min(config["unit_health"],unit["hp"]+5)
        state["action_points"]-=1
        events.append(action)
    if not state["enemies"]:
        state["finished"]=True
        events.append("mission_complete")
    if all(u["hp"]==0 for u in state["units"]):
        state["failed"]=True
        events.append("squad_lost")
    return events


def _defense_start(config, seed):
    return {
        "tick":0, "credits":config["starting_credits"],"base_hp":20,
        "towers":[], "enemies":[], "spawned":0, "defeated":0,
        "escaped":0, "waves_completed":0,"priority":"first",
        "events":[], "finished":False, "failed":False,
        "seed":seed, "lane_length":config["lane_length"],
        "allowed_slots":[0,1,2], "wave_limit":3,
    }


def _defense_tick(state, config):
    state["tick"]+=1
    events=[]
    limit=config["wave_size"]*state["wave_limit"]
    if state["spawned"] < limit and state["tick"] % 2 == 1:
        idx=state["spawned"]
        state["enemies"].append({"id":idx,"x":0,"hp":3+idx//config["wave_size"]*2,
                                  "armor":idx%3 == 0,"slow":0})
        state["spawned"]+=1
        events.append("enemy_spawned")
    for enemy in state["enemies"]:
        enemy["x"]+=1 if enemy["slow"]==0 else 0
        enemy["slow"]=max(0,enemy["slow"]-1)
    for tower in state["towers"]:
        choices=[enemy for enemy in state["enemies"]
                 if abs(enemy["x"]-(tower["slot"]*max(1,config["lane_length"]//3)+2)) <= config["tower_range"]]
        if not choices: continue
        enemy=(max(choices,key=lambda e:(e["hp"],-e["id"])) if state["priority"]=="strong"
               else max(choices,key=lambda e:(e["x"],-e["id"])))
        power=config["tower_damage"] * tower["level"]
        if enemy["armor"]: power=max(1,power-1)
        enemy["hp"]-=power
        if tower["level"]>=2: enemy["slow"]=1
        events.append("tower_fired")
    survivors=[]
    for enemy in state["enemies"]:
        if enemy["hp"]<=0:
            state["defeated"]+=1;state["credits"]+=5
            events.append("enemy_defeated")
        elif enemy["x"] >= config["lane_length"]:
            state["escaped"]+=1;state["base_hp"]=max(0,state["base_hp"]-2)
            events.append("enemy_escaped")
        else:
            survivors.append(enemy)
    state["enemies"]=survivors
    completed_waves=min(state["wave_limit"],(state["defeated"]+state["escaped"])//config["wave_size"])
    if completed_waves>state["waves_completed"]:
        state["waves_completed"]=completed_waves
        events.append("wave_resolved")
    if state["spawned"] == limit and not state["enemies"]:
        state["waves_completed"]=state["wave_limit"]
        state["finished"]=True
        events.append("authored_waves_resolved")
    if state["base_hp"] == 0:
        state["failed"]=True
        state["finished"]=False
        events.append("base_destroyed")
    return events


def _defense_step(state, config, action):
    events=[]
    if action in ("tick","tick:4"):
        for _ in range(4 if action=="tick:4" else 1):
            if state["finished"] or state["failed"]: break
            events.extend(_defense_tick(state,config))
    elif action.startswith("build:"):
        slot=int(action[-1])
        if slot not in state["allowed_slots"]:
            raise AdvancedRuntimeError("tower slot not enabled by authored lane scene")
        if any(t["slot"]==slot for t in state["towers"]):
            raise AdvancedRuntimeError("build slot already occupied")
        if state["credits"] < 20:
            raise AdvancedRuntimeError("not enough finite tower credits")
        state["credits"]-=20
        state["towers"].append({"slot":slot,"level":1})
        events.append("tower_constructed")
    elif action.startswith("upgrade:"):
        slot=int(action[-1])
        tower=next((t for t in state["towers"] if t["slot"]==slot),None)
        if tower is None or tower["level"]>=3:
            raise AdvancedRuntimeError("tower upgrade requires existing upgradable structure")
        price=15*tower["level"]
        if state["credits"]<price:
            raise AdvancedRuntimeError("not enough finite upgrade credits")
        state["credits"]-=price;tower["level"]+=1
        events.append("tower_upgraded")
    elif action.startswith("sell:"):
        slot=int(action[-1])
        tower=next((t for t in state["towers"] if t["slot"]==slot),None)
        if tower is None:
            raise AdvancedRuntimeError("cannot sell missing tower")
        state["credits"]+=10*tower["level"]
        state["towers"].remove(tower)
        events.append("tower_sold")
    elif action.startswith("priority:"):
        state["priority"]=action.split(":")[1]
        events.append("target_priority_changed")
    else:
        raise AdvancedRuntimeError("invalid tower-defense command")
    return events


def _racing_start(config, seed):
    length=config["track_length"]
    return {
        "tick":0,"distance":0,"position":0,"lap":0,"laps":config["laps"],
        "track_length":length,"speed":0,"lane":0,
        "fuel":max(20, (length*config["laps"])//5),
        "fuel_capacity":max(20, (length*config["laps"])//5),
        "tire_condition":100,"engine_integrity":100,
        "boost_charges":3,"pit_stops":0,"pit_crews":3,
        "weather":("dry","wet","storm")[seed % 3],
        "corners":sorted(set([max(2,length//4),max(3,length//2),
                             max(4,3*length//4)])),
        "track_obstacle":max(5,length//3)+(seed % 3),
        "events":[],"finished":False,"failed":False,"championship_points":0,
    }


def _racing_step(state,config,action):
    if action not in ACTION_HELP["racing"]:
        raise AdvancedRuntimeError("unrecognized advanced driving command")
    events=[]
    state["tick"]+=1
    weather=state["weather"]
    grip=max(2,config["max_speed"]-(0 if weather=="dry" else
                                   max(1,config["max_speed"]//4) if weather=="wet"
                                   else max(2,config["max_speed"]//3)))
    position=state["position"]
    if action=="pit":
        if position > min(10,config["track_length"]//5) or state["speed"]>max(3,config["brake_force"]):
            raise AdvancedRuntimeError("pit entry requires slow speed near start line")
        if state["pit_crews"]==0:
            raise AdvancedRuntimeError("all service stops have been spent")
        state["pit_crews"]-=1;state["pit_stops"]+=1
        state["fuel"]=state["fuel_capacity"]
        state["tire_condition"]=100
        state["engine_integrity"]=min(100,state["engine_integrity"]+30)
        state["speed"]=0
        events.append("pit_service")
        return events
    if action=="accelerate":
        state["speed"]=min(config["max_speed"],state["speed"]+config["acceleration"])
    elif action=="brake":
        state["speed"]=max(0,state["speed"]-config["brake_force"])
    elif action=="coast":
        state["speed"]=max(0,state["speed"]-1)
    elif action.startswith("steer_"):
        delta=-1 if action=="steer_left" else 1
        state["lane"]=max(-1,min(1,state["lane"]+delta))
        state["speed"]=max(0,state["speed"]-1)
        events.append("lane_changed")
    elif action=="boost":
        if state["boost_charges"]<=0:
            raise AdvancedRuntimeError("nitro charge exhausted")
        state["boost_charges"]-=1
        state["speed"]=min(config["max_speed"],
                           state["speed"]+config["acceleration"]*2)
        events.append("boost_consumed")
    if state["fuel"]<=0:
        state["speed"]=0
        events.append("fuel_empty")
    else:
        state["fuel"]=max(0,state["fuel"]-1-state["speed"]//15)
    # An engine or tire failure reduces feasible speed; running on worn tires
    # without maintenance is a real, stateful handicap.
    if state["tire_condition"]<25 or state["engine_integrity"]<30:
        state["speed"]=min(state["speed"],max(1,grip//2))
        events.append("mechanical_limp_mode")
    travel=state["speed"]
    old_distance=state["distance"]
    next_distance=min(config["track_length"]*config["laps"],
                      old_distance+travel)
    lap0=old_distance//config["track_length"]
    lap1=next_distance//config["track_length"]
    for lap in range(lap0,lap1+1):
        segment_start=max(old_distance,lap*config["track_length"])
        segment_end=min(next_distance,(lap+1)*config["track_length"])
        for corner in state["corners"]:
            absolute=lap*config["track_length"]+corner
            if segment_start<=absolute<=segment_end and state["speed"]>grip:
                state["tire_condition"]=max(0,state["tire_condition"]-12)
                state["engine_integrity"]=max(0,state["engine_integrity"]-6)
                events.append("corner_understeer_damage")
        obstacle=lap*config["track_length"]+state["track_obstacle"]
        if segment_start<=obstacle<=segment_end and state["lane"]==0:
            state["engine_integrity"]=max(0,state["engine_integrity"]-12)
            events.append("centerline_obstacle_hit")
    state["tire_condition"]=max(0,state["tire_condition"]-1)
    state["distance"]=next_distance
    state["position"]=next_distance%config["track_length"]
    state["lap"]=min(config["laps"],next_distance//config["track_length"])
    if lap1>lap0:
        events.append("lap_completed")
    if state["engine_integrity"]==0:
        state["failed"]=True
        events.append("engine_destroyed")
    if next_distance>=config["track_length"]*config["laps"] and not state["failed"]:
        state["finished"]=True
        state["championship_points"]=max(1,1000-state["tick"]*4-
                                        (100-state["engine_integrity"])*3)
        events.append("race_completed")
    return events


def _survival_start(config,seed):
    regions=[]
    for index in range(4):
        profile=(index+seed)%4
        regions.append({
            "id":index,"biome":("forest","plains","wetland","highland")[profile],
            "food_stock":(12,8,6,4)[profile],
            "wood_stock":(16,7,5,4)[profile],
            "water_stock":(10,4,16,5)[profile],
            "stone_stock":(7,4,2,18)[profile],
            "game_stock":(5,7,4,2)[profile],
            "merchant_food_stock":4,
            "merchant_water_stock":4,
        })
    return {
        "tick":0,"day":1,"region":0,"regions":regions,
        "health":config["max_health"],"max_health":config["max_health"],
        "food":config["starting_food"],"water":config["starting_water"],
        "wood":config["initial_wood"],"stone":0,"raw_meat":0,
        "tools":0,"fire_ticks":0,"shelter_level":0,"energy":10,
        "trade_tokens":2,"milestones":[],
        "weather":("clear","rain","cold","heat")[seed%4],
        "events":[],"finished":False,"failed":False,
    }


def _survival_step(state,config,action):
    if action not in ACTION_HELP["survival"]:
        raise AdvancedRuntimeError("unrecognized survival command")
    events=[]
    state["tick"]+=1
    local=state["regions"][state["region"]]
    if action=="travel":
        if state["energy"]<3:
            raise AdvancedRuntimeError("player is too exhausted to travel")
        state["energy"]-=3
        state["region"]=(state["region"]+1)%len(state["regions"])
        events.append("region_discovered")
    elif action in ("forage","gather_wood","mine_stone","hunt","drink"):
        stock_field={
            "forage":"food_stock","gather_wood":"wood_stock",
            "mine_stone":"stone_stock","hunt":"game_stock","drink":"water_stock",
        }[action]
        if local[stock_field]<=0:
            raise AdvancedRuntimeError("finite local resource has been depleted")
        if state["energy"]<=0:
            raise AdvancedRuntimeError("not enough energy to harvest")
        amount=min(local[stock_field],2+(1 if state["tools"] else 0))
        local[stock_field]-=amount
        if action=="forage":state["food"]+=amount
        elif action=="gather_wood":state["wood"]+=amount
        elif action=="mine_stone":state["stone"]+=amount
        elif action=="hunt":state["raw_meat"]+=amount
        elif action=="drink":state["water"]+=amount
        state["energy"]-=1
        events.append("finite_resource_harvested")
    elif action=="craft_tool":
        if state["wood"]<2 or state["stone"]<2:
            raise AdvancedRuntimeError("crafting requires two wood and two stone")
        state["wood"]-=2;state["stone"]-=2;state["tools"]+=1
        events.append("tool_crafted")
    elif action=="light_fire":
        if state["wood"]<2:
            raise AdvancedRuntimeError("lighting fire requires two real wood")
        state["wood"]-=2;state["fire_ticks"]=4
        events.append("fire_lit")
    elif action=="cook":
        if state["fire_ticks"]<=0 or state["raw_meat"]<=0:
            raise AdvancedRuntimeError("cooking needs fire and raw meat")
        state["raw_meat"]-=1;state["food"]+=3
        events.append("meal_cooked")
    elif action=="build_shelter":
        needed_wood=3+state["shelter_level"]
        if state["wood"]<needed_wood or state["stone"]<2 or state["shelter_level"]>=3:
            raise AdvancedRuntimeError("shelter requires finite construction resources")
        state["wood"]-=needed_wood;state["stone"]-=2
        state["shelter_level"]+=1
        events.append("shelter_built")
        if "permanent_camp" not in state["milestones"]:
            state["milestones"].append("permanent_camp")
    elif action=="trade":
        if state["trade_tokens"]<=0:
            raise AdvancedRuntimeError("trade credits are exhausted")
        if local["merchant_food_stock"]<2 or local["merchant_water_stock"]<2:
            raise AdvancedRuntimeError("finite merchant stocks are exhausted")
        state["trade_tokens"]-=1
        local["merchant_food_stock"]-=2
        local["merchant_water_stock"]-=2
        state["food"]+=2;state["water"]+=2
        events.append("finite_market_trade")
    elif action=="rest":
        state["energy"]=min(10,state["energy"]+5+state["shelter_level"])
        state["health"]=min(config["max_health"],state["health"]+
                            (2 if state["shelter_level"] else 1))
        events.append("rested")
    if state["fire_ticks"]>0:state["fire_ticks"]-=1
    # Explicit finite consumption; no hidden infinite replenishment. Weather
    # changes every six turns and shelter/fire dampen its effects.
    if state["tick"]%2==0:
        if state["food"]>0:state["food"]-=1
        if state["water"]>0:state["water"]-=1
        if (state["food"]==0 or state["water"]==0):
            state["health"]=max(0,state["health"]-config["hunger_rate"])
            events.append("dehydration_or_hunger")
    if state["tick"]%6==0:
        state["day"]+=1
        state["weather"]=("clear","rain","cold","heat")[
            (state["day"]+state["region"])%4]
        if state["weather"] in ("cold","heat") and not state["shelter_level"]:
            state["health"]=max(0,state["health"]-1)
            events.append("weather_exposure")
    if state["shelter_level"]>=2 and state["tools"]>=1:
        if "self_sufficient_outpost" not in state["milestones"]:
            state["milestones"].append("self_sufficient_outpost")
            events.append("original_world_milestone")
    if state["health"]==0:
        state["failed"]=True
        events.append("survivor_lost")
    # Open-ended world: achieving a settlement milestone does NOT force a
    # victory screen; user can continue until finite resources run out.
    return events


def run_advanced_session(editor: str, settings: Mapping[str, object] | None = None,
                         actions: Sequence[str] = (), *, seed: int = 0,
                         scene: Mapping[str, object] | None = None) -> dict:
    if editor not in ENGINES:
        raise AdvancedRuntimeError("advanced playable session is not implemented for this family")
    _bounded(seed, actions)
    config = make_editor_document(editor, settings)
    rules = config["settings"]
    starts = {
        "platformer":_platform_start,
        "tactics":_tactics_start,
        "tower_defense":_defense_start,
        "racing":_racing_start,
        "survival":_survival_start,
        "farming":farming_start,
        "factory":factory_start,
        "colony":colony_start,
        "city_builder":city_start,
        "stealth":stealth_start,
        "metroidvania":explore_start,
        "sandbox":sandbox_start,
        "roguelike":rogue_start,
        "rts":rts_start,
        "rhythm":rhythm_start,
        "fighting":fight_start,
        "quest_director":quest_start,
        "flight":flight_start,
        "sailing":sail_start,
        "parkour":parkour_start,
        "sports":sports_start,
        "maze":maze_start,
        "rpg":rpg_start,
        "procedural_world":proc_start,
        "npc_society":society_start,
        "ecosystem":ecosystem_start,
        **GENRE_STARTS,
    }
    try:
        state=starts[editor](rules,seed)
    except (GenreActionError,FarmingActionError,FactoryActionError,
            ColonyActionError,CityActionError,StealthActionError,ExplorationActionError,SandboxActionError,RoguelikeActionError,RTSActionError,RhythmActionError,FightingActionError,QuestDirectorError,FlightActionError,SailingActionError,ParkourActionError,SportsActionError,MazeActionError,RPGActionError,ProceduralWorldActionError,SocietyActionError,EcosystemActionError) as exc:
        raise AdvancedRuntimeError(str(exc)) from exc
    if scene is not None:
        from .advanced_level_scenes import validate_advanced_scene
        authored=validate_advanced_scene(scene,rules)
        if authored["editor"]!=editor or authored["seed"]!=seed:
            raise AdvancedRuntimeError("authored scene identity/seed mismatches gameplay")
        layout=authored["layout"]
        if editor=="platformer":
            state.update(x=layout["spawn_x"],checkpoint=layout["spawn_x"],
                exit_x=layout["exit_x"],spikes=list(layout["hazards"]),
                collectibles=list(layout["collectibles"]),checkpoints=list(layout["checkpoints"]))
        elif editor=="tactics":
            state["obstacles"]=[list(c) for c in layout["obstacles"]]
            state["objective"]=list(layout["objective"])
            for unit,point in zip(state["units"],layout["squad_spawns"]):
                unit.update(x=point[0],y=point[1])
            for enemy,point in zip(state["enemies"],layout["enemy_spawns"]):
                enemy.update(x=point[0],y=point[1])
        elif editor=="tower_defense":
            state["allowed_slots"]=list(layout["build_slots"])
            state["wave_limit"]=layout["waves"]
        elif editor=="racing":
            state.update(corners=list(layout["corners"]),
                track_obstacle=layout["track_obstacle"],
                weather=layout["weather"],lane=layout["starting_lane"])
        elif editor=="survival":
            state["regions"]=[dict(r) for r in layout["regions"]]
            state["region"]=layout["starting_region"]
            state["weather"]=layout["weather"]
        elif editor=="farming":
            apply_farm_scene(state,rules,layout)
        elif editor=="factory":
            apply_factory_scene(state,rules,layout)
        elif editor=="colony":
            apply_colony_scene(state,rules,layout)
        elif editor=="city_builder":
            apply_city_scene(state,rules,layout)
        elif editor=="stealth":
            apply_stealth_scene(state,rules,layout)
        elif editor=="metroidvania":
            apply_explore_scene(state,rules,layout)
        elif editor=="sandbox":
            apply_sandbox_scene(state,rules,layout)
        elif editor=="roguelike":
            apply_rogue_scene(state,rules,layout)
        elif editor=="rts":
            apply_rts_scene(state,rules,layout)
        elif editor=="rhythm":
            apply_rhythm_scene(state,rules,layout)
        elif editor=="fighting":
            apply_fight_scene(state,rules,layout)
        elif editor=="quest_director":
            apply_quest_scene(state,rules,layout)
        elif editor=="flight":
            apply_flight_scene(state,rules,layout)
        elif editor=="sailing":
            apply_sail_scene(state,rules,layout)
        elif editor=="parkour":
            apply_parkour_scene(state,rules,layout)
        elif editor=="sports":
            apply_sports_scene(state,rules,layout)
        elif editor=="maze":
            apply_maze_scene(state,rules,layout)
        elif editor=="rpg":
            apply_rpg_scene(state,rules,layout)
        elif editor=="procedural_world":
            apply_proc_scene(state,rules,layout)
        elif editor=="npc_society":
            apply_society_scene(state,rules,layout)
        elif editor=="ecosystem":
            apply_ecosystem_scene(state,rules,layout)
        else:
            apply_genre_scene(editor,state,layout)
    baseline=_digest({"editor":editor,"configuration":config["digest"],"seed":seed,
                      "scene_digest":scene["digest"] if scene is not None else None,
                      "quality_floor":"advanced"})
    previous=baseline
    trace=[]
    for index,action in enumerate(actions):
        if action not in ACTION_HELP[editor]:
            raise AdvancedRuntimeError("action not registered for advanced runtime")
        if state["finished"] or state["failed"]:
            raise AdvancedRuntimeError("gameplay cannot advance after terminal outcome")
        steps = {
            "platformer":_platform_step,"tactics":_tactics_step,
            "tower_defense":_defense_step,"racing":_racing_step,
            "survival":_survival_step,
            "farming":farming_step,
            "factory":factory_step,
            "colony":colony_step,
            "city_builder":city_step,
            "stealth":stealth_step,
            "metroidvania":explore_step,
            "sandbox":sandbox_step,
            "roguelike":rogue_step,
            "rts":rts_step,
            "rhythm":rhythm_step,
            "fighting":fight_step,
            "quest_director":quest_step,
            "flight":flight_step,
            "sailing":sail_step,
            "parkour":parkour_step,
            "sports":sports_step,
            "maze":maze_step,
            "rpg":rpg_step,
            "procedural_world":proc_step,
            "npc_society":society_step,
            "ecosystem":ecosystem_step,
            **GENRE_STEPS,
        }
        try:
            events=steps[editor](state,rules,action)
        except (GenreActionError,FarmingActionError,FactoryActionError,ColonyActionError,CityActionError,StealthActionError,ExplorationActionError,SandboxActionError,RoguelikeActionError,RTSActionError,RhythmActionError,FightingActionError,QuestDirectorError,FlightActionError,SailingActionError,ParkourActionError,SportsActionError,MazeActionError,RPGActionError,ProceduralWorldActionError,SocietyActionError,EcosystemActionError) as exc:
            raise AdvancedRuntimeError(str(exc)) from exc
        state["events"]=events
        receipt={"index":index,"action":action,"events":events,
                 "state_digest":_digest(state),"previous":previous}
        receipt["digest"]=_digest(receipt)
        trace.append(receipt);previous=receipt["digest"]
    report={
        "schema":SCHEMA,"editor":editor,"quality_floor":"advanced",
        "configuration_digest":config["digest"],"seed":seed,
        "scene":dict(scene) if scene is not None else None,
        "scene_digest":scene["digest"] if scene is not None else None,
        "actions":list(actions),"state":state,"trace":trace,
        "baseline_digest":baseline,"head_digest":previous,
        "terminal":state["finished"] or state["failed"],
        "validated_turn_count":len(trace),
        "native_hardware_verified":False,"publication_certified":False,
        "source_code_executed":False,
    }
    return {**report,"digest":_digest(report)}


def verify_advanced_session(receipt: Mapping[str, object],
                            settings: Mapping[str, object] | None = None) -> bool:
    if type(receipt) is not dict or receipt.get("schema") != SCHEMA:
        raise AdvancedRuntimeError("advanced session evidence requires exact schema")
    candidate=run_advanced_session(receipt.get("editor"),settings,
                                   receipt.get("actions"),seed=receipt.get("seed"),
                                   scene=receipt.get("scene"))
    if candidate != receipt:
        raise AdvancedRuntimeError("advanced gameplay receipt was altered or mismatched")
    return True


__all__ = ["SCHEMA","ENGINES","ACTION_HELP","AdvancedRuntimeError",
           "run_advanced_session","verify_advanced_session"]
