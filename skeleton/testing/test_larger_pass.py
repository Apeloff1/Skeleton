"""Larger-pass tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_larger_driving():
    sim = DrivingSimulator(power=900)
    s = sim.step(1.0, 0.2, 0.1)
    assert s.speed > 0
    assert s.telemetry["steps"] == 1
    assert sim.export_telemetry()
def test_larger_multi():
    auth = SessionAuthority("larger")
    g = auth.issue_grant("p1")
    auth.sync("p1", "p2", (25.0, 35.0, 0.0), 15)
    assert auth.verify("p1", g.digest)
    assert len(g.interest_set) >= 0
