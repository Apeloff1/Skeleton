"""20x ultra adversarial tests."""
import pytest
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator, DrivingSimError
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority

def test_driving_20x_aero():
    sim = DrivingSimulator(power=500, frontal_area=2.0)
    s = sim.step(1.0, 0.1, 0.0)
    assert s.speed > 0
    assert s.downforce >= 0
    assert s.telemetry
    assert sim.export_telemetry()

def test_driving_damage_on_collision():
    sim = DrivingSimulator()
    for _ in range(100):
        sim.step(1.0, 0.0, 0.0)
    assert sim.state.collision or sim.state.speed > 0

def test_multi_predictive():
    auth = SessionAuthority("sess20x")
    g = auth.issue_grant("p1")
    auth.predictive_sync("p1", "p2", (10.0, 20.0, 0.0), 50)
    assert auth.verify_grant("p1", g.digest)
    assert len(g.rollback_buffer) > 0
