from skeleton.jeeves.game_frontier_milestone_index import MILESTONES, milestone_ids, require
import pytest


def test_index_has_eight():
    assert len(MILESTONES) == 8
    assert milestone_ids() == ("P0", "P1", "P2", "P3", "M4", "M5", "M6", "M7")


def test_all_candidate_only():
    assert all(m.claim == "candidate-only" for m in MILESTONES)


def test_require_known():
    assert require("M7").module == "game_frontier_campaign"


def test_require_unknown():
    with pytest.raises(KeyError):
        require("M99")
