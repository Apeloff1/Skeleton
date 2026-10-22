"""Another-pass tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_another_driving():
    sim = DrivingSimulator(power=800)
    s = sim.step(1.0, 0.15)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_another_multi():
    auth = SessionAuthority("pass")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (10,20,0), 20)
    assert auth.verify("p", g.digest)
    assert len(g.interest_set) >= 0
