from __future__ import annotations
from scripts.build_p1_adversarial_ac02_evidence import build

def test_ac02_evidence_shape():
    report = build("a" * 40)
    candidate = report["candidate"]
    assert report["axis_id"] == "AC-02"
    assert tuple(candidate["required_evidence_modes"]) == (
        "shutdown_race", "restart_replay", "fault_injection", "state_machine_property"
    )
    assert candidate["expected_head"] == "a" * 40
    assert candidate["creates_binding"] is False
    assert candidate["accepts_risk"] is False
    assert candidate["lowers_severity"] is False
    assert candidate["promotes_maturity"] is False
