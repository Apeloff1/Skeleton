from dataclasses import replace

import pytest

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.runtime_attestation import RuntimeAttestation, verify_attestation
from skeleton.school.runtime_replay import RuntimeReplaySnapshot
from skeleton.school.session_runtime import SessionEvent, SessionPhase


def test_runtime_attestation_round_trip(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    assert verify_attestation(attestation, runtime_snapshot, ledger) == ()
    assert attestation.session_root_decision_id == runtime_snapshot.events[0].decision_id
    assert attestation.selected_policy_decision_id == runtime_snapshot.selected_policy_decision_id
    assert len(attestation.capsule_digest) == 64


def test_runtime_attestation_detects_runtime_tamper(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    tampered = replace(runtime_snapshot, phase="complete")
    assert "runtime audit is invalid" in verify_attestation(attestation, tampered, ledger)


def test_runtime_attestation_detects_attestation_tamper(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    tampered = replace(attestation, ledger_count=attestation.ledger_count + 1)
    assert "attestation ledger identity diverges" in verify_attestation(tampered, runtime_snapshot, ledger)


def test_runtime_attestation_detects_capsule_binding_tamper(runtime_snapshot, ledger):
    attestation = RuntimeAttestation.capture(runtime_snapshot, ledger)
    tampered = replace(attestation, capsule_digest="0" * 64)
    failures = verify_attestation(tampered, runtime_snapshot, ledger)
    assert "attestation capsule digest diverges" in failures
    assert "attestation digest diverges" in failures


def test_runtime_attestation_capture_fails_closed_on_invalid_runtime(runtime_snapshot, ledger):
    tampered = replace(runtime_snapshot, phase="complete")
    with pytest.raises(ValueError, match="invalid runtime snapshot"):
        RuntimeAttestation.capture(tampered, ledger)


def test_runtime_attestation_capture_requires_selected_identity_match(runtime_snapshot, ledger):
    tampered = replace(runtime_snapshot, selected_policy="challenge")
    with pytest.raises(ValueError, match="invalid runtime snapshot"):
        RuntimeAttestation.capture(tampered, ledger)


def test_runtime_attestation_accepts_same_action_rejected_counterfactual():
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "observed", 1.0, "test"))
    ledger.append(
        session_id="s1",
        decision_id="s1:orient",
        domain="session_runtime",
        action="orient",
        rationale=("root",),
        evidence=("e1",),
        disposition=DecisionDisposition.ACCEPTED,
    )
    ledger.append(
        session_id="s1",
        decision_id="s1:challenge-rejected",
        domain="session_runtime",
        action="challenge",
        rationale=("counterfactual",),
        disposition=DecisionDisposition.REJECTED,
        predecessors=("s1:orient",),
    )
    ledger.append(
        session_id="s1",
        decision_id="s1:challenge-selected",
        domain="session_runtime",
        action="challenge",
        rationale=("selected",),
        disposition=DecisionDisposition.ACCEPTED,
        predecessors=("s1:challenge-rejected",),
    )
    snapshot = RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.DIAGNOSE,
        events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),),
        selected_policy="challenge",
        selected_policy_decision_id="s1:challenge-selected",
        rejected_policies=("challenge",),
        ledger=ledger,
    )

    attestation = RuntimeAttestation.capture(snapshot, ledger)
    assert verify_attestation(attestation, snapshot, ledger) == ()
    assert attestation.selected_policy_decision_id == "s1:challenge-selected"
    assert attestation.rejected_decision_ids == ("s1:challenge-rejected",)
