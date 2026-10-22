"""More-pass-6 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more6_driving():
    sim = DrivingSimulator(power=5000)
    s = sim.step(1.0, 0.9)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more6_multi():
    auth = SessionAuthority("more6")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (110,120,0), 0)
    assert auth.verify("p", g.digest)
