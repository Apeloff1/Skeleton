"""Tests for gap CI verification."""
from skeleton.app.gap_ci import verify

def test_ci_verify():
    assert verify() == 0
