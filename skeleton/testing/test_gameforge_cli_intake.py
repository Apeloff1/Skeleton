"""Executable regressions for GameForge CLI intake/playtest and tensor fidelity."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from skeleton.__main__ import _load_run_answers, _parse_run_args, main
from skeleton.context.questionnaire import intake


def test_run_args_carry_questionnaire_and_build_policy(tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"pace": "unhurried", "genre": "rpg"}), encoding="utf-8")
    parsed = _parse_run_args([
        "a", "quiet", "village", "--answers-file", str(answers),
        "--playtest", "require", "--repair-mode", "suggest",
        "--archetype", "auto", "--out", str(tmp_path / "game"), "--json",
    ])
    assert parsed[0] == "a quiet village"
    assert parsed[2] == str(tmp_path / "game")
    assert parsed[4] is True
    assert parsed[7] == {"pace": "unhurried", "genre": "rpg"}
    assert parsed[8:] == ("require", "suggest", "auto")


@pytest.mark.parametrize("source", [
    "[]", '{"pace":"broken"}', '{"unknown":"yes"}', '{"pace":7}', "{broken",
])
def test_answers_reject_ignored_or_invalid_operator_intent(source):
    with pytest.raises(ValueError):
        _load_run_answers(source)


def test_run_rejects_malformed_flags_before_running(capsys):
    assert main(["run", "a game", "--playtest", "maybe"]) == 2
    assert "playtest" in capsys.readouterr().err
    assert main(["run", "--answers", '{"pace":"broken"}']) == 2


def test_run_passes_answers_playtest_and_repair_into_real_pipeline(capsys):
    output = {"succeeded": True, "era": "cozy_wholesome", "mass": 1.0,
              "forge": {"file_count": 12}, "sim": {"passed": True},
              "playtest": {"passed": True}, "intake": {"answers": {"pace": "unhurried"}}}
    with patch("skeleton.context.pipeline.GameForgeRun.live") as live:
        live.return_value.execute.return_value = output
        assert main(["run", "--answers", '{"pace":"unhurried"}',
                     "--playtest", "auto", "--repair-mode", "suggest",
                     "--archetype", "auto", "--json"]) == 0
        kwargs = live.return_value.execute.call_args.kwargs
        assert kwargs["answers"] == {"pace": "unhurried"}
        assert kwargs["playtest"] == "auto"
        assert kwargs["repair_mode"] == "suggest"
        assert kwargs["archetype"] == "auto"
    assert json.loads(capsys.readouterr().out)["playtest"]["passed"] is True


def test_questionnaire_tensor_survives_pipeline_tensor_stage():
    from skeleton.context.cockpit import Cockpit
    from skeleton.context.pipeline import _stage_tensor

    taken = intake({"pace": "unhurried", "death": "nothing"})
    cockpit = Cockpit()
    with patch("skeleton.context.pipeline._commit"):
        _stage_tensor({"era": taken.era, "cockpit": cockpit,
                       "intake_tensor": taken.tensor})
    assert cockpit.tensor.values == taken.tensor.values
    # Intake nudges individual axes; it is not just the era factory preset.
    from skeleton.context.tensor import ContextTensor
    assert cockpit.tensor.values != ContextTensor.from_era(taken.era).values


def test_explicit_era_override_uses_requested_era_tensor():
    from skeleton.context.cockpit import Cockpit
    from skeleton.context.pipeline import _stage_tensor
    from skeleton.context.tensor import ContextTensor

    cockpit = Cockpit()
    with patch("skeleton.context.pipeline._commit"):
        _stage_tensor({"era": "soulslike", "cockpit": cockpit,
                       "intake_tensor": None})
    assert cockpit.tensor.values == ContextTensor.from_era("soulslike").values
