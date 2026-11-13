"""Deterministic scoreboard never trusts claimed player score or source identity."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage_season_leaderboard import (
    build_season_leaderboard, verify_season_leaderboard,
)
from skeleton.testing.test_harbor_crafting_salvage_season import completed_season


def test_rank_by_verified_score_then_rounds_then_name():
    start, first, full = completed_season()
    entries = [{"player": "zoe", "save": first},
               {"player": "ada", "save": full},
               {"player": "ben", "save": full}]
    board = build_season_leaderboard(entries)
    ranking = verify_season_leaderboard(board)
    assert [r["player"] for r in ranking] == ["ada", "ben", "zoe"]
    assert ranking[0]["score"] == 36


def test_scoreboard_rejects_duplicate_and_resealed_score():
    start, first, full = completed_season()
    with pytest.raises(HarborError):
        build_season_leaderboard([{"player": "same", "save": first},
                                  {"player": "same", "save": full}])
    board = build_season_leaderboard([{"player": "ada", "save": full}])
    damaged = deepcopy(board)
    damaged["ranking"][0]["score"] += 1
    damaged["leaderboard_digest"] = digest({k: v for k, v in damaged.items()
                                              if k != "leaderboard_digest"})
    with pytest.raises(HarborError):
        verify_season_leaderboard(damaged)
