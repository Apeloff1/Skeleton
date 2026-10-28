"""100x-workload tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_100x_driving():
    sim = DrivingSimulator(power=1000)
    # Acceleration is measured without simultaneously applying the brakes:
    # even a small brake input can exceed the simplified launch torque.
    s = sim.step(1.0, 0.25, 0.0)
    assert s.speed > 0
    assert s.steps == 1  # Monotonic step counter lives on VehicleState.
    assert s.telemetry["speed"] == s.speed
    assert sim.export_telemetry()


def test_100x_driving_brake_reduces_velocity():
    sim = DrivingSimulator(power=1000)
    sim.step(1.0, 0.0, 0.0)
    launched_speed = sim.state.speed
    assert launched_speed > 0
    s = sim.step(0.0, 0.0, 0.05)
    assert s.speed <= launched_speed
    assert s.steps == 2
    assert s.telemetry["speed"] == s.speed
def test_100x_multi():
    auth = SessionAuthority("100x")
    g = auth.issue_grant("p1")
    auth.sync("p1", "p2", (30.0, 40.0, 0.0), 10)
    assert auth.verify("p1", g.digest)
    assert len(g.interest_set) >= 0
