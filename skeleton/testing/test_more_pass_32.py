"""More-pass-32 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_more32_driving():
    sim = DrivingSimulator(power=1e42)
    s = sim.step(1.0, 1.0)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_more32_multi():
    auth = SessionAuthority("more32")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (370,380,0), 0)
    assert auth.verify("p", g.digest)
