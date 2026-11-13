"""Native Godot quest runtime from archived B028/B030/B037: focused contracts.

Tests use the real era pack and Godot emitter, and separately exercise the
canonical 10-stage emit path with the real source manifest and static checks.
These are source-level and integration tests, not physical-device playtests.
"""
from __future__ import annotations

from copy import deepcopy
import json
import hashlib

import pytest

from skeleton.ai.game_builder.godot_quest_bridge import (
    NativeQuestError, QUEST_PATH, SCRIPT_PATH, SCHEMA,
    attach_native_quest, verify_native_quest,
)
from skeleton.ai.game_builder.constraint_quest_synthesis import ContentPolicy, WorldModel, validate_quest
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.gdscript_check import check_ok
from skeleton.forge.source_manifest import source_manifest


def base():
    return emit_godot(compile_era("extraction_now"))


def test_real_godot_project_gets_original_quest_autoload_and_source():
    before = base()
    original = deepcopy(before)
    files, receipt = attach_native_quest(before, length=4)
    assert before == original  # no caller mutation
    assert receipt["schema"] == SCHEMA
    assert receipt["steps"] == 4
    assert receipt["replay_verified"]
    assert receipt["quest_sha256"] == hashlib.sha256(files[QUEST_PATH].encode()).hexdigest()
    assert 'QuestRuntime="*res://scripts/autoloads/quest_runtime.gd"' in files["project.godot"]
    assert "EventBus.room_entered.connect(_on_room_entered)" in files[SCRIPT_PATH]
    assert "func restore_snapshot(save: Dictionary) -> bool:" in files[SCRIPT_PATH]
    assert "func quest_status() -> Dictionary:" in files[SCRIPT_PATH]
    assert "func _mount_hud()" in files[SCRIPT_PATH]
    assert verify_native_quest(files)
    ok, problems = check_ok(files)
    assert ok, problems
    manifest = source_manifest(files)
    assert manifest["files"][QUEST_PATH] == receipt["quest_sha256"]
    assert manifest["file_count"] == len(before) + 2


def test_native_quest_is_deterministic_and_binds_to_actual_room_locations():
    a, ar = attach_native_quest(base(), length=5)
    b, br = attach_native_quest(base(), length=5)
    assert a == b and ar == br
    document = json.loads(a[QUEST_PATH])
    assert document["schema"] == SCHEMA
    graph = json.loads(a["data/rooms.json"])
    ids = {room["id"] for room in graph["rooms"]}
    steps = document["slice"]["world_quest"]["quest"]["steps"]
    assert len(steps) == 5
    assert set(step["location"] for step in steps) <= ids
    assert document["slice"]["proof"]["status"] == "completed"


def test_source_manifest_detects_post_generation_corruption():
    files, receipt = attach_native_quest(base())
    assert verify_native_quest(files)
    forged = dict(files)
    source = json.loads(forged[QUEST_PATH])
    source["slice"]["world_quest"]["quest"]["steps"][0]["location"] = "r99"
    forged[QUEST_PATH] = json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n"
    assert not verify_native_quest(forged)
    forged = dict(files)
    forged["data/rooms.json"] += " "
    assert not verify_native_quest(forged)
    forged = dict(files)
    forged[SCRIPT_PATH] += "\n# modified"
    assert not verify_native_quest(forged)
    forged = dict(files)
    forged["project.godot"] = forged["project.godot"].replace("QuestRuntime=", "QuestOld=")
    assert not verify_native_quest(forged)


def test_duplicate_or_invalid_room_graphs_fail_closed_without_mutation():
    for bad in (
        "not-json", "{}", json.dumps({"rooms": [], "edges": []}),
    ):
        files = base()
        files["data/rooms.json"] = bad
        before = dict(files)
        with pytest.raises(NativeQuestError):
            attach_native_quest(files)
        assert files == before
    files = base()
    graph = json.loads(files["data/rooms.json"])
    graph["rooms"][1]["id"] = "r00"
    files["data/rooms.json"] = json.dumps(graph)
    with pytest.raises(NativeQuestError):
        attach_native_quest(files)


@pytest.mark.parametrize("length", (0, -1, 9, True, 1.5, "3"))
def test_invalid_quest_length_rejected(length):
    with pytest.raises(NativeQuestError, match="length"):
        attach_native_quest(base(), length=length)


def test_existing_project_path_or_autoload_conflicts_rejected():
    for key in (QUEST_PATH, SCRIPT_PATH):
        files = base()
        files[key] = "existing"
        with pytest.raises(NativeQuestError, match="conflicts"):
            attach_native_quest(files)
    files = base()
    files["project.godot"] = files["project.godot"].replace(
        'InputBind="*res://scripts/autoloads/input_bind.gd"\n', ""
    )
    with pytest.raises(NativeQuestError, match="autoload"):
        attach_native_quest(files)


def test_real_gameforge_emit_stage_includes_quest_before_manifest_and_checks(monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = base()
    ctx = {
        "era": "extraction_now", "target": "godot",
        "files": dict(original), "quest_content": True, "quest_length": 3,
        "project_root": None, "playtest_mode": "off",
    }
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    assert verify_native_quest(ctx["files"])
    assert ctx["file_count"] == len(original) + 2
    assert ctx["native_quest_receipt"]["replay_verified"] is True
    assert source_manifest(ctx["files"])["file_count"] == len(original) + 2


def test_non_quest_builds_are_byte_identical_in_emit(monkeypatch):
    from skeleton.context import pipeline
    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    before = base()
    ctx = {
        "era": "extraction_now", "files": deepcopy(before),
        "project_root": None, "playtest_mode": "off",
    }
    pipeline._stage_emit(ctx)
    assert ctx["files"] == before
    assert "native_quest_receipt" not in ctx


def test_api_route_forwards_opt_in_and_preserves_legacy_default(monkeypatch):
    from backend.routes.skeleton_gameforge import RunRequest, run
    from skeleton.context.pipeline import GameForgeRun
    seen = []

    class Stub:
        def execute(self, vision, **kwargs):
            seen.append((vision, kwargs))
            return {"succeeded": True, "files": {"project.godot": "content"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    legacy = run(RunRequest(vision="Build original game"))
    assert legacy["file_names"] == ["project.godot"]
    assert "quest_content" not in seen[-1][1]
    advanced = run(RunRequest(vision="Build original game", quest_content=True, quest_length=5))
    assert advanced["succeeded"]
    assert seen[-1][1]["quest_content"] is True
    assert seen[-1][1]["quest_length"] == 5


@pytest.mark.parametrize("bad", (0, 9, -7))
def test_api_rejects_invalid_quest_length(bad):
    from pydantic import ValidationError
    from backend.routes.skeleton_gameforge import RunRequest
    with pytest.raises(ValidationError):
        RunRequest(quest_content=True, quest_length=bad)
