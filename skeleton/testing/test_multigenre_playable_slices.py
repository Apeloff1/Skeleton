"""Original self-contained game-loop production integration contracts.

Tests emitted Godot source, static graph closure and API handoff. Native
Godot autoplay, player device controls and installer E2E remain separate gates.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from skeleton.forge.archetype_content import (
    COMPLETE_MARKER, FAILED_MARKER, archetype_files,
    attach_archetype_content, content_archetypes,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.source_manifest import source_manifest


SUPPORTED = (
    "combat_loop", "crafting", "extraction", "pipeline",
    "puzzle", "racing", "stealth", "survival",
)


def godot_files():
    return emit_godot(compile_era("extraction_now"))


def test_exactly_eight_honest_original_playable_modes_exist():
    from backend.routes.skeleton_gameforge import playable_archetypes
    assert content_archetypes() == SUPPORTED
    result = playable_archetypes()
    assert result["archetypes"] == list(SUPPORTED)
    assert result["count"] == len(SUPPORTED)
    assert result["kind"] == "original_self_contained_godot_2d_mini_game"


@pytest.mark.parametrize("name", SUPPORTED)
def test_each_archetype_adds_real_scene_controller_and_winnable_loop(name):
    original = godot_files()
    before = deepcopy(original)
    added = archetype_files(name)
    assert set(added) == {
        f"scenes/archetypes/{name}/main.tscn",
        f"scripts/archetypes/{name}/player_controller.gd",
        f"scripts/archetypes/{name}/core_loop.gd",
    }
    assert COMPLETE_MARKER in added[f"scripts/archetypes/{name}/core_loop.gd"]
    assert FAILED_MARKER in added[f"scripts/archetypes/{name}/core_loop.gd"]
    assert 'func _tick(' in added[f"scripts/archetypes/{name}/core_loop.gd"]
    assert 'func _physics_process(' in added[f"scripts/archetypes/{name}/player_controller.gd"]
    assert 'func _draw()' in added[f"scripts/archetypes/{name}/player_controller.gd"]
    assert 'arrows: move' in added[f"scripts/archetypes/{name}/core_loop.gd"]
    result = attach_archetype_content(original, name)
    assert original == before
    assert len(result) == len(original) + 3
    assert result["project.godot"] == original["project.godot"]
    assert source_manifest(result)["file_count"] == len(result)
    valid, issues = check_ok(result)
    assert valid, (name, issues)


@pytest.mark.parametrize("name", SUPPORTED)
def test_canonical_emit_can_make_each_mini_game_the_actual_launch_scene(name, monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_files()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": dict(original), "project_root": None,
        "playtest_mode": "off", "playable_content": True,
        "playable_archetype_selection": name,
        "playable_main_scene": True,
    }
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    expected = f"res://scenes/archetypes/{name}/main.tscn"
    assert ctx["playable_archetype"] == name
    assert ctx["playable_scene"] == expected
    assert ctx["playable_launch_scene"] == expected
    assert f'run/main_scene="{expected}"' in ctx["files"]["project.godot"]
    assert "data/rooms.json" in ctx["files"]
    assert ctx["files"]["data/rooms.json"] == original["data/rooms.json"]
    assert ctx["file_count"] == len(original) + 3
    assert source_manifest(ctx["files"])["file_count"] == len(original) + 3


def test_extra_scene_mode_preserves_normal_quest_compatible_startup(monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_files()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": dict(original), "project_root": None,
        "playtest_mode": "off", "playable_content": True,
        "playable_archetype_selection": "puzzle",
        "playable_main_scene": False,
        "quest_content": True, "quest_length": 3,
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"]["project.godot"] != original["project.godot"]
    assert 'run/main_scene="res://scenes/levels/run_level.tscn"' in ctx["files"]["project.godot"]
    assert ctx["native_quest_receipt"]["steps"] == 3
    assert ctx["playable_scene"] == "res://scenes/archetypes/puzzle/main.tscn"
    assert "scenes/archetypes/puzzle/main.tscn" in ctx["files"]
    from skeleton.ai.game_builder.godot_quest_bridge import verify_native_quest
    assert verify_native_quest(ctx["files"])


def test_default_emit_does_not_change_original_source(monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_files()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": deepcopy(original), "project_root": None,
        "playtest_mode": "off",
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"] == original
    assert "playable_scene" not in ctx
    assert "native_quest_receipt" not in ctx


@pytest.mark.parametrize("invalid", [
    {"playable_content": True, "target": "json"},
    {"playable_main_scene": True},
    {"playable_archetype": "puzzle"},
    {"playable_content": True, "playable_archetype": "unknown"},
    {"playable_content": True, "playable_main_scene": True, "quest_content": True},
    {"playable_content": True, "playable_archetype": "__proto__"},
])
def test_invalid_or_conflicting_playable_requests_fail_before_pipeline_execution(invalid):
    from skeleton.context.pipeline import GameForgeRun
    uninitialised = object.__new__(GameForgeRun)
    with pytest.raises(ValueError):
        uninitialised.execute("An original game", **invalid)


def test_backend_plays_explicit_mode_and_main_scene_only_when_requested(monkeypatch):
    from backend.routes.skeleton_gameforge import RunRequest, run
    from skeleton.context.pipeline import GameForgeRun

    calls = []
    class Stub:
        def execute(self, vision, **opts):
            calls.append(opts)
            return {"succeeded": True, "files": {"project.godot": "content"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    run(RunRequest(vision="Original craft world"))
    assert "playable_content" not in calls[-1]
    result = run(RunRequest(
        vision="Original craft world",
        playable_content=True, playable_archetype="crafting",
        playable_main_scene=True,
    ))
    assert result["succeeded"]
    assert calls[-1]["playable_content"] is True
    assert calls[-1]["playable_archetype"] == "crafting"
    assert calls[-1]["playable_main_scene"] is True
    with pytest.raises(HTTPException) as exc:
        run(RunRequest(playable_content=False, playable_archetype="racing"))
    assert exc.value.status_code == 422
