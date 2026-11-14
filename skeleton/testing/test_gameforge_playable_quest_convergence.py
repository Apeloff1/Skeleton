"""Executable Godot archetype sidecars and original native quests in one build.

No external engine, network, model provider or project publication is used.
This is a focused source and emit qualification, not native device validation.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from backend.routes.skeleton_gameforge import RunRequest, run
from skeleton.ai.game_builder.godot_quest_bridge import verify_native_quest
from skeleton.context import pipeline
from skeleton.forge.archetype_content import (
    COMPLETE_MARKER,
    FAILED_MARKER,
    archetype_files,
    attach_archetype_content,
    content_archetypes,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.source_manifest import source_manifest
from skeleton.forge.playable_portal import SCRIPT_PATH, verify_playable_portal


def base() -> dict[str, str]:
    return emit_godot(compile_era("extraction_now"))


@pytest.mark.parametrize("archetype", ("extraction", "combat_loop", "pipeline"))
def test_each_gameplay_archetype_produces_actual_godot_loop_scripts(archetype: str) -> None:
    original = base()
    frozen = deepcopy(original)
    generated = attach_archetype_content(original, archetype)
    assert original == frozen
    assert len(generated) == len(original) + 3
    expected = archetype_files(archetype)
    assert set(expected).issubset(generated)
    assert all(generated[name] == body for name, body in expected.items())
    assert COMPLETE_MARKER in generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert FAILED_MARKER in generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert "func _physics_process" in generated[f"scripts/archetypes/{archetype}/player_controller.gd"]
    loop = generated[f"scripts/archetypes/{archetype}/core_loop.gd"]
    assert "ForgeGameplayHUD" in loop and "TouchControls" in loop
    assert "func _draw_objectives() -> void:" in loop
    assert "func _hud_status() -> String:" in loop
    assert "draw_circle(player.global_position" in loop
    assert 'Input.action_press(action)' in loop
    assert 'Input.action_release(action)' in loop
    assert 'DisplayServer.get_name() == "headless"' in loop
    assert "CharacterBody2D" in generated[f"scenes/archetypes/{archetype}/main.tscn"]
    ok, problems = check_ok(generated)
    assert ok, problems
    manifest = source_manifest(generated)
    assert manifest["file_count"] == len(generated)


def test_three_real_playable_scene_prototypes_not_158_engines() -> None:
    assert content_archetypes() == ("combat_loop", "extraction", "pipeline")
    generated = attach_archetype_content(base(), "auto")
    assert "scenes/archetypes/extraction/main.tscn" in generated
    assert "scenes/archetypes/auto/main.tscn" not in generated


def test_playable_archetype_and_native_room_quest_coexist_at_emit(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    before = base()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline", "files": deepcopy(before),
        "playable_content": True, "quest_content": True, "quest_length": 5,
        "project_root": None, "playtest_mode": "off",
    }
    response = pipeline._stage_emit(ctx)
    assert response["emitted"] is True
    assert ctx["playable_archetype"] == "pipeline"
    assert ctx["native_quest_receipt"]["steps"] == 5
    assert ctx["native_quest_receipt"]["replay_verified"] is True
    assert verify_native_quest(ctx["files"])
    assert "scenes/archetypes/pipeline/main.tscn" in ctx["files"]
    assert verify_playable_portal(ctx["files"], "pipeline")
    assert ctx["playable_portal_receipt"]["return_supported"] is True
    assert ctx["playable_portal_receipt"]["headless_inert"] is True
    assert SCRIPT_PATH in ctx["files"]
    assert ctx["file_count"] == len(before) + 3 + 1 + 2
    assert source_manifest(ctx["files"])["file_count"] == len(before) + 3 + 1 + 2
    ok, problems = check_ok(ctx["files"])
    assert ok, problems


def test_no_playable_opt_in_keeps_source_outputs_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    originals = base()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline", "files": dict(originals),
        "project_root": None, "playtest_mode": "off",
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"] == originals
    assert "playable_archetype" not in ctx
    assert "native_quest_receipt" not in ctx


def test_http_route_forwards_both_independent_opt_ins_and_defaults(monkeypatch) -> None:
    from skeleton.context.pipeline import GameForgeRun
    seen: list[dict] = []

    class Stub:
        def execute(self, vision, **kwargs):
            seen.append(kwargs)
            return {"succeeded": True, "files": {"project.godot": "fixture"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    baseline = run(RunRequest(vision="An original game"))
    assert baseline["succeeded"]
    assert "playable_content" not in seen[-1]
    assert "quest_content" not in seen[-1]
    combined = run(RunRequest(
        vision="An original game", archetype="pipeline", target="godot",
        playable_content=True, quest_content=True, quest_length=5,
        operator_axes={"tempo": 0.61},
    ))
    assert combined["succeeded"]
    assert seen[-1]["playable_content"] is True
    assert seen[-1]["quest_content"] is True
    assert seen[-1]["quest_length"] == 5
    assert seen[-1]["operator_axes"] == {"tempo": 0.61}


def test_json_target_cannot_generate_native_playable_scenes():
    from skeleton.context.pipeline import GameForgeRun
    with pytest.raises(ValueError, match="Godot target"):
        GameForgeRun().execute(
            "An original blueprint", target="json",
            playable_content=True,
        )


@pytest.mark.parametrize("archetype,axes,expected", [
    ("extraction", {"tempo": 0.0, "risk": 1.0, "scarcity": 1.0, "agency": 0.0},
     ("speed: float = 195.0", "HEAT_PER_SECOND := 10.00", "HEAT_LIMIT := 70.00", "PICKUP_RADIUS := 8.00")),
    ("combat_loop", {"tempo": 1.0, "lethality": 1.0, "grind": 1.0, "agency": 1.0},
     ("speed: float = 300.0", "CONTACT_DAMAGE := 5", "WAVES := 5", "ATTACK_RANGE := 40.00")),
    ("pipeline", {"tempo": 0.0, "risk": 1.0, "grind": 1.0, "agency": 1.0},
     ("speed: float = 240.0", "MAX_FRAMES := 3600", "QUOTA := 8", "RADIUS := 20.00")),
])
def test_operator_knobs_generate_distinct_native_mechanics(archetype, axes, expected):
    from skeleton.forge.archetype_content import archetype_files, verify_archetype_content
    tuned = archetype_files(archetype, operator_axes=axes)
    baseline = archetype_files(archetype)
    assert tuned != baseline
    source = tuned[f"scripts/archetypes/{archetype}/core_loop.gd"]
    player = tuned[f"scripts/archetypes/{archetype}/player_controller.gd"]
    assert expected[0] in player
    assert all(part in source for part in expected[1:])
    attached = attach_archetype_content(base(), archetype, operator_axes=axes)
    assert verify_archetype_content(attached, archetype, operator_axes=axes)
    assert not verify_archetype_content(attached, archetype)


@pytest.mark.parametrize("invalid", [
    {"risk": float("nan")}, {"tempo": float("inf")}, {"risk": -0.001},
    {"tempo": 1.001}, {"agency": True}, {"unsupported": 0.5},
    {f"axis_{i}": 0.5 for i in range(11)},
])
def test_native_mechanics_reject_unbounded_or_unknown_axes(invalid):
    from skeleton.forge.archetype_content import archetype_files
    with pytest.raises(ValueError):
        archetype_files("extraction", operator_axes=invalid)


def test_final_mechanics_attestation_rejects_quest_writer_modification(monkeypatch):
    from skeleton.ai.game_builder import godot_quest_bridge
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_quest_bridge.attach_native_quest

    def tamper(files, *, length=3):
        generated, receipt = original(files, length=length)
        generated["scripts/archetypes/pipeline/core_loop.gd"] += "\n# tamper"
        return generated, receipt

    monkeypatch.setattr(godot_quest_bridge, "attach_native_quest", tamper)
    ctx = {
        "era": "extraction_now", "target": "godot", "archetype": "pipeline",
        "playable_content": True, "quest_content": True,
        "operator_axes": {"tempo": 0.8, "grind": 1.0},
        "files": base(), "playtest_mode": "off", "project_root": None,
    }
    with pytest.raises(RuntimeError, match="final native playable mechanics verification failed"):
        pipeline._stage_emit(ctx)
