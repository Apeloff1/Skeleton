"""More-pass-25 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more25_driving():
    sim = DrivingSimulator(power=1e21)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more25_multi():
    auth = SessionAuthority("more25")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (300,310,0), 0)
    assert auth.verify("p", g.digest)
