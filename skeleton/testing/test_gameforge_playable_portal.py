"""Source-verified in-game navigation from the generated Godot main world.

These checks are hermetic. A native Godot engine test remains a separate,
independent device/CI requirement, never inferred from this static suite.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.context import pipeline
from skeleton.forge.archetype_content import attach_archetype_content, content_archetypes
from skeleton.forge.eras import compile_era
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.playable_portal import (
    AUTOLOAD_ENTRY,
    SCRIPT_PATH,
    PlayablePortalError,
    attach_playable_portal,
    verify_playable_portal,
)
from skeleton.forge.source_manifest import source_manifest


def world():
    return emit_godot(compile_era("extraction_now"))


@pytest.mark.parametrize("archetype", content_archetypes())
def test_real_emitted_world_has_a_start_and_return_portal(archetype):
    original = world()
    scene_files = attach_archetype_content(original, archetype)
    before = deepcopy(scene_files)
    files, receipt = attach_playable_portal(scene_files, archetype)
    assert original == world()
    assert scene_files == before
    assert verify_playable_portal(files, archetype)
    assert len(files) == len(scene_files) + 1
    assert files["project.godot"].count(AUTOLOAD_ENTRY) == 1
    assert 'run/main_scene="res://scenes/levels/run_level.tscn"' in files["project.godot"]
    assert f'res://scenes/archetypes/{archetype}/main.tscn' in files[SCRIPT_PATH]
    assert 'change_scene_to_file(destination)' in files[SCRIPT_PATH]
    assert 'Return to Forge world' in files[SCRIPT_PATH]
    assert 'DisplayServer.get_name() == "headless"' in files[SCRIPT_PATH]
    assert 'Control.MOUSE_FILTER_STOP' in files[SCRIPT_PATH]
    assert receipt["scene"] == f"scenes/archetypes/{archetype}/main.tscn"
    assert receipt["return_supported"] is True
    assert receipt["headless_inert"] is True
    ok, problems = check_ok(files)
    assert ok, problems
    assert source_manifest(files)["file_count"] == len(scene_files) + 1


def test_no_playable_opt_in_preserves_exact_original_source(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = world()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "extraction", "files": deepcopy(original),
        "project_root": None, "playtest_mode": "off",
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"] == original
    assert SCRIPT_PATH not in ctx["files"]
    assert "PlayablePortal=" not in ctx["files"]["project.godot"]
    assert "playable_portal_receipt" not in ctx


def test_pipeline_attaches_audited_launcher_and_quest_in_one_world(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = world()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "combat_loop",
        "files": deepcopy(original),
        "playable_content": True,
        "quest_content": True,
        "quest_length": 5,
        "project_root": None,
        "playtest_mode": "off",
    }
    emitted = pipeline._stage_emit(ctx)
    assert emitted["emitted"] is True
    assert verify_playable_portal(ctx["files"], "combat_loop")
    assert "QuestRuntime=" in ctx["files"]["project.godot"]
    assert ctx["files"]["project.godot"].count("PlayablePortal=") == 1
    assert ctx["playable_portal_receipt"]["schema"] == "skeleton.forge.playable_portal.v1"
    assert ctx["native_quest_receipt"]["steps"] == 5
    assert ctx["file_count"] == len(original) + 6
    assert source_manifest(ctx["files"])["file_count"] == len(original) + 6


def test_cross_feature_final_source_verification_catches_mutation_between_attachers(monkeypatch):
    from skeleton.ai.game_builder import godot_quest_bridge
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = godot_quest_bridge.attach_native_quest

    def malicious_mutation(files, *, length=3):
        out, receipt = original(files, length=length)
        out[SCRIPT_PATH] += "\n# tampered between attachments"
        return out, receipt

    monkeypatch.setattr(godot_quest_bridge, "attach_native_quest", malicious_mutation)
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline",
        "playable_content": True, "quest_content": True, "quest_length": 3,
        "project_root": None, "playtest_mode": "off",
        "files": world(),
    }
    with pytest.raises(RuntimeError, match="final in-game playable portal verification failed"):
        pipeline._stage_emit(ctx)


@pytest.mark.parametrize("invalid", [None, "", "auto", "combat_loop;rm", "__proto__", True])
def test_unrecognized_portal_sources_fail_closed(invalid):
    files = attach_archetype_content(world(), "extraction")
    before = deepcopy(files)
    with pytest.raises(PlayablePortalError, match="unknown"):
        attach_playable_portal(files, invalid)
    assert files == before


def test_prototype_portal_rejects_missing_source_and_autoload_collisions():
    original = attach_archetype_content(world(), "pipeline")
    tamper_cases = [
        lambda f: f.pop("scenes/archetypes/pipeline/main.tscn"),
        lambda f: f.pop("scripts/autoloads/input_bind.gd"),
        lambda f: f.__setitem__(
            "project.godot",
            f["project.godot"].replace(
                'InputBind="*res://scripts/autoloads/input_bind.gd"\n', "",
            ),
        ),
        lambda f: f.__setitem__(
            "project.godot",
            f["project.godot"].replace(
                'InputBind="*res://scripts/autoloads/input_bind.gd"\n',
                'InputBind="*res://scripts/autoloads/input_bind.gd"\n'
                'PlayablePortal="*res://scripts/autoloads/malicious.gd"\n',
            ),
        ),
        lambda f: f.__setitem__(SCRIPT_PATH, "extends Node\n"),
    ]
    for mutate in tamper_cases:
        files = deepcopy(original)
        mutate(files)
        before = deepcopy(files)
        # The portal validates source map, not the rest of the Godot project.
        # The missing InputBind *file* alone is caught by check_ok at emit.
        if "scripts/autoloads/input_bind.gd" not in files:
            with pytest.raises(PlayablePortalError):
                # Here reject incomplete physical autoload source before writing.
                attach_playable_portal(files, "pipeline")
        else:
            with pytest.raises(PlayablePortalError):
                attach_playable_portal(files, "pipeline")
        assert files == before


def test_verifier_rejects_any_post_generation_retarget_or_text_change():
    original = attach_archetype_content(world(), "pipeline")
    files, _ = attach_playable_portal(original, "pipeline")
    assert verify_playable_portal(files, "pipeline")
    tampered = dict(files)
    tampered[SCRIPT_PATH] += "\n# unreviewed"
    assert not verify_playable_portal(tampered, "pipeline")
    tampered = dict(files)
    tampered["project.godot"] += AUTOLOAD_ENTRY
    assert not verify_playable_portal(tampered, "pipeline")
    tampered = dict(files)
    tampered.pop("scenes/archetypes/pipeline/main.tscn")
    assert not verify_playable_portal(tampered, "pipeline")
    assert not verify_playable_portal(files, "extraction")
