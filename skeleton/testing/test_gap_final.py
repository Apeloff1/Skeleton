"""Tests for gap final status."""
from skeleton.app.gap_final import final_status

def test_final():
    f = final_status()
    assert f["kind"] == "gap_final"
    assert f["sealed"] is True
    assert f["stored_prose"] == 0
    assert f["plane_count"] == 10
    assert len(f["digest"]) == 64
