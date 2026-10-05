import pytest

from skeleton.frontier.gameforge_receipt import Receipt


def test_receipt_exposes_acceptance_state():
    receipt = Receipt("r1", "accept", "admitted")
    assert receipt.accepted
    assert not receipt.rejected


def test_receipt_requires_request_id():
    with pytest.raises(ValueError):
        Receipt("", "accept", "admitted")
