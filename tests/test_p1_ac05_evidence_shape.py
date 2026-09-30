from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_p1_adversarial_ac05_evidence.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ac05_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ac05_evidence_contract():
    module = load_module()
    assert module.AXIS_ID == "AC-05"
    assert module.EXPECTED_MODES == (
        "unknown_outcome_reconciliation",
        "idempotency_replay",
        "provider_fault",
        "receipt_recovery",
    )
    assert module.NON_AUTHORITATIVE is True
    assert module.CREATES_BINDING is False
    assert module.ACCEPTS_RISK is False
    assert module.LOWERS_SEVERITY is False
    assert module.PROMOTES_MATURITY is False
