from skeleton.jeeves.agent.delivery_milestones import DELIVERY_MILESTONES, delivery_ids, require_delivery
import pytest


def test_eight_stages():
    assert len(DELIVERY_MILESTONES) == 8
    assert delivery_ids() == ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8")


def test_all_candidate():
    assert all(m.claim == "candidate-only" for m in DELIVERY_MILESTONES)


def test_require():
    assert require_delivery("D8").stage == "final-receipt"


def test_unknown():
    with pytest.raises(KeyError):
        require_delivery("D99")
