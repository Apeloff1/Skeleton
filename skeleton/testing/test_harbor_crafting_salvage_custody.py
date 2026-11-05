"""Salvage transactional editing, journals, packaging and acceptance regression."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_salvage import build_salvage
from skeleton.game.gameplay.harbor_crafting_salvage_authoring import (
    edit_salvage, verify_salvage_revision,
)
from skeleton.game.gameplay.harbor_crafting_salvage_journal import (
    append_salvage_journal, create_salvage_journal, fast_forward_salvage_journal,
    fork_salvage_journal, salvage_journal_at, verify_salvage_journal,
)
from skeleton.game.gameplay.harbor_crafting_salvage_package import (
    build_salvage_package, play_salvage_package, verify_salvage_package,
    verify_salvage_package_play,
)
from skeleton.game.gameplay.harbor_crafting_salvage_acceptance import (
    accept_salvage, verify_salvage_acceptance,
)
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions


def test_editor_preview_and_exact_revision():
    source, board = inputs()
    edit = [{"op": "set-site", "id": "tide_cache", "field": "reward", "value": 12}]
    revision = edit_salvage(source, board, edit, expected_board_digest=digest(board),
                            preview_actions=actions())
    assert verify_salvage_revision(revision)["sites"][1]["reward"] == 12
    assert revision["preview_before"] != revision["preview_after"]
    assert board["sites"][1]["reward"] == 7
    with pytest.raises(HarborError, match="stale"):
        edit_salvage(source, board, edit, expected_board_digest="0" * 64)


def test_editor_rejects_unplayable_preview_and_invalid_batch():
    source, board = inputs()
    with pytest.raises(HarborError):
        edit_salvage(source, board,
                     [{"op": "move-site", "id": "tide_cache", "at": [5, 1]}],
                     expected_board_digest=digest(board), preview_actions=actions())
    with pytest.raises(HarborError):
        edit_salvage(source, board, [{"op": "set-rule", "field": "schema", "value": "x"}],
                     expected_board_digest=digest(board))


def test_cas_journal_append_fork_and_fast_forward():
    source, board = inputs()
    journal = create_salvage_journal(source, board)
    first = append_salvage_journal(journal, actions()[:4], expected_tip=journal["tip"])
    full = append_salvage_journal(first, actions()[4:], expected_tip=first["tip"])
    checked = verify_salvage_journal(full)
    assert checked["revision_count"] == 2
    assert checked["report"]["state"]["complete"]
    assert salvage_journal_at(full, 1)["actions"] == actions()[:4]
    fork = fork_salvage_journal(full, 1)
    assert fast_forward_salvage_journal(fork, full) == full
    with pytest.raises(HarborError, match="stale"):
        append_salvage_journal(first, actions()[4:], expected_tip="0" * 64)
    with pytest.raises(HarborError, match="history conflict"):
        fast_forward_salvage_journal(full, first)


def test_package_play_is_source_bound_and_replay_verified():
    source, board = inputs()
    package = build_salvage_package(source, board, package_id="lantern_salvage")
    assert verify_salvage_package(package) == package
    play = play_salvage_package(package, actions(), require_complete=True)
    assert verify_salvage_package_play(play, require_complete=True)["reward"] == 11
    damaged = deepcopy(play)
    damaged["report"]["state"]["reward"] = 999
    damaged["play_digest"] = digest({k: v for k, v in damaged.items() if k != "play_digest"})
    with pytest.raises(HarborError):
        verify_salvage_package_play(damaged)


def test_full_acceptance_and_adversarial_event_chain():
    source, board = inputs()
    accepted = accept_salvage(source, board, actions())
    assert verify_salvage_acceptance(accepted)["complete"]
    assert accepted["journal"]["tip"] == accepted["report"]["report_digest"]
    damaged = deepcopy(accepted)
    damaged["journal"]["revisions"][0]["actions"][0]["direction"] = "west"
    damaged["acceptance_digest"] = digest({k: v for k, v in damaged.items()
                                             if k != "acceptance_digest"})
    with pytest.raises(HarborError):
        verify_salvage_acceptance(damaged)


def test_incomplete_cannot_be_accepted():
    source, board = inputs()
    with pytest.raises(HarborError, match="not completed"):
        accept_salvage(source, board, actions()[:3])
