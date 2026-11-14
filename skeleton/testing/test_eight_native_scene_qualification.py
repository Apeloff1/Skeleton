"""Native eight-archetype scene completion is independent of world boot.

The unit tests mock only the Godot process boundary. Real Godot 4 device
qualification remains a separate required exact-head release gate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from skeleton.forge import playtest as native
from skeleton.forge.archetype_content import (
    COMPLETE_MARKER, FAILED_MARKER, archetype_files, content_archetypes,
)


def _files(name: str) -> dict[str, str]:
    return {
        "project.godot": '[application]\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
        **archetype_files(name),
    }


def _admit(monkeypatch: pytest.MonkeyPatch, verified: bool = True) -> None:
    monkeypatch.setattr(
        native, "resolve_binary",
        lambda binary=None: ("/admitted/godot", "fixture", verified),
    )


@pytest.mark.parametrize("genre", content_archetypes())
def test_all_eight_original_scenes_need_their_own_completion_marker(
    genre: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], Path]] = []
    _admit(monkeypatch)

    def run(cmd: list[str], root: Path, timeout: float):
        assert timeout > 0
        calls.append((cmd, root))
        if "--import" in cmd:
            return 0, "Godot import complete", False
        return 0, f"{COMPLETE_MARKER} {genre} objective_reached", False

    monkeypatch.setattr(native, "_run", run)
    result = native.playtest_archetype_scene(_files(genre), genre)
    assert result["status"] == "passed"
    assert result["passed"] is True
    assert result["verified"] is True
    assert len(calls) == 2
    assert "--import" in calls[0][0]
    assert calls[1][0][-1] == f"res://scenes/archetypes/{genre}/main.tscn"
    assert not calls[0][1].exists(), "native scratch project must be removed"


@pytest.mark.parametrize("case", [
    "no-marker", "other-game", "failed-marker", "script-error",
    "scene-nonzero", "scene-timeout",
])
def test_incomplete_native_scene_never_becomes_green(
    case: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _admit(monkeypatch)
    name = "puzzle"

    def run(cmd: list[str], root: Path, timeout: float):
        if "--import" in cmd:
            return 0, "Godot import complete", False
        results = {
            "no-marker": (0, "Godot normal exit", False),
            "other-game": (0, f"{COMPLETE_MARKER} racing done", False),
            "failed-marker": (0, f"{COMPLETE_MARKER} puzzle win\n{FAILED_MARKER} puzzle died", False),
            "script-error": (0, f"{COMPLETE_MARKER} puzzle win\nSCRIPT ERROR: invalid node", False),
            "scene-nonzero": (1, f"{COMPLETE_MARKER} puzzle win", False),
            "scene-timeout": (-1, f"{COMPLETE_MARKER} puzzle win", True),
        }
        return results[case]

    monkeypatch.setattr(native, "_run", run)
    result = native.playtest_archetype_scene(_files(name), name)
    assert result["status"] == "failed"
    assert result["passed"] is False
    assert result["errors"]


def test_failed_native_import_prevents_scene_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    _admit(monkeypatch)
    calls = []

    def run(cmd: list[str], root: Path, timeout: float):
        calls.append(cmd)
        return 5, "nonzero import", False

    monkeypatch.setattr(native, "_run", run)
    result = native.playtest_archetype_scene(_files("survival"), "survival")
    assert not result["passed"]
    assert len(calls) == 1
    assert result["errors"] == ["import: engine exited 5"]


def test_unavailable_native_engine_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native, "resolve_binary", lambda binary=None: (None, "no-godot", False))
    result = native.playtest_archetype_scene(_files("racing"), "racing")
    assert result["status"] == "unavailable"
    assert result["passed"] is False
    assert result["verified"] is False


@pytest.mark.parametrize("invalid", ["unknown", "../puzzle", "PuzzLE", "", None])
def test_unrecognized_or_unsafe_native_scene_rejected(invalid: Any) -> None:
    with pytest.raises(ValueError, match="archetype"):
        native.playtest_archetype_scene(_files("puzzle"), invalid)


@pytest.mark.parametrize("frames,timeout", [(True, 10), (0, 10), (12001, 10), (6000, float("nan")), (6000, 301), (6000, True)])
def test_native_admission_budgets_are_strict(frames: Any, timeout: Any) -> None:
    with pytest.raises(ValueError):
        native.playtest_archetype_scene(_files("puzzle"), "puzzle", frames=frames, timeout=timeout)


def test_main_world_import_nonzero_is_also_a_failed_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    _admit(monkeypatch)
    monkeypatch.setattr(native, "_run", lambda cmd, root, timeout: (3, "", False))
    result = native.playtest(_files("extraction"))
    assert result["status"] == "failed"
    assert result["passed"] is False
    assert any("import: engine exited 3" in e for e in result["errors"])


def test_unverified_engine_can_finish_gameplay_but_is_not_source_attested(monkeypatch: pytest.MonkeyPatch) -> None:
    _admit(monkeypatch, verified=False)
    monkeypatch.setattr(
        native, "_run",
        lambda cmd, root, timeout: (0, "" if "--import" in cmd
            else f"{COMPLETE_MARKER} crafting delivered", False),
    )
    result = native.playtest_archetype_scene(_files("crafting"), "crafting")
    assert result["passed"] is True
    assert result["verified"] is False
