"""scenes.py — .tscn scene text generation for scaffolded projects.

Pure functions: spec in, scene file text out. No I/O.
Art identity: every rendered scene runs through art_identity.apply_art_pass
so materialise ships lighting + readable materials, not a bare Node2D.
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
    """Build a scaffold scene and apply the Art Director identity pass."""
    builder = SCENE_BUILDERS.get(template, empty_scene)
    raw = builder(script) if script else builder()
    try:
        from core.art_identity import apply_art_pass, critique
    except ImportError:  # pragma: no cover — package layout fallback
        try:
            from backend.core.art_identity import apply_art_pass, critique  # type: ignore
        except ImportError:
            return raw
    lit = apply_art_pass(raw, template=template)
    # Soft assert in debug: critique should pass after the pass.
    _ = critique(lit)
    return lit
