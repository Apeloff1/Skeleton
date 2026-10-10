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
