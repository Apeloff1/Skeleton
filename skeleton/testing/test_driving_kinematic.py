"""Tests for driving kinematic starter."""
import pytest
from skeleton.simulation.game.driving_kinematic import DrivingKinematic, DrivingError

def test_step_bounds():
    d = DrivingKinematic()
    s = d.step(10.0, 0.0, 0.1)
    assert abs(s.vx) <= 100.0
    assert abs(s.x) <= 10000.0
    assert len(s.digest) == 64

def test_bad_dt():
    d = DrivingKinematic()
    with pytest.raises(DrivingError):
        d.step(1.0, 1.0, 2.0)

def test_reset():
    d = DrivingKinematic()
    d.step(1.0, 1.0, 0.1)
    d.reset()
    assert d.state.x == 0.0
