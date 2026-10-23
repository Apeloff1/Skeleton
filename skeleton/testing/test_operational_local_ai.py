"""
Operational tests. Verify generate path, CAS rejection, seam wiring, and status.
"""
import pytest
from skeleton.local_ai.operational_engine import get_engine
from skeleton.local_ai.gap_filler import GapFiller

def test_operational_generate():
    eng = get_engine()
    out = eng.generate("test prompt", "valid_cas_string_16+")
    assert "text" in out
    assert out["seams_active"] > 40
    assert "g_state" in out

def test_cas_rejection():
    eng = get_engine()
    with pytest.raises(PermissionError):
        eng.generate("x", "short")

def test_gap_filler_wires_seams():
    filler = GapFiller()
    seams = filler.list()
    assert len(seams) > 50
    # Call a numbered one if present
    if "seam_000" in seams:
        r = filler.call("seam_000", {"k": 1})
        assert r.get("ok") is True

def test_status_healthy():
    eng = get_engine()
    st = eng.status()
    assert st["operational"] is True
    assert st["facade"]["status"] == "complete"
