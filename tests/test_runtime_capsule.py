from dataclasses import replace

from skeleton.school.decision_ledger import DecisionDisposition, DecisionLedger, EvidenceKind, EvidenceRef
from skeleton.school.runtime_capsule import RuntimeIntegrityCapsule
from skeleton.school.runtime_replay import RuntimeReplaySnapshot
from skeleton.school.session_runtime import SessionEvent, SessionPhase


def _ledger():
    ledger = DecisionLedger()
    ledger.register_evidence(EvidenceRef("e1", EvidenceKind.OBSERVATION, "skill", "observed", 1.0, "test"))
    ledger.append(
        session_id="s1",
        decision_id="s1:orient",
        domain="session_runtime",
        action="practice",
        rationale=("test",),
        evidence=("e1",),
        disposition=DecisionDisposition.ACCEPTED,
    )
    return ledger


def _snapshot(ledger):
    return RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.DIAGNOSE,
        events=(SessionEvent(1, SessionPhase.INTAKE, "session_opened"),),
        selected_policy="practice",
        rejected_policies=(),
        ledger=ledger,
        pipeline_contract_digest="a" * 64,
        provenance_digest="b" * 64,
    )


def test_capsule_is_deterministic_and_verifiable():
    ledger = _ledger()
    first = RuntimeIntegrityCapsule.capture(_snapshot(ledger), ledger)
    second = RuntimeIntegrityCapsule.capture(_snapshot(ledger), ledger)
    assert first == second
    assert first.verify(ledger).valid


def test_capsule_detects_runtime_tampering():
    ledger = _ledger()
    capsule = RuntimeIntegrityCapsule.capture(_snapshot(ledger), ledger)
    tampered_runtime = replace(capsule.runtime, selected_policy="challenge")
    tampered = replace(capsule, runtime=tampered_runtime)
    audit = tampered.verify(ledger)
    assert not audit.valid
    assert any("runtime-integrity divergence" in item for item in audit.violations)


def test_capsule_detects_capsule_digest_tampering():
    ledger = _ledger()
    capsule = RuntimeIntegrityCapsule.capture(_snapshot(ledger), ledger)
    tampered = replace(capsule, capsule_digest="f" * 64)
    audit = tampered.verify(ledger)
    assert not audit.valid
    assert any("capsule-integrity divergence" in item for item in audit.violations)
