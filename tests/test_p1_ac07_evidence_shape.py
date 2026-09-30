from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_p1_adversarial_ac07_evidence.py"


def test_ac07_evidence_contract():
    spec = importlib.util.spec_from_file_location("ac07_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.AXIS_ID == "AC-07"
    assert module.EXPECTED_MODES == (
        "mixed_version",
        "upgrade_downgrade",
        "schema_compatibility",
        "rollback_rehearsal",
    )
    assert module.NON_AUTHORITATIVE is True
    assert module.CREATES_BINDING is False
    assert module.ACCEPTS_RISK is False
    assert module.LOWERS_SEVERITY is False
    assert module.PROMOTES_MATURITY is False
