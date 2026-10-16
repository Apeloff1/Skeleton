"""Export a data-bound Godot 4 scene atlas for the approved Director world.

This is an interactive scene/cast/quest/cutscene preview, not a faithful
compiled quest game or a claim that native rendering/playthrough was verified.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.director_atlas_export.v1"
FILES = ("project.godot", "main.tscn", "director_atlas.gd", "director_world.json")
GDSCRIPT = r'''extends Control

var world: Dictionary = {}
var scenes: Dictionary = {}
var here: String = ""
var display: VBoxContainer

func _ready() -> void:
    var source := FileAccess.get_file_as_string("res://director_world.json")
    var parsed = JSON.parse_string(source)
    if not (parsed is Dictionary):
        push_error("Invalid Director scene atlas")
        return
    world = parsed
    for scene in world.get("scenes", []):
        scenes[scene["key"]] = scene
    here = world["starting_scene"]
    var layout := VBoxContainer.new()
    layout.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(layout)
    var heading := Label.new()
    heading.text = "Original-game Director scene atlas"
    heading.add_theme_font_size_override("font_size", 25)
    layout.add_child(heading)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    layout.add_child(scroll)
    display = VBoxContainer.new()
    display.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(display)
    _render()

func _line(value: String) -> void:
    var item := Label.new()
    item.text = value
    item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    display.add_child(item)

func _navigate(target: String) -> void:
    if not scenes.has(target):
        return
    if not scenes[here].get("links", []).has(target):
        return
    here = target
    _render()

func _render() -> void:
    if not scenes.has(here):
        return
    for child in display.get_children():
        child.queue_free()
        display.remove_child(child)
    var scene: Dictionary = scenes[here]
    _line("Location: " + str(scene["title"]) + " (" + here + ")")
    _line(str(scene["setting"]))
    _line("Lighting: " + str(scene["lighting"]) + " | Weather: " + str(scene["weather"]))
    _line("Camera: " + str(scene["camera"]) + " | Audio cue: " + str(scene["music"]))
    _line("Cast: " + str(scene.get("cast", [])))
    _line("Props: " + str(scene.get("props", [])))
    _line("Connections:")
    for target in scene.get("links", []):
        var b := Button.new()
        b.text = "Travel to " + str(scenes[target]["title"])
        b.pressed.connect(_navigate.bind(str(target)))
        display.add_child(b)
    _line("Declared gameplay affordances (logic gameplay stays in Director runtime):")
    for affordance in scene.get("affordances", []):
        _line("  " + str(affordance["kind"]) + " -> " + str(affordance["target"]))
    _line("Authored cinematic cue timeline:")
    for cut in scene.get("cutscenes", []):
        _line("  " + str(cut["title"]) + " [" + str(cut["trigger"]) + "]")
        for cue in cut.get("cues", []):
            _line("    " + str(cue["at"]) + "ms " + str(cue["kind"]) + ": " + str(cue["value"]))
    _line("Quest stages requiring this scene:")
    for quest in world.get("quests", []):
        for stage in quest.get("stages", []):
            if stage.get("scene_ids", []).has(here):
                _line("  " + str(quest["name"]) + " / " + str(stage["title"]))
    _line("Preview only: no canonical quest completion, player telemetry or release certification.")
'''
SCENE = '''[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://director_atlas.gd" id="1_script"]

[node name="DirectorAtlas" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
script = ExtResource("1_script")
'''


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _parent(root: Path) -> Path:
    from skeleton.developer.game_cli import _load
    _load(root)
    base = root / "build"
    directory = base / "director_atlases"
    for path in (base, directory):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("unsafe Director atlas build directory")
    return directory


def _payload(root: Path, source: str) -> tuple[dict[str, bytes], dict[str, Any]]:
    world, source_sha = _load_world(root, source)
    # All game-authored text travels in JSON only. Never interpolate titles,
    # captions or user-controlled text into executable GDScript source.
    data = (json.dumps(world.payload(), sort_keys=True, indent=2,
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    name = world.project_id.replace("_", " ")
    name = name.replace('"', "")
    project = (f'''config_version=5

[application]
config/name="{name}"
run/main_scene="res://main.tscn"

[display]
window/size/viewport_width=1152
window/size/viewport_height=768

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
''').encode("utf-8")
    contents = {
        "project.godot": project, "main.tscn": SCENE.encode("utf-8"),
        "director_atlas.gd": GDSCRIPT.encode("utf-8"),
        "director_world.json": data,
    }
    if any(len(content) > 2 * 1024 * 1024 for content in contents.values()):
        raise ValueError("Director atlas export file exceeds its supported size")
    manifest = {
        "schema": SCHEMA, "project": world.project_id,
        "source": source, "source_sha256": source_sha,
        "director_world_sha256": world.digest,
        "files_sha256": {path: _hash(content) for path, content in sorted(contents.items())},
        "engine": "Godot 4 gl_compatibility",
        "scope": "interactive-scene-atlas-only",
        "quest_logic_implemented_in_native_preview": False,
        "native_binary_executed": False,
        "real_game_playthrough_verified": False,
        "original_visual_assets_created": False,
    }
    return contents, manifest


def export(root: Path, *, source: str, dry_run: bool = False) -> dict[str, Any]:
    contents, manifest = _payload(root, source)
    identity = manifest["source_sha256"]
    dirname = manifest["director_world_sha256"][:20]
    directory = _parent(root)
    destination = directory / dirname
    if destination.is_symlink() or destination.exists():
        raise ValueError("Director atlas for this exact world already exists")
    if dry_run:
        return {"ok": True, "action": "director-atlas-export", "dry_run": True,
                "path": str(destination), "manifest": manifest}
    directory.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".director-atlas-", dir=directory))
    try:
        for name, content in contents.items():
            (stage / name).write_bytes(content)
        (stage / "ATLAS_MANIFEST.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if _payload(root, source)[1]["source_sha256"] != identity:
            raise ValueError("Director source changed during native scene atlas export")
        os.rename(stage, destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {"ok": True, "action": "director-atlas-export", "dry_run": False,
            "path": str(destination), "manifest": manifest}


def verify(root: Path, *, source: str) -> dict[str, Any]:
    contents, manifest = _payload(root, source)
    location = _parent(root) / manifest["director_world_sha256"][:20]
    if location.is_symlink() or not location.is_dir():
        raise ValueError("Director atlas missing or unsafe")
    entries = sorted(location.iterdir())
    # Godot creates its own regular local .godot cache after opening a project.
    cache = location / ".godot"
    if cache.exists() and (cache.is_symlink() or not cache.is_dir()):
        raise ValueError("unsafe Godot atlas cache")
    entries = [p for p in entries if p.name != ".godot"]
    if set(x.name for x in entries) != {*FILES, "ATLAS_MANIFEST.json"}:
        raise ValueError("Director atlas has unexpected source files")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ValueError("unsafe Director atlas entry")
    for name, expected in contents.items():
        if (location / name).stat().st_size > 2 * 1024 * 1024:
            raise ValueError("oversized Director atlas source")
        if _hash((location / name).read_bytes()) != _hash(expected):
            raise ValueError("Director atlas generated file differs from exact project")
    stored = json.loads((location / "ATLAS_MANIFEST.json").read_text("utf-8"))
    if stored != manifest:
        raise ValueError("Director atlas manifest differs")
    return {"ok": True, "action": "director-atlas-verify",
            "path": str(location), "source_manifest_verified": True,
            "godot_binary_executed": False, "real_native_gameplay_verified": False,
            "file_count": len(FILES)}
