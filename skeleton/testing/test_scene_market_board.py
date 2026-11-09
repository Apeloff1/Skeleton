"""The market board is a read-only replayed view, including bounded hints."""
from __future__ import annotations

import copy

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import new_market, original_market
from skeleton.game.gameplay.scene_market_board import (
    market_board, verify_market_board,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_board_is_repeatable_and_never_mutates_player_currency():
    source, _ = original_market()
    checkpoint = new_market(source)
    original = copy.deepcopy(checkpoint)
    a = market_board(checkpoint, hint_nodes=2, hint_depth=1)
    b = market_board(checkpoint, hint_nodes=2, hint_depth=1)
    assert a == b
    assert a["state_digest"] == checkpoint["state_digest"]
    assert verify_market_board(checkpoint, a) == a
    assert checkpoint == original


def test_rechecksummed_forged_balance_is_not_authoritative():
    source, _ = original_market()
    checkpoint = new_market(source)
    original = market_board(checkpoint, hint_nodes=2, hint_depth=1)
    forged = copy.deepcopy(original)
    forged["credits"] += 1000
    assert forged != original
    forged["checksum"] = dig(
        {key: value for key, value in forged.items() if key != "checksum"}
    )
    with pytest.raises(SceneTravelError):
        verify_market_board(checkpoint, forged)
