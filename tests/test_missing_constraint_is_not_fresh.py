"""A required constraint that is absent is not a fresh prompt."""

import pytest

from skeleton.memory.rot_guard import ContextRotGuard


def test_absent_constraint_is_rot() -> None:
    with pytest.raises(ValueError):
        ContextRotGuard(attention_budget=True)
    with pytest.raises(ValueError):
        ContextRotGuard(dead_zone=True)
    guard = ContextRotGuard(attention_budget=32_000, dead_zone=0.6)
    report = guard.assess("the answer may wander", constraints=["do not invent a source"])
    assert "do not invent a source" in report.buried
    assert report.burial_score == 1.0
    assert report.verdict == "rot"
    present = guard.assess("do not invent a source\nthen answer", constraints=["do not invent a source"])
    assert present.verdict != "rot" or present.burial_score < 1.0
