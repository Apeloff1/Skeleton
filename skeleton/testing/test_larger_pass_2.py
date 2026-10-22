"""Larger-pass-2 tests."""
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
def test_larger2_driving():
    sim = DrivingSimulator(power=1400)
    s = sim.step(1.0, 0.35)
    assert s.speed > 0
    assert sim.export_telemetry()
def test_larger2_multi():
    auth = SessionAuthority("larger2")
    g = auth.issue_grant("p")
    auth.sync("p", "q", (50,60,0), 3)
    assert auth.verify("p", g.digest)
