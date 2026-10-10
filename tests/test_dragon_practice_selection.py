"""Verified original practice-game discovery, progression and user play receipts."""
from __future__ import annotations

from dataclasses import replace
import io
import json
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from pathlib import Path

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.playable_simulation import play_actions
from skeleton.ai.game_builder.practice_game_library import load_practice_game
from skeleton.ai.game_builder.practice_game_selection import (
    PracticeSelectionError, compare_practice_challenges, filter_practice_games,
    plan_practice_progression, practice_game_catalog, practice_portfolio_receipt,
    verified_practice_run,
)


def test_catalog_has_100_independently_solved_distinct_original_games():
    rows = practice_game_catalog(authorized=True)
    assert len(rows) == 100
    assert len({row.game_id for row in rows}) == 100
    assert len({row.world_digest for row in rows}) == 100
    assert rows[0].game_id == "dragon-practice-001"
    assert rows[-1].game_id == "dragon-practice-100"
    for entry in rows:
        assert entry.solution_steps >= 1
        assert entry.route_cost == (
            entry.solution_steps + 4 * entry.collectible_count + 3 * entry.hazard_count
        )
        assert entry.to_payload()["release_authorized"] is False


@pytest.mark.parametrize("theme", ["forest", "space", "desert", "ocean", "arcade"])
def test_theme_filter_uses_real_verified_content_and_sorted_route_cost(theme):
    entries = filter_practice_games(authorized=True, theme=theme, limit=100)
    assert len(entries) == 20
    assert all(row.theme == theme for row in entries)
    assert [(row.route_cost, row.game_id) for row in entries] == sorted(
        (row.route_cost, row.game_id) for row in entries
    )
    constrained = filter_practice_games(
        authorized=True, theme=theme, min_solution_steps=50,
        max_solution_steps=80, max_hazards=3, limit=7,
    )
    assert len(constrained) <= 7
    assert all(50 <= x.solution_steps <= 80 and x.hazard_count <= 3
               for x in constrained)


@pytest.mark.parametrize("options", [
    {"theme": "imaginary"}, {"min_solution_steps": -1},
    {"max_solution_steps": 20001},
    {"min_solution_steps": 50, "max_solution_steps": 49},
    {"max_hazards": True}, {"limit": 0}, {"limit": 101},
])
def test_filter_rejects_untrusted_or_unbounded_requests(options):
    with pytest.raises(PracticeSelectionError):
        filter_practice_games(authorized=True, **options)
    with pytest.raises(PermissionError):
        filter_practice_games(authorized=1)


@pytest.mark.parametrize("count", [1, 2, 5, 8, 20])
def test_progression_chooses_nonrepeating_increasing_replay_difficulty(count):
    first = plan_practice_progression(authorized=True, count=count)
    second = plan_practice_progression(authorized=True, count=count)
    assert first == second
    assert len(first) == count
    assert len({row.world_digest for row in first}) == count
    assert list(first) == sorted(first, key=lambda row: (row.route_cost, row.game_id))
    if count > 1:
        assert first[0].route_cost < first[-1].route_cost


def test_progression_respects_theme_and_refuses_insufficient_choices():
    ocean = plan_practice_progression(authorized=True, count=20, theme="ocean")
    assert len(ocean) == 20
    assert all(game.theme == "ocean" for game in ocean)
    for count in (0, -1, True, 21, 1.5):
        with pytest.raises(PracticeSelectionError):
            plan_practice_progression(authorized=True, count=count)
    with pytest.raises(PermissionError):
        plan_practice_progression(authorized="yes", count=3)
