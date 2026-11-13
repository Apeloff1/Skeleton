"""Godot world-to-archetype playable gateway, bounded and source-verifiable.

The three existing playable archetypes previously shipped as Godot sidecar
scenes only: the built game's main scene had no discoverable way to start
them. This additive, opt-in autoload exposes a touch/keyboard accessible
button in the actual running world and a return control in the prototype.

The portal is disabled when Godot is headless, so CI's independent scene
autopilot and default-world playtest remain unaffected. It never downloads
assets or executes arbitrary scripts. No default project changes occur
unless playable_content was explicitly requested.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

from skeleton.forge.archetype_content import content_archetypes

SCRIPT_PATH = "scripts/autoloads/playable_portal.gd"
AUTOLOAD_ENTRY = 'PlayablePortal="*res://scripts/autoloads/playable_portal.gd"\n'
INPUT_ENTRY = 'InputBind="*res://scripts/autoloads/input_bind.gd"\n'
WORLD_SCENE = "res://scenes/levels/run_level.tscn"
SCHEMA = "skeleton.forge.playable_portal.v1"

_GDSCRIPT = r'''extends CanvasLayer
## Forge's explicit playable prototype navigation.
## The source scene is an admitted native archetype, never arbitrary input.
const WORLD_SCENE: String = "res://scenes/levels/run_level.tscn"
const PROTOTYPE_SCENE: String = "res://scenes/archetypes/__NAME__/main.tscn"

var _switching: bool = false
var _button: Button = null

func _ready() -> void:
	layer = 24
	# A CI headless scene boot already targets the archetype directly.
	if DisplayServer.get_name() == "headless":
		return
	_button = Button.new()
	_button.name = "ForgePlayablePrototype"
	_button.position = Vector2(16.0, 156.0)
	_button.custom_minimum_size = Vector2(272.0, 52.0)
	_button.focus_mode = Control.FOCUS_ALL
	_button.mouse_filter = Control.MOUSE_FILTER_STOP
	_button.tooltip_text = "Launch an original playable prototype or return to the Forge world"
	add_child(_button)
	_button.pressed.connect(_on_button_pressed)
	get_tree().scene_changed.connect(_on_scene_changed)
	call_deferred("_refresh_button")

func _on_scene_changed(_scene: Node) -> void:
	_switching = false
	_refresh_button()

func _refresh_button() -> void:
	if _button == null:
		return
	var current: Node = get_tree().current_scene
	if current == null:
		_button.visible = false
		return
	var active: String = current.scene_file_path
	var in_prototype: bool = active == PROTOTYPE_SCENE
	_button.visible = active == WORLD_SCENE or in_prototype
	_button.disabled = _switching
	_button.text = "Return to Forge world" if in_prototype else "Play __TITLE__ prototype"

func _on_button_pressed() -> void:
	if _switching:
		return
	var current: Node = get_tree().current_scene
	if current == null:
		return
	var active: String = current.scene_file_path
	if active != WORLD_SCENE and active != PROTOTYPE_SCENE:
		return
	var destination: String = WORLD_SCENE if active == PROTOTYPE_SCENE else PROTOTYPE_SCENE
	_switching = true
	_button.disabled = true
	var status: Error = get_tree().change_scene_to_file(destination)
	if status != OK:
		_switching = false
		_refresh_button()
		push_error("Forge playable prototype scene transition failed")
'''


class PlayablePortalError(ValueError):
    """Unrecognized archetype, source conflict, or malformed emitted project."""


def _script(archetype: str) -> str:
    # The ID is chosen from a closed tuple of imported original archetypes.
    if type(archetype) is not str or archetype not in content_archetypes():
        raise PlayablePortalError("unknown original playable archetype")
    return _GDSCRIPT.replace("__NAME__", archetype).replace(
        "__TITLE__", archetype.replace("_", " ").title(),
    )


def attach_playable_portal(
    files: Mapping[str, str], archetype: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Attach one persistent in-game scene switcher; preserve caller files."""
    if not isinstance(files, Mapping):
        raise PlayablePortalError("Godot file map is required")
    script = _script(archetype)
    scene = f"scenes/archetypes/{archetype}/main.tscn"
    project = files.get("project.godot")
    if (
        type(project) is not str
        or project.count(INPUT_ENTRY) != 1
        or f'run/main_scene="{WORLD_SCENE}"' not in project
        or "PlayablePortal=" in project
        or SCRIPT_PATH in files
        or scene not in files
        or "scenes/levels/run_level.tscn" not in files
    ):
        raise PlayablePortalError("playable portal project or scene contract is invalid")
    out = dict(files)
    out["project.godot"] = project.replace(INPUT_ENTRY, INPUT_ENTRY + AUTOLOAD_ENTRY)
    out[SCRIPT_PATH] = script
    return out, {
        "schema": SCHEMA,
        "autoload": "PlayablePortal",
        "script": SCRIPT_PATH,
        "scene": scene,
        "world": "scenes/levels/run_level.tscn",
        "source_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
        "return_supported": True,
        "headless_inert": True,
    }


def verify_playable_portal(files: Mapping[str, str], archetype: str) -> bool:
    """Verify exact generated gateway, both scenes and the autoload binding."""
    try:
        scene = f"scenes/archetypes/{archetype}/main.tscn"
        project = files["project.godot"]
        return (
            type(project) is str
            and project.count(INPUT_ENTRY) == 1
            and project.count(AUTOLOAD_ENTRY) == 1
            and project.count("PlayablePortal=") == 1
            and f'run/main_scene="{WORLD_SCENE}"' in project
            and scene in files
            and "scenes/levels/run_level.tscn" in files
            and files[SCRIPT_PATH] == _script(archetype)
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


__all__ = [
    "SCHEMA", "SCRIPT_PATH", "AUTOLOAD_ENTRY", "PlayablePortalError",
    "attach_playable_portal", "verify_playable_portal",
]
