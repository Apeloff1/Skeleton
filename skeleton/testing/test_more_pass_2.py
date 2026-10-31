"""More-pass-2 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more2_driving():
    sim = DrivingSimulator(power=2000)
    s = sim.step(1.0, 0.5)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more2_multi():
    auth = SessionAuthority("more2")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (70,80,0), 1)
    assert auth.verify("p", g.digest)
