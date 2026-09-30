from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_p1_adversarial_ac09_evidence.py"


def test_ac09_evidence_contract():
    spec = importlib.util.spec_from_file_location("ac09_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.AXIS_ID == "AC-09"
    assert module.EXPECTED_MODES == (
        "clock_skew",
        "suspend_resume",
        "lease_fencing",
        "expiry_property",
    )
    assert module.NON_AUTHORITATIVE is True
    assert module.CREATES_BINDING is False
    assert module.ACCEPTS_RISK is False
    assert module.LOWERS_SEVERITY is False
    assert module.PROMOTES_MATURITY is False
