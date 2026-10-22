"""100x tests injected."""
import pytest
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
def test_100x_smoke():
    sim = DrivingSimulator()
    s = sim.step(1.0, 0.1)
    assert s.speed >= 0
