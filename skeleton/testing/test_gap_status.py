"""Tests for gap status report."""
from skeleton.app.gap_status import generate_status

def test_status_structure():
    status = generate_status()
    assert status["kind"] == "gap_status"
    assert status["stored_prose"] == 0
    assert status["ready"] is True
    assert status["plane_count"] == 10
    assert len(status["digest"]) == 64
