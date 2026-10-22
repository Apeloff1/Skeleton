"""More-pass-11 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more11_driving():
    sim = DrivingSimulator(power=30000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more11_multi():
    auth = SessionAuthority("more11")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (160,170,0), 0)
    assert auth.verify("p", g.digest)
