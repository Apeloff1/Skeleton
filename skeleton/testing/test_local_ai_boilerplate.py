"""
Focused tests for local AI boilerplate. Named cases for adapter, bridge, clipped-G, CAS rejection.
"""
import pytest
from skeleton.local_ai import get_complete

def test_complete_status():
    ai = get_complete()
    status = ai.status()
    # Legacy construction is only a seam inventory; it does not bind a GGUF
    # model, tokenizer, authorization guard, or verified inference backend.
    assert status["status"] == "unavailable"
    assert status["seams"] > 40
    assert status["adapter"] == "legacy_unverified"
    assert status["bridge"] == "disabled_unverified"
    assert status["ready"] is False
    assert status["readiness_code"] == "LOCAL_INFERENCE_NOT_BOUND"

def test_clipped_g_bounds():
    from skeleton.local_ai.clipped_g_observer import ClippedGObserver
    obs = ClippedGObserver()
    state = obs.observe({"delta": 5.0, "mass": 1.5})
    assert state.G <= 11.0
    assert state.mass_hint <= 1.5
