"""Native Godot 4 integration for authored Forge Studio physical gameplay.

An actual running child node executes 3D radius entry/exit, authored zone
interactions, limited signed force-field dynamics, and locally authored quest
activations. Existing expedition remains the navigation/runtime authority.
No generative scripts from model/user payload are executed: this fixed,
reviewable GDScript is determined by the typed, validated source descriptors.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_studio import (
    StudioError, StudioProject, compile_studio_gameplay_zones,
    compile_studio_gameplay_force_fields, compile_studio_native_quest_graph,
    compile_studio_project,
)

_STUDIO_RUNTIME = r'''extends Node
# Executable native companions to the canonical Forge Studio source model.
# The parent expedition remains responsible for source navigation and saves.
const ZONE_PATH = "res://game/frontier/studio_gameplay_zones.json"
const FIELD_PATH = "res://game/frontier/studio_gameplay_fields.json"
const QUEST_PATH = "res://game/frontier/studio_gameplay_quests.json"
const ENV_PATH = "res://game/frontier/studio_gameplay_environment.json"
var zones: Array = []
var fields: Array = []
var quests: Dictionary = {}
var pages: Array = []
var occupied: Dictionary = {}
var active_quests: Dictionary = {}
var linear_velocity: Vector3 = Vector3.ZERO
var source_digest: String = ""
var last_anchor_id: String = ""
var game_events: Array = []
const MAX_EVENTS = 2048

func _read(path: String) -> Dictionary:
    if not FileAccess.file_exists(path):
        push_error("Studio gameplay source not found " + path)
        return {}
    var data: String = FileAccess.get_file_as_string(path)
    if data.length() > 4000000:
        push_error("Studio gameplay input exceeded budget")
        return {}
    var parsed = JSON.parse_string(data)
    if typeof(parsed) != TYPE_DICTIONARY:
        push_error("Studio gameplay source not an object")
        return {}
    return parsed

func _ready() -> void:
    var zone_data: Dictionary = _read(ZONE_PATH)
    var field_data: Dictionary = _read(FIELD_PATH)
    var quest_data: Dictionary = _read(QUEST_PATH)
    var env_data: Dictionary = _read(ENV_PATH)
    source_digest = str(zone_data.get("studio_sha256", ""))
    if (source_digest.length() != 64
            or source_digest != str(field_data.get("studio_sha256", ""))
            or source_digest != str(quest_data.get("studio_sha256", ""))
            or source_digest != str(env_data.get("studio_sha256", ""))):
        push_error("Studio gameplay descriptor lineage mismatch")
        return
    zones = zone_data.get("zones", [])
    fields = field_data.get("fields", [])
    quests = quest_data
    pages = env_data.get("pages", [])
    if (typeof(zones) != TYPE_ARRAY or zones.size() > 64
            or typeof(fields) != TYPE_ARRAY or fields.size() > 64
            or typeof(pages) != TYPE_ARRAY or pages.size() > 4096):
        push_error("Studio gameplay source exceeded typed capacity")
        zones = []
        fields = []
        pages = []
        return
    print("STUDIO_GAMEPLAY_READY " + source_digest)

func _center(row: Dictionary) -> Vector3:
    var xyz: Array = row.get("center_xyz_m", [0.0, 0.0, 0.0])
    if xyz.size() != 3:
        return Vector3.ZERO
    return Vector3(float(xyz[0]), float(xyz[1]), float(xyz[2]))

func _event(kind: String, name: String, target: String) -> void:
    var record := {"kind": kind, "name": name, "target": target}
    game_events.append(record)
    if game_events.size() > MAX_EVENTS:
        game_events.pop_front()
    print("STUDIO_GAMEPLAY_EVENT " + JSON.stringify(record))
    var game = get_parent()
    if kind == "start_quest":
        active_quests[target] = true
        game.flags[target] = true
    elif kind == "show_dialogue":
        if game.hud != null:
            game.hud.text = target
    elif kind == "spatial_audio":
        if game.sound_player != null:
            game.sound_player.play()

func _zone_tick(position: Vector3) -> void:
    for zone in zones:
        if typeof(zone) != TYPE_DICTIONARY:
            continue
        var name: String = str(zone.get("id", ""))
        var radius: float = float(zone.get("radius_m", 0.0))
        if radius < 0.1:
            continue
        var current: bool = position.distance_squared_to(_center(zone)) <= radius * radius
        var previous: bool = bool(occupied.get(name, false))
        if current and not previous:
            occupied[name] = true
            _event(str(zone.get("action_kind", "show_dialogue")),
                   name, str(zone.get("event_value", "")))
        elif not current and previous:
            occupied.erase(name)
            _event("zone_exit", name, str(zone.get("event_page_id", "")))

func _force_tick(position: Vector3, delta: float) -> Vector3:
    var acceleration := Vector3.ZERO
    for field in fields:
        if typeof(field) != TYPE_DICTIONARY:
            continue
        var center: Vector3 = _center(field)
        var radius: float = float(field.get("radius_m", 0.0))
        if radius <= 0.0:
            continue
        var relative: Vector3 = position - center
        var taper: float = maxf(0.0, 1.0 - relative.length_squared() / (radius * radius))
        var size: float = minf(25.0, float(field.get("acceleration_mps2", 0.0))) * taper
        match str(field.get("kind", "")):
            "updraft":
                acceleration.z += size
            "downdraft":
                acceleration.z -= size
            "eastward_current":
                acceleration.x += size
            "vortex":
                var horizontal: Vector2 = Vector2(relative.x, relative.y)
                if horizontal.length_squared() > 0.000001:
                    var swirl: Vector2 = Vector2(-horizontal.y, horizontal.x).normalized() * size
                    acceleration.x += swirl.x
                    acceleration.y += swirl.y
    linear_velocity = (linear_velocity + acceleration.limit_length(50.0) * delta) * maxf(0.0, 1.0 - delta * 2.5)
    linear_velocity = linear_velocity.limit_length(12.0)
    return linear_velocity * delta

func _environment_tick(position: Vector3) -> void:
    # Only physically measured in-game altitude is available in this
    # standalone source runtime. Unknown sensors are never fabricated.
    var measured_altitude: float = position.z
    for page in pages:
        if typeof(page) != TYPE_DICTIONARY or not bool(page.get("enabled", false)):
            continue
        var conditions: Array = page.get("conditions", [])
        var eligible: bool = conditions.size() > 0
        for condition in conditions:
            if str(condition.get("signal", "")) != "altitude_m":
                eligible = false
                break
            var threshold: float = float(condition.get("threshold", 0))
            match str(condition.get("comparison", "")):
                "above":
                    eligible = eligible and measured_altitude > threshold
                "below":
                    eligible = eligible and measured_altitude < threshold
                "at_least":
                    eligible = eligible and measured_altitude >= threshold
                "at_most":
                    eligible = eligible and measured_altitude <= threshold
                _:
                    eligible = false
        if not eligible:
            continue
        var page_id: String = str(page.get("id", ""))
        if bool(occupied.get("environment:" + page_id, false)):
            continue
        var required = page.get("flags", [])
        var game = get_parent()
        for rule in required:
            if rule.size() != 2 or bool(game.flags.get(str(rule[0]), false)) != bool(rule[1]):
                eligible = false
        if not eligible:
            continue
        occupied["environment:" + page_id] = true
        for action in page.get("actions", []):
            if str(action.get("kind", "")) == "set_flag":
                game.flags[str(action.get("target", ""))] = str(action.get("value", "")) == "true"
            elif str(action.get("kind", "")) == "start_quest":
                _event("start_quest", page_id, str(action.get("target", "")))

func _physics_process(delta: float) -> void:
    if source_digest == "":
        return
    var game = get_parent()
    if game == null or game.actor == null or game.failed or game.won:
        return
    var id: String = str(game.current_id)
    if id != last_anchor_id:
        linear_velocity = Vector3.ZERO
        last_anchor_id = id
    var position: Vector3 = game.actor.global_position
    _zone_tick(position)
    _environment_tick(position)
    var displacement: Vector3 = _force_tick(position, minf(delta, 0.05))
    game.actor.position += displacement
'''
def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode()).hexdigest()


def add_studio_native_gameplay(project: StudioProject,
                              files: Mapping[str, str]) -> dict[str, str]:
    """Attach deterministic runnable Godot mechanics with source-bound descriptors."""
    if not isinstance(project, StudioProject) or not isinstance(files, Mapping):
        raise StudioError("native mechanics require authored Studio and emitted Godot files")
    original = dict(files)
    if not (project.native_trigger_volumes or project.native_gameplay_force_fields
            or project.native_quests or project.environmental_pages):
        return original
    scene_path = "game/frontier/expedition.tscn"
    if scene_path not in original or "game/frontier/studio_gameplay.gd" in original:
        raise StudioError("native original expedition scene unavailable or conflicting")
    source_sha256 = compile_studio_project(project)["content_sha256"]
    zones = compile_studio_gameplay_zones(project)
    fields = compile_studio_gameplay_force_fields(project)
    quests = compile_studio_native_quest_graph(project)
    values = {event.event_id: event.value for event in project.events}
    for zone in zones["zones"]:
        zone["event_value"] = values[zone["event_page_id"]]
    packages = {
        "game/frontier/studio_gameplay_zones.json": {
            "schema": "skeleton.forge.godot_gameplay_zones.v1",
            "studio_sha256": source_sha256, "zones": zones["zones"],
        },
        "game/frontier/studio_gameplay_fields.json": {
            "schema": "skeleton.forge.godot_gameplay_fields.v1",
            "studio_sha256": source_sha256, "fields": fields["fields"],
        },
        "game/frontier/studio_gameplay_quests.json": {
            **quests, "studio_sha256": source_sha256,
        },
        "game/frontier/studio_gameplay_environment.json": {
            "schema": "skeleton.forge.godot_gameplay_environment.v1",
            "studio_sha256": source_sha256,
            "pages": project.authored_manifest()["environmental_pages"],
        },
    }
    scene = original[scene_path]
    ext = '[ext_resource type="Script" path="res://game/frontier/expedition.gd" id="1"]'
    if ext not in scene or "[gd_scene load_steps=2 format=3]" not in scene:
        raise StudioError("existing Godot scene does not have expected editor markers")
    scene = scene.replace("[gd_scene load_steps=2 format=3]",
                          "[gd_scene load_steps=3 format=3]", 1)
    scene = scene.replace(ext, ext +
        '\n[ext_resource type="Script" path="res://game/frontier/studio_gameplay.gd" id="2"]', 1)
    scene += '\n[node name="StudioGameplay" type="Node" parent="."]\nscript = ExtResource("2")\n'
    original[scene_path] = scene
    original["game/frontier/studio_gameplay.gd"] = _STUDIO_RUNTIME
    for path, value in packages.items():
        if path in original:
            raise StudioError("cannot overwrite existing native gameplay source")
        original[path] = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False, ensure_ascii=False)
    return original
