"""Tests for gap metrics."""
from skeleton.app.gap_metrics import metrics_summary

def test_metrics():
    m = metrics_summary()
    assert m["kind"] == "gap_metrics"
    assert m["stored_prose"] == 0
    assert m["ready"] is True
    assert m["plane_count"] == 10
    assert len(m["digest"]) == 64
