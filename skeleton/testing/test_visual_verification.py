"""Tests for visual verification starter."""
from pathlib import Path
import pytest
from skeleton.simulation.platform.visual_verification import verify_binding, reject_false_engine_claim, VisualVerifyError

def test_binding_ok(tmp_path: Path):
    atlas = tmp_path / "a.png"
    tres = tmp_path / "a.tres"
    atlas.write_bytes(b"\x89PNG fake")
    tres.write_text("[gd_resource]")
    receipt = verify_binding(atlas, tres, "src")
    assert len(receipt) == 64

def test_missing_rejected(tmp_path: Path):
    with pytest.raises(VisualVerifyError):
        verify_binding(tmp_path / "missing.png", tmp_path / "m.tres", "src")

def test_false_claim_rejected():
    with pytest.raises(VisualVerifyError):
        reject_false_engine_claim(True)
    reject_false_engine_claim(False)  # no raise
