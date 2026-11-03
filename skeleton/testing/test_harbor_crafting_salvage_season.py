"""Source-bound two-round salvage championship, CAS and deterministic forks."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, demo_actions, digest
from skeleton.game.gameplay.harbor_crafting_salvage_season import (
    append_salvage_round, compare_salvage_seasons, fast_forward_salvage_season,
    salvage_season_at, start_salvage_season, verify_salvage_season,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def season_board():
    return json.loads((FIXTURES / "harbor_lantern_quay_salvage_season.json").read_text())


def second_round():
    return demo_actions()[:-2] + [
        {"op": "salvage", "site": "tide_cache"},
        {"op": "offload"}, {"op": "deliver"}, {"op": "rescue"},
    ]


def completed_season():
    source, _ = inputs()
    start = start_salvage_season(source, season_board())
    first = append_salvage_round(start, actions(), expected_tip=start["tip"])
    full = append_salvage_round(first, second_round(), expected_tip=first["tip"])
    return start, first, full


def test_championship_two_rounds_and_replay():
    start, first, full = completed_season()
    assert verify_salvage_season(start)["rounds_earned"] == 0
    assert verify_salvage_season(first)["rounds_earned"] == 1
    status = verify_salvage_season(full, require_complete=True)
    assert status["complete"]
    assert status["score"] == 36
    assert salvage_season_at(full, 1) == first
    assert compare_salvage_seasons(start, full)["advanced_rounds"] == 2
    assert fast_forward_salvage_season(first, full) == full


def test_stale_lease_and_unearned_round_rejected():
    start, first, full = completed_season()
    with pytest.raises(HarborError, match="stale"):
        append_salvage_round(start, actions(), expected_tip="0" * 64)
    with pytest.raises(HarborError, match="already complete"):
        append_salvage_round(full, second_round(), expected_tip=full["tip"])
    with pytest.raises(HarborError, match="not completed"):
        append_salvage_round(first, second_round()[:4], expected_tip=first["tip"])


def test_season_fork_conflict_and_tamper():
    start, first, full = completed_season()
    damaged = deepcopy(full)
    damaged["score"] = 999
    damaged["save_digest"] = digest({k: v for k, v in damaged.items()
                                      if k != "save_digest"})
    with pytest.raises(HarborError):
        verify_salvage_season(damaged)
    alternative = deepcopy(first)
    alternative["board"]["rounds"][1]["points"] = 100
    alternative["save_digest"] = digest({k: v for k, v in alternative.items()
                                          if k != "save_digest"})
    with pytest.raises(HarborError):
        compare_salvage_seasons(alternative, full)
