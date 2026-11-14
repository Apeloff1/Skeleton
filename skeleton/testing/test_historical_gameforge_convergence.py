"""End-to-end source contracts for the unified historical game creator.

The converged candidate includes #5296/#5306 Galaxy instruments and #5304/
#5310 native quests in the *same* GameForgeRun execution. These tests check
source emission and request forwarding; native Godot/device boot is separate.
"""
from __future__ import annotations

import json

from skeleton.context.galaxy_profile import (
    ARTIFACT_PATH, galaxy_profile_receipt, normalise_galaxy_profile,
)
from skeleton.ai.game_builder.godot_quest_bridge import (
    QUEST_PATH, SCRIPT_PATH, verify_native_quest,
)
from skeleton.forge.eras import compile_era
from skeleton.forge.godot_emit import emit_godot
from skeleton.forge.source_manifest import source_manifest
from skeleton.testing.test_galaxy_profile import sample


def test_single_emission_preserves_full_galaxy_profile_and_native_quest(monkeypatch):
    from skeleton.context import pipeline

    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    profile = normalise_galaxy_profile(sample())
    files = emit_godot(compile_era("extraction_now"))
    original = dict(files)
    ctx = {
        "era": "extraction_now",
        "target": "godot",
        "files": files,
        "galaxy_profile": profile,
        "galaxy_receipt": galaxy_profile_receipt(profile),
        "quest_content": True,
        "quest_length": 3,
        "project_root": None,
        "playtest_mode": "off",
    }
    result = pipeline._stage_emit(ctx)
    assert result["emitted"] is True
    produced = ctx["files"]
    assert ARTIFACT_PATH in produced
    assert QUEST_PATH in produced
    assert SCRIPT_PATH in produced
    assert json.loads(produced[ARTIFACT_PATH]) == profile
    assert verify_native_quest(produced)
    assert ctx["native_quest_receipt"]["steps"] == 3
    assert produced["data/rooms.json"] == original["data/rooms.json"]
    assert produced["scripts/autoloads/game_state.gd"] == original["scripts/autoloads/game_state.gd"]
    manifest = source_manifest(produced)
    assert manifest["file_count"] == len(original) + 3
    assert ctx["native_quest_receipt"]["quest_sha256"] == manifest["files"][QUEST_PATH]


def test_galaxy_only_and_quest_only_do_not_change_each_others_receipts(monkeypatch):
    from skeleton.context import pipeline

    monkeypatch.setattr(pipeline, "_commit", lambda *args, **kwargs: None)
    original = emit_godot(compile_era("extraction_now"))
    profile = normalise_galaxy_profile(sample())
    contexts = []
    for galaxy, quest in ((True, False), (False, True), (False, False)):
        ctx = {
            "era": "extraction_now", "target": "godot",
            "files": dict(original), "project_root": None,
            "playtest_mode": "off", "quest_content": quest,
            "quest_length": 4,
            "galaxy_profile": profile if galaxy else None,
            "galaxy_receipt": galaxy_profile_receipt(profile) if galaxy else None,
        }
        pipeline._stage_emit(ctx)
        contexts.append(ctx)
    assert ARTIFACT_PATH in contexts[0]["files"] and QUEST_PATH not in contexts[0]["files"]
    assert ARTIFACT_PATH not in contexts[1]["files"] and QUEST_PATH in contexts[1]["files"]
    assert contexts[2]["files"] == original
    assert "native_quest_receipt" not in contexts[0]
    assert "native_quest_receipt" in contexts[1]
    assert "native_quest_receipt" not in contexts[2]


def test_http_route_forwards_every_recovered_input_to_one_gameforge_execution(monkeypatch):
    from backend.routes.skeleton_gameforge import RunRequest, run
    from skeleton.context.pipeline import GameForgeRun

    called = {}
    class Stub:
        def execute(self, vision, **opts):
            called["vision"] = vision
            called["opts"] = opts
            return {"succeeded": True, "files": {"project.godot": "content"}}

    monkeypatch.setattr(GameForgeRun, "live", lambda: Stub())
    profile = sample()
    req = RunRequest(
        vision="Original cross-genre adventure", archetype="auto",
        target="godot", answers={"genre": "rpg"},
        operator_axes={"risk": 0.9, "tempo": 0.4},
        galaxy_profile=profile, quest_content=True, quest_length=6,
    )
    result = run(req)
    assert result["succeeded"]
    assert "files" not in result
    assert called["vision"] == "Original cross-genre adventure"
    assert called["opts"]["answers"] == {"genre": "rpg"}
    assert called["opts"]["operator_axes"] == {"risk": 0.9, "tempo": 0.4}
    assert called["opts"]["galaxy_profile"] == profile
    assert called["opts"]["quest_content"] is True
    assert called["opts"]["quest_length"] == 6
