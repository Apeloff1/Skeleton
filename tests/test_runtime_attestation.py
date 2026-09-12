from dataclasses import replace

from skeleton.school.runtime_attestation import RuntimeAttestation, verify_attestation


def test_runtime_attestation_round_trip(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    assert verify_attestation(attestation, runtime_snapshot, ledger) == ()
    assert attestation.session_root_decision_id == runtime_snapshot.events[0].decision_id
    assert attestation.selected_policy_decision_id == runtime_snapshot.selected_policy_decision_id


def test_runtime_attestation_detects_runtime_tamper(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    tampered = replace(runtime_snapshot, phase="complete")
    assert "runtime audit is invalid" in verify_attestation(attestation, tampered, ledger)


def test_runtime_attestation_detects_attestation_tamper(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    tampered = replace(attestation, ledger_count=attestation.ledger_count + 1)
    assert "attestation ledger identity diverges" in verify_attestation(tampered, runtime_snapshot, ledger)
