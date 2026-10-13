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
from .advanced_genre_engines import STARTS as GENRE_STARTS, CARDS, puzzle_default_layout
from .advanced_quest_director_runtime import (default_layout as quest_layout,
    normalize_layout as validate_quest_layout,QuestDirectorError)
from .advanced_fighting_runtime import (default_layout as fight_layout,
                                         normalize_layout as validate_fight_layout,
                                         FightingActionError)
from .advanced_rhythm_runtime import (default_layout as rhythm_layout,
                                      normalize_layout as validate_rhythm_layout,
                                      RhythmActionError)
from .advanced_npc_society_runtime import (
    default_layout as society_layout, normalize_layout as validate_society_layout,
    SocietyActionError,
)
from .advanced_dialogue_runtime import (
    default_layout as dialogue_layout, normalize_layout as validate_dialogue_layout,
    DialogueActionError,
)
from .advanced_voxel_runtime import (
    default_layout as voxel_layout, normalize_layout as validate_voxel_layout,
    VoxelActionError,
)
from .advanced_ecosystem_runtime import (
    default_layout as ecosystem_layout, normalize_layout as validate_ecosystem_layout,
    EcosystemActionError,
)
from .advanced_economy_runtime import (
    default_layout as economy_layout, normalize_layout as validate_economy_layout,
    EconomyActionError,
)
from .advanced_rpg_runtime import (
    default_layout as rpg_layout, normalize_layout as validate_rpg_layout,
    RPGActionError,
)
from .advanced_procedural_world_runtime import (
    default_layout as proc_layout, normalize_layout as validate_proc_layout,
    ProceduralWorldActionError,
)
from .advanced_maze_runtime import (
    default_layout as maze_layout, normalize_layout as validate_maze_layout,
    MazeActionError,
)
from .advanced_sports_runtime import (
    default_layout as sports_layout, normalize_layout as validate_sports_layout,
    SportsActionError,
)
from .advanced_parkour_runtime import (
    default_layout as parkour_layout, normalize_layout as validate_parkour_layout,
    ParkourActionError,
)
from .advanced_sailing_runtime import (
    default_layout as sailing_layout, normalize_layout as validate_sailing_layout,
    SailingActionError,
)
from .advanced_maritime_rescue_runtime import (
    default_layout as maritime_layout, normalize_layout as validate_maritime_layout,
    SailingActionError as MaritimeRescueActionError,
)
from .advanced_flight_runtime import (
    default_layout as flight_layout, normalize_layout as validate_flight_layout,
    FlightActionError,
)
from .advanced_rts_runtime import (default_layout as rts_layout,
                                   normalize_layout as validate_rts_layout,
                                   RTSActionError)
from .advanced_roguelike_runtime import (default_layout as rogue_layout,
                                         normalize_layout as validate_rogue_layout,
                                         RoguelikeActionError)
from .advanced_sandbox_runtime import (default_layout as sandbox_layout,
                                       normalize_layout as validate_sandbox_layout,
                                       SandboxActionError)
from .advanced_metroidvania_runtime import (default_layout as explore_layout,
                                          normalize_layout as validate_explore_layout,
                                          ExplorationActionError)
from .advanced_stealth_runtime import (default_layout as stealth_layout,
                                      normalize_layout as validate_stealth_layout,
                                      StealthActionError)
from .advanced_city_runtime import (default_layout as city_layout,
                                    normalize_layout as validate_city_layout,
                                    CityActionError)
from .advanced_colony_runtime import (default_layout as colony_layout,
                                      normalize_layout as validate_colony_layout,
                                      ColonyActionError)
from .advanced_factory_runtime import (default_layout as factory_layout,
                                       normalize_layout as validate_factory_layout,
                                       FactoryActionError)
from .advanced_farming_runtime import (default_layout as farm_layout,
                                       normalize_layout as validate_farm_layout,
                                       FarmingActionError)

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
    if engine == "shooter":
        state=GENRE_STARTS["shooter"](config,seed)
        return {"width":state["width"],"height":state["height"],
                "player_spawn":state["player"],"cover":state["cover"],
                "enemy_spawns":state["spawns"],"extraction":state["extraction"],
                "medkits":state["pickups"]}
    if engine == "deck_battler":
        state=GENRE_STARTS["deck_battler"](config,seed)
        return {"cards":state["deck_origin"],
                "enemy_pattern":state["enemy_pattern"],
                "hand_size":state["hand_limit"],
                "enemy_armor":state["enemy_block"],
                "potions":state["potions"]}
    if engine == "puzzle":
        return puzzle_default_layout(config)
    if engine == "farming":
        return farm_layout(config,seed)
    if engine == "factory":
        return factory_layout(config,seed)
    if engine == "colony":
        return colony_layout(config,seed)
    if engine == "city_builder":
        return city_layout(config,seed)
    if engine == "stealth":
        return stealth_layout(config,seed)
    if engine == "metroidvania":
        return explore_layout(config,seed)
    if engine == "sandbox":
        return sandbox_layout(config,seed)
    if engine == "roguelike":
        return rogue_layout(config,seed)
    if engine == "rts":
        return rts_layout(config,seed)
    if engine == "rhythm":
        return rhythm_layout(config,seed)
    if engine == "fighting":
        return fight_layout(config,seed)
    if engine == "quest_director":
        return quest_layout(config,seed)
    if engine == "flight":
        return flight_layout(config,seed)
    if engine == "sailing":
        return sailing_layout(config,seed)
    if engine == "maritime_rescue":
        return maritime_layout(config,seed)
    if engine == "parkour":
        return parkour_layout(config,seed)
    if engine == "sports":
        return sports_layout(config,seed)
    if engine == "maze":
        return maze_layout(config,seed)
    if engine == "rpg":
        return rpg_layout(config,seed)
    if engine == "procedural_world":
        return proc_layout(config,seed)
    if engine == "npc_society":
        return society_layout(config,seed)
    if engine == "ecosystem":
        return ecosystem_layout(config,seed)
    if engine == "voxel":
        return voxel_layout(config,seed)
    if engine == "dialogue":
        return dialogue_layout(config,seed)
    if engine == "economy":
        return economy_layout(config,seed)
    raise SceneError("no advanced authored scene available for that engine")


def _normalize_layout(engine, config, layout):
    if type(layout) is not dict:
        raise SceneError("authored layout must be a JSON object")
    if engine=="quest_director":
        try:
            return validate_quest_layout(config,layout)
        except QuestDirectorError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="flight":
        try:
            return validate_flight_layout(config,layout)
        except FlightActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="sailing":
        try:
            return validate_sailing_layout(config,layout)
        except SailingActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="maritime_rescue":
        try:
            return validate_maritime_layout(config,layout)
        except MaritimeRescueActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="parkour":
        try:
            return validate_parkour_layout(config,layout)
        except ParkourActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="sports":
        try:
            return validate_sports_layout(config,layout)
        except SportsActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="maze":
        try:
            return validate_maze_layout(config,layout)
        except MazeActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="rpg":
        try:
            return validate_rpg_layout(config,layout)
        except RPGActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="procedural_world":
        try:
            return validate_proc_layout(config,layout)
        except ProceduralWorldActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="npc_society":
        try:
            return validate_society_layout(config,layout)
        except SocietyActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="ecosystem":
        try:
            return validate_ecosystem_layout(config,layout)
        except EcosystemActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="voxel":
        try:
            return validate_voxel_layout(config,layout)
        except VoxelActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="economy":
        try:
            return validate_economy_layout(config,layout)
        except EconomyActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="dialogue":
        try:
            return validate_dialogue_layout(config,layout)
        except DialogueActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="fighting":
        try:
            return validate_fight_layout(config,layout)
        except FightingActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="rhythm":
        try:
            return validate_rhythm_layout(config,layout)
        except RhythmActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="rts":
        try:
            return validate_rts_layout(config,layout)
        except RTSActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="roguelike":
        try:
            return validate_rogue_layout(config,layout)
        except RoguelikeActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="sandbox":
        try:
            return validate_sandbox_layout(config,layout)
        except SandboxActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="metroidvania":
        try:
            return validate_explore_layout(config,layout)
        except ExplorationActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="stealth":
        try:
            return validate_stealth_layout(config,layout)
        except StealthActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="city_builder":
        try:
            return validate_city_layout(config,layout)
        except CityActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="colony":
        try:
            return validate_colony_layout(config,layout)
        except ColonyActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="factory":
        try:
            return validate_factory_layout(config,layout)
        except FactoryActionError as exc:
            raise SceneError(str(exc)) from exc
    if engine=="farming":
        try:
            return validate_farm_layout(config,layout)
        except FarmingActionError as exc:
            raise SceneError(str(exc)) from exc
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
    if engine=="shooter":
        keys={"width","height","player_spawn","cover","enemy_spawns",
              "extraction","medkits"}
        if set(layout)!=keys:
            raise SceneError("exact advanced arena scene layout required")
        width=_number(layout["width"],8,30,"width")
        height=_number(layout["height"],6,20,"height")
        cover=_cells(layout["cover"],width,height,100,"cover")
        enemies=_cells(layout["enemy_spawns"],width,height,3,"enemy_spawns")
        pickups=_cells(layout["medkits"],width,height,12,"medkits")
        player=_cells([layout["player_spawn"]],width,height,1,"player_spawn")[0]
        extraction=_cells([layout["extraction"]],width,height,1,"extraction")[0]
        if len(enemies)!=3 or player==extraction:
            raise SceneError("arena requires three enemy spawns and distinct extraction")
        occupied={tuple(x) for x in cover+enemies+pickups+[player,extraction]}
        if len(occupied)!=len(cover)+len(enemies)+len(pickups)+2:
            raise SceneError("combat arena cannot overlap terrain, units or pickups")
        blocked={tuple(c) for c in cover}
        visited={tuple(player)};queue=deque([tuple(player)])
        while queue:
            x,y=queue.popleft()
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if (0<=point[0]<width and 0<=point[1]<height
                    and point not in visited and point not in blocked):
                    visited.add(point);queue.append(point)
        if tuple(extraction) not in visited or any(tuple(e) not in visited for e in enemies):
            raise SceneError("original arena blocks extraction or enemy combat route")
        return {"width":width,"height":height,"player_spawn":player,
                "cover":cover,"enemy_spawns":enemies,"extraction":extraction,
                "medkits":pickups}
    if engine=="deck_battler":
        keys={"cards","enemy_pattern","hand_size","enemy_armor","potions"}
        if set(layout)!=keys:
            raise SceneError("exact original deck and boss encounter required")
        cards=layout["cards"];patterns=layout["enemy_pattern"]
        if type(cards) is not list or not 10<=len(cards)<=40 or any(
            type(card) is not str or card not in CARDS for card in cards
        ):
            raise SceneError("deck must use ten to forty registered original card rules")
        if type(patterns) is not list or not 2<=len(patterns)<=8 or any(
            type(p) is not str or p not in {"attack","defend","poison","charge"}
            for p in patterns
        ):
            raise SceneError("enemy intent pattern must be a bounded typed cycle")
        hand=_number(layout["hand_size"],3,5,"hand_size")
        armor=_number(layout["enemy_armor"],0,20,"enemy_armor")
        potions=_number(layout["potions"],0,5,"potions")
        if not any(card in {"strike","pierce","drain","spark"} and
                   CARDS[card][0]<=config["energy_per_turn"] for card in cards):
            raise SceneError("deck requires at least one affordable damaging card")
        return {"cards":list(cards),"enemy_pattern":list(patterns),
                "hand_size":hand,"enemy_armor":armor,"potions":potions}
    if engine=="puzzle":
        keys={"spawn","exit","walls","doors","switches","crates",
              "targets","nodes","portals","phase_gates"}
        if set(layout)!=keys:
            raise SceneError("exact puzzle geometry and mode-specific devices required")
        w=config["board_width"];h=config["board_height"]
        result={}
        for key in ("walls","doors","switches","crates","targets","nodes","phase_gates"):
            result[key]=_cells(layout[key],w,h,min(96,w*h),key)
        result["spawn"]=_cells([layout["spawn"]],w,h,1,"spawn")[0]
        result["exit"]=_cells([layout["exit"]],w,h,1,"exit")[0]
        portals=layout["portals"]
        if type(portals) is not list or len(portals)>4:
            raise SceneError("puzzle portal count exceeds bounded original scene")
        result["portals"]=[]
        for pair in portals:
            if type(pair) is not list or len(pair)!=2:
                raise SceneError("portal must link exactly two cells")
            endpoints=_cells(pair,w,h,2,"portal")
            if endpoints[0]==endpoints[1]:
                raise SceneError("self-referential portal is not a valid original link")
            result["portals"].append(endpoints)
        mode=config["logic"]
        mode_objects={
            "switches":{"switches","doors"},
            "push_blocks":{"crates","targets"},
            "circuits":{"nodes","doors"},
            "time":{"phase_gates"},
            "non_euclidean":{"portals"},
        }[mode]
        for group in ("doors","switches","crates","targets","nodes","phase_gates","portals"):
            if group not in mode_objects and result[group]:
                raise SceneError("scene contains inactive devices for puzzle logic mode")
        requirements={
            "switches":bool(result["switches"]),
            "push_blocks":bool(result["crates"]) and len(result["crates"])==len(result["targets"]),
            "circuits":bool(result["nodes"]),
            "time":bool(result["phase_gates"]),
            "non_euclidean":bool(result["portals"]),
        }
        if not requirements[mode]:
            raise SceneError("mode-specific puzzle victory devices are required")
        groups=[result[k] for k in ("walls","doors","switches","crates","nodes","phase_gates")]
        all_items=[tuple(x) for group in groups for x in group]
        all_items += [tuple(x) for pair in result["portals"] for x in pair]
        all_items += [tuple(result["spawn"]),tuple(result["exit"])]
        if len(all_items)!=len(set(all_items)):
            raise SceneError("puzzle walls, devices, portals and spawn/exits overlap")
        if result["spawn"]==result["exit"]:
            raise SceneError("puzzle entrance and exit must be distinct")
        # Targets are legitimate future crate locations, but cannot be walls or exits.
        if any(tuple(c) in {tuple(p) for p in result["walls"]+[result["spawn"],result["exit"]]}
               for c in result["targets"]):
            raise SceneError("push-block goals cannot be impassable or initial spawn/exit")
        if config["solution_required"]:
            blocked={tuple(c) for c in result["walls"]}
            seen={tuple(result["spawn"])};queue=deque([tuple(result["spawn"])])
            while queue:
                x,y=queue.popleft()
                for q in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if 0<=q[0]<w and 0<=q[1]<h and q not in blocked and q not in seen:
                        seen.add(q);queue.append(q)
            if tuple(result["exit"]) not in seen:
                raise SceneError("required-solution puzzle exit is statically isolated")
        # Static reachability alone does not certify actual puzzle solvability.
        return result
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
