"""Backend GameForge API keeps complete Galaxy source without implicit playback."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from backend.routes import skeleton_gameforge as api
from skeleton.forge.galaxy_authoring import MATRIX_FIELDS, PROFILE_SCHEMA


def _profile():
    config = {
        "title": "Original island game",
        "genre": "rpg",
        "narrative_phases": {"prelude": {"count": 3}},
        "extra_params": {"quest_variety": 99},
        "style_params": {"graphic_style": "original"},
    }
    config.update({name: {"chapter_1": {"count": 5, "complexity": 3}}
                   for name in MATRIX_FIELDS})
    return {"schema": PROFILE_SCHEMA, "config": config}


def test_public_post_run_forwards_complete_authoring_to_canonical_pipeline(monkeypatch):
    sent = {}
    class FakeRun:
        def execute(self, vision, **kwargs):
            sent.update({"vision": vision, **kwargs})
            return {"succeeded": True, "files": {"project.godot": "[application]\n"}}
    monkeypatch.setattr("skeleton.context.pipeline.GameForgeRun.live",
                        lambda: FakeRun())
    profile = _profile()
    result = api.run(api.RunRequest(
        vision="Original quest world", galaxy_profile=profile,
        playable_content=True, playable_archetype="crafting",
        playable_main_scene=True, playtest="require",
    ))
    assert sent["galaxy_profile"] == profile
    assert sent["playable_archetype"] == "crafting"
    assert sent["playable_main_scene"] is True
    assert result["file_names"] == ["project.godot"]
    assert "files" not in result
    assert sent["playtest"] == "require"


@pytest.mark.parametrize("damage", [
    lambda p: p.update(schema="unknown"),
    lambda p: p["config"].pop("unique_flair_matrix"),
    lambda p: p["config"]["qa_matrix"]["chapter_1"].update(count=float("nan")),
    lambda p: p["config"].update(prototype={"__proto__": 1}),
])
def test_invalid_authoring_never_enters_run_pipeline(damage):
    profile = _profile()
    damage(profile)
    with pytest.raises(ValidationError):
        api.RunRequest(galaxy_profile=profile)


def test_default_gameforge_request_is_byte_compatible_without_new_optins():
    req = api.RunRequest()
    assert req.galaxy_profile is None
    assert req.playable_archetype is None
    assert req.playable_main_scene is False
    assert req.playable_content is False


def test_authoring_validation_clones_request_without_editing_user_payload():
    original = _profile()
    accepted = api.RunRequest(galaxy_profile=original)
    clone = copy.deepcopy(accepted.galaxy_profile)
    accepted.galaxy_profile["config"]["title"] = "changed"
    assert original["config"]["title"] == "Original island game"
    assert clone["config"]["title"] == "Original island game"
