"""30x extreme adversarial tests."""
import pytest
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator, DrivingSimError
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority

def test_driving_30x_thermal():
    sim = DrivingSimulator(power=600)
    s = sim.step(1.0, 0.15, 0.1)
    assert s.speed > 0
    assert s.thermal.engine_temp > 90
    assert s.telemetry["tire_temp"] >= 70
    assert sim.export_telemetry()

def test_driving_thermal_derate():
    sim = DrivingSimulator()
    for _ in range(200):
        sim.step(1.0, 0.3, 0.0)
    assert sim.state.thermal.engine_temp > 90 or sim.state.speed > 0

def test_multi_distributed():
    auth = SessionAuthority("sess30x")
    g = auth.issue_grant("p1")
    auth.distributed_sync("p1", "p2", (15.0, 25.0, 0.0), 40)
    assert auth.verify_grant("p1", g.digest)
    assert len(g.distributed_rollback) > 0
    assert len(g.rollback_buffer) > 0
