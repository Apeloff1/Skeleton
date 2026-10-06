from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import unittest

from skeleton.ai.learning.audit_chain import (
    LearningAuditError,
    LearningAuditEvent,
    LearningAuditLedger,
    LearningAuditReceipt,
)
from skeleton.ai.learning.evidence import (
    EvidenceStateReceipt,
    LearningEvidenceError,
    LearningEvidenceStore,
    Observation,
    UpdateKind,
    canonical_fingerprint,
    make_provenance,
)
from skeleton.ai.learning.school.decision_ledger import (
    DecisionDisposition,
    DecisionLedger,
    EvidenceKind,
    EvidenceRef,
)
from skeleton.ai.learning.school.runtime_attestation import (
    RuntimeAttestation,
    verify_attestation,
)
from skeleton.ai.learning.school.runtime_capsule import (
    RuntimeIntegrityCapsule,
)
from skeleton.ai.learning.school.runtime_replay import (
    RuntimeReplaySnapshot,
    audit_runtime,
    replay_digest,
)
from skeleton.ai.learning.school.session_runtime import (
    SessionEvent,
    SessionPhase,
)
from skeleton.shells.evidence_chain import EvidenceNode


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

    def get(self, namespace: str, key: str):
        return self.records.get((namespace, key))

    def put_if_absent(self, namespace: str, key: str, value: object):
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
        slot = (namespace, key)
        current = self.records.get(slot)
        current_revision = 0 if current is None else current.revision
        if current_revision != expected_revision:
            raise RuntimeError("CAS conflict")
        record = _Record(current_revision + 1, value)
        self.records[slot] = record
        return record


def audit_event(
    event_id: str,
    *,
    kind: str = "training_started",
    subject_id: str = "model:a",
    subject_digest: str | None = None,
    parent: str | None = None,
    details: dict[str, object] | None = None,
) -> LearningAuditEvent:
    return LearningAuditEvent(
        event_id=event_id,
        kind=kind,
        actor_principal="principal:trainer",
        subject_id=subject_id,
        subject_digest=subject_digest or sha(subject_id),
        policy_digest=sha("policy"),
        decision="allow",
        evidence_root=sha("evidence"),
        code_revision="revision-1",
        parent_event_id=parent,
        details=details or {"run_id": "run-1"},
    )


def evidence_store() -> LearningEvidenceStore:
    return LearningEvidenceStore(
        clock=lambda: NOW,
        clock_version=1,
        max_age_seconds=60.0,
        max_history=16,
    )


def observation(
    observation_id: str,
    *,
    score: int = 1,
) -> Observation:
    payload = {"score": score}
    return Observation(
        observation_id=observation_id,
        subject_id="skill:python",
        payload=payload,
        provenance=make_provenance(
            payload,
            observed_at=NOW,
            clock_version=1,
            source_id=f"source:{observation_id}",
            source_kind="fixture",
        ),
    )


def decision_ledger() -> DecisionLedger:
    ledger = DecisionLedger()
    ledger.register_evidence(
        EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill:python",
            "observed competency",
            1.0,
            "fixture",
        )
    )
    ledger.append(
        session_id="session-1",
        decision_id="session-1:orient",
        domain="session_runtime",
        action="practice",
        rationale=("fixture",),
        evidence=("e1",),
        state={"mastery": 0.5},
        policy={"mode": "practice"},
        disposition=DecisionDisposition.ACCEPTED,
    )
    return ledger


def runtime_snapshot(
    ledger: DecisionLedger,
) -> RuntimeReplaySnapshot:
    return RuntimeReplaySnapshot.capture_verified(
        session_id="session-1",
        phase=SessionPhase.DIAGNOSE,
        events=(
            SessionEvent(
                1,
                SessionPhase.INTAKE,
                "session_opened",
                (("session_id", "session-1"),),
            ),
        ),
        selected_policy="practice",
        selected_policy_decision_id="session-1:orient",
        rejected_policies=(),
        ledger=ledger,
        pipeline_contract_digest="a" * 64,
        provenance_digest="b" * 64,
    )


class EvidenceRuntimeAttestationIntegrityTests(unittest.TestCase):
    def test_canonical_fingerprint_rejects_runtime_object_coercion(self) -> None:
        class RuntimeOnly:
            pass

        with self.assertRaisesRegex(
            LearningEvidenceError,
            "unsupported value",
        ):
            canonical_fingerprint({"object": RuntimeOnly()})

    def test_canonical_fingerprint_rejects_nonfinite_numbers(self) -> None:
        for value in (
            float("nan"),
            float("inf"),
            -float("inf"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    LearningEvidenceError,
                    "non-finite",
                ):
                    canonical_fingerprint({"value": value})

    def test_observation_payload_is_detached_from_caller_mutation(self) -> None:
        payload = {"score": 1}
        item = Observation(
            observation_id="obs-1",
            subject_id="skill:python",
            payload=payload,
            provenance=make_provenance(
                payload,
                observed_at=NOW,
                clock_version=1,
            ),
        )
        identity = item.digest
        payload["score"] = 99

        self.assertEqual(item.digest, identity)
        self.assertEqual(dict(item.payload), {"score": 1})
        with self.assertRaises(TypeError):
            item.payload["score"] = 2  # type: ignore[index]

    def test_record_digest_binds_provenance_identity(self) -> None:
        first = observation("obs-1")
        second = Observation(
            observation_id=first.observation_id,
            subject_id=first.subject_id,
            payload=dict(first.payload),
            provenance=replace(
                first.provenance,
                source_id="source:different",
            ),
        )
        self.assertNotEqual(
            first.provenance.digest,
            second.provenance.digest,
        )
        self.assertNotEqual(first.digest, second.digest)

    def test_state_receipt_round_trip_and_mutation_detection(self) -> None:
        store = evidence_store()
        first = store.state_receipt()
        self.assertIsInstance(first, EvidenceStateReceipt)
        self.assertTrue(store.verify_state_receipt(first))

        update = store.record_observation(
            observation("obs-1")
        )
        second = store.state_receipt()

        self.assertFalse(store.verify_state_receipt(first))
        self.assertTrue(store.verify_state_receipt(second))
        self.assertNotEqual(
            first.state_digest,
            second.state_digest,
        )
        self.assertEqual(
            update.state_digest,
            second.state_digest,
        )
        self.assertEqual(
            update.previous_state_digest,
            first.state_digest,
        )

    def test_state_receipt_history_digest_changes_with_journal(self) -> None:
        store = evidence_store()
        initial = store.state_receipt()
        store.record_observation(observation("obs-1"))
        first = store.state_receipt()
        store.record_observation(
            observation("obs-2", score=2)
        )
        second = store.state_receipt()

        self.assertNotEqual(
            initial.history_digest,
            first.history_digest,
        )
        self.assertNotEqual(
            first.history_digest,
            second.history_digest,
        )

    def test_rollback_can_require_exact_historical_state_identity(self) -> None:
        store = evidence_store()
        store.record_observation(observation("obs-1"))
        target = store.state_receipt()
        store.record_observation(
            observation("obs-2", score=2)
        )
        before = store.state_receipt()

        with self.assertRaisesRegex(
            LearningEvidenceError,
            "state digest mismatch",
        ):
            store.rollback(
                target.version,
                expected_state_digest=sha("wrong-target"),
            )
        self.assertEqual(store.state_receipt(), before)

        rolled = store.rollback(
            target.version,
            expected_state_digest=target.state_digest,
        )
        self.assertIs(rolled.kind, UpdateKind.ROLLBACK)
        self.assertEqual(
            rolled.rollback_target_digest,
            target.state_digest,
        )
        self.assertEqual(
            rolled.previous_state_digest,
            before.state_digest,
        )
        self.assertEqual(
            tuple(item.observation_id for item in store.observations()),
            ("obs-1",),
        )

    def test_learning_audit_details_are_deeply_immutable(self) -> None:
        details = {
            "nested": {
                "labels": ["a", "b"],
            }
        }
        event = audit_event(
            "evt-1",
            details=details,
        )
        identity = event.event_digest
        details["nested"]["labels"].append("c")

        self.assertEqual(event.event_digest, identity)
        self.assertEqual(
            event.as_dict()["details"],
            {"nested": {"labels": ["a", "b"]}},
        )
        with self.assertRaises(TypeError):
            event.details["new"] = "value"  # type: ignore[index]

    def test_learning_audit_rejects_cross_subject_parent_custody(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        ledger.append(
            audit_event(
                "evt-a",
                subject_id="model:a",
            )
        )
        with self.assertRaisesRegex(
            LearningAuditError,
            "crosses subject boundary",
        ):
            ledger.append(
                audit_event(
                    "evt-b",
                    kind="training_completed",
                    subject_id="model:b",
                    parent="evt-a",
                )
            )

    def test_learning_audit_receipt_binds_policy_evidence_and_decision(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        receipt = ledger.append(audit_event("evt-1"))
        self.assertTrue(ledger.verify_receipt(receipt))

        tampered = LearningAuditReceipt(
            event_id=receipt.event_id,
            event_digest=receipt.event_digest,
            sequence=receipt.sequence,
            previous_root=receipt.previous_root,
            root_hash=receipt.root_hash,
            kind=receipt.kind,
            subject_id=receipt.subject_id,
            subject_digest=receipt.subject_digest,
            policy_digest=sha("different-policy"),
            evidence_root=receipt.evidence_root,
            decision=receipt.decision,
        )
        self.assertFalse(ledger.verify_receipt(tampered))

    def test_learning_audit_snapshot_is_content_addressed_and_extension_sensitive(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        ledger.append(audit_event("evt-1"))
        snapshot = ledger.snapshot_receipt()
        self.assertTrue(snapshot.verify_identity())
        self.assertTrue(ledger.verify_snapshot(snapshot))

        ledger.append(
            audit_event(
                "evt-2",
                kind="training_completed",
                parent="evt-1",
            )
        )
        self.assertFalse(ledger.verify_snapshot(snapshot))
        updated = ledger.snapshot_receipt()
        self.assertNotEqual(
            snapshot.snapshot_digest,
            updated.snapshot_digest,
        )

    def test_learning_audit_detects_payload_event_digest_rebinding(self) -> None:
        backend = _MemoryBackend()
        ledger = LearningAuditLedger(backend)
        receipt = ledger.append(audit_event("evt-1"))
        slot = (
            "ai-learning-audit-v1",
            f"node:{receipt.root_hash}",
        )
        stored = backend.records[slot]
        node = stored.value
        self.assertIsInstance(node, EvidenceNode)
        assert isinstance(node, EvidenceNode)

        payload = dict(node.payload)
        payload["event_digest"] = sha("forged-event")
        tampered = EvidenceNode(
            sequence=node.sequence,
            previous_hash=node.previous_hash,
            node_hash=node.node_hash,
            kind=node.kind,
            payload=payload,
        )
        backend.records[slot] = _Record(
            stored.revision + 1,
            tampered,
        )
        self.assertFalse(ledger.verify())
        self.assertFalse(ledger.verify_receipt(receipt))

    def test_decision_hash_binds_evidence_content_not_only_id(self) -> None:
        ledger = decision_ledger()
        record = ledger.records[0]
        original_evidence_digest = record.evidence_digests[0]

        ledger.evidence["e1"] = EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill:python",
            "altered evidence content",
            1.0,
            "fixture",
        )
        self.assertNotEqual(
            ledger.evidence["e1"].digest,
            original_evidence_digest,
        )
        with self.assertRaisesRegex(
            ValueError,
            "evidence content drift",
        ):
            ledger.verify()

    def test_decision_checkpoint_binds_evidence_root(self) -> None:
        ledger = decision_ledger()
        first = ledger.checkpoint()
        self.assertTrue(ledger.verify_checkpoint(first))

        ledger.register_evidence(
            EvidenceRef(
                "e2",
                EvidenceKind.MEMORY,
                "skill:python",
                "new memory",
                0.8,
                "fixture",
            )
        )
        second = ledger.checkpoint()

        self.assertEqual(
            first.head_hash,
            second.head_hash,
        )
        self.assertEqual(
            first.record_count,
            second.record_count,
        )
        self.assertNotEqual(
            first.evidence_root,
            second.evidence_root,
        )
        self.assertNotEqual(first.digest, second.digest)
        self.assertFalse(ledger.verify_checkpoint(first))

    def test_runtime_snapshot_binds_evidence_root_and_ledger_identity(self) -> None:
        ledger = decision_ledger()
        snapshot = runtime_snapshot(ledger)

        self.assertEqual(
            snapshot.evidence_root,
            ledger.evidence_root,
        )
        self.assertEqual(
            snapshot.ledger_identity,
            ledger.ledger_identity,
        )
        self.assertTrue(audit_runtime(snapshot, ledger).valid)

    def test_verified_runtime_capture_rejects_forged_selected_decision(self) -> None:
        ledger = decision_ledger()
        with self.assertRaisesRegex(
            ValueError,
            "cannot capture verified runtime snapshot",
        ):
            RuntimeReplaySnapshot.capture_verified(
                session_id="session-1",
                phase=SessionPhase.DIAGNOSE,
                events=(
                    SessionEvent(
                        1,
                        SessionPhase.INTAKE,
                        "session_opened",
                    ),
                ),
                selected_policy="practice",
                selected_policy_decision_id="session-1:forged",
                rejected_policies=(),
                ledger=ledger,
            )

    def test_runtime_audit_detects_post_capture_evidence_drift(self) -> None:
        ledger = decision_ledger()
        snapshot = runtime_snapshot(ledger)
        before = replay_digest(snapshot)

        ledger.evidence["e1"] = EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill:python",
            "post-capture tamper",
            1.0,
            "fixture",
        )
        audit = audit_runtime(snapshot, ledger)

        self.assertFalse(audit.valid)
        self.assertTrue(
            any(
                "evidence" in violation
                or "ledger integrity" in violation
                for violation in audit.violations
            )
        )
        self.assertEqual(
            replay_digest(snapshot),
            before,
        )

    def test_capsule_detects_evidence_drift_without_decision_extension(self) -> None:
        ledger = decision_ledger()
        snapshot = runtime_snapshot(ledger)
        capsule = RuntimeIntegrityCapsule.capture(
            snapshot,
            ledger,
        )

        ledger.evidence["e1"] = EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill:python",
            "capsule tamper",
            1.0,
            "fixture",
        )
        audit = capsule.verify(ledger)

        self.assertFalse(audit.valid)
        self.assertTrue(
            any(
                "evidence root changed" in item
                or "ledger identity changed" in item
                or "ledger integrity" in item
                for item in audit.violations
            )
        )

    def test_attestation_detects_evidence_drift_without_new_decision(self) -> None:
        ledger = decision_ledger()
        snapshot = runtime_snapshot(ledger)
        attestation = RuntimeAttestation.capture(
            snapshot,
            ledger,
        )

        ledger.evidence["e1"] = EvidenceRef(
            "e1",
            EvidenceKind.OBSERVATION,
            "skill:python",
            "attestation tamper",
            1.0,
            "fixture",
        )
        failures = verify_attestation(
            attestation,
            snapshot,
            ledger,
        )

        self.assertTrue(failures)
        self.assertTrue(
            any(
                "evidence root diverges" in item
                or "ledger content identity diverges" in item
                or "runtime audit is invalid" in item
                for item in failures
            )
        )

    def test_attestation_identity_binds_checkpoint_and_evidence_root(self) -> None:
        ledger = decision_ledger()
        snapshot = runtime_snapshot(ledger)
        attestation = RuntimeAttestation.capture(
            snapshot,
            ledger,
        )
        identity = attestation.attestation_digest

        self.assertTrue(attestation.verify_identity())
        self.assertEqual(
            attestation.evidence_root,
            ledger.evidence_root,
        )
        self.assertEqual(
            attestation.ledger_identity,
            ledger.ledger_identity,
        )
        self.assertEqual(
            attestation.checkpoint_digest,
            ledger.checkpoint().digest,
        )

        tampered = replace(
            attestation,
            checkpoint_digest=sha("wrong-checkpoint"),
        )
        self.assertFalse(tampered.verify_identity())
        self.assertNotEqual(
            tampered.attestation_digest,
            identity
            if tampered.verify_identity()
            else sha("never-equal"),
        )

    def test_capsule_and_attestation_are_deterministic_for_same_state(self) -> None:
        ledger = decision_ledger()
        first_snapshot = runtime_snapshot(ledger)
        second_snapshot = runtime_snapshot(ledger)
        first_capsule = RuntimeIntegrityCapsule.capture(
            first_snapshot,
            ledger,
        )
        second_capsule = RuntimeIntegrityCapsule.capture(
            second_snapshot,
            ledger,
        )
        first_attestation = RuntimeAttestation.capture(
            first_snapshot,
            ledger,
        )
        second_attestation = RuntimeAttestation.capture(
            second_snapshot,
            ledger,
        )

        self.assertEqual(
            first_snapshot,
            second_snapshot,
        )
        self.assertEqual(
            first_capsule,
            second_capsule,
        )
        self.assertEqual(
            first_attestation,
            second_attestation,
        )


if __name__ == "__main__":
    unittest.main()
