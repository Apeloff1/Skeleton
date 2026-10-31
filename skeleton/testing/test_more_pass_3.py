"""More-pass-3 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more3_driving():
    sim = DrivingSimulator(power=2500)
    s = sim.step(1.0, 0.6)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more3_multi():
    auth = SessionAuthority("more3")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (80,90,0), 0)
    assert auth.verify("p", g.digest)
