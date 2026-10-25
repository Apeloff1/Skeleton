"""More-pass-4 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more4_driving():
    sim = DrivingSimulator(power=3000)
    s = sim.step(1.0, 0.7)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more4_multi():
    auth = SessionAuthority("more4")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (90,100,0), 0)
    assert auth.verify("p", g.digest)
