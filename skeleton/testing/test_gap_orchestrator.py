"""Expanded tests for the multi-gap orchestrator."""
from skeleton.app.gap_orchestrator import run_all_starters

def test_run_all():
    result = run_all_starters()
    assert "digest" in result
    assert len(result["digest"]) == 64
    assert result["stored_prose"] == 0
    planes = result["planes"]
    assert "hardener" in planes
    assert "atlas" in planes
    assert "multiplayer" in planes
    assert "sheaf" in planes
    assert "emulation" in planes
    assert "weight" in planes
    assert "visual" in planes
    assert "driving" in planes
    assert "genos" in planes
    assert "shim" in planes
    assert len(planes) == 10
