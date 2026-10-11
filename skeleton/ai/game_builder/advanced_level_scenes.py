"""Advanced game-scene authoring bound to runtime settings and replay receipts.

Five game families support actual authored spatial/world arrangements, not
merely seed changes. Every scene is a strict, size-bounded, content-addressed
JSON object; layouts never contain executable expressions or asset links.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
import re
from typing import Mapping

from .advanced_gameplay_runtime import (
    ENGINES, _layout, _tactics_start, _racing_start, _survival_start,
)
from .system_editors import make_editor_document, SystemEditorError

SCHEMA = "skeleton.game_builder.advanced_scene.v1"
MAX_SCENE_BYTES = 64_000
BIOMES = frozenset(("forest", "plains", "wetland", "highland", "desert", "tundra"))
WEATHER = frozenset(("clear", "rain", "cold", "heat"))


class SceneError(SystemEditorError):
    """Authored original game geometry or resource rules cannot be trusted."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(value):
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _number(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise SceneError("invalid bounded scene integer: " + name)
    return value


def _positions(value, low, high, maximum, name):
    if type(value) is not list or len(value) > maximum:
        raise SceneError("scene positions must be bounded arrays: " + name)
    if any(type(v) is not int or not low <= v <= high for v in value):
        raise SceneError("invalid scene coordinate in: " + name)
    if len(value) != len(set(value)) or value != sorted(value):
        raise SceneError("scene coordinates must be unique ascending: " + name)
    return list(value)


def _cells(value, width, height, maximum, name):
    if type(value) is not list or len(value) > maximum:
        raise SceneError("scene cells must be a bounded list: " + name)
    tuples=[]
    for cell in value:
        if type(cell) is not list or len(cell) != 2:
            raise SceneError("2D map cell must have exactly two integer coordinates")
        x=_number(cell[0],0,width-1,name+".x")
        y=_number(cell[1],0,height-1,name+".y")
        tuples.append((x,y))
    if len(set(tuples)) != len(tuples):
        raise SceneError("colliding cell coordinates: " + name)
    return [list(cell) for cell in tuples]


def _default_layout(engine, config, seed):
    if engine == "platformer":
        hazards, crystals, checkpoints = _layout(seed,config["level_width"])
        exit_x=config["level_width"]-1
        checkpoints=sorted(set(c for c in checkpoints if 0<c<exit_x))
        hazards=sorted(set(x for x in hazards
                           if 0<x<exit_x and x not in checkpoints))
        crystals=sorted(set(x for x in crystals if 0<x<exit_x))
        return {"spawn_x":0,"exit_x":exit_x,
                "hazards":hazards,"collectibles":crystals,
                "checkpoints":checkpoints}
    if engine == "tactics":
        state=_tactics_start(config,seed)
        return {"obstacles":state["obstacles"],
                "squad_spawns":[[p["x"],p["y"]] for p in state["units"]],
                "enemy_spawns":[[p["x"],p["y"]] for p in state["enemies"]],
                "objective":state["objective"]}
    if engine == "tower_defense":
        return {"build_slots":[0,1,2],"waves":3}
    if engine == "racing":
        state=_racing_start(config,seed)
        return {"corners":state["corners"],
                "track_obstacle":state["track_obstacle"],
                "weather":state["weather"],"starting_lane":0}
    if engine == "survival":
        state=_survival_start(config,seed)
        return {"regions":state["regions"],"starting_region":0,
                "weather":state["weather"]}
    raise SceneError("no advanced authored scene available for that engine")


def _normalize_layout(engine, config, layout):
    if type(layout) is not dict:
        raise SceneError("authored layout must be a JSON object")
    if engine=="platformer":
        if set(layout)!={"spawn_x","exit_x","hazards","collectibles","checkpoints"}:
            raise SceneError("exact platformer scene layout fields required")
        width=config["level_width"]
        spawn=_number(layout["spawn_x"],0,width-2,"spawn_x")
        exit_x=_number(layout["exit_x"],spawn+1,width-1,"exit_x")
        hazards=_positions(layout["hazards"],spawn+1,exit_x-1,64,"hazards")
        crystals=_positions(layout["collectibles"],spawn+1,exit_x-1,64,"collectibles")
        checks=_positions(layout["checkpoints"],spawn+1,exit_x-1,16,"checkpoints")
        if set(hazards)&set(checks):
            raise SceneError("checkpoints cannot overlap damaging hazard tiles")
        # Static terrain reachability is not a claim about jump physics or
        # challenge quality; it prevents zero-length and out-of-order maps.
        return {"spawn_x":spawn,"exit_x":exit_x,"hazards":hazards,
                "collectibles":crystals,"checkpoints":checks}
    if engine=="tactics":
        if set(layout)!={"obstacles","squad_spawns","enemy_spawns","objective"}:
            raise SceneError("exact tactics authored scene fields required")
        w=config["board_width"];h=config["board_height"]
        maximum=min(200,w*h-4)
        obstacles=_cells(layout["obstacles"],w,h,maximum,"obstacles")
        units=_cells(layout["squad_spawns"],w,h,2,"squad_spawns")
        enemies=_cells(layout["enemy_spawns"],w,h,2,"enemy_spawns")
        if len(units)!=2 or len(enemies)!=2:
            raise SceneError("reference squad battle needs two units and two enemies")
        objective=_cells([layout["objective"]],w,h,1,"objective")[0]
        occup={tuple(c) for c in obstacles+units+enemies}
        if len(occup)!=len(obstacles)+len(units)+len(enemies):
            raise SceneError("a unit or enemy occupies a blocked/occupied location")
        if tuple(objective) in {tuple(c) for c in obstacles}:
            raise SceneError("mission objective is blocked")
        # Check spatial traversability without pretending to solve combat AI.
        forbidden={tuple(c) for c in obstacles}
        start=tuple(units[0]); discovered={start}; queue=deque([start])
        while queue:
            x,y=queue.popleft()
            for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                cell=(nx,ny)
                if 0<=nx<w and 0<=ny<h and cell not in forbidden and cell not in discovered:
                    discovered.add(cell);queue.append(cell)
        if tuple(objective) not in discovered or any(tuple(e) not in discovered for e in enemies):
            raise SceneError("authored mission geometry isolates objective or enemy")
        return {"obstacles":obstacles,"squad_spawns":units,
                "enemy_spawns":enemies,"objective":objective}
    if engine=="tower_defense":
        if set(layout)!={"build_slots","waves"}:
            raise SceneError("exact advanced tower scene fields required")
        slots=_positions(layout["build_slots"],0,2,3,"build_slots")
        if not slots:
            raise SceneError("tower-defense editor requires at least one build slot")
        waves=_number(layout["waves"],1,12,"waves")
        return {"build_slots":slots,"waves":waves}
    if engine=="racing":
        if set(layout)!={"corners","track_obstacle","weather","starting_lane"}:
            raise SceneError("exact race circuit layout fields required")
        length=config["track_length"]
        corners=_positions(layout["corners"],1,length-2,24,"corners")
        obstacle=_number(layout["track_obstacle"],1,length-2,"track_obstacle")
        weather=layout["weather"]
        if type(weather) is not str or weather not in {"dry","wet","storm"}:
            raise SceneError("unsupported authored race weather")
        lane=_number(layout["starting_lane"],-1,1,"starting_lane")
        return {"corners":corners,"track_obstacle":obstacle,
                "weather":weather,"starting_lane":lane}
    if engine=="survival":
        if set(layout)!={"regions","starting_region","weather"}:
            raise SceneError("exact authored survival geography required")
        regions=layout["regions"]
        if type(regions) is not list or not 2<=len(regions)<=8:
            raise SceneError("survival scene requires two to eight distinct regions")
        keys={"id","biome","food_stock","wood_stock","water_stock",
              "stone_stock","game_stock","merchant_food_stock","merchant_water_stock"}
        checked=[]
        for index,region in enumerate(regions):
            if type(region) is not dict or set(region)!=keys:
                raise SceneError("survival regions require exact finite resource fields")
            if region["id"] != index or type(region["id"]) is not int:
                raise SceneError("region identities must be contiguous and unique")
            if type(region["biome"]) is not str or region["biome"] not in BIOMES:
                raise SceneError("unsupported original biome")
            checked.append({"id":index,"biome":region["biome"],
                **{key:_number(region[key],0,100000,key) for key in sorted(keys-{"id","biome"})}})
        region_id=_number(layout["starting_region"],0,len(regions)-1,"starting_region")
        weather=layout["weather"]
        if type(weather) is not str or weather not in WEATHER:
            raise SceneError("unsupported survival weather")
        return {"regions":checked,"starting_region":region_id,"weather":weather}
    raise SceneError("unsupported authored scene type")


def make_advanced_scene(editor: str, settings: Mapping[str,object] | None = None,
                        *, seed: int = 0, layout: Mapping[str,object] | None = None,
                        scene_id: str = "scene_01") -> dict:
    if type(editor) is not str or editor not in ENGINES:
        raise SceneError("advanced playable scene family required")
    if type(seed) is not int or not 0<=seed<=2**31-1:
        raise SceneError("scene seed must be bounded")
    if type(scene_id) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}",scene_id):
        raise SceneError("invalid safe original scene ID")
    configuration=make_editor_document(editor,settings)
    if layout is None:
        layout=_default_layout(editor,configuration["settings"],seed)
    result={"schema":SCHEMA,"editor":editor,"scene_id":scene_id,
            "settings_digest":configuration["digest"],"seed":seed,
            "layout":_normalize_layout(editor,configuration["settings"],layout)}
    if len(_canonical(result).encode("utf-8"))>MAX_SCENE_BYTES:
        raise SceneError("original authored scene exceeds source budget")
    return {**result,"digest":_digest(result)}


def validate_advanced_scene(document: object, settings: Mapping[str,object] | None = None) -> dict:
    if type(document) is not dict or set(document)!={
        "schema","editor","scene_id","settings_digest","seed","layout","digest"
    } or document.get("schema")!=SCHEMA:
        raise SceneError("exact authored scene document required")
    rebuilt=make_advanced_scene(document["editor"],settings,
                                seed=document["seed"],layout=document["layout"],
                                scene_id=document["scene_id"])
    if rebuilt != document:
        raise SceneError("scene source checksum, schema or configuration binding changed")
    return rebuilt


def scene_path(document: Mapping[str,object]) -> str:
    if type(document) is not dict:
        raise SceneError("authored scene document required")
    scene_id=document.get("scene_id")
    editor=document.get("editor")
    if type(scene_id) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{1,63}",scene_id):
        raise SceneError("safe original scene identity required")
    if type(editor) is not str or editor not in ENGINES:
        raise SceneError("original playable engine family required")
    return "scenes/advanced_"+editor+"_"+scene_id+".json"


__all__=["SCHEMA","SceneError","MAX_SCENE_BYTES","make_advanced_scene",
         "validate_advanced_scene","scene_path"]
