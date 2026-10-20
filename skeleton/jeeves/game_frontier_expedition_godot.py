"""Original, playable Godot 4 world export for the Jeeves 3D expedition.

Produces an actual standalone .tscn/GDScript project and source-bound authored
data, not a mock renderer or copied commercial project. The in-engine avatar
uses explicit edge selection, stamina/health, limited rest, discoveries and
instrument-gated conditions. Tests can launch Godot headless when installed.

Native engine output remains untrusted observations until independently
checked against the exact authored world and run evidence.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionError, ExpeditionWorld, Traveler, world_export,
    _json,
)

_GODOT_PROJECT = """config_version=5

[application]
config/name="Original Frontier Expedition"
run/main_scene="res://game/frontier/expedition.tscn"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
textures/default_filters/use_nearest_mipmap_filter=false
"""

_GODOT_SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://game/frontier/expedition.gd" id="1"]

[node name="FrontierExpedition" type="Node3D"]
script = ExtResource("1")
"""

_GODOT_SCRIPT = r'''extends Node3D
# Original engine-neutral authored route graph, executed as a Godot 4 game.
# Observe and challenge the native receipts before source or canon promotion.

const WORLD_FILE = "res://game/frontier/expedition.json"
const PLAYER_FILE = "res://game/frontier/player.json"
const CONTROLLER_FILE = "res://game/frontier/controller.json"
const CANON_FILE = "res://game/frontier/canon.json"
const VISUALS_FILE = "res://game/frontier/visuals_manifest.json"
const QUESTS_FILE = "res://game/frontier/quests.json"
const AUDIO_FILE = "res://game/frontier/audio_pcm.json"
const AUDIO_MIX_FILE = "res://game/frontier/audio_mix.json"
const ECOLOGY_SCRIPT = "res://game/frontier/ecology.gd"
const NPC_FILE = "res://game/frontier/npcs.json"
const LOD_FILE = "res://game/frontier/lod_runtime.json"
const CINEMATIC_SCENE = "res://game/frontier/cinematic.tscn"
const STORYBOARD_FILE = "res://game/frontier/storyboard.json"
const AUTOPLAY_FILE = "res://game/frontier/autoplay.json"
const MAX_GAME_EDGES = 65536
var world: Dictionary = {}
var player: Dictionary = {}
var waypoint_by_id: Dictionary = {}
var edge_by_id: Dictionary = {}
var current_id: String = ""
var selected: int = 0
var stamina: int = 0
var health: int = 100
var elapsed_s: float = 0.0
var flags: Dictionary = {}
var inventory: Dictionary = {}
var visited: Dictionary = {}
var receipts: Array = []
var receipt_head: String = ""
var won: bool = false
var failed: bool = false
var camera: Camera3D
var hud: Label
var controller_hud: Label
var canon: Dictionary = {}
var visuals: Dictionary = {}
var quests: Dictionary = {}
var npc_cast: Dictionary = {}
var npc_markers: Dictionary = {}
var storyboard: Dictionary = {}
var quest_flags: Dictionary = {}
var quest_progress: Dictionary = {}
var lod_policy: Dictionary = {}
var marker_by_id: Dictionary = {}
var lod_frame: int = 0
var cinematic: Node3D
var sound_player: AudioStreamPlayer
var story_flags: Dictionary = {}
var completed_scenes: Dictionary = {}
var actor: MeshInstance3D

func _load_json(path: String) -> Dictionary:
    if not FileAccess.file_exists(path):
        push_error("Expedition game source missing: " + path)
        return {}
    var raw := FileAccess.get_file_as_string(path)
    if raw.length() > 4000000:
        push_error("Authored expedition exceeded bounded source budget")
        return {}
    var parsed = JSON.parse_string(raw)
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Invalid authored expedition JSON")
        return {}
    return parsed

func _ready() -> void:
    world = _load_json(WORLD_FILE)
    player = _load_json(PLAYER_FILE)
    if (world.get("schema", "") != "skeleton.game.frontier_expedition.v1"
            or player.get("schema", "") != "skeleton.game.frontier_expedition_player.v1"
            or str(world.get("world_digest", "")).length() != 64
            or str(player.get("traveler_digest", "")).length() != 64):
        push_error("Authored expedition schema mismatch")
        return
    var nodes = world.get("waypoints", [])
    var links = world.get("edges", [])
    if (typeof(nodes) != TYPE_ARRAY or typeof(links) != TYPE_ARRAY
            or nodes.size() < 2 or nodes.size() > 8192
            or links.size() < 1 or links.size() > MAX_GAME_EDGES):
        push_error("Invalid authored navigation source")
        return
    for node in nodes:
        if typeof(node) != TYPE_DICTIONARY or not node.has("waypoint_id"):
            push_error("Invalid authored waypoint")
            return
        var nid := str(node["waypoint_id"])
        if waypoint_by_id.has(nid):
            push_error("Duplicate authored waypoint ID")
            return
        waypoint_by_id[nid] = node
    for edge in links:
        if typeof(edge) != TYPE_DICTIONARY:
            push_error("Invalid authored travel link")
            return
        if (not waypoint_by_id.has(str(edge.get("source", "")))
                or not waypoint_by_id.has(str(edge.get("target", "")))):
            push_error("Authored travel link has unresolved endpoint")
            return
        var eid := str(edge.get("edge_id", ""))
        if edge_by_id.has(eid):
            push_error("Duplicate authored travel edge ID")
            return
        edge_by_id[eid] = edge
        if not bool(edge.get("one_way", true)):
            var backward: Dictionary = (edge as Dictionary).duplicate(true)
            backward["edge_id"] = eid + ".reverse"
            backward["source"] = edge["target"]
            backward["target"] = edge["source"]
            backward["one_way"] = true
            if edge_by_id.has(backward["edge_id"]):
                push_error("Authored reverse edge collides with source")
                return
            edge_by_id[backward["edge_id"]] = backward
    current_id = str(world.get("arrival", ""))
    if not waypoint_by_id.has(current_id):
        push_error("Authored expedition has no real starting waypoint")
        return
    stamina = int(player.get("max_stamina", 0))
    if stamina < 1 or stamina > 1000:
        push_error("Invalid authored traveler stamina")
        return
    for token in player.get("flags", []):
        flags[str(token)] = true
    for token in player.get("equipment", []):
        flags[str(token)] = true
    visited[current_id] = true
    receipt_head = (str(world.get("source", "")) + ":" +
        str(world.get("project", "")) + ":" + current_id).sha256_text()
    _load_optional_authored_game()
    _setup_scene()
    _install_controller()
    _install_soundscape()
    _advance_quests()
    _refresh_ui()
    print("EXPEDITION_READY " + str(world.get("project", "")) +
          " " + str(waypoint_by_id.size()) + " " + str(edge_by_id.size()))
    _emit_observation("spawn", "start")
    if OS.get_cmdline_user_args().has("--expedition-autoplay"):
        _run_autoplay()

func _run_autoplay() -> void:
    var recipe := _load_json(AUTOPLAY_FILE)
    if (recipe.get("schema", "") != "skeleton.game.expedition_autoplay.v1"
            or str(recipe.get("world_digest", "")) != str(world.get("world_digest", ""))
            or str(recipe.get("traveler_digest", "")) != str(player.get("traveler_digest", ""))):
        push_error("Autoplay source or player differs from exact game files")
        get_tree().quit(21)
        return
    var steps = recipe.get("steps", [])
    if typeof(steps) != TYPE_ARRAY or steps.size() < 1 or steps.size() > 4096:
        push_error("Autoplay sequence exceeds game execution budget")
        get_tree().quit(22)
        return
    for step in steps:
        if typeof(step) != TYPE_DICTIONARY:
            push_error("Autoplay action schema invalid")
            get_tree().quit(23)
            return
        var edge_id := str(step.get("edge_id", ""))
        var edge: Dictionary = edge_by_id.get(edge_id, {})
        if edge.is_empty() or str(edge["source"]) != current_id:
            push_error("Autoplay edge is not connected to actual gameplay")
            get_tree().quit(24)
            return
        _travel(edge)
        if current_id != str(step.get("target", "")):
            push_error("Autoplay action failed authored travel constraints")
            get_tree().quit(25)
            return
    var completed: bool = won and not failed and bool(
        world.get("destinations", []).has(current_id))
    print("EXPEDITION_COMPLETE " + JSON.stringify({
        "world_digest": str(world.get("world_digest", "")),
        "route_digest": str(recipe.get("route_digest", "")),
        "completed":completed,
        "steps": receipts.size(),
        "candidate_receipt_head":receipt_head,
    }))
    if not completed:
        push_error("Native expedition did not reach its actual authored goal")
        get_tree().quit(26)
    else:
        get_tree().quit(0)

func _load_optional_authored_game() -> void:
    if FileAccess.file_exists(CANON_FILE):
        var source: Dictionary = _load_json(CANON_FILE)
        if (source.get("schema", "") == "skeleton.game.canon_dialogue.v1"
                and str(source.get("world_digest", "")) == str(world.get("world_digest", ""))):
            canon = source
        else:
            push_error("Optional story canon differs from original world")
    if FileAccess.file_exists(VISUALS_FILE):
        var style: Dictionary = _load_json(VISUALS_FILE)
        if (style.get("schema", "") == "skeleton.game.original_3d_assets.v1"
                and str(style.get("world_digest", "")) == str(world.get("world_digest", ""))):
            visuals = style
        else:
            push_error("Optional visual asset manifest differs from original world")
    if FileAccess.file_exists(NPC_FILE):
        var actors: Dictionary = _load_json(NPC_FILE)
        if (actors.get("schema", "") == "skeleton.game.original_npc_cast.v1"
                and str(actors.get("world_digest", "")) == str(world.get("world_digest", ""))):
            npc_cast = actors
        else:
            push_error("Optional NPC source is not the original world")
    if FileAccess.file_exists(QUESTS_FILE):
        var quest_source: Dictionary = _load_json(QUESTS_FILE)
        if (quest_source.get("schema", "") == "skeleton.game.canon_quest_endings.v1"
                and str(quest_source.get("world", "")) == str(world.get("world_digest", ""))):
            quests = quest_source
        else:
            push_error("Optional quest source is not game-bound")
    if FileAccess.file_exists(STORYBOARD_FILE):
        var authored_clips: Dictionary = _load_json(STORYBOARD_FILE)
        if (authored_clips.get("schema", "") == "skeleton.game.original_storyboard.v1"
                and str(authored_clips.get("world", "")) == str(world.get("world_digest", ""))):
            storyboard = authored_clips
        else:
            push_error("Cinematics are authored for another world")
    if FileAccess.file_exists(LOD_FILE):
        var lod: Dictionary = _load_json(LOD_FILE)
        if (lod.get("schema", "") == "skeleton.game.original_lod_runtime.v1"
                and str(lod.get("world_digest", "")) == str(world.get("world_digest", ""))):
            lod_policy = lod
        else:
            push_error("Render LOD source belongs to another world")

func _install_soundscape() -> void:
    if not FileAccess.file_exists(AUDIO_FILE):
        return
    var path: String = AUDIO_MIX_FILE if FileAccess.file_exists(AUDIO_MIX_FILE) else AUDIO_FILE
    var data: Dictionary = _load_json(path)
    if (str(data.get("schema", "")) not in [
            "skeleton.game.original_audio_pcm.v1",
            "skeleton.game.adaptive_original_audio_resource.v1"]
            or str(data.get("world_digest", "")) != str(world.get("world_digest", ""))):
        push_error("Original soundscape was built for another game")
        return
    var raw: PackedByteArray = Marshalls.base64_to_raw(str(data.get("pcm_base64", "")))
    var rate: int = int(data.get("rate", 0))
    if raw.size() < 200 or raw.size() > 3000000 or rate not in [8000,16000,22050,44100]:
        push_error("Original soundscape PCM exceeds resource budget")
        return
    var wav := AudioStreamWAV.new()
    wav.format = AudioStreamWAV.FORMAT_16_BITS
    wav.mix_rate = rate
    wav.stereo = false
    wav.data = raw
    sound_player = AudioStreamPlayer.new()
    sound_player.stream = wav
    sound_player.volume_db = -18.0
    add_child(sound_player)
    sound_player.play()
    print("EXPEDITION_AUDIO_READY " + str(world.get("world_digest", "")))

func _advance_quests() -> void:
    for quest in quests.get("quests", []):
        var quest_id := str(quest.get("quest_id", ""))
        var steps: Array = quest.get("stages", [])
        var index: int = int(quest_progress.get(quest_id, 0))
        if index >= steps.size():
            continue
        var stage: Dictionary = steps[index]
        if str(stage.get("waypoint", "")) != current_id:
            continue
        var eligible: bool = true
        for required in stage.get("requires_game_flags", []):
            if not flags.has(str(required)):
                eligible = false
        for required in stage.get("requires_items", []):
            if not inventory.has(str(required)):
                eligible = false
        for required in stage.get("requires_story_flags", []):
            if not story_flags.has(str(required)):
                eligible = false
        if not eligible:
            continue
        quest_progress[quest_id] = index+1
        for token in stage.get("unlocks", []):
            quest_flags[str(token)] = true
        print("EXPEDITION_QUEST " + JSON.stringify({
            "world_digest":str(world.get("world_digest", "")),
            "quest":quest_id,"stage":str(stage.get("stage_id", "")),
            "step":index+1,"game_receipt_head":receipt_head,
        }))

func _resolve_ending() -> void:
    if not won:
        return
    var qualified: Array = []
    for ending in quests.get("endings", []):
        var valid: bool = true
        for flag in ending.get("needs_game_flags", []):
            if not flags.has(str(flag)) and not inventory.has(str(flag)):
                valid = false
        for flag in ending.get("needs_story_flags", []):
            if not story_flags.has(str(flag)):
                valid = false
        for flag in ending.get("needs_quest_flags", []):
            if not quest_flags.has(str(flag)):
                valid = false
        if valid:
            qualified.append(ending)
    qualified.sort_custom(func(a, b): return int(a["priority"]) > int(b["priority"]))
    if qualified.size()>0:
        print("EXPEDITION_ENDING " + JSON.stringify({
            "source":str(world.get("world_digest", "")),
            "ending_id":str(qualified[0]["ending_id"]),
            "game_receipt_head":receipt_head,
            "quest_flags":quest_flags.keys(),
        }))

func _story_scene() -> Dictionary:
    for scene in canon.get("scenes", []):
        if str(scene.get("waypoint", "")) != current_id:
            continue
        if completed_scenes.has(str(scene.get("scene_id", ""))) and not bool(scene.get("repeatable", false)):
            continue
        var allowed: bool = true
        for flag in scene.get("requires_game_flags", []):
            if not flags.has(str(flag)) and not inventory.has(str(flag)):
                allowed = false
        for flag in scene.get("requires_story_flags", []):
            if not story_flags.has(str(flag)):
                allowed = false
        if allowed:
            return scene
    return {}

func _choose_story(index: int) -> void:
    if won or failed:
        return
    var scene := _story_scene()
    if scene.is_empty():
        return
    var choices: Array = scene.get("choices", [])
    if index < 0 or index >= choices.size():
        return
    var choice: Dictionary = choices[index]
    for grant in choice.get("advances", []):
        story_flags[str(grant)] = true
    completed_scenes[str(scene["scene_id"])] = true
    _advance_quests()
    print("EXPEDITION_STORY " + JSON.stringify({
        "world_digest":str(world.get("world_digest", "")),
        "scene":str(scene["scene_id"]), "choice":str(choice["choice_id"]),
        "at":current_id, "game_receipt_head":receipt_head,
        "story_flags":story_flags.keys(),
    }))
    _refresh_ui()

func _install_controller() -> void:
    if not FileAccess.file_exists(CONTROLLER_FILE):
        return
    var profile: Dictionary = _load_json(CONTROLLER_FILE)
    if (profile.get("schema", "") != "skeleton.game.controller_profile.v1"
            or str(profile.get("world_digest", "")) != str(world.get("world_digest", ""))):
        push_error("Controller belongs to another authored game")
        return
    var mappings: Dictionary = profile.get("input_map", {})
    for action_name in ["ui_up", "ui_down", "ui_accept", "ui_cancel"]:
        if not mappings.has(action_name):
            push_error("Missing controller game action")
            return
        var button_index: int = int(mappings[action_name])
        if button_index < 0 or button_index > 31:
            push_error("Unsupported controller physical index")
            return
        var gamepad := InputEventJoypadButton.new()
        gamepad.device = -1
        gamepad.button_index = button_index
        gamepad.pressed = true
        if not InputMap.action_has_event(action_name, gamepad):
            InputMap.action_add_event(action_name, gamepad)
    if controller_hud != null:
        var labels: Array = []
        for button in profile.get("buttons", []):
            labels.append(str(button.get("legend", "")) + ": " + str(button.get("action", "")))
        controller_hud.text = "GAMEPAD  " + str(profile.get("era", "")) + "\n" + "  |  ".join(labels)

func _where(node: Dictionary) -> Vector3:
    return Vector3(float(node["x_m"]), float(node["altitude_m"]), float(node["y_m"]))

func _setup_scene() -> void:
    var sun := DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-48, 20, 0)
    sun.light_energy = 1.6
    add_child(sun)
    for node in waypoint_by_id.values():
        var marker := MeshInstance3D.new()
        var ball := SphereMesh.new()
        ball.radius = 1.8 if str(node["kind"]) == "sky_island" else 1.1
        ball.height = ball.radius * 2.0
        marker.mesh = ball
        var model_path := "res://game/frontier/assets/" + str(node["waypoint_id"]) + "_lod0.obj"
        if ResourceLoader.exists(model_path):
            var loaded: Resource = load(model_path)
            if loaded is Mesh:
                marker.mesh = loaded
        var mat := StandardMaterial3D.new()
        var kind := str(node["kind"])
        if kind == "sky_island":
            mat.albedo_color = Color(0.3, 0.75, 0.95)
        elif kind == "underwater":
            mat.albedo_color = Color(0.1, 0.35, 0.85)
        elif kind == "ruins":
            mat.albedo_color = Color(0.85, 0.55, 0.9)
        else:
            mat.albedo_color = Color(0.4, 0.9, 0.45)
        marker.material_override = mat
        marker.position = _where(node)
        marker.set_meta("waypoint_id", str(node["waypoint_id"]))
        add_child(marker)
        marker_by_id[str(node["waypoint_id"])] = marker
    if not npc_cast.is_empty():
        var count: int = 0
        for row in npc_cast.get("cast", []):
            var profile: Dictionary = row.get("design", {})
            var home_id := str(profile.get("home", ""))
            if not waypoint_by_id.has(home_id) or count >= 64:
                continue
            var npc := MeshInstance3D.new()
            var npc_body := CapsuleMesh.new()
            npc_body.radius = 0.42
            npc_body.height = 2.1
            npc.mesh = npc_body
            var clothing := StandardMaterial3D.new()
            clothing.albedo_color = Color(0.45, 0.7, 1.0)
            npc.material_override = clothing
            npc.position = _where(waypoint_by_id[home_id])+Vector3(0, 2, 0)
            add_child(npc)
            npc_markers[str(profile.get("npc_id", ""))] = npc
            count += 1
        print("EXPEDITION_NPC_READY " + str(world.get("world_digest", "")) + " " + str(count))
    if ResourceLoader.exists(ECOLOGY_SCRIPT):
        var flora := Node3D.new()
        flora.set_meta("expected_world", str(world.get("world_digest", "")))
        flora.set_script(load(ECOLOGY_SCRIPT))
        add_child(flora)
    var segments := ImmediateMesh.new()
    segments.surface_begin(Mesh.PRIMITIVE_LINES)
    for edge in world["edges"]:
        var a = waypoint_by_id[str(edge["source"])]
        var b = waypoint_by_id[str(edge["target"])]
        segments.surface_add_vertex(_where(a))
        segments.surface_add_vertex(_where(b))
    segments.surface_end()
    var links := MeshInstance3D.new()
    links.mesh = segments
    var lines := StandardMaterial3D.new()
    lines.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    lines.albedo_color = Color(1, 0.8, 0.35)
    links.material_override = lines
    add_child(links)
    actor = MeshInstance3D.new()
    var capsule := CapsuleMesh.new()
    capsule.radius = 1.0
    capsule.height = 3.0
    actor.mesh = capsule
    var actor_material := StandardMaterial3D.new()
    actor_material.albedo_color = Color(1, 0.35, 0.2)
    actor.material_override = actor_material
    add_child(actor)
    _place_actor()
    camera = Camera3D.new()
    camera.current = true
    camera.far = 100000.0
    camera.fov = 60.0
    add_child(camera)
    camera.position = actor.position + Vector3(0, 28, 45)
    camera.look_at(actor.position, Vector3.UP)
    var layer := CanvasLayer.new()
    add_child(layer)
    hud = Label.new()
    hud.position = Vector2(16, 16)
    hud.add_theme_color_override("font_color", Color.WHITE)
    layer.add_child(hud)
    controller_hud = Label.new()
    controller_hud.position = Vector2(16, 580)
    controller_hud.add_theme_color_override("font_color", Color(0.8, 0.9, 1))
    layer.add_child(controller_hud)
    if ResourceLoader.exists(CINEMATIC_SCENE):
        var packed: PackedScene = load(CINEMATIC_SCENE)
        if packed != null:
            cinematic = packed.instantiate()
            add_child(cinematic)

func _place_actor() -> void:
    actor.position = _where(waypoint_by_id[current_id]) + Vector3(0, 3, 0)

func _outgoing() -> Array:
    var choices: Array = []
    for edge in edge_by_id.values():
        if str(edge["source"]) == current_id:
            choices.append(edge)
    choices.sort_custom(func(a, b): return str(a["edge_id"]) < str(b["edge_id"]))
    return choices

func _can_travel(edge: Dictionary) -> bool:
    if not player.get("permitted_modes", []).has(str(edge.get("mode", ""))):
        return false
    for requirement in edge.get("requires", []):
        if not flags.has(str(requirement)):
            return false
    var weather: Dictionary = world.get("weather", {})
    if (float(weather.get("visibility", 1.0)) < 0.12
            and str(edge.get("mode", "")) in ["glide", "updraft", "airship", "portal"]
            and not flags.has("instrument_navigation")):
        return false
    return true

func _edge_cost(edge: Dictionary) -> Dictionary:
    var a = _where(waypoint_by_id[str(edge["source"])])
    var b = _where(waypoint_by_id[str(edge["target"])])
    var weather: Dictionary = world.get("weather", {})
    var horizontal: Vector2 = Vector2(b.x - a.x, b.z - a.z)
    var wind: Vector2 = Vector2(
        float(weather.get("wind_x_mps", 0)),
        float(weather.get("wind_y_mps", 0)))
    var along: float = horizontal.normalized().dot(wind) if horizontal.length() > 0.00001 else 0.0
    var mode := str(edge["mode"])
    var air := mode in ["glide", "updraft", "airship"]
    var wet := mode in ["walk", "climb", "rope_bridge"]
    var rain := float(weather.get("rain", 0.0))
    var turbulence := float(weather.get("turbulence", 0.0))
    var pressure: float = 1.0 + maxf(0.0, -along)*0.025 + (
        turbulence*0.8 if air else 0.0) + (rain*0.5 if wet else 0.0)
    if air and mode == "updraft" and float(weather.get("vertical_mps", 0.0)) > 0:
        pressure = maxf(0.5, pressure-float(weather["vertical_mps"])*0.02)
    var weight_ratio: float = float(player.get("carried_kg", 0.0)) / maxf(
        0.1, float(player.get("capacity_kg", 30.0)))
    var skill: float = float(player.get("skill", 0.5))
    var energy: int = maxi(0, mini(1000, ceili(
        float(edge["stamina_cost"])*pressure*(1.0+weight_ratio*0.6-skill*0.2))))
    var exposure: float = float(edge.get("risk", 0.0))*(
        1.0+turbulence*0.7+rain*0.4)*(1.0-0.45*skill)*(
        1.0-0.75*float(player.get("shelter", 0.0)))
    return {
        "stamina":energy,
        "damage":maxi(0, floori(exposure*10.0)),
        "seconds":snappedf(float(edge["duration_s"])*pressure*(
            1.0+weight_ratio*0.4),0.0001),
    }

func _commit(kind: String, evidence: String) -> void:
    var state := _state()
    var subject = JSON.stringify({
        "previous": receipt_head,
        "kind": kind,
        "evidence": evidence,
        "world": str(world.get("source", "")),
        "state": state,
    })
    receipt_head = subject.sha256_text()
    receipts.append(receipt_head)
    _emit_observation(kind, evidence)

func _state() -> Dictionary:
    return {
        "position":current_id,"stamina":stamina,"health":health,
        "seconds":elapsed_s,"visited":visited.keys(),
        "flags":flags.keys(),"inventory":inventory.keys(),"won":won,
        "failed":failed,"actions":receipts.size(),
    }

func _emit_observation(action: String, evidence: String) -> void:
    print("EXPEDITION_OBSERVATION " + JSON.stringify({
        "schema":"skeleton.game.expedition_native_observation.v1",
        "source_digest":str(world.get("source", "")),
        "world_digest":str(world.get("world_digest", "")),
        "traveler_digest":str(player.get("traveler_digest", "")),
        "project_id":str(world.get("project", "")),
        "action":action,"evidence":evidence,
        "state":_state(),"receipt_head":receipt_head,
        "native_authority":"untrusted_native_candidate_for_independent_review",
    }))

func _travel(edge: Dictionary) -> void:
    if won or failed or not _can_travel(edge):
        return
    var costs := _edge_cost(edge)
    if stamina < int(costs["stamina"]):
        return
    stamina -= int(costs["stamina"])
    health = maxi(0, health-int(costs["damage"]))
    elapsed_s += float(costs["seconds"])
    current_id = str(edge["target"])
    for token in edge.get("grants", []):
        flags[str(token)] = true
    if not visited.has(current_id):
        visited[current_id] = true
        var node: Dictionary = waypoint_by_id[current_id]
        if str(node.get("collectible", "")) != "":
            inventory[str(node["collectible"])] = true
        if str(node.get("quest_flag", "")) != "":
            flags[str(node["quest_flag"])] = true
    _place_actor()
    selected = 0
    if health <= 0:
        failed = true
    if world.get("destinations", []).has(current_id) and health > 0:
        won = true
    _commit("travel",str(edge["edge_id"]))
    _advance_quests()
    if cinematic != null and cinematic.has_method("play_clip"):
        for clip in storyboard.get("clips", []):
            if str(clip.get("waypoint", "")) == current_id:
                cinematic.call("play_clip", str(clip.get("clip_id", "")),
                               str(world.get("world_digest", "")))
                break
    _resolve_ending()
    _refresh_ui()

func _rest() -> void:
    if won or failed or not bool(waypoint_by_id[current_id].get("safe_rest", false)):
        return
    stamina = mini(int(player["max_stamina"]),stamina+25)
    elapsed_s += 60.0
    _commit("rest",current_id)
    _refresh_ui()

func _refresh_ui() -> void:
    if hud == null:
        return
    var choices := _outgoing()
    var lines := [
        "ORIGINAL FRONTIER | " + str(world.get("project", "")),
        "Location: " + current_id + "  HP: " + str(health) +
            "  Stamina: " + str(stamina),
        "Time: " + str(snappedf(elapsed_s, 0.01)) +
            "  Visited: " + str(visited.size()),
        "UP/DOWN select   ENTER travel   ESC rest",
    ]
    if won:
        lines.append("DESTINATION REACHED: original expedition complete")
    elif failed:
        lines.append("GAME OVER: health depleted")
    for i in range(mini(choices.size(), 8)):
        var edge: Dictionary = choices[i]
        var marker := "> " if i == (selected % maxi(1, choices.size())) else "  "
        var cost := _edge_cost(edge)
        lines.append(marker + str(edge["edge_id"]) + " -> " +
            str(edge["target"]) + " (" + str(edge["mode"]) + ")" +
            " stamina " + str(cost["stamina"]) +
            (" [LOCKED]" if not _can_travel(edge) else ""))
    var story_scene := _story_scene()
    if not story_scene.is_empty():
        lines.append("STORY - " + str(story_scene.get("speaker", "")) + ": " +
            str(story_scene.get("opening", "")))
        var options: Array = story_scene.get("choices", [])
        for n in range(mini(options.size(), 4)):
            lines.append("[" + str(n+1) + "] " + str(options[n].get("spoken_line", "")))
    hud.text = "\n".join(lines)

func _unhandled_input(event: InputEvent) -> void:
    if not event.is_pressed() or event.is_echo() or won or failed:
        return
    var choices := _outgoing()
    if event is InputEventKey:
        var keycode: int = (event as InputEventKey).keycode
        if keycode >= KEY_1 and keycode <= KEY_4:
            _choose_story(keycode - KEY_1)
            get_viewport().set_input_as_handled()
            return
    if event.is_action_pressed("ui_down") and choices.size() > 0:
        selected = (selected+1)%choices.size()
        _refresh_ui()
        get_viewport().set_input_as_handled()
    elif event.is_action_pressed("ui_up") and choices.size() > 0:
        selected = (selected-1+choices.size())%choices.size()
        _refresh_ui()
        get_viewport().set_input_as_handled()
    elif event.is_action_pressed("ui_accept") and choices.size() > 0:
        _travel(choices[selected%choices.size()])
        get_viewport().set_input_as_handled()
    elif event.is_action_pressed("ui_cancel"):
        _rest()
        get_viewport().set_input_as_handled()

func _animate_original_npcs() -> void:
    if npc_cast.is_empty():
        return
    for row in npc_cast.get("cast", []):
        var profile: Dictionary = row.get("design", {})
        var npc_id := str(profile.get("npc_id", ""))
        if not npc_markers.has(npc_id):
            continue
        var history: Dictionary = row.get("proof", {})
        var steps: Array = history.get("steps", [])
        if steps.is_empty():
            continue
        var move: Dictionary = steps[int(lod_frame / 120) % steps.size()]
        var target_id := str(move.get("new", ""))
        if waypoint_by_id.has(target_id):
            var marker: MeshInstance3D = npc_markers[npc_id]
            marker.position = marker.position.lerp(
                _where(waypoint_by_id[target_id])+Vector3(0, 2, 0), .18)

func _refresh_lod() -> void:
    if lod_policy.is_empty() or camera == null:
        return
    var near: float = float(lod_policy.get("near_m", 80))
    var far: float = float(lod_policy.get("far_m", 240))
    var updates: int = 0
    for node_id in marker_by_id:
        if updates >= 64:
            break
        var marker: MeshInstance3D = marker_by_id[node_id]
        var distance: float = marker.position.distance_to(camera.position)
        var level: int = 0 if distance < near else 1 if distance < far else 2
        if int(marker.get_meta("lod", -1)) == level:
            continue
        var path := "res://game/frontier/assets/" + str(node_id) + "_lod" + str(level) + ".obj"
        if ResourceLoader.exists(path):
            var candidate: Resource = load(path)
            if candidate is Mesh:
                marker.mesh = candidate
                marker.set_meta("lod", level)
                updates += 1

func _process(delta: float) -> void:
    lod_frame += 1
    if lod_frame % 30 == 0:
        _refresh_lod()
        _animate_original_npcs()
    if camera != null and actor != null:
        var goal := actor.position + Vector3(0, 28, 45)
        camera.position = camera.position.lerp(goal, minf(1.0,delta*3.0))
        camera.look_at(actor.position, Vector3.UP)
'''

_README = """# Original Frontier Expedition

A playable generated Godot 4 scene with original authored sky islands, caves,
underwater landmarks, portals, quest flags, collectibles and multiple paths.

Run in Godot 4. Select outgoing connections with Up/Down, press Enter to
travel, and Escape to rest at an authored safe site. Stamina, weather and
equipment may block actions. Reaching the target ends the expedition.

Godot stdout emits EXPEDITION_READY and EXPEDITION_OBSERVATION JSON records.
These are *untrusted native candidates*, not signed hardware attestations
or proof of full long-term production qualification.
"""


def _traveler_json(traveler: Traveler) -> str:
    from .game_frontier_expedition import _digest
    profile = {
        "permitted_modes": sorted(traveler.permitted_modes),
        "flags": sorted(traveler.flags),
        "equipment": sorted(traveler.equipment),
        "max_stamina": traveler.max_stamina,
        "carried_kg": traveler.carried_kg,
        "capacity_kg": traveler.capacity_kg,
        "skill": traveler.skill,
        "shelter": traveler.shelter,
    }
    return _json({
        "schema": "skeleton.game.frontier_expedition_player.v1",
        "traveler_digest": _digest(profile),
        "permitted_modes": sorted(traveler.permitted_modes),
        "flags": sorted(traveler.flags),
        "equipment": sorted(traveler.equipment),
        "max_stamina": traveler.max_stamina,
        "carried_kg": traveler.carried_kg,
        "capacity_kg": traveler.capacity_kg,
        "skill": traveler.skill,
        "shelter": traveler.shelter,
    }).decode("utf-8")


def make_expedition_autoplay(
    world: ExpeditionWorld, traveler: Traveler,
    *, destination: str | None = None,
) -> dict:
    """Use the actual source-bound simulator to author an executable native route."""
    from .game_frontier_expedition import find_route, verify_route
    if not isinstance(world, ExpeditionWorld) or not isinstance(traveler, Traveler):
        raise ExpeditionError("native autoplay needs a typed original game source")
    target = world.destinations[0] if destination is None else destination
    route = find_route(world, traveler, target)
    if len(route.edge_ids) > 4096:
        raise ExpeditionError("native autoplay requires bounded finite gameplay")
    proof = verify_route(world, traveler, route)
    if not proof["final_state"]["won"]:
        raise ExpeditionError("native candidate autoplay must terminate in victory")
    recipe = {
        "schema": "skeleton.game.expedition_autoplay.v1",
        "source_digest":world.source_digest,
        "world_digest":world.digest,
        "traveler_digest":_digest_traveler(traveler),
        "route_digest":route.digest,
        "steps":[
            {"edge_id":eid,"target":world.by_edge[eid].target}
            for eid in route.edge_ids
        ],
        "simulated_playthrough_receipt":proof["receipt_head"],
        "engine_execution_pending":True,
    }
    recipe["receipt_digest"]=sha256(_json(recipe)).hexdigest()
    return recipe


def _digest_traveler(traveler: Traveler) -> str:
    from .game_frontier_expedition import _digest
    return _digest({
        "permitted_modes": sorted(traveler.permitted_modes),
        "flags": sorted(traveler.flags),
        "equipment": sorted(traveler.equipment),
        "max_stamina": traveler.max_stamina,
        "carried_kg": traveler.carried_kg,
        "capacity_kg": traveler.capacity_kg,
        "skill": traveler.skill,
        "shelter": traveler.shelter,
    })


def emit_expedition_godot_project(
    world: ExpeditionWorld, traveler: Traveler, *,
    include_project_config: bool = True,
    include_autoplay: bool = False,
    controller_profile=None,
) -> dict[str, str]:
    """Compile executable, resource-safe Godot 4 files for an original game."""
    if not isinstance(world, ExpeditionWorld) or not isinstance(traveler, Traveler):
        raise ExpeditionError("typed source world and traveler required for native game")
    if type(include_project_config) is not bool or type(include_autoplay) is not bool:
        raise ExpeditionError("Godot project and autoplay policy must be explicit boolean")
    export = world_export(world)
    files = {
        "game/frontier/expedition.tscn": _GODOT_SCENE,
        "game/frontier/expedition.gd": _GODOT_SCRIPT,
        export["asset_path"]: export["content"],
        "game/frontier/player.json": _traveler_json(traveler),
        "game/frontier/README.md": _README,
    }
    if include_project_config:
        files["project.godot"] = _GODOT_PROJECT
    if include_autoplay:
        files["game/frontier/autoplay.json"] = _json(
            make_expedition_autoplay(world, traveler)
        ).decode("utf-8")
    if controller_profile is not None:
        from .game_frontier_expedition_controllers import (
            ControllerProfile, export_controller_profile,
        )
        if not isinstance(controller_profile, ControllerProfile):
            raise ExpeditionError("controller requires a validated source profile")
        files["game/frontier/controller.json"] = _json(
            export_controller_profile(controller_profile, world.digest)
        ).decode("utf-8")
    return files


def verify_expedition_godot_project(
    files: Mapping[str, str], world: ExpeditionWorld,
    traveler: Traveler, *, include_project_config: bool = True,
    include_autoplay: bool = False,
    controller_profile=None,
) -> dict:
    """Compare every generated game byte with independent deterministic export."""
    expected = emit_expedition_godot_project(
        world, traveler, include_project_config=include_project_config,
        include_autoplay=include_autoplay, controller_profile=controller_profile,
    )
    if (not isinstance(files, Mapping) or set(files) != set(expected)
            or any(type(files.get(path)) is not str or files[path] != content
                   for path, content in expected.items())):
        raise ExpeditionError("Godot source candidate differs from exact authored data")
    file_proofs = {
        path: sha256(text.encode("utf-8")).hexdigest()
        for path, text in sorted(expected.items())
    }
    proof = {
        "schema": "skeleton.game.expedition_native_candidate.v1",
        "world_digest": world.digest,
        "traveler_digest": sha256(_traveler_json(traveler).encode()).hexdigest(),
        "asset_count": len(expected),
        "file_hashes": file_proofs,
        "native_playthrough_verified": False,
        "authority": "authored_candidate_godot4_not_tested_on_engine",
    }
    proof["receipt_digest"] = sha256(_json(proof)).hexdigest()
    return proof


def attach_expedition_godot_project(
    existing_files: Mapping[str, str],
    world: ExpeditionWorld, traveler: Traveler,
    *, standalone: bool = False,
) -> dict[str, str]:
    """Do not silently replace an existing game, addon or native source file."""
    if not isinstance(existing_files, Mapping):
        raise ExpeditionError("existing Godot files must be a typed mapping")
    output = dict(existing_files)
    added = emit_expedition_godot_project(
        world, traveler, include_project_config=standalone,
    )
    for path, text in added.items():
        if (not isinstance(path, str) or
                PurePosixPath(path).is_absolute() or
                ".." in PurePosixPath(path).parts):
            raise ExpeditionError("unsafe generated game file path")
        if path in output and output[path] != text:
            raise ExpeditionError("existing native game source would be overwritten")
        output[path] = text
    return output
