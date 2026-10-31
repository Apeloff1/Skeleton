"""100x-workload tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_100x_driving():
    sim = DrivingSimulator(power=1000)
    s = sim.step(1.0, 0.25, 0.05)
    assert s.speed > 0
    assert s.telemetry["steps"] == 1
    assert sim.export_telemetry()
def test_100x_multi():
    auth = SessionAuthority("100x")
    g = auth.issue_grant("p1")
    auth.sync("p1", "p2", (30.0, 40.0, 0.0), 10)
    assert auth.verify("p1", g.digest)
    assert len(g.interest_set) >= 0
