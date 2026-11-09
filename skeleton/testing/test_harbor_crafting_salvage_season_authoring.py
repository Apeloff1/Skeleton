"""Transactional season authoring with live replay preview and CAS validation."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage_season_authoring import (
    edit_season, verify_season_revision,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions
from skeleton.testing.test_harbor_crafting_salvage_season import season_board, second_round


def test_edit_round_points_with_replay_safe_preview():
    source, _ = inputs()
    board = season_board()
    edits = [{"op": "set-round", "id": "harbor_cache_return",
              "field": "points", "value": 20}]
    revision = edit_season(source, board, edits, expected_board_digest=digest(board),
                           preview_round_actions=[actions(), second_round()])
    assert verify_season_revision(revision)["rounds"][1]["points"] == 20
    assert revision["preview_before"]["score"] == 36
    assert revision["preview_after"]["score"] == 49
    assert board["rounds"][1]["points"] == 7


def test_edit_nested_salvage_board_rejects_unplayable_preview():
    source, _ = inputs()
    board = season_board()
    edits = [{"op": "edit-board", "id": "harbor_cache_return", "edits": [
        {"op": "move-site", "id": "tide_cache", "at": [5, 1]},
    ]}]
    with pytest.raises(HarborError):
        edit_season(source, board, edits, expected_board_digest=digest(board),
                    preview_round_actions=[actions(), second_round()])
    with pytest.raises(HarborError, match="stale"):
        edit_season(source, board, edits, expected_board_digest="0" * 64)


def test_tampered_revision_with_recomputed_digest_fails():
    source, _ = inputs()
    board = season_board()
    revision = edit_season(source, board, [{"op": "set-round",
        "id": "skiff_and_cache", "field": "points", "value": 8}],
        expected_board_digest=digest(board))
    damaged = deepcopy(revision)
    damaged["after"]["rounds"][0]["points"] = 100
    damaged["revision_digest"] = digest({k: v for k, v in damaged.items()
                                           if k != "revision_digest"})
    with pytest.raises(HarborError):
        verify_season_revision(damaged)
