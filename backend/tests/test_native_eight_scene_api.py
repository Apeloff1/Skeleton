"""Native scene qualification request is explicit and cannot be silently downgraded."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.routes import skeleton_gameforge as api
from skeleton.context import pipeline


def test_route_transfers_require_mode_and_selected_eight_mode_archetype(monkeypatch):
    captured = {}

    class FakeRun:
        def execute(self, vision, **kwargs):
            captured["vision"] = vision
            captured.update(kwargs)
            return {
                "succeeded": True, "files": {"project.godot": "[application]\n"},
                "playtest": {"status": "passed", "passed": True, "verified": False},
                "playable_scene_playtest": {
                    "status": "passed", "passed": True, "verified": False,
                    "scene": "res://scenes/archetypes/crafting/main.tscn",
                },
            }

    monkeypatch.setattr(pipeline.GameForgeRun, "live", lambda: FakeRun())
    result = api.run(api.RunRequest(
        vision="An original crafting survival experience",
        playable_content=True, playable_archetype="crafting",
        playtest="require",
    ))
    assert captured["playtest"] == "require"
    assert captured["playable_content"] is True
    assert captured["playable_archetype"] == "crafting"
    assert result["playable_scene_playtest"]["verified"] is False
    assert "files" not in result
    assert result["file_names"] == ["project.godot"]


@pytest.mark.parametrize("invalid", ["skip", "always", "none", "required", "false"])
def test_invalid_native_mode_rejected_by_public_request(invalid):
    with pytest.raises(ValidationError):
        api.RunRequest(vision="original game", playtest=invalid)


def test_native_verification_is_off_by_default():
    assert api.RunRequest().playtest is None
    assert api.RunRequest(playtest="off").playtest == "off"
