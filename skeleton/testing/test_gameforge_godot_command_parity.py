"""Godot API/CLI share the same generation engine; JSON remains compatible."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from skeleton.app.runtime.command_contracts import CommandError
from skeleton.app.runtime.runtime_commands import _run_handler
from skeleton.context.questionnaire import validate_answers


def _state():
    return SimpleNamespace(gameforge=Mock())


def test_godot_command_invokes_ten_stage_pipeline_in_memory():
    handler = _run_handler(_state())
    with patch("skeleton.context.pipeline.GameForgeRun") as cls:
        cls.return_value.execute.return_value = {
            "succeeded": True, "era": "cozy_wholesome",
            "files": {"project.godot": "config"},
            "intake": {"answers": {"pace": "unhurried"}},
        }
        result = handler({"target": "godot", "vision": "quiet village",
                          "answers": {"pace": "unhurried"},
                          "repair": True, "playtest": "auto"})
    assert result["engine"] == "gameforge_ten_stage"
    assert result["game"]["files"]["project.godot"] == "config"
    kwargs = cls.return_value.execute.call_args.kwargs
    assert "project_root" not in kwargs
    assert kwargs["target"] == "godot"
    assert kwargs["answers"] == {"pace": "unhurried"}
    assert kwargs["playtest"] == "auto"


@pytest.mark.parametrize("key,value", [
    ("project_root", "/tmp/another-user"), ("out", "/etc"),
    ("overwrite", True),
])
def test_remote_caller_cannot_control_server_paths(key, value):
    with pytest.raises(CommandError) as caught:
        _run_handler(_state())({"target": "godot", "answers": {}, key: value})
    assert caught.value.code == "invalid_argument"


def test_godot_rejects_invalid_answers_before_any_pipeline_call():
    with patch("skeleton.context.pipeline.GameForgeRun") as cls:
        with pytest.raises(CommandError) as caught:
            _run_handler(_state())({"target": "godot", "answers": {"pace": "unknown"}})
    assert caught.value.code == "invalid_argument"
    cls.assert_not_called()


def test_legacy_json_target_still_uses_existing_game_spec():
    state = _state()
    state.gameforge.run.return_value.to_dict.return_value = {"spec_id": "abc"}
    result = _run_handler(state)({"answers": {"genre": "rpg"}})
    assert result == {"game": {"spec_id": "abc"}, "status": "generated"}
    assert state.gameforge.run.call_args.kwargs["target"] == "json"


def test_pipeline_failure_is_not_reported_as_success():
    with patch("skeleton.context.pipeline.GameForgeRun") as cls:
        cls.return_value.execute.return_value = {"succeeded": False}
        with pytest.raises(CommandError) as caught:
            _run_handler(_state())({"target": "godot", "answers": {}})
    assert caught.value.code == "unavailable"


@pytest.mark.parametrize("bad", [{"bad":"yes"}, {"pace":"nope"}, {"pace":42}])
def test_shared_answer_validation_rejects_invalid_data(bad):
    with pytest.raises(ValueError):
        validate_answers(bad)
