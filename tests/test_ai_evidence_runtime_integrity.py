from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import threading

import pytest

from skeleton.ai.learning.audit_chain import (
    LearningAuditError,
    LearningAuditEvent,
    LearningAuditLedger,
)
from skeleton.ai.learning.evidence import (
    EvidenceStateReceipt,
    LearningEvidenceError,
    LearningEvidenceStore,
    Observation,
    canonical_fingerprint,
    make_provenance,
)
from skeleton.learning.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
    EvidenceKind,
    EvidenceRef,
)
from skeleton.learning.school.runtime_attestation import (
    RuntimeAttestation,
    verify_attestation,
)
from skeleton.learning.school.runtime_capsule import (
    RuntimeIntegrityCapsule,
)
from skeleton.learning.school.runtime_replay import (
    RuntimeReplaySnapshot,
    audit_runtime,
)
from skeleton.learning.school.session_runtime import (
    SessionEvent,
    SessionPhase,
)


NOW = 1_000.0


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class _Record:
    revision: int
    value: object


class _MemoryBackend:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], _Record] = {}
        self.lock = threading.RLock()

    def get(self, namespace: str, key: str):
        with self.lock:
            return self.records.get((namespace, key))

    def put_if_absent(
        self,
        namespace: str,
        key: str,
        value: object,
    ):
        with self.lock:
            slot = (namespace, key)
            if slot in self.records:
                raise RuntimeError("already exists")
            record = _Record(1, value)
            self.records[slot] = record
            return record

    def compare_and_swap(
        self,
        namespace: str,
        key: str,
        *,
        expected_revision: int,
        value: object,
    ):
        with self.lock:
            slot = (namespace, key)
            current = self.records.get(slot)
            revision = 0 if current is None else current.revision
            if revision != expected_revision:
                raise RuntimeError("CAS conflict")
            record = _Record(revision + 1, value)
            self.records[slot] = record
            return record


def audit_event(
    event_id: str = "evt-1",
    *,
    kind: str = "training_started",
    subject_id: str = "model:a",
    parent: str | None = None,
    details: dict[str, object] | None = None,
) -> LearningAuditEvent:
    return LearningAuditEvent(
        event_id=event_id,
        kind=kind,
        actor_principal="principal:trainer",
        subject_id=subject_id,
        subject_digest=sha(subject_id),
        policy_digest=sha("policy"),
        decision="allow",
        evidence_root=sha("evidence"),
        code_revision="deadbeef",
        parent_event_id=parent,
        details=details or {"run": {"id": "run-1", "tags": ["a"]}},
    )


def evidence_store(**overrides) -> LearningEvidenceStore:
    values = {
        "clock": lambda: NOW,
        "clock_version": 1,
        "max_age_seconds": 60.0,
        "max_history": 16,
    }
    values.update(overrides)
    return LearningEvidenceStore(**values)


def observation(
    observation_id: str = "obs-1",
    *,
    payload: dict[str, object] | None = None,
) -> Observation:
    body = payload or {"score": 1}
    return Observation(
        observation_id=observation_id,
        subject_id="skill:python",
        payload=body,
        provenance=make_provenance(
            body,
            observed_at=NOW,
            clock_version=1,
        ),
    )


def decision_ledger() -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.register_evidence(
        EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill",
            "observed",
            1.0,
            "fixture",
        )
    )
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


def runtime_snapshot(
    ledger: DecisionLedger,
    *,
    pipeline: str = "a" * 64,
    provenance: str = "b" * 64,
) -> RuntimeReplaySnapshot:
    return RuntimeReplaySnapshot.capture(
        session_id="s1",
        phase=SessionPhase.DIAGNOSE,
        events=(
            SessionEvent(
                1,
                SessionPhase.INTAKE,
                "session_opened",
                (("session_id", "s1"),),
            ),
        ),
        selected_policy="practice",
        rejected_policies=(),
        ledger=ledger,
        pipeline_contract_digest=pipeline,
        provenance_digest=provenance,
    )


def test_audit_event_deep_freezes_details() -> None:
    details = {"run": {"id": "run-1", "tags": ["a"]}}
    event = audit_event(details=details)
    digest = event.event_digest
    details["run"]["tags"].append("b")
    assert event.event_digest == digest
    assert event.as_dict()["details"] == {
        "run": {"id": "run-1", "tags": ["a"]}
    }
    with pytest.raises(TypeError):
        event.details["x"] = 1  # type: ignore[index]


def test_audit_event_rejects_self_parent_and_nonfinite_details() -> None:
    with pytest.raises(LearningAuditError, match="parent itself"):
        audit_event(parent="evt-1")
    with pytest.raises(LearningAuditError, match="non-finite"):
        audit_event(details={"score": float("nan")})


def test_audit_parent_cannot_cross_subject_boundary() -> None:
    backend = _MemoryBackend()
    ledger = LearningAuditLedger(backend)
    ledger.append(audit_event("evt-1", subject_id="model:a"))
    with pytest.raises(
        LearningAuditError,
        match="crosses subject boundary",
    ):
        ledger.append(
            audit_event(
                "evt-2",
                kind="training_completed",
                subject_id="model:b",
                parent="evt-1",
            )
        )


def test_audit_receipt_binds_policy_evidence_and_decision() -> None:
    ledger = LearningAuditLedger(_MemoryBackend())
    receipt = ledger.append(audit_event())
    assert receipt.policy_digest == sha("policy")
    assert receipt.evidence_root == sha("evidence")
    assert receipt.decision == "allow"
    assert ledger.verify_receipt(receipt)

    wrong = replace(receipt, policy_digest=sha("other-policy"))
    assert not ledger.verify_receipt(wrong)


def test_audit_snapshot_identity_round_trip_and_extension_detection() -> None:
    ledger = LearningAuditLedger(_MemoryBackend())
    ledger.append(audit_event("evt-1"))
    snapshot = ledger.snapshot_receipt()
    assert snapshot.verify_identity()
    assert ledger.verify_snapshot(snapshot)

    ledger.append(
        audit_event(
            "evt-2",
            kind="training_completed",
            parent="evt-1",
        )
    )
    assert not ledger.verify_snapshot(snapshot)


def test_shared_backend_event_id_claim_prevents_cross_instance_race() -> None:
    backend = _MemoryBackend()
    first = LearningAuditLedger(backend)
    second = LearningAuditLedger(backend)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(ledger: LearningAuditLedger) -> None:
        barrier.wait()
        try:
            ledger.append(audit_event("evt-race"))
            result = "admitted"
        except LearningAuditError:
            result = "rejected"
        with lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=worker, args=(first,)),
        threading.Thread(target=worker, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["admitted", "rejected"]
    verifier = LearningAuditLedger(backend)
    assert verifier.verify()
    assert verifier.length() == 1


def test_strict_fingerprint_rejects_runtime_objects_and_nonfinite_values() -> None:
    with pytest.raises(
        LearningEvidenceError,
        match="unsupported",
    ):
        canonical_fingerprint({"x": object()})
    with pytest.raises(
        LearningEvidenceError,
        match="non-finite",
    ):
        canonical_fingerprint({"x": float("inf")})


def test_fingerprint_rejects_normalized_key_collision() -> None:
    with pytest.raises(
        LearningEvidenceError,
        match="collide",
    ):
        canonical_fingerprint({"x": 1, " x": 2})


def test_observation_payload_is_immutable_after_construction() -> None:
    body = {"score": 1}
    item = observation(payload=body)
    digest = item.digest
    body["score"] = 2
    assert item.digest == digest
    assert dict(item.payload) == {"score": 1}
    with pytest.raises(TypeError):
        item.payload["score"] = 3  # type: ignore[index]


def test_evidence_state_receipt_binds_current_state_and_history() -> None:
    store = evidence_store()
    initial = store.state_receipt()
    assert isinstance(initial, EvidenceStateReceipt)
    assert store.verify_state_receipt(initial)

    update = store.record_observation(observation())
    current = store.state_receipt()
    assert current.version == 1
    assert current.state_digest == update.state_digest
    assert current.receipt_digest != initial.receipt_digest
    assert not store.verify_state_receipt(initial)
    assert store.verify_state_receipt(current)


def test_evidence_update_binds_pre_and_post_state() -> None:
    store = evidence_store()
    before = store.state_digest()
    update = store.record_observation(observation())
    after = store.state_digest()
    assert update.previous_state_digest == before
    assert update.state_digest == after
    assert before != after


def test_rollback_requires_exact_historical_state_when_requested() -> None:
    store = evidence_store()
    first = store.record_observation(observation())
    target_digest = first.state_digest
    assert target_digest is not None
    store.record_observation(observation("obs-2", payload={"score": 2}))

    before = store.state_receipt()
    with pytest.raises(
        LearningEvidenceError,
        match="state digest mismatch",
    ):
        store.rollback(
            1,
            expected_state_digest=sha("wrong-state"),
        )
    assert store.state_receipt() == before

    rollback = store.rollback(
        1,
        expected_state_digest=target_digest,
    )
    assert rollback.rollback_target_digest == target_digest
    assert rollback.previous_state_digest == before.state_digest
    assert "obs-1" in store.facts()
    assert "obs-2" not in store.facts()


def test_concurrent_duplicate_evidence_write_commits_once() -> None:
    store = evidence_store()
    item = observation()
    barrier = threading.Barrier(8)
    results: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        try:
            store.record_observation(item)
            result = "admitted"
        except LearningEvidenceError:
            result = "rejected"
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("admitted") == 1
    assert results.count("rejected") == 7
    assert store.version == 1
    assert len(store.history()) == 1


def test_decision_hash_binds_exact_evidence_content() -> None:
    ledger = decision_ledger()
    ledger.verify()
    record = ledger.records[0]
    assert len(record.evidence_digests) == 1
    assert record.evidence_digests[0] == ledger.evidence["e1"].digest

    ledger.evidence["e1"] = EvidenceRef(
        "e1",
        EvidenceKind.OBSERVATION,
        "skill",
        "tampered",
        1.0,
        "fixture",
    )
    with pytest.raises(ValueError, match="evidence content drift"):
        ledger.verify()


def test_decision_ledger_rejects_nonfinite_state_hash_inputs() -> None:
    ledger = DecisionLedger()
    with pytest.raises(ValueError, match="non-finite"):
        ledger.append(
            session_id="s1",
            decision_id="d1",
            domain="runtime",
            action="test",
            state={"score": float("nan")},
        )


def test_checkpoint_identity_changes_when_evidence_registry_changes() -> None:
    ledger = decision_ledger()
    checkpoint = ledger.checkpoint()
    assert ledger.verify_checkpoint(checkpoint)

    ledger.register_evidence(
        EvidenceRef(
            "e2",
            EvidenceKind.OBSERVATION,
            "skill",
            "later",
            1.0,
            "fixture",
        )
    )
    assert not ledger.verify_checkpoint(checkpoint)
    assert ledger.checkpoint().evidence_root != checkpoint.evidence_root


def test_runtime_snapshot_binds_evidence_root_and_ledger_identity() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    assert snapshot.evidence_root == ledger.evidence_root
    assert snapshot.ledger_identity == ledger.ledger_identity
    assert audit_runtime(snapshot, ledger).valid


def test_runtime_audit_detects_evidence_only_drift() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    ledger.register_evidence(
        EvidenceRef(
            "e2",
            EvidenceKind.OBSERVATION,
            "other",
            "later",
            1.0,
            "fixture",
        )
    )
    audit = audit_runtime(snapshot, ledger)
    assert not audit.valid
    assert any("evidence root diverges" in item for item in audit.violations)
    assert any("ledger identity diverges" in item for item in audit.violations)


def test_capture_verified_rejects_malformed_provenance_but_capture_stays_auditable() -> None:
    ledger = decision_ledger()
    captured = runtime_snapshot(
        ledger,
        pipeline="not-a-digest",
        provenance="",
    )
    assert not audit_runtime(captured, ledger).valid

    with pytest.raises(
        ValueError,
        match="cannot capture verified runtime snapshot",
    ):
        RuntimeReplaySnapshot.capture_verified(
            session_id="s1",
            phase=SessionPhase.DIAGNOSE,
            events=(
                SessionEvent(
                    1,
                    SessionPhase.INTAKE,
                    "session_opened",
                ),
            ),
            selected_policy="practice",
            rejected_policies=(),
            ledger=ledger,
            pipeline_contract_digest="not-a-digest",
            provenance_digest="",
        )


def test_runtime_event_payload_duplicate_keys_are_rejected() -> None:
    ledger = decision_ledger()
    with pytest.raises(ValueError, match="keys must be unique"):
        RuntimeReplaySnapshot.capture(
            session_id="s1",
            phase=SessionPhase.DIAGNOSE,
            events=(
                SessionEvent(
                    1,
                    SessionPhase.INTAKE,
                    "session_opened",
                    (("x", "1"), ("x", "2")),
                ),
            ),
            selected_policy="practice",
            rejected_policies=(),
            ledger=ledger,
        )


def test_capsule_binds_evidence_root_ledger_identity_and_session_hashes() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    capsule = RuntimeIntegrityCapsule.capture(snapshot, ledger)
    assert capsule.evidence_root == ledger.evidence_root
    assert capsule.ledger_identity == ledger.ledger_identity
    assert capsule.session_record_hashes == (
        ledger.records[0].record_hash,
    )
    assert capsule.verify(ledger).valid


def test_capsule_detects_evidence_registry_extension() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    capsule = RuntimeIntegrityCapsule.capture(snapshot, ledger)
    ledger.register_evidence(
        EvidenceRef(
            "e2",
            EvidenceKind.OBSERVATION,
            "other",
            "later",
            1.0,
            "fixture",
        )
    )
    audit = capsule.verify(ledger)
    assert not audit.valid
    assert any("evidence root" in item for item in audit.violations)


def test_attestation_binds_checkpoint_and_evidence_identity() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    attestation = RuntimeAttestation.capture(snapshot, ledger)
    assert attestation.evidence_root == ledger.evidence_root
    assert attestation.ledger_identity == ledger.ledger_identity
    assert attestation.checkpoint_digest == ledger.checkpoint().digest
    assert attestation.verify_identity()
    assert verify_attestation(attestation, snapshot, ledger) == ()


def test_attestation_detects_self_digest_tampering() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    attestation = RuntimeAttestation.capture(snapshot, ledger)
    tampered = replace(
        attestation,
        evidence_root=sha("forged-evidence-root"),
    )
    failures = verify_attestation(tampered, snapshot, ledger)
    assert "attestation evidence root diverges" in failures
    assert "attestation digest diverges" in failures


def test_attestation_invalidates_when_evidence_content_is_replaced() -> None:
    ledger = decision_ledger()
    snapshot = runtime_snapshot(ledger)
    attestation = RuntimeAttestation.capture(snapshot, ledger)

    ledger.evidence["e1"] = EvidenceRef(
        "e1",
        EvidenceKind.OBSERVATION,
        "skill",
        "replaced-content",
        1.0,
        "fixture",
    )
    failures = verify_attestation(attestation, snapshot, ledger)
    assert "runtime audit is invalid" in failures
    assert "attestation evidence root diverges" in failures
    assert "attestation ledger content identity diverges" in failures
