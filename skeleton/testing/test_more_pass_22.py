"""More-pass-22 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more22_driving():
    sim = DrivingSimulator(power=10000000000000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more22_multi():
    auth = SessionAuthority("more22")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (270,280,0), 0)
    assert auth.verify("p", g.digest)
