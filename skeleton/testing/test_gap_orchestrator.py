"""Tests for the multi-gap orchestrator."""
from skeleton.app.gap_orchestrator import run_all_starters

def test_run_all():
    result = run_all_starters()
    assert "digest" in result
    assert len(result["digest"]) == 64
    assert result["stored_prose"] == 0
    assert len(result["planes"]) >= 8
