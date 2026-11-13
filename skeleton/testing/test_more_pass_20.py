"""More-pass-20 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more20_driving():
    sim = DrivingSimulator(power=100000000000)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more20_multi():
    auth = SessionAuthority("more20")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (250,260,0), 0)
    assert auth.verify("p", g.digest)
