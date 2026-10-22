"""Tests for gap health card."""
from skeleton.app.gap_health import health_card

def test_health_ready():
    card = health_card()
    assert card["kind"] == "gap_health"
    assert card["stored_prose"] == 0
    assert card["ready"] is True
    assert card["plane_count"] == 10
    assert len(card["digest"]) == 64
