"""Advanced-floor playable reference sessions for three original game families.

Runs entirely offline, integer-only, content-addressed and stateless. Gameplay
is reconstructed from a bounded command transcript, so client-controlled state
cannot award itself money, HP, equipment or victory. This is a reference game
runtime, not a native-engine, publication, or hardware certification.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Mapping, Sequence

from .system_editors import make_editor_document, SystemEditorError

SCHEMA = "skeleton.game_builder.advanced_session.v1"
ENGINES = ("platformer", "tactics", "tower_defense")
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
    }


def _defense_tick(state, config):
    state["tick"]+=1
    events=[]
    limit=config["wave_size"]*3
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
    completed_waves=min(3,(state["defeated"]+state["escaped"])//config["wave_size"])
    if completed_waves>state["waves_completed"]:
        state["waves_completed"]=completed_waves
        events.append("wave_resolved")
    if state["spawned"] == limit and not state["enemies"]:
        state["waves_completed"]=3
        state["finished"]=True
        events.append("three_waves_resolved")
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


def run_advanced_session(editor: str, settings: Mapping[str, object] | None = None,
                         actions: Sequence[str] = (), *, seed: int = 0) -> dict:
    if editor not in ENGINES:
        raise AdvancedRuntimeError("advanced playable session is not implemented for this family")
    _bounded(seed, actions)
    config = make_editor_document(editor, settings)
    rules = config["settings"]
    state = ( _platform_start(rules,seed) if editor=="platformer" else
              _tactics_start(rules,seed) if editor=="tactics" else
              _defense_start(rules,seed) )
    baseline=_digest({"editor":editor,"configuration":config["digest"],"seed":seed,
                      "quality_floor":"advanced"})
    previous=baseline
    trace=[]
    for index,action in enumerate(actions):
        if action not in ACTION_HELP[editor]:
            raise AdvancedRuntimeError("action not registered for advanced runtime")
        if state["finished"] or state["failed"]:
            raise AdvancedRuntimeError("gameplay cannot advance after terminal outcome")
        if editor=="platformer":
            events=_platform_step(state,rules,action)
        elif editor=="tactics":
            events=_tactics_step(state,rules,action)
        else:
            events=_defense_step(state,rules,action)
        state["events"]=events
        receipt={"index":index,"action":action,"events":events,
                 "state_digest":_digest(state),"previous":previous}
        receipt["digest"]=_digest(receipt)
        trace.append(receipt);previous=receipt["digest"]
    report={
        "schema":SCHEMA,"editor":editor,"quality_floor":"advanced",
        "configuration_digest":config["digest"],"seed":seed,
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
                                   receipt.get("actions"),seed=receipt.get("seed"))
    if candidate != receipt:
        raise AdvancedRuntimeError("advanced gameplay receipt was altered or mismatched")
    return True


__all__ = ["SCHEMA","ENGINES","ACTION_HELP","AdvancedRuntimeError",
           "run_advanced_session","verify_advanced_session"]
