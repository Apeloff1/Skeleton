"""Emit combat VFX catalog cues into Godot 4 scene/script text.

Pure functions: :class:`~core.vfx_combat_catalog.CombatCue` in, Godot 4
``.tscn`` / ``.gd`` text out. No I/O. Colours are palette indices
(``Color8(i, i, i)``) — no invented RGB — so HUD and renderer share
:data:`~core.vfx_combat_catalog.DANGER_RAMP` tiers by name.
"""
from __future__ import annotations

from core.eras import get_era
from core.vfx_combat_catalog import CombatCue, cue_for, telegraph_for

SCRIPT_PATH = "res://scripts/combat_vfx.gd"
SCENE_PATH = "res://scenes/combat_vfx.tscn"
NODE_NAME = "CombatVfx"

_SHAPE_NODES: dict[str, str] = {
    "circle": "Circle",
    "cone": "Cone",
    "line": "Line",
    "ring": "Ring",
}


def is_pixel_era(era_key: str) -> bool:
    return get_era(era_key)["max_poly"] == 0


def palette_color(index: int, colors: int) -> str:
    """Map a cue colour slot to a Godot ``Color8`` without inventing RGB.

    Slot ``i`` of ``colors`` becomes a grey ramp ``Color8(v, v, v)`` where
    ``v`` steps from 64 to 255. Semantic danger still lives on
    ``metadata/severity``; renderers replace the grey with the era palette.
    """
    if colors <= 0:
        raise ValueError("colors must be positive")
    i = max(0, min(colors - 1, int(index)))
    if colors == 1:
        v = 255
    else:
        v = 64 + round(191 * i / (colors - 1))
    return f"Color8({v}, {v}, {v}, 255)"


def combat_vfx_script() -> str:
    """GDScript that plays catalog cues, gates on hit_frame, stamps severity."""
    return '''class_name CombatVfx
extends Node2D

## Plays combat cues from Tutolage's VFX catalog. Colour indices come from
## the cue; severity is metadata so HUD can share DANGER_RAMP tiers.

@export var hit_frame: int = -1
@export var severity: String = ""
@export var shape: String = "cone"
@export var duration_ms: int = 450
@export var particle_count: int = 16
@export var trauma: float = 0.0

var _elapsed_ms: float = 0.0
var _playing: bool = false
var _pending_hit_frame: int = -1


func play_cue(cue_shape: String, duration: int, particles: int, cue_trauma: float,
        cue_severity: String = "", cue_hit_frame: int = -1) -> void:
    shape = cue_shape
    duration_ms = duration
    particle_count = particles
    trauma = cue_trauma
    severity = cue_severity
    hit_frame = cue_hit_frame
    _pending_hit_frame = cue_hit_frame
    _elapsed_ms = 0.0
    _playing = cue_hit_frame < 0
    visible = _playing
    _apply_shape()
    if _playing:
        _emit_particles()


func play_telegraph(damage: float, max_health: float, era_key: String = "modern",
        cue_shape: String = "", cue_hit_frame: int = -1) -> void:
    ## Stretches lead time with damage share; colour slots come from DANGER_RAMP.
    var lead := int(clamp(250.0 + 650.0 * (damage / max(max_health, 0.001)), 250.0, 1500.0))
    var share := clamp(damage / max(max_health, 0.001), 0.0, 1.0)
    var tier := "low"
    var slots := 1
    if share > 0.85:
        tier = "lethal"
        slots = 4
    elif share > 0.5:
        tier = "high"
        slots = 3
    elif share > 0.25:
        tier = "moderate"
        slots = 2
    var chosen := cue_shape if cue_shape != "" else shape
    # Telegraphs must be visible before impact; the separate hit burst
    # remains armed until the animation timeline reaches its contact frame.
    play_cue(chosen, lead, 16 * slots, 0.0, tier, -1)
    hit_frame = cue_hit_frame
    _pending_hit_frame = cue_hit_frame


func notify_hit_frame(frame: int) -> void:
    if _pending_hit_frame >= 0 and frame == _pending_hit_frame:
        _pending_hit_frame = -1
        _playing = true
        _elapsed_ms = 0.0
        visible = true
        _emit_particles()


func _process(delta: float) -> void:
    if not _playing:
        return
    _elapsed_ms += delta * 1000.0
    if _elapsed_ms >= duration_ms:
        _playing = false
        visible = false


func _apply_shape() -> void:
    for child in get_children():
        if child is Node2D:
            child.visible = child.name.to_lower().begins_with(shape.to_lower())


func _emit_particles() -> void:
    # Shape nodes own the actual GPUParticles2D grandchildren. Emitting
    # only direct children silently produced no particles at runtime.
    for child in get_children():
        if child is Node2D and child.visible:
            for emitter in child.get_children():
                if emitter is GPUParticles2D:
                    emitter.amount = particle_count
                    emitter.restart()
                    emitter.emitting = true
'''


def combat_vfx_scene(era_key: str | None = None, *, include_pixel_sprites: bool | None = None) -> str:
    """``.tscn`` with shape markers, GPUParticles2D (or Sprite2D for pixel eras), and script."""
    era = get_era(era_key)
    pixel = is_pixel_era(era["key"]) if include_pixel_sprites is None else include_pixel_sprites
    cue = cue_for(era["key"], "telegraph")
    shape = cue.shape or "cone"
    severity = cue.severity or "moderate"
    colors = cue.colors
    particles = cue.particles
    duration = cue.lead_ms or cue.duration_ms
    trauma = cue.trauma

    nodes: list[str] = [
        '[gd_scene load_steps=4 format=3 uid="uid://tutolage_combat_vfx"]',
        "",
        f'[ext_resource type="Script" path="{SCRIPT_PATH}" id="1"]',
        "",
        '[node name="CombatVfx" type="Node2D"]',
        'script = ExtResource("1")',
        f'metadata/era = "{era["key"]}"',
        f'metadata/severity = "{severity}"',
        f'metadata/shape = "{shape}"',
        f"metadata/duration_ms = {duration}",
        f"metadata/particles = {particles}",
        f"metadata/trauma = {trauma}",
        f"metadata/colors = {colors}",
        f"metadata/hit_frame = {cue.hit_frame if cue.hit_frame is not None else -1}",
        "",
    ]

    for shape_name in ("Circle", "Cone", "Line", "Ring"):
        vis = "true" if shape_name.lower() == shape else "false"
        color = palette_color(0, colors)
        nodes += [
            f'[node name="{shape_name}" type="Node2D" parent="CombatVfx"]',
            f"visible = {vis}",
            "",
        ]
        if pixel:
            nodes += [
                f'[node name="Sprite" type="Sprite2D" parent="CombatVfx/{shape_name}"]',
                f"modulate = {color}",
                "",
            ]
        else:
            nodes += [
                f'[node name="Particles" type="GPUParticles2D" parent="CombatVfx/{shape_name}"]',
                f"amount = {particles}",
                "emitting = false",
                f"modulate = {color}",
                "",
            ]

    return "\n".join(nodes)


def combat_vfx_node_block(
    *,
    parent: str = ".",
    era_key: str | None = "modern",
    position: tuple[float, float] = (0.0, 0.0),
) -> str:
    """Snippet to nest CombatVfx under an existing main scene (instance or inline)."""
    x, y = position
    return "\n".join([
        f'[node name="{NODE_NAME}" type="Node2D" parent="{parent}"]',
        f'script = preload("{SCRIPT_PATH}")',
        f"position = Vector2({x}, {y})",
        f'metadata/era = "{get_era(era_key)["key"]}"',
        "",
    ])


def cue_scene_assertions(cue: CombatCue) -> dict[str, object]:
    """Facts a test can assert against generated scene text."""
    return {
        "era": cue.era,
        "cue_type": cue.cue_type,
        "shape": cue.shape,
        "severity": cue.severity,
        "colors": cue.colors,
        "particles": cue.particles,
        "duration_ms": cue.lead_ms or cue.duration_ms,
        "trauma": cue.trauma,
        "hit_frame": cue.hit_frame,
        "pixel": is_pixel_era(cue.era),
    }


def telegraph_scene_for(
    era_key: str | None,
    damage: float,
    max_health: float,
    *,
    hit_frame: int | None = None,
) -> str:
    """Full .tscn for a damage-scaled telegraph cue."""
    tele = telegraph_for(era_key, damage, max_health, hit_frame=hit_frame)
    # Rebuild scene around this specific telegraph (not the catalog default).
    era = get_era(tele.era)
    pixel = is_pixel_era(era["key"])
    shape = tele.shape or "cone"
    nodes: list[str] = [
        '[gd_scene load_steps=4 format=3 uid="uid://tutolage_combat_vfx"]',
        "",
        f'[ext_resource type="Script" path="{SCRIPT_PATH}" id="1"]',
        "",
        '[node name="CombatVfx" type="Node2D"]',
        'script = ExtResource("1")',
        f'metadata/era = "{tele.era}"',
        f'metadata/severity = "{tele.severity}"',
        f'metadata/shape = "{shape}"',
        f"metadata/duration_ms = {tele.lead_ms}",
        f"metadata/particles = {tele.particles}",
        f"metadata/trauma = {tele.trauma}",
        f"metadata/colors = {tele.colors}",
        f"metadata/hit_frame = {tele.hit_frame if tele.hit_frame is not None else -1}",
        f'metadata/cue_type = "telegraph"',
        "",
    ]
    for shape_name in ("Circle", "Cone", "Line", "Ring"):
        vis = "true" if shape_name.lower() == shape else "false"
        color = palette_color(0, tele.colors)
        nodes += [
            f'[node name="{shape_name}" type="Node2D" parent="CombatVfx"]',
            f"visible = {vis}",
            "",
        ]
        if pixel:
            nodes += [
                f'[node name="Sprite" type="Sprite2D" parent="CombatVfx/{shape_name}"]',
                f"modulate = {color}",
                "",
            ]
        else:
            nodes += [
                f'[node name="Particles" type="GPUParticles2D" parent="CombatVfx/{shape_name}"]',
                f"amount = {tele.particles}",
                "emitting = false",
                f"modulate = {color}",
                "",
            ]
    return "\n".join(nodes)
