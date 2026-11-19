"""Eight actual native Godot sidecar sources and source-only safety gates.

Real Godot headless execution remains an additional external qualification;
these tests verify the maintained source contract and explicit startup.
"""
from __future__ import annotations

import pytest

from skeleton.forge.archetype_content import (
    archetype_files, attach_archetype_content, content_archetypes,
    verify_archetype_content,
)
from skeleton.forge.playable_portal import (
    INPUT_ENTRY, WORLD_SCENE, attach_playable_portal,
    verify_playable_portal,
)


EIGHT = (
    "extraction", "combat_loop", "pipeline",
    "puzzle", "racing", "survival", "stealth", "crafting",
)


@pytest.mark.parametrize("name", EIGHT)
def test_real_godot_mode_has_independent_authored_win_lose_logic(name: str) -> None:
    source = archetype_files(name)
    root = f"scenes/archetypes/{name}/main.tscn"
    loop = f"scripts/archetypes/{name}/core_loop.gd"
    controller = f"scripts/archetypes/{name}/player_controller.gd"
    assert set(source) == {root, loop, controller}
    assert f'const ARCHETYPE := "{name}"' in source[loop]
    assert "func _tick(" in source[loop]
    assert "func _hud_status(" in source[loop]
    assert "func _draw_objectives(" in source[loop]
    assert "_finish(true," in source[loop]
    assert "_finish(false," in source[loop] or "frame budget exhausted" in source[loop]
    assert "ARCHETYPE_LOOP_COMPLETE" in source[loop]
    assert "ARCHETYPE_LOOP_FAILED" in source[loop]
    assert "autopilot_target" in source[loop]
    assert "touch controls" in source[loop].lower()
    assert "input.get_vector" in source[controller].lower()
    assert verify_archetype_content(source, name)


def test_exact_eight_modes_without_fictional_catalog_widening() -> None:
    assert tuple(sorted(content_archetypes())) == tuple(sorted(EIGHT))
    assert all(archetype_files(name) != archetype_files(other)
               for index, name in enumerate(EIGHT)
               for other in EIGHT[index + 1:])


@pytest.mark.parametrize("name,axes,actual", [
    ("puzzle", {"opacity": 0.8}, "const SHOW_SWITCH_HINTS := false"),
    ("racing", {"risk": 0.9}, "const CHECKPOINT_LIMIT := 17.20"),
    ("racing", {"grind": 1.0}, "const RACE_LAPS := 5"),
    ("survival", {"scarcity": 1.0}, "const HYDRATION_DRAIN := 5.00"),
    ("stealth", {"risk": 1.0}, "const GUARD_DETECTION_RADIUS := 54.00"),
    ("stealth", {"opacity": 0.7}, "const SHOW_GUARD_ZONES := false"),
    ("combat_loop", {"lethality": 1.0}, "var player_hp: int = 50"),
    ("pipeline", {"grind": 1.0}, "const QUOTA := 8"),
])
def test_real_tensor_knobs_change_native_script_not_just_ui(
    name: str, axes: dict, actual: str,
) -> None:
    tuned = archetype_files(name, operator_axes=axes)
    script = tuned[f"scripts/archetypes/{name}/core_loop.gd"]
    assert actual in script
    assert verify_archetype_content(tuned, name, operator_axes=axes)
    assert not verify_archetype_content(
        tuned, name, operator_axes={},
    )


@pytest.mark.parametrize("name", ["../../escape", "", "unreal", "json", "auto", "__proto__"])
def test_unknown_explicit_source_cannot_emit_any_untrusted_native_script(name: str) -> None:
    with pytest.raises(KeyError):
        archetype_files(name)


def test_optional_additive_content_never_overwrites_unrelated_source() -> None:
    files = {"project.godot": "normal-game-source", "scripts/author.gd": "author-content"}
    for name in EIGHT:
        attached = attach_archetype_content(files, name)
        assert attached["project.godot"] == files["project.godot"]
        assert attached["scripts/author.gd"] == files["scripts/author.gd"]
        assert verify_archetype_content(attached, name)
    for name in EIGHT:
        scene = f"scenes/archetypes/{name}/main.tscn"
        bad = {scene: "corrupt previous owner"}
        with pytest.raises(ValueError, match="collides"):
            attach_archetype_content(bad, name)


def test_staged_startup_must_be_verified_against_actual_project_manifest() -> None:
    # The portal attaches only when core run-level + InputBind are genuine.
    base = {
        "project.godot": (
            '[application]\nrun/main_scene="' + WORLD_SCENE +
            '"\n[autoload]\n' + INPUT_ENTRY
        ),
        "scripts/autoloads/input_bind.gd": "native binding",
        "scenes/levels/run_level.tscn": "world source",
    }
    native = attach_archetype_content(base, "puzzle")
    attached, evidence = attach_playable_portal(native, "puzzle")
    assert verify_playable_portal(attached, "puzzle")
    assert evidence["return_supported"] is True
    assert not verify_playable_portal(attached, "puzzle", launch=True)
    source = attached["project.godot"]
    selected = 'run/main_scene="res://scenes/archetypes/puzzle/main.tscn"'
    attached["project.godot"] = source.replace(
        f'run/main_scene="{WORLD_SCENE}"', selected
    )
    assert verify_playable_portal(attached, "puzzle", launch=True)
    assert not verify_playable_portal(attached, "puzzle")
    attached["project.godot"] = source + '\nrun/main_scene="unexpected"\n'
    assert not verify_playable_portal(attached, "puzzle")


@pytest.mark.parametrize("axes", [
    {"risk": float("nan")}, {"tempo": 2.0}, {"opacity": -0.1},
    {"made_up": 0.7}, {"risk": True},
])
def test_native_tuning_denies_nonfinite_or_unrecognised_axes(axes: dict) -> None:
    with pytest.raises(ValueError):
        archetype_files("puzzle", operator_axes=axes)
