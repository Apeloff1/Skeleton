"""Tests for gap provenance seal."""
from skeleton.app.gap_seal import provenance_seal

def test_seal():
    s = provenance_seal()
    assert s["kind"] == "gap_seal"
    assert s["sealed"] is True
    assert s["stored_prose"] == 0
    assert s["plane_count"] == 10
    assert len(s["digest"]) == 64
