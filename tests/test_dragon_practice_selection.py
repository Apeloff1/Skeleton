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


def test_actual_practice_attempt_is_reexecuted_not_trusted_metadata():
    game = load_practice_game("dragon-practice-001", authorized=True)
    verified = verified_practice_run(
        game.game_id, game.proof, authorized=True,
    )
    assert verified["completed"] is True
    assert verified["status"] == "won"
    assert verified["steps"] == len(game.proof.action_receipts)
    assert verified["world_digest"] == game.world.digest
    assert verified["training_authorized"] is False
    assert verified["memory_promotion_authorized"] is False
    partial = play_actions(game.world, (), authorized=True)
    advisory = verified_practice_run(game.game_id, partial, authorized=True)
    assert advisory["completed"] is False
    assert advisory["status"] == "playing"
    with pytest.raises(PermissionError):
        verified_practice_run(game.game_id, game.proof, authorized="true")


def test_practice_attempt_rejects_foreign_world_and_manipulated_ledger():
    left = load_practice_game("dragon-practice-001", authorized=True)
    right = load_practice_game("dragon-practice-002", authorized=True)
    with pytest.raises(ValueError):
        verified_practice_run(left.game_id, right.proof, authorized=True)
    forged = replace(
        left.proof, action_receipts=left.proof.action_receipts[:-1],
    )
    with pytest.raises(ValueError):
        verified_practice_run(left.game_id, forged, authorized=True)
    with pytest.raises(PracticeSelectionError):
        verified_practice_run(left.game_id, object(), authorized=True)


def test_portfolio_receipt_binds_exact_100_verified_game_worlds():
    receipt = practice_portfolio_receipt(authorized=True)
    assert receipt["schema"] == "skeleton.dragon.practice_portfolio.v1"
    assert receipt["game_count"] == len(receipt["games"]) == 100
    assert len({x["world_digest"] for x in receipt["games"]}) == 100
    assert receipt["digest"] == canonical_digest(
        {k: v for k, v in receipt.items() if k != "digest"}
    )
    assert receipt == practice_portfolio_receipt(authorized=True)
    assert receipt["native_binary_build_verified"] is False
    assert receipt["originality_independently_cleared"] is False
    assert receipt["release_authorized"] is False


def test_game_comparison_reports_factual_delta_not_quality_judgment():
    a = load_practice_game("dragon-practice-001", authorized=True)
    b = load_practice_game("dragon-practice-002", authorized=True)
    evidence = compare_practice_challenges(a.game_id, b.game_id, authorized=True)
    assert evidence["first_world_digest"] == a.world.digest
    assert evidence["second_world_digest"] == b.world.digest
    assert evidence["route_step_difference"] == (
        len(b.proof.action_receipts) - len(a.proof.action_receipts)
    )
    assert evidence["hazard_difference"] == (
        len(b.world.levels[0].hazards) - len(a.world.levels[0].hazards)
    )
    assert evidence["quality_comparison_authorized"] is False
    with pytest.raises(PracticeSelectionError):
        compare_practice_challenges(a.game_id, a.game_id, authorized=True)
    with pytest.raises(PermissionError):
        compare_practice_challenges(a.game_id, b.game_id, authorized=1)
