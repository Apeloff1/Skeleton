"""More-pass-10 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more10_driving():
    sim = DrivingSimulator(power=20000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more10_multi():
    auth = SessionAuthority("more10")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (150,160,0), 0)
    assert auth.verify("p", g.digest)
