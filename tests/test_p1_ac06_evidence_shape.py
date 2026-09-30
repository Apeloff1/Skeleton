from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_p1_adversarial_ac06_evidence.py"


def test_ac06_evidence_contract():
    spec = importlib.util.spec_from_file_location("ac06_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.AXIS_ID == "AC-06"
    assert module.EXPECTED_MODES == (
        "reconciliation_drill",
        "duplicate_delivery",
        "orphan_sweep",
        "projection_rebuild",
    )
    assert module.NON_AUTHORITATIVE is True
    assert module.CREATES_BINDING is False
    assert module.ACCEPTS_RISK is False
    assert module.LOWERS_SEVERITY is False
    assert module.PROMOTES_MATURITY is False
