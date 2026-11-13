"""Replay-derived cooperative branch comparison and selection acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import (
    import_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_compare import (
    accept_comparison, cli, compare_party, select_party,
    verify_comparison, verify_selection,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def branches():
    source, turns = original_party()
    won = simulate_party(source, turns)
    short = simulate_party(source, turns[:len(turns) // 2])
    alternative = simulate_party(source, [
        {"player_id": source["players"][0]["player_id"],
         "action": {"kind": "pass"}}])
    return source, won, short, alternative


def test_common_prefix_and_shorter_branch(branches):
    _, won, short, _ = branches
    report = compare_party(won, short)
    assert report["diverged"] is False
    assert report["common_prefix_turns"] == len(short["journal"])
    assert report["right_remaining_turns"] == 0
    assert report["left_remaining_turns"] > 0
    assert verify_comparison(won, short, json.loads(json.dumps(report))) == report


def test_divergent_choice_consequences_and_export(branches):
    _, won, _, other = branches
    report = compare_party(won, other)
    assert report["diverged"]
    assert report["common_prefix_turns"] == 0
    assert report["left"]["phase"] == "won"
    assert report["right"]["phase"] == "active"
    selected = select_party(won, other, "left",
                            expected_left_digest=won["state_digest"],
                            expected_right_digest=other["state_digest"])
    assert import_party(selected["portable"]) == won
    assert verify_selection(won, other, selected) == selected


def test_source_mismatch_rejected(branches):
    source, won, _, _ = branches
    other_source = copy.deepcopy(source)
    other_source["players"][0]["player_id"] = "foreign"
    foreign = simulate_party(other_source, [])
    with pytest.raises(SceneTravelError, match="source mismatch"):
        compare_party(won, foreign)


def test_stale_selection_and_invalid_choice_fail_closed(branches):
    _, won, _, other = branches
    for choice, a, b in [
        ("left", "0" * 64, other["state_digest"]),
        ("right", won["state_digest"], "0" * 64),
        ("both", won["state_digest"], other["state_digest"]),
    ]:
        with pytest.raises(SceneTravelError):
            select_party(won, other, choice,
                         expected_left_digest=a, expected_right_digest=b)


@pytest.mark.parametrize("field", [
    "common_prefix_turns", "left_minus_right_credits", "diverged",
])
def test_tampered_comparison_fails_even_with_recomputed_checksum(branches, field):
    _, won, _, other = branches
    report = compare_party(won, other)
    forged = copy.deepcopy(report)
    forged[field] = 999 if field != "diverged" else False
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_comparison(won, other, forged)


def test_checksum_only_tamper_rejected(branches):
    _, won, _, other = branches
    report = compare_party(won, other)
    forged = copy.deepcopy(report)
    forged["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_comparison(won, other, forged)


def test_tampered_selection_fails_even_with_recomputed_checksum(branches):
    _, won, _, other = branches
    selected = select_party(won, other, "left",
                            expected_left_digest=won["state_digest"],
                            expected_right_digest=other["state_digest"])
    forged = copy.deepcopy(selected)
    forged["selected_state_digest"] = "0" * 64
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_selection(won, other, forged)


def test_end_to_end_cli_and_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-compare", "demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["comparison"]["left"]["phase"] == "won"
    assert report["selection"]["choice"] == "left"
    assert cli(["compare", "--left-json", "{}", "--right-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
