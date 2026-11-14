"""Deterministic rescue endings, branching consequences, tamper and CLI."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_weather_rescue import (
    new_rescue, original_rescue, play_rescue,
)
from skeleton.game.gameplay.scene_weather_rescue_epilogue import (
    original_epilogue, epilogue_rescue, verify_epilogue,
    compare_rescue_endings, verify_comparison,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_rescue_story_replays_terminal_reward():
    epilogue = original_epilogue()
    assert epilogue["story"]["phase"] == "won"
    assert epilogue["story"]["safe_npcs"] == ["canal_medic"]
    assert epilogue["story"]["earned"] == 25
    assert epilogue["story"]["lost_npcs"] == []
    assert "reached shelter" in epilogue["story"]["lines"][0]["text"]
    assert verify_epilogue(json.loads(json.dumps(epilogue))) == epilogue


def test_active_rescue_never_misrepresented_as_terminal_victory():
    source, _ = original_rescue()
    epilogue = epilogue_rescue(new_rescue(source))
    assert epilogue["story"]["phase"] == "active"
    assert epilogue["story"]["safe_npcs"] == []
    assert epilogue["story"]["unresolved_npcs"] == ["canal_medic"]
    assert epilogue["story"]["earned"] == 0
    assert verify_epilogue(epilogue) == epilogue


def test_deterministic_branch_comparison_and_divergence():
    source, actions = original_rescue()
    early = play_rescue(source, actions[:1])
    finished = play_rescue(source, actions)
    comparison = compare_rescue_endings(early, finished)
    detail = comparison["comparison"]
    assert detail["source_digest"] == early["source_digest"]
    assert detail["earned_delta"] == 25
    assert detail["safe_delta"] == 1
    assert detail["first_divergence"] == 1
    assert detail["changed_npcs"][0]["npc_id"] == "canal_medic"
    assert verify_comparison(json.loads(json.dumps(comparison))) == comparison
    same = compare_rescue_endings(finished, copy.deepcopy(finished))
    assert same["comparison"]["first_divergence"] is None
    assert same["comparison"]["outcomes_equal"] is True


@pytest.mark.parametrize("change", [
    lambda e: e["story"].update(earned=999),
    lambda e: e["story"]["lines"][0].update(text="invented"),
    lambda e: e["session"]["state"].update(earned=999),
    lambda e: e["session"]["save"].update(parent_digest="forged"),
    lambda e: e.update(receipt="forged"),
])
def test_forged_story_source_save_and_receipt_rejected(change):
    bad = copy.deepcopy(original_epilogue())
    change(bad)
    with pytest.raises(SceneTravelError):
        verify_epilogue(bad)


def test_comparison_fails_closed_on_forged_deltas_and_different_sources():
    source, actions = original_rescue()
    first = new_rescue(source)
    second = play_rescue(source, actions)
    report = compare_rescue_endings(first, second)
    bad = copy.deepcopy(report)
    bad["comparison"]["earned_delta"] = 5000
    with pytest.raises(SceneTravelError):
        verify_comparison(bad)
    modified = copy.deepcopy(source)
    modified["npcs"][0]["reward"] = 30
    with pytest.raises(SceneTravelError, match="source mismatch"):
        compare_rescue_endings(first, new_rescue(modified))


def test_installed_cli_demo_verify_and_branch_compare(capsys):
    assert main(["scene-rescue-epilogue", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["story"]["earned"] == 25
    assert main(["scene-rescue-epilogue", "verify",
                 "--epilogue-json", json.dumps(result)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    source, actions = original_rescue()
    first = new_rescue(source)
    second = play_rescue(source, actions)
    assert main(["scene-rescue-epilogue", "compare",
                 "--first-json", json.dumps(first),
                 "--second-json", json.dumps(second)]) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["comparison"]["earned_delta"] == 25
    assert main(["scene-rescue-epilogue", "verify-comparison",
                 "--comparison-json", json.dumps(comparison)]) == 0
    assert json.loads(capsys.readouterr().out) == comparison
