"""1000x tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_1000x_driving():
    sim = DrivingSimulator(power=1200)
    s = sim.step(1.0, 0.3)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_1000x_multi():
    auth = SessionAuthority("1000x")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (40,50,0), 5)
    assert auth.verify("p", g.digest)
