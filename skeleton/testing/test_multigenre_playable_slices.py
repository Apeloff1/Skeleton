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
    assert "func _objective_text() -> String:" in added[f"scripts/archetypes/{name}/core_loop.gd"]
    assert "_status.text" in added[f"scripts/archetypes/{name}/core_loop.gd"]
    controller = added[f"scripts/archetypes/{name}/player_controller.gd"]
    assert "Input.get_vector" in controller
    assert "Input.action_press(action)" in controller
    assert "Input.action_release(action)" in controller
    assert "DisplayServer.is_touchscreen_available()" in controller
    assert "_touch_controls.append" in controller
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



@pytest.mark.parametrize("name", SUPPORTED)
def test_bonus_mode_adds_reachable_in_game_launcher_without_rewriting_default_world(name):
    from skeleton.forge.archetype_content import (
        attach_playable_launcher, PLAYABLE_LAUNCHER_PATH,
    )
    base = godot_files()
    scene = attach_archetype_content(base, name)
    source = attach_playable_launcher(scene, name)
    assert len(source) == len(base) + 4
    assert source["data/rooms.json"] == base["data/rooms.json"]
    assert source["project.godot"].count("PlayableHub=") == 1
    assert 'run/main_scene="res://scenes/levels/run_level.tscn"' in source["project.godot"]
    assert PLAYABLE_LAUNCHER_PATH in source
    script = source[PLAYABLE_LAUNCHER_PATH]
    assert f'res://scenes/archetypes/{name}/main.tscn' in script
    assert "get_tree().change_scene_to_file(target)" in script
    assert "get_tree().current_scene" in script
    assert "ORIGINAL_WORLD" in script
    assert source_manifest(source)["file_count"] == len(source)
    ok, problems = check_ok(source)
    assert ok, problems
    assert base == godot_files(), "launcher construction mutated canonical source"


def test_launcher_rejects_source_collisions_and_unregistered_paths():
    from skeleton.forge.archetype_content import (
        attach_playable_launcher, PLAYABLE_LAUNCHER_PATH,
    )
    base = attach_archetype_content(godot_files(), "puzzle")
    with pytest.raises(ValueError):
        attach_playable_launcher(base, "../../system")
    with pytest.raises(ValueError):
        attach_playable_launcher(godot_files(), "puzzle")
    source = attach_playable_launcher(base, "puzzle")
    with pytest.raises(ValueError):
        attach_playable_launcher(source, "puzzle")
    changed = dict(base)
    changed[PLAYABLE_LAUNCHER_PATH] = "extends Node"
    with pytest.raises(ValueError):
        attach_playable_launcher(changed, "puzzle")
    changed = dict(base)
    changed["project.godot"] = changed["project.godot"].replace(
        "[autoload]\n", "[autoload]\nPlayableHub=\"*res://unknown.gd\"\n"
    )
    with pytest.raises(ValueError):
        attach_playable_launcher(changed, "puzzle")


def test_pipeline_bonus_launcher_and_quest_are_composed_without_clobbering(monkeypatch):
    from skeleton.context import pipeline
    from skeleton.ai.game_builder.godot_quest_bridge import verify_native_quest
    from skeleton.forge.archetype_content import PLAYABLE_LAUNCHER_PATH
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": godot_files(), "project_root": None,
        "playtest_mode": "off", "playable_content": True,
        "playable_archetype_selection": "stealth",
        "playable_main_scene": False,
        "quest_content": True, "quest_length": 2,
    }
    pipeline._stage_emit(ctx)
    files = ctx["files"]
    assert PLAYABLE_LAUNCHER_PATH in files
    assert ctx["playable_launcher"] == PLAYABLE_LAUNCHER_PATH
    assert "PlayableHub=" in files["project.godot"]
    assert "QuestRuntime=" in files["project.godot"]
    assert verify_native_quest(files)
    assert ctx["native_quest_receipt"]["steps"] == 2
    assert files["data/rooms.json"] == godot_files()["data/rooms.json"]
    assert source_manifest(files)["file_count"] == len(files)



def test_playable_receipt_binds_exact_scripts_and_godot_launcher(monkeypatch):
    from skeleton.context import pipeline
    from skeleton.forge.archetype_content import PLAYABLE_LAUNCHER_PATH
    import hashlib

    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    for launch in (False, True):
        ctx = {
            "era": "extraction_now", "target": "godot",
            "files": godot_files(), "project_root": None, "playtest_mode": "off",
            "playable_content": True, "playable_archetype_selection": "puzzle",
            "playable_main_scene": launch,
        }
        pipeline._stage_emit(ctx)
        receipt = ctx["playable_receipt"]
        assert receipt["schema"] == "skeleton.gameforge.playable_source.v1"
        assert receipt["mode"] == "puzzle"
        assert receipt["scene"] == "res://scenes/archetypes/puzzle/main.tscn"
        assert receipt["launch_scene"] == receipt["scene"] if launch else receipt["launch_scene"] is None
        hashes = source_manifest(ctx["files"])["files"]
        assert receipt["source_files"] == {
            path: hashes[path] for path in sorted(receipt["source_files"])
        }
        assert receipt["launcher"] == (None if launch else PLAYABLE_LAUNCHER_PATH)
        expected = hashlib.sha256(json.dumps(
            receipt["source_files"], sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        assert receipt["source_sha256"] == expected


def test_receipts_are_absent_for_non_opt_in_default_output(monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": godot_files(), "project_root": None, "playtest_mode": "off",
        "playable_content": False,
    }
    pipeline._stage_emit(ctx)
    assert "playable_receipt" not in ctx



@pytest.mark.parametrize("mode", SUPPORTED)
def test_explicit_tempo_slider_changes_actual_controller_source_for_all_modes(mode):
    from skeleton.forge.playable_tuning import SOURCE_PATH, SCHEMA

    pristine = archetype_files(mode)
    tuned = archetype_files(mode, tuning={"tempo": 1.0, "spectacle": 0.9})
    controller = f"scripts/archetypes/{mode}/player_controller.gd"
    assert tuned[controller] != pristine[controller]
    assert "@export var speed: float = " in tuned[controller]
    assert SOURCE_PATH not in pristine
    assert set(tuned) == set(pristine) | {SOURCE_PATH}
    receipt = json.loads(tuned[SOURCE_PATH])
    assert receipt["schema"] == SCHEMA
    assert receipt["mode"] == mode
    assert receipt["axes"] == {"spectacle": 0.9, "tempo": 1.0}
    assert receipt["mapped_axes"] == ["tempo"]
    assert receipt["unmapped_axes"] == ["spectacle"]
    assert receipt["applied"]["player.speed"] > 0
    assert tuned == archetype_files(mode, tuning={"spectacle": 0.9, "tempo": 1})
    assert pristine == archetype_files(mode)
    ok, errors = check_ok(tuned)
    assert ok, errors


@pytest.mark.parametrize("mode,axis,target,constant", [
    ("extraction", "risk", "extraction.heat_per_second", "const HEAT_PER_SECOND := 7.50"),
    ("racing", "risk", "racing.time_limit_seconds", "const TIME_LIMIT := 36.00"),
    ("stealth", "risk", "stealth.detection_radius", "const DETECTION_RADIUS := 80.00"),
    ("survival", "scarcity", "survival.hydration_drain_per_second", "const DRAIN_PER_SECOND := 3.00"),
    ("combat_loop", "lethality", "combat_loop.starting_hp", "var player_hp: int = 75"),
])
def test_risk_scarcity_lethality_knobs_really_change_the_specific_game_logic(
    mode, axis, target, constant,
):
    from skeleton.forge.playable_tuning import SOURCE_PATH

    files = archetype_files(mode, tuning={axis: 1.0})
    path = f"scripts/archetypes/{mode}/core_loop.gd"
    assert constant in files[path]
    assert files[path] != archetype_files(mode)[path]
    receipt = json.loads(files[SOURCE_PATH])
    assert receipt["applied"][target] > 0
    assert receipt["mapped_axes"] == [axis]
    assert receipt["unmapped_axes"] == []
    okay, errors = check_ok(files)
    assert okay, errors


def test_cockpit_sparse_tuning_is_bounded_and_does_not_execute_untrusted_values():
    from skeleton.forge.playable_tuning import SOURCE_PATH

    invalid = [
        {"tempo": True},
        {"tempo": -0.01},
        {"risk": float("inf")},
        {"scarcity": float("nan")},
        {"risk": 1.01},
        {"constructor": 1},
        {"tempo": "0.8"},
        {x: 0 for x in "abcdefghijk"},
    ]
    for axes in invalid + [[], "", False, 0]:
        with pytest.raises(ValueError):
            archetype_files("racing", tuning=axes)
    assert SOURCE_PATH not in archetype_files("racing")
    assert SOURCE_PATH not in archetype_files("racing", tuning={})
    assert archetype_files("racing", tuning={}) == archetype_files("racing")


def test_tuning_collides_closed_on_existing_source_and_does_not_mutate_inputs():
    from skeleton.forge.playable_tuning import SOURCE_PATH

    files = godot_files()
    original = deepcopy(files)
    source = attach_archetype_content(files, "survival", tuning={"tempo": 0.8})
    assert files == original
    assert SOURCE_PATH in source
    assert source_manifest(source)["files"][SOURCE_PATH]
    # Different authored tuning is never silently overwritten.
    with pytest.raises(ValueError, match="collides"):
        attach_archetype_content(source, "survival", tuning={"tempo": 0.1})
    collision = dict(files)
    collision[SOURCE_PATH] = "untrusted"
    with pytest.raises(ValueError, match="collides"):
        attach_archetype_content(collision, "survival", tuning={"risk": 0.9})


def test_full_galaxy_tensor_and_quest_can_compile_one_tuned_playable_bundle(monkeypatch):
    from skeleton.context import pipeline
    from skeleton.context.galaxy_profile import (
        ARTIFACT_PATH, galaxy_profile_receipt, normalise_galaxy_profile,
    )
    from skeleton.testing.test_galaxy_profile import sample
    from skeleton.forge.playable_tuning import SOURCE_PATH
    from skeleton.ai.game_builder.godot_quest_bridge import QUEST_PATH, verify_native_quest

    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    profile = normalise_galaxy_profile(sample())
    source = godot_files()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": source, "project_root": None, "playtest_mode": "off",
        "playable_content": True, "playable_archetype_selection": "survival",
        "playable_main_scene": False, "quest_content": True, "quest_length": 3,
        "operator_axes": {"tempo": 0.8, "scarcity": 0.9, "risk": 0.6},
        "galaxy_profile": profile, "galaxy_receipt": galaxy_profile_receipt(profile),
    }
    pipeline._stage_emit(ctx)
    generated = ctx["files"]
    assert ARTIFACT_PATH in generated
    assert QUEST_PATH in generated
    assert SOURCE_PATH in generated
    assert verify_native_quest(generated)
    assert json.loads(generated[ARTIFACT_PATH]) == profile
    assert ctx["playable_tuning"]["applied"]["player.speed"] > 0
    assert ctx["playable_tuning"]["applied"]["survival.hydration_drain_per_second"] > 0
    assert ctx["playable_tuning"]["unmapped_axes"] == ["risk"]
    manifest = source_manifest(generated)
    assert len(generated) == ctx["file_count"] == manifest["file_count"]
    assert ctx["playable_receipt"]["tuning"] == json.loads(generated[SOURCE_PATH])
    assert ctx["playable_receipt"]["source_files"][SOURCE_PATH] == manifest["files"][SOURCE_PATH]
    assert generated["data/rooms.json"] == source["data/rooms.json"]



@pytest.mark.parametrize("mode", SUPPORTED)
@pytest.mark.parametrize("startup", [False, True])
def test_authoritative_playable_provenance_reconstructs_tuned_source(mode, startup, monkeypatch):
    from skeleton.context import pipeline
    from skeleton.forge.playable_provenance import verify_playable_source
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": godot_files(), "project_root": None, "playtest_mode": "off",
        "playable_content": True, "playable_archetype_selection": mode,
        "playable_main_scene": startup,
        "operator_axes": {"tempo": 0.8, "risk": 0.9, "lethality": 0.4, "scarcity": 0.7},
    }
    pipeline._stage_emit(ctx)
    source, receipt = ctx["files"], ctx["playable_receipt"]
    assert verify_playable_source(source, receipt)
    assert receipt["tuning"]["axes"] == {
        "lethality": 0.4, "risk": 0.9, "scarcity": 0.7, "tempo": 0.8,
    }
    assert receipt["tuning"]["mapped_axes"] != []
    assert receipt["source_files"]["data/playable_tuning.json"] == \
        source_manifest(source)["files"]["data/playable_tuning.json"]


def test_recomputed_unkeyed_hash_cannot_hide_adulterated_gdscript(monkeypatch):
    from skeleton.context import pipeline
    from skeleton.forge.playable_provenance import verify_playable_source
    import hashlib

    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": godot_files(), "project_root": None, "playtest_mode": "off",
        "playable_content": True, "playable_archetype_selection": "racing",
        "playable_main_scene": True,
        "operator_axes": {"risk": 0.8, "tempo": 0.6},
    }
    pipeline._stage_emit(ctx)
    good_files, good_receipt = ctx["files"], ctx["playable_receipt"]
    assert verify_playable_source(good_files, good_receipt)

    forged_files = dict(good_files)
    loop = "scripts/archetypes/racing/core_loop.gd"
    forged_files[loop] = forged_files[loop].replace(
        "const GOAL_LAPS := 3", "const GOAL_LAPS := 999",
    )
    forged_receipt = deepcopy(good_receipt)
    forged_receipt["source_files"] = {
        path: source_manifest(forged_files)["files"][path]
        for path in forged_receipt["source_files"]
    }
    forged_receipt["source_sha256"] = hashlib.sha256(json.dumps(
        forged_receipt["source_files"], sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert not verify_playable_source(forged_files, forged_receipt)
    assert verify_playable_source(good_files, good_receipt)


def test_tuning_receipt_and_launcher_cannot_be_rebound_to_other_prototype(monkeypatch):
    from skeleton.context import pipeline
    from skeleton.forge.playable_provenance import verify_playable_source
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": godot_files(), "project_root": None, "playtest_mode": "off",
        "playable_content": True, "playable_archetype_selection": "survival",
        "playable_main_scene": False,
        "operator_axes": {"tempo": 0.9, "scarcity": 0.7},
    }
    pipeline._stage_emit(ctx)
    files, receipt = ctx["files"], ctx["playable_receipt"]
    assert verify_playable_source(files, receipt)

    forged = deepcopy(receipt)
    forged["mode"] = "racing"
    assert not verify_playable_source(files, forged)
    forged = deepcopy(receipt)
    forged["tuning"]["axes"]["scarcity"] = 0.1
    assert not verify_playable_source(files, forged)
    forged = deepcopy(receipt)
    forged["launcher"] = None
    assert not verify_playable_source(files, forged)
    altered = dict(files)
    altered[receipt["launcher"]] += "\n# actor-swapped"
    assert not verify_playable_source(altered, receipt)
    assert not verify_playable_source(files, {"schema": "skeleton.gameforge.playable_source.v1"})
