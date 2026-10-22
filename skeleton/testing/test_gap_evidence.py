"""Tests for gap evidence card."""
from skeleton.app.gap_evidence import evidence_card

def test_evidence():
    e = evidence_card()
    assert e["kind"] == "gap_evidence"
    assert e["ci_ok"] is True
    assert e["stored_prose"] == 0
    assert e["plane_count"] == 10
    assert len(e["digest"]) == 64
