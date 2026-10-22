"""Tests for gap readiness probe."""
from skeleton.app.gap_probe import probe

def test_probe_ready():
    assert probe() == 0
