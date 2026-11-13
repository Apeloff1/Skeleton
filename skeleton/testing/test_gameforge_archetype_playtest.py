"""Bounded Godot runtime qualification for generated playable sidecar scenes.

Always-hermetic mock-engine checks; a passing simulated engine is not native
qualification and does not replace an independent installed-Godot E2E run.
"""
from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.routes.skeleton_gameforge import RunRequest, run
from skeleton.context import pipeline
from skeleton.forge import playtest as pt
from skeleton.forge.archetype_content import COMPLETE_MARKER, FAILED_MARKER, attach_archetype_content
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot


def generated(archetype="pipeline"):
    return attach_archetype_content(emit_godot(compile_era("extraction_now")), archetype)


def test_playable_scene_unavailable_is_not_a_pass(monkeypatch):
    monkeypatch.setattr(pt, "resolve_binary", lambda: (None, "missing-godot-binary", False))
    report = pt.playtest_archetype_scene(generated(), "pipeline")
    assert report["status"] == "unavailable"
    assert report["passed"] is False
    assert report["scene"] == "scenes/archetypes/pipeline/main.tscn"


@pytest.mark.parametrize("bad", ["auto", "python;rm", "new_unverified", None])
def test_scene_validation_rejects_unrecognized_archetype(bad):
    with pytest.raises(ValueError, match="unknown"):
        pt.playtest_archetype_scene(generated(), bad)


@pytest.mark.parametrize("frames", [-1, 0, True, 12001, 1.5])
def test_scene_playtest_rejects_unbounded_frames(frames):
    with pytest.raises(ValueError, match="frame budget"):
        pt.playtest_archetype_scene(generated(), "pipeline", frames=frames)


@pytest.mark.parametrize("mode", ["complete", "missing", "script_error", "failure", "nonzero", "timed_out"])
def test_scene_qualification_requires_real_completion_marker_and_zero_exit(monkeypatch, mode):
    monkeypatch.setattr(pt, "resolve_binary", lambda: ("godot-test-binary", "fixture", False))
    events = []

    def fake_run(cmd, cwd, timeout):
        events.append((cmd, timeout))
        if len(events) == 1:
            return 0, "Godot Engine v4.3", False
        if mode == "complete":
            return 0, f"{COMPLETE_MARKER} pipeline shipped=4", False
        if mode == "missing":
            return 0, "Godot started but no goal was reached", False
        if mode == "script_error":
            return 0, "SCRIPT ERROR: invalid scene\n", False
        if mode == "failure":
            return 0, f"{FAILED_MARKER} pipeline frame budget exhausted", False
        if mode == "nonzero":
            return 3, f"{COMPLETE_MARKER} pipeline", False
        return -1, "", True

    monkeypatch.setattr(pt, "_run", fake_run)
    report = pt.playtest_archetype_scene(generated(), "pipeline")
    assert len(events) == 2
    assert "--headless" in events[0][0]
    assert "--import" in events[0][0]
    assert "res://scenes/archetypes/pipeline/main.tscn" in events[1][0]
    assert report["passed"] is (mode == "complete")
    assert report["status"] == ("passed" if mode == "complete" else "failed")
    if mode != "complete":
        assert report["errors"]


def test_strict_mode_rejects_failed_archetype_before_publish(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(pt, "playtest", lambda files: {"status": "passed", "passed": True})
    monkeypatch.setattr(pt, "playtest_archetype_scene", lambda files, arch: {
        "status": "failed", "passed": False, "errors": ["loop never completed"],
    })
    base = emit_godot(compile_era("extraction_now"))
    ctx = {
        "era": "extraction_now", "target": "godot",
        "archetype": "pipeline", "playable_content": True,
        "files": deepcopy(base), "playtest_mode": "require",
        "project_root": None,
    }
    with pytest.raises(RuntimeError, match="playable scene failed"):
        pipeline._stage_emit(ctx)
    assert ctx["playable_scene_playtest"]["passed"] is False


def test_auto_mode_reports_unavailable_sidecar_without_claiming_success(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(pt, "playtest", lambda files: {"status": "unavailable", "passed": False})
    monkeypatch.setattr(pt, "playtest_archetype_scene", lambda files, arch: {
        "status": "unavailable", "passed": False, "reason": "missing-godot-binary",
    })
    ctx = {
        "era": "extraction_now", "target": "godot", "archetype": "extraction",
        "files": emit_godot(compile_era("extraction_now")),
        "playable_content": True, "playtest_mode": "auto", "project_root": None,
    }
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    assert result["playable_scene_playtest"]["status"] == "unavailable"
    assert ctx["playable_scene_playtest"]["passed"] is False


def test_required_world_boot_without_playable_opt_in_does_not_run_sidecar(monkeypatch):
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    monkeypatch.setattr(pt, "playtest", lambda files: {"status": "passed", "passed": True})
    monkeypatch.setattr(pt, "playtest_archetype_scene", lambda *args: pytest.fail("unexpected sidecar boot"))
    ctx = {
        "era": "extraction_now", "target": "godot", "archetype": "extraction",
        "files": emit_godot(compile_era("extraction_now")),
        "playtest_mode": "require", "project_root": None,
    }
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    assert result["playable_scene_playtest"] is None


def test_non_godot_output_rejects_headless_playtest_before_side_effects():
    from skeleton.context.pipeline import GameForgeRun
    with pytest.raises(ValueError, match="requires the Godot target"):
        GameForgeRun().execute(
            "An original cross-platform blueprint", target="json",
            playtest="require",
        )


def test_http_qualifier_mode_reaches_pipeline_only_when_explicit(monkeypatch):
    from skeleton.context.pipeline import GameForgeRun
    seen = []

    class Stub:
        def execute(self, vision, **kwargs):
            seen.append(kwargs)
            return {"succeeded": True, "files": {"project.godot": "fixture"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    run(RunRequest(vision="An original game"))
    assert "playtest" not in seen[-1]
    run(RunRequest(vision="An original game", playable_content=True, playtest="require"))
    assert seen[-1]["playtest"] == "require"
    assert seen[-1]["playable_content"] is True
    with pytest.raises(ValidationError):
        RunRequest(playtest="occasionally")
