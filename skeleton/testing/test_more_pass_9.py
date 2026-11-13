"""More-pass-9 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more9_driving():
    sim = DrivingSimulator(power=12000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more9_multi():
    auth = SessionAuthority("more9")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (140,150,0), 0)
    assert auth.verify("p", g.digest)
