"""Tests for gap route handlers."""
from skeleton.api.gap_routes import get_health, get_metrics, get_status

def test_routes():
    h = get_health()
    assert h["ready"] is True
    assert h["stored_prose"] == 0
    m = get_metrics()
    assert m["plane_count"] == 10
    s = get_status()
    assert s["plane_count"] == 10
    assert len(s["digest"]) == 64
