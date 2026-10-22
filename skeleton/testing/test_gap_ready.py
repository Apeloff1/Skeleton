"""Tests for gap readiness declaration."""
from skeleton.app.gap_ready import readiness_declaration

def test_ready():
    r = readiness_declaration()
    assert r["kind"] == "gap_ready"
    assert r["ready"] is True
    assert r["stored_prose"] == 0
    assert r["plane_count"] == 10
    assert len(r["digest"]) == 64
