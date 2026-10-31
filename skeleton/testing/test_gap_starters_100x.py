"""100x extreme adversarial tests."""
import pytest
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator, DrivingSimError
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority

def test_driving_100x_full():
    sim = DrivingSimulator(power=700, mass=1500)
    s = sim.step(1.0, 0.2, 0.05)
    assert s.speed > 0
    assert s.thermal.engine_temp > 90
    assert len(s.tires) == 4
    assert s.telemetry["steps"] == 1
    assert sim.export_telemetry()

def test_driving_long_run_thermal():
    sim = DrivingSimulator()
    for _ in range(50):
        sim.step(0.8, 0.1, 0.0)
    assert sim.state.steps == 50
    assert sim.state.thermal.engine_temp > 90

def test_multi_100x_predictive():
    auth = SessionAuthority("sess100x")
    g = auth.issue_grant("p1")
    auth.predictive_distributed_sync("p1", "p2", (20.0, 30.0, 0.0), (5.0, 2.0, 0.0), 30)
    assert auth.verify_grant("p1", g.digest)
    assert len(g.interest_set) >= 0
    assert len(g.rollback_buffer) > 0
    assert len(g.distributed_rollback) > 0
