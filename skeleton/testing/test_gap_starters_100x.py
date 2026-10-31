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
    assert s.thermal.tire_temp == sum(t.temperature for t in s.tires) / 4.0
    assert s.telemetry["steps"] == 1
    assert sim.export_telemetry()

def test_driving_long_run_thermal():
    sim = DrivingSimulator()
    for _ in range(50):
        sim.step(0.8, 0.1, 0.0)
    assert sim.state.steps == 50
    assert sim.state.thermal.engine_temp > 90

def test_driving_tire_loading_and_reset():
    sim = DrivingSimulator()
    original = sim.state.tires
    for _ in range(30):
        sim.step(1.0, 0.7, 0.0)
    tires = sim.state.tires
    assert tires[0].temperature > tires[2].temperature
    assert tires[1].temperature > tires[3].temperature
    assert all(0.0 <= t.wear <= 1.0 for t in tires)
    assert all(0.2 <= t.grip <= 1.0 for t in tires)
    sim.reset()
    assert len(sim.state.tires) == 4
    assert all(t.wear == 0.0 for t in sim.state.tires)
    assert all(t.temperature == 70.0 for t in sim.state.tires)
    assert all(a is not b for a, b in zip(original, sim.state.tires))


def test_multi_100x_predictive():
    auth = SessionAuthority("sess100x")
    g = auth.issue_grant("p1")
    auth.predictive_distributed_sync("p1", "p2", (20.0, 30.0, 0.0), (5.0, 2.0, 0.0), 30)
    assert auth.verify_grant("p1", g.digest)
    assert len(g.interest_set) >= 0
    assert len(g.rollback_buffer) > 0
    assert len(g.distributed_rollback) > 0
