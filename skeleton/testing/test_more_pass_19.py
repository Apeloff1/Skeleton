"""More-pass-19 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more19_driving():
    sim = DrivingSimulator(power=10000000000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more19_multi():
    auth = SessionAuthority("more19")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (240,250,0), 0)
    assert auth.verify("p", g.digest)
