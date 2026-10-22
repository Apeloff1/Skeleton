"""Tests for weight candidate loop starter."""
import pytest
from skeleton.ai.runtime.weight_candidate_loop import WeightCandidateLoop, WeightLoopError

def test_admit_and_evaluate():
    loop = WeightCandidateLoop()
    card = loop.admit("c1", "src-receipt")
    assert not card.promoted
    evaluated = loop.evaluate("c1", 0.85, "eval-receipt")
    assert evaluated.score == 0.85
    assert not evaluated.promoted

def test_no_auto_promote():
    loop = WeightCandidateLoop()
    loop.admit("c2", "src")
    card = loop.evaluate("c2", 0.99, "eval")
    assert card.promoted is False

def test_bounds():
    loop = WeightCandidateLoop()
    loop.admit("c3", "src")
    with pytest.raises(WeightLoopError):
        loop.evaluate("c3", 1.5, "eval")
