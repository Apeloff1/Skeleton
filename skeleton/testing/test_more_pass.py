"""More-pass tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more_driving():
    sim = DrivingSimulator(power=1600)
    s = sim.step(1.0, 0.4)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more_multi():
    auth = SessionAuthority("more")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (60,70,0), 2)
    assert auth.verify("p", g.digest)
