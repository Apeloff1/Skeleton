"""scenes.py — .tscn scene text generation for scaffolded projects.

Pure functions: spec in, scene file text out. No I/O.
"""
from __future__ import annotations

HEADER = '[gd_scene load_steps={steps} format=3 uid="uid://{uid}"]'


def _ext_resource(idx: int, path: str) -> str:
    return f'[ext_resource type="Script" path="{path}" id="{idx}"]'


def platformer_scene(script: str = "res://scripts/player.gd") -> str:
    return "\n".join([
        HEADER.format(steps=2, uid="tutolage_platformer"),
        "",
        _ext_resource(1, script),
        "",
        '[node name="Main" type="Node2D"]',
        "",
        '[node name="Player" type="CharacterBody2D" parent="."]',
        'script = ExtResource("1")',
        "",
        '[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]',
        "",
        '[node name="Camera2D" type="Camera2D" parent="Player"]',
        "position_smoothing_enabled = true",
        "",
        '[node name="Ground" type="StaticBody2D" parent="."]',
        "position = Vector2(0, 300)",
        "",
        '[node name="CollisionShape2D" type="CollisionShape2D" parent="Ground"]',
        "",
    ]) + "\n"


def topdown_scene(script: str = "res://scripts/player.gd") -> str:
    return "\n".join([
        HEADER.format(steps=2, uid="tutolage_topdown"),
        "",
        _ext_resource(1, script),
        "",
        '[node name="Main" type="Node2D"]',
        "",
        '[node name="Player" type="CharacterBody2D" parent="."]',
        'script = ExtResource("1")',
        "",
        '[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]',
        "",
        '[node name="Camera2D" type="Camera2D" parent="Player"]',
        "zoom = Vector2(1.2, 1.2)",
        "",
    ]) + "\n"


def empty_scene(script: str = "res://scripts/main.gd") -> str:
    return "\n".join([
        HEADER.format(steps=2, uid="tutolage_empty"),
        "",
        _ext_resource(1, script),
        "",
        '[node name="Main" type="Node2D"]',
        'script = ExtResource("1")',
        "",
        '[node name="Camera2D" type="Camera2D" parent="."]',
        "",
    ]) + "\n"


SCENE_BUILDERS = {
    "platformer": platformer_scene,
    "topdown": topdown_scene,
    "empty": empty_scene,
}


def render_scene(template: str, script: str | None = None) -> str:
    builder = SCENE_BUILDERS.get(template, empty_scene)
    return builder(script) if script else builder()
