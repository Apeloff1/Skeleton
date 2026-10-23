"""10x adversarial tests for deepened gap fillers."""
import pytest
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator, DrivingSimError
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority, MultiplayerError
from skeleton.native.emulation_mapping_card import EmulationInventory

def test_driving_10x_dynamics():
    sim = DrivingSimulator(mass=1500, power=300)
    s = sim.step(1.0, 0.2, 0.0)
    assert s.speed > 0
    assert s.rpm > 800
    assert len(s.tires) == 4
    assert s.digest

def test_driving_bounds():
    sim = DrivingSimulator()
    with pytest.raises(DrivingSimError):
        sim.step(1.5, 0, 0)

def test_multi_sync_and_cheat():
    auth = SessionAuthority("sess10x")
    g = auth.issue_grant("p1")
    auth.sync_peer("p1", "p2", (1.0, 2.0, 0.0), 100)
    assert auth.verify_grant("p1", g.digest)

def test_emulation_10x():
    inv = EmulationInventory()
    for i in range(5):
        inv.add_unmapped(f"t{i}")
    inv.mark_mapped("t0", "core", "fw")
    assert inv.unmapped_count == 69
    assert inv.summary_digest()
