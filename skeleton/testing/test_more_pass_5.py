"""More-pass-5 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more5_driving():
    sim = DrivingSimulator(power=4000)
    s = sim.step(1.0, 0.8)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more5_multi():
    auth = SessionAuthority("more5")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (100,110,0), 0)
    assert auth.verify("p", g.digest)
