import pytest

from skeleton.frontier.gameforge_receipt import Receipt


def test_receipt_rejects_blank_identity():
    with pytest.raises(ValueError):
        Receipt("   ", "accept", "ok")


def test_receipt_requires_string_identity():
    with pytest.raises(ValueError):
        Receipt(123, "accept", "ok")
