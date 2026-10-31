"""More-pass-30 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more30_driving():
    sim = DrivingSimulator(power=1e36)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more30_multi():
    auth = SessionAuthority("more30")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (350,360,0), 0)
    assert auth.verify("p", g.digest)
