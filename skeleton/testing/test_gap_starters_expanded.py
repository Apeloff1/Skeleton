"""Expanded longform tests for all injected gap starters."""
from pathlib import Path
import pytest

from skeleton.security.path_url_hardener import harden_path, PathHardeningError
from skeleton.forge.pipelines.commercial_asset_starter import emit_atlas
from skeleton.distributed.mesh.multiplayer_authority import SessionAuthority
from skeleton.simulation.game.driving_sim_starter import DrivingSimulator, DrivingSimError
from skeleton.native.emulation_mapping_card import EmulationInventory, MappingError

def test_driving_step():
    sim = DrivingSimulator()
    s = sim.step(1.0, 0.1)
    assert s.speed > 0
    assert s.digest

def test_driving_bad_input():
    sim = DrivingSimulator()
    with pytest.raises(DrivingSimError):
        sim.step(2.0, 0.0)

def test_emulation_unmapped():
    inv = EmulationInventory()
    card = inv.add_unmapped("target-70")
    assert not card.mapped
    assert inv.unmapped_count == 70

def test_emulation_map():
    inv = EmulationInventory()
    inv.add_unmapped("t1")
    inv.mark_mapped("t1", "core-x", "fw-1")
    assert inv.cards["t1"].mapped
    assert inv.unmapped_count == 69

def test_combined_receipt_flow(tmp_path: Path):
    # hardener
    root = tmp_path / "s"
    root.mkdir()
    with pytest.raises(PathHardeningError):
        harden_path("../escape", root=root)
    # atlas
    frame = bytes([128] * 16)
    p, c = emit_atlas([frame], 2, 2, tmp_path, "r")
    assert p.exists()
    # multi
    a = SessionAuthority("sess")
    g = a.issue_grant("player")
    assert a.verify_grant("player", g.digest)
