"""Conserved-mass GameForge stages cannot equate world boot with playable proof."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.context import pipeline
from skeleton.forge import playtest as native
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot


def ctx(name: str = "puzzle", mode: str = "require") -> dict:
    return {
        "era": "extraction_now",
        "target": "godot",
        "files": emit_godot(compile_era("extraction_now")),
        "project_root": None,
        "playtest_mode": mode,
        "playable_content": True,
        "playable_archetype_selection": name,
        "playable_main_scene": False,
    }


@pytest.mark.parametrize("genre", [
    "combat_loop", "crafting", "extraction", "pipeline",
    "puzzle", "racing", "stealth", "survival",
])
def test_gameforge_requests_exact_playable_scene_after_world_boot(
    genre: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *a, **kw: None)
    events = []
    monkeypatch.setattr(native, "playtest", lambda files: {
        "status": "passed", "passed": True, "verified": True,
    })

    def scene(files, name):
        events.append((name, f"scenes/archetypes/{name}/main.tscn" in files))
        return {
            "schema": "skeleton.gameforge.native_playable_scene.v1",
            "scene": f"res://scenes/archetypes/{name}/main.tscn",
            "status": "passed", "passed": True, "verified": True,
        }

    monkeypatch.setattr(native, "playtest_archetype_scene", scene)
    context = ctx(genre)
    result = pipeline._stage_emit(context)
    assert events == [(genre, True)]
    assert result["emitted"] is True
    assert context["playable_scene_playtest"]["passed"] is True
    assert result["playable_scene_playtest"]["scene"].endswith(f"{genre}/main.tscn")


@pytest.mark.parametrize("status", ["unavailable", "failed"])
def test_required_native_completion_rejects_project_publication(
    status: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *a, **kw: None)
    monkeypatch.setattr(native, "playtest", lambda files: {
        "status": "passed", "passed": True, "verified": True,
    })
    monkeypatch.setattr(native, "playtest_archetype_scene", lambda files, name: {
        "status": status, "passed": False, "verified": False, "errors": ["not complete"],
    })
    context = ctx(mode="require")
    destination = tmp_path / "unpublished-project"
    context["project_root"] = str(destination)
    with pytest.raises(RuntimeError, match="playable scene"):
        pipeline._stage_emit(context)
    assert not destination.exists()
    assert context["playable_scene_playtest"]["passed"] is False


def test_best_effort_keeps_unverified_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *a, **kw: None)
    monkeypatch.setattr(native, "playtest", lambda files: {
        "status": "passed", "passed": True, "verified": False,
    })
    monkeypatch.setattr(native, "playtest_archetype_scene", lambda files, name: {
        "status": "unavailable", "passed": False, "verified": False,
        "reason": "missing-godot-binary",
    })
    context = ctx(mode="auto")
    result = pipeline._stage_emit(context)
    assert result["emitted"]
    assert context["playable_scene_playtest"]["status"] == "unavailable"


def test_unchanged_default_off_does_not_invoke_native_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *a, **kw: None)
    monkeypatch.setattr(native, "playtest_archetype_scene", lambda *a, **kw: pytest.fail("unexpected invocation"))
    context = ctx(mode="off")
    result = pipeline._stage_emit(context)
    assert result["playable_scene_playtest"] is None
    assert "playable_scene_playtest" not in context


def test_required_main_world_boot_must_also_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setattr(pipeline, "_commit", lambda *a, **kw: None)
    monkeypatch.setattr(native, "playtest", lambda files: {
        "status": "failed", "passed": False, "verified": True,
        "errors": ["world failed"],
    })
    monkeypatch.setattr(native, "playtest_archetype_scene", lambda *a, **kw: pytest.fail("unexpected scene qualification"))
    context = ctx(mode="require")
    context["project_root"] = str(tmp_path / "no-world-output")
    with pytest.raises(RuntimeError, match="playtest failed"):
        pipeline._stage_emit(context)
    assert not Path(context["project_root"]).exists()
