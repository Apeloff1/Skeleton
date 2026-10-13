"""Godot combat VFX emit — catalog cues become .tscn / .gd text."""
from gameforge.godot_engine.combat_vfx import (
    NODE_NAME,
    SCRIPT_PATH,
    combat_vfx_scene,
    combat_vfx_script,
    cue_scene_assertions,
    palette_color,
    telegraph_scene_for,
)
from gameforge.godot_engine.project import ProjectSpec, available_templates, scaffold_project
from gameforge.godot_engine.scenes import platformer_scene, topdown_scene, empty_scene
from core.eras import ERA_ORDER
from core.vfx_combat_catalog import CATALOG, cue_for, telegraph_for
from pathlib import Path
import tempfile


def test_script_plays_cues_and_gates_hit_frame():
    src = combat_vfx_script()
    assert "func play_cue" in src
    assert "func play_telegraph" in src
    assert "func notify_hit_frame" in src
    assert "DANGER_RAMP" in src or "lethal" in src


def test_impact_cue_waits_for_contact_and_only_fires_once():
    script = combat_vfx_script()
    assert "_pending_hit_frame = cue_hit_frame" in script
    assert "_playing = cue_hit_frame < 0" in script
    assert "if _playing:\n        _emit_particles()" in script
    assert "if _pending_hit_frame >= 0 and frame == _pending_hit_frame:" in script
    assert "_pending_hit_frame = -1" in script
    # Readability telegraphs are shown immediately instead of deferred to impact.
    assert "play_cue(chosen, lead, 16 * slots, 0.0, tier, -1)" in script


def test_shape_emitter_traverses_nested_particles_in_godot_scene():
    script = combat_vfx_script()
    scene = combat_vfx_scene("modern")
    assert "for emitter in child.get_children():" in script
    assert "if emitter is GPUParticles2D:" in script
    assert "emitter.restart()" in script
    assert 'parent="CombatVfx/Cone"' in scene


def test_scene_has_combat_vfx_and_shape_nodes():
    text = combat_vfx_scene("modern")
    assert 'node name="CombatVfx"' in text
    assert SCRIPT_PATH in text
    for shape in ("Circle", "Cone", "Line", "Ring"):
        assert f'node name="{shape}"' in text
    assert "metadata/severity" in text
    assert "GPUParticles2D" in text


def test_pixel_era_uses_sprites_not_gpu_particles():
    text = combat_vfx_scene("8bit")
    assert "Sprite2D" in text
    assert "GPUParticles2D" not in text


def test_palette_color_is_grey_ramp_not_invented_rgb():
    assert palette_color(0, 1) == "Color8(255, 255, 255, 255)"
    c0, c1 = palette_color(0, 2), palette_color(1, 2)
    assert c0.startswith("Color8(") and c1.startswith("Color8(")
    assert c0 != c1


def test_telegraph_scene_carries_ramp_severity_and_hit_frame():
    tele = telegraph_for("modern", 100, 100, hit_frame=8)
    text = telegraph_scene_for("modern", 100, 100, hit_frame=8)
    facts = cue_scene_assertions(tele)
    assert f'metadata/severity = "{facts["severity"]}"' in text
    assert f'metadata/shape = "{facts["shape"]}"' in text
    assert f'metadata/particles = {facts["particles"]}' in text
    assert 'metadata/hit_frame = 8' in text
    assert f'metadata/colors = {facts["colors"]}' in text


def test_catalog_eras_all_emit_scenes():
    for era in ERA_ORDER:
        for cue_type in ("hit_spark", "crit", "telegraph", "death", "pickup"):
            cue = cue_for(era, cue_type)
            text = combat_vfx_scene(era)
            assert NODE_NAME in text
            assert cue.era == era


def test_platformer_and_topdown_include_combat_vfx():
    for builder in (platformer_scene, topdown_scene):
        text = builder()
        assert 'node name="CombatVfx"' in text
        assert "combat_vfx.gd" in text
    empty = empty_scene()
    assert "CombatVfx" not in empty


def test_scaffold_writes_combat_vfx_files():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold_project(ProjectSpec(title="Vfx Emit"), Path(tmp))
        written = set(result.files_written)
        assert "scripts/combat_vfx.gd" in written
        assert "scenes/combat_vfx.tscn" in written
        gd = (result.project_dir / "scripts/combat_vfx.gd").read_text()
        tscn = (result.project_dir / "scenes/combat_vfx.tscn").read_text()
        main = (result.project_dir / "scenes/main.tscn").read_text()
        assert "func play_cue" in gd
        assert 'node name="CombatVfx"' in tscn
        assert 'node name="CombatVfx"' in main


def test_blank_template_has_no_combat_vfx():
    with tempfile.TemporaryDirectory() as tmp:
        result = scaffold_project(
            ProjectSpec(title="Blank Only", template="blank2d"), Path(tmp)
        )
        assert "scripts/combat_vfx.gd" not in result.files_written
        main = (result.project_dir / "scenes/main.tscn").read_text()
        assert "CombatVfx" not in main


def test_available_templates_still_lists_combat_capable():
    ids = {t["id"] for t in available_templates()}
    assert {"platformer2d", "topdown2d", "blank2d"} <= ids
