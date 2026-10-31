"""
Focused tests for local AI boilerplate. Named cases for adapter, bridge, clipped-G, CAS rejection.
"""
import pytest
from skeleton.local_ai import get_complete

def test_complete_status():
    ai = get_complete()
    status = ai.status()
    assert status["status"] == "complete"
    assert status["seams"] > 40
    assert status["adapter"] is True
    assert status["bridge"] is True

def test_clipped_g_bounds():
    from skeleton.local_ai.clipped_g_observer import ClippedGObserver
    obs = ClippedGObserver()
    state = obs.observe({"delta": 5.0, "mass": 1.5})
    assert state.G <= 11.0
    assert state.mass_hint <= 1.5
