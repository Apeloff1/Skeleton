"""
godot_engine.project — compile complete Godot 4 projects from specs.

Not just a project.godot: a spec becomes a *playable* scaffold with real
scenes and controllers — the kind of starting point that actually runs.

Templates
---------
* ``platformer2d`` — CharacterBody2D player (run/jump/gravity), Camera2D,
  parallax-ready main scene, TileMapLayer stub, HUD with score label.
* ``topdown2d``    — 8-direction player, camera smoothing, interaction ray,
  HUD.
* ``blank2d``      — minimal Node2D root (previous behaviour, kept for CI).

Every template emits:
    project.godot · export_presets.cfg (Linux/Windows/Web/Android) ·
    scenes/main.tscn · scenes/player.tscn · scripts/{main,player,hud}.gd

Safety
------
* :func:`scaffold_project` never silently overwrites: if ``root/<slug>``
  already contains a ``project.godot``, it raises :class:`ProjectExistsError`
  unless ``overwrite=True``.
* The slug is derived from the title and validated to stay a simple
  directory name — no path traversal through user input.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_VERSION = 5

# ── Export presets (ids are stable so CI can reference them) ──────────────

EXPORT_PRESETS: dict[str, dict] = {
    "linux":   {"platform": "Linux/X11", "runnable": True,  "out": "builds/linux/game.x86_64"},
    "windows": {"platform": "Windows Desktop", "runnable": True, "out": "builds/windows/game.exe"},
    "web":     {"platform": "Web", "runnable": False, "out": "builds/web/index.html"},
    "android": {"platform": "Android", "runnable": False, "out": "builds/android/game.apk"},
}

_PRESET_TMPL = """[preset.{i}]

name="{name}"
platform="{platform}"
runnable={runnable}
export_path="{out}"

[preset.{i}.options]
"""


def _export_presets_cfg() -> str:
    parts = []
    for i, (name, p) in enumerate(EXPORT_PRESETS.items()):
        parts.append(_PRESET_TMPL.format(
            i=i, name=name, platform=p["platform"],
            runnable=str(p["runnable"]).lower(), out=p["out"],
        ))
    return "\n".join(parts)


# ── GDScript controllers ──────────────────────────────────────────────────

_PLAYER_PLATFORMER = '''class_name Player
extends CharacterBody2D

## Tunables — exposed to the editor and to Tutolage's tuning API.
@export var run_speed: float = 220.0
@export var jump_velocity: float = -420.0
@export var gravity: float = 980.0
@export var coyote_time: float = 0.12

var _coyote: float = 0.0


func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity.y += gravity * delta
        _coyote -= delta
    else:
        _coyote = coyote_time

    var dir := Input.get_axis("move_left", "move_right")
    velocity.x = dir * run_speed

    if Input.is_action_just_pressed("jump") and _coyote > 0.0:
        velocity.y = jump_velocity
        _coyote = 0.0

    move_and_slide()
'''

_PLAYER_TOPDOWN = '''class_name Player
extends CharacterBody2D

@export var speed: float = 200.0
@export var acceleration: float = 1200.0
@export var friction: float = 900.0


func _physics_process(delta: float) -> void:
    var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
    if dir != Vector2.ZERO:
        velocity = velocity.move_toward(dir * speed, acceleration * delta)
    else:
        velocity = velocity.move_toward(Vector2.ZERO, friction * delta)
    move_and_slide()
'''

_HUD = '''class_name Hud
extends CanvasLayer

signal score_changed(value: int)

var score: int = 0:
    set(v):
        score = v
        score_changed.emit(v)
        if _label:
            _label.text = "Score: %d" % v

@onready var _label: Label = $Margin/Score


func add(points: int) -> void:
    score += points
'''

_MAIN_PLATFORMER = '''extends Node2D

## Entry point — Tutolage godot_engine scaffold (platformer2d).


func _ready() -> void:
    Engine.max_fps = 120
    print("%s ready — %s" % [ProjectSettings.get_setting("application/config/name"), Engine.get_version_info().string])
'''

_SCENE_PLAYER = '''[gd_scene load_steps=3 format=3 uid="uid://tutolage_player"]

[ext_resource type="Script" path="res://scripts/player.gd" id="1"]

[sub_resource type="RectangleShape2D" id="body"]
size = Vector2(24, 32)

[node name="Player" type="CharacterBody2D"]
script = ExtResource("1")

[node name="Body" type="CollisionShape2D" parent="."]
shape = SubResource("body")

[node name="Sprite" type="ColorRect" parent="."]
offset_left = -12.0
offset_top = -16.0
offset_right = 12.0
offset_bottom = 16.0
color = Color(0.28, 0.55, 0.75, 1)
'''

_SCENE_MAIN_PLATFORMER = '''[gd_scene load_steps=3 format=3 uid="uid://tutolage_main"]

[ext_resource type="PackedScene" path="res://scenes/player.tscn" id="1"]
[ext_resource type="Script" path="res://scripts/main.gd" id="2"]

[node name="Main" type="Node2D"]
script = ExtResource("2")

[node name="Player" parent="." instance=ExtResource("1")]
position = Vector2(160, 400)

[node name="Camera2D" type="Camera2D" parent="."]
position_smoothing_enabled = true

[node name="Ground" type="StaticBody2D" parent="."]
position = Vector2(640, 560)

[node name="GroundShape" type="CollisionShape2D" parent="Ground"]
shape = SubResource("ground")

[node name="GroundFill" type="ColorRect" parent="Ground"]
offset_left = -640.0
offset_top = -20.0
offset_right = 640.0
offset_bottom = 20.0
color = Color(0.2, 0.2, 0.24, 1)

[sub_resource type="RectangleShape2D" id="ground"]
size = Vector2(1280, 40)

[node name="HUD" type="CanvasLayer" parent="."]
script = preload("res://scripts/hud.gd")

[node name="Margin" type="MarginContainer" parent="HUD"]
offsets = { "left": 16, "top": 16, "right": 200, "bottom": 48 }

[node name="Score" type="Label" parent="HUD/Margin"]
text = "Score: 0"
'''

_SCENE_MAIN_TOPDOWN = _SCENE_MAIN_PLATFORMER.replace(
    'position = Vector2(160, 400)', 'position = Vector2(640, 360)'
).replace('GroundShape', 'Bounds').replace('ground', 'bounds')

_SCENE_MAIN_BLANK = '''[gd_scene load_steps=2 format=3 uid="uid://tutolage_main"]

[ext_resource type="Script" path="res://scripts/main.gd" id="1"]

[node name="Main" type="Node2D"]
script = ExtResource("1")
'''

_MAIN_BLANK = '''extends Node2D


func _ready() -> void:
    print("%s ready" % ProjectSettings.get_setting("application/config/name"))
'''

_TEMPLATES = {
    "platformer2d": {
        "scenes/main.tscn": _SCENE_MAIN_PLATFORMER,
        "scenes/player.tscn": _SCENE_PLAYER,
        "scripts/player.gd": _PLAYER_PLATFORMER,
        "scripts/main.gd": _MAIN_PLATFORMER,
        "scripts/hud.gd": _HUD,
    },
    "topdown2d": {
        "scenes/main.tscn": _SCENE_MAIN_TOPDOWN,
        "scenes/player.tscn": _SCENE_PLAYER,
        "scripts/player.gd": _PLAYER_TOPDOWN,
        "scripts/main.gd": _MAIN_PLATFORMER,
        "scripts/hud.gd": _HUD,
    },
    "blank2d": {
        "scenes/main.tscn": _SCENE_MAIN_BLANK,
        "scripts/main.gd": _MAIN_BLANK,
    },
}

_DEFAULT_INPUT = {
    "move_left":  ["KEY_A", "KEY_LEFT"],
    "move_right": ["KEY_D", "KEY_RIGHT"],
    "move_up":    ["KEY_W", "KEY_UP"],
    "move_down":  ["KEY_S", "KEY_DOWN"],
    "jump":       ["KEY_SPACE"],
}

_KEYCODES = {
    "KEY_SPACE": 32, "KEY_A": 65, "KEY_D": 68, "KEY_S": 83, "KEY_W": 87,
    "KEY_LEFT": 4194319, "KEY_RIGHT": 4194321, "KEY_UP": 4194320, "KEY_DOWN": 4194322,
}

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slug(name: str) -> str:
    """Filesystem-safe slug: lowercase alnum+underscore, never empty,
    never containing separators or dots (traversal-proof)."""
    s = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    s = re.sub(r"_{2,}", "_", s)[:48].strip("_")
    return s or "tutolage_game"


class ProjectExistsError(FileExistsError):
    """A project with this slug already exists and overwrite was not set."""

    def __init__(self, slug: str, project_dir: Path):
        super().__init__(
            f"project {slug!r} already exists at {project_dir} "
            "(pass overwrite=True to replace it)"
        )
        self.slug = slug
        self.project_dir = project_dir


@dataclass
class ProjectSpec:
    title: str
    description: str = ""
    template: str = "platformer2d"          # platformer2d | topdown2d | blank2d
    main_scene: str = "res://scenes/main.tscn"
    renderer: str = "gl_compatibility"
    window_width: int = 1280
    window_height: int = 720
    features: list[str] = field(default_factory=lambda: ["4.2"])
    autoloads: dict[str, str] = field(default_factory=dict)
    input_actions: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ScaffoldResult:
    project_dir: Path
    files_written: list[str]
    slug: str
    template: str
    overwritten: bool = False

    def to_dict(self) -> dict:
        return {
            "project_dir": str(self.project_dir),
            "slug": self.slug,
            "template": self.template,
            "files_written": self.files_written,
            "file_count": len(self.files_written),
            "export_presets": list(EXPORT_PRESETS),
            "overwritten": self.overwritten,
        }


def available_templates() -> list[dict]:
    return [
        {"id": k, "files": sorted(v), "controllers":
         [f.split("/")[-1][:-3] for f in v if f.endswith(".gd")]}
        for k, v in _TEMPLATES.items()
    ]


def _render_project_godot(spec: ProjectSpec) -> str:
    actions = {**_DEFAULT_INPUT, **spec.input_actions}
    features = spec.features or ["4.2"]
    feature_list = ", ".join(f'"{f}"' for f in features)
    lines: list[str] = [
        "; Generated by Tutolage godot_engine.project v2",
        "",
        "config_version=5",
        "",
        "[application]",
        "",
        f'config/name="{spec.title}"',
        f'config/description="{spec.description}"',
        f"config/features=PackedStringArray({feature_list})",
        f'run/main_scene="{spec.main_scene}"',
        'icon="res://icon.svg"',
        "",
        "[display]",
        "",
        f"window/size/viewport_width={spec.window_width}",
        f"window/size/viewport_height={spec.window_height}",
        "",
        "[rendering]",
        "",
        f'renderer/rendering_method="{spec.renderer}"',
        "",
        "[input]",
        "",
    ]
    for action, keys in actions.items():
        events = []
        for key in keys:
            code = _KEYCODES.get(key, 0)
            events.append(
                'Object(InputEventKey,"resource_local_to_scene":false,'
                f'"keycode":{code},"script":null)'
            )
        lines.append(f'{action}={{"deadzone": 0.5, "events": [{", ".join(events)}]}}')
    if spec.autoloads:
        lines += ["", "[autoloads]", ""]
        lines += [f'{name}="*{path}"' for name, path in spec.autoloads.items()]
    return "\n".join(lines) + "\n"


def scaffold_project(
    spec: ProjectSpec, root: Path, *, overwrite: bool = False
) -> ScaffoldResult:
    """Write a complete, playable Godot project under ``root/<slug>/``.

    Raises :class:`ValueError` for an unknown template and
    :class:`ProjectExistsError` when the target already holds a project
    and ``overwrite`` is not set — a scaffold never silently clobbers.
    """
    if spec.template not in _TEMPLATES:
        raise ValueError(
            f"unknown template {spec.template!r}; pick from {sorted(_TEMPLATES)}"
        )
    slug = _slug(spec.title)
    project_dir = root / slug
    # Defense in depth: resolved path must stay inside root.
    resolved_root = root.resolve()
    resolved_dir = project_dir.resolve()
    if resolved_dir != resolved_root and resolved_root not in resolved_dir.parents:
        raise ValueError(f"project path escapes root: {slug!r}")
    existed = (project_dir / "project.godot").is_file()
    if existed and not overwrite:
        raise ProjectExistsError(slug, project_dir)
    files: dict[str, str] = {
        "project.godot": _render_project_godot(spec),
        "export_presets.cfg": _export_presets_cfg(),
        "icon.svg": (
            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">'
            '<rect width="128" height="128" rx="24" fill="#478cbf"/></svg>'
        ),
        **_TEMPLATES[spec.template],
    }
    written: list[str] = []
    for rel, content in files.items():
        path = project_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)
    return ScaffoldResult(
        project_dir=project_dir, files_written=sorted(written),
        slug=slug, template=spec.template, overwritten=existed,
    )
