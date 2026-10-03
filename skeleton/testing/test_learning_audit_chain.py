from __future__ import annotations

from dataclasses import dataclass
import hashlib
import unittest

from skeleton.ai.learning.audit_chain import (
    LearningAuditError,
    LearningAuditEvent,
    LearningAuditLedger,
)
from skeleton.shells.evidence_chain import EvidenceNode


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


class LearningAuditChainTests(unittest.TestCase):
    def event(
        self,
        event_id: str,
        kind: str,
        *,
        parent: str | None = None,
    ) -> LearningAuditEvent:
        return LearningAuditEvent(
            event_id=event_id,
            kind=kind,
            actor_principal="principal:trainer",
            subject_id="model:test",
            subject_digest=sha("model"),
            policy_digest=sha("policy"),
            decision="allow",
            evidence_root=sha("evidence"),
            code_revision="deadbeef",
            parent_event_id=parent,
            details={"run_id": "run-1"},
        )

    def test_append_and_verify_typed_learning_receipts(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        first = ledger.append(self.event("evt-1", "training_started"))
        second = ledger.append(
            self.event("evt-2", "training_completed", parent="evt-1")
        )
        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(second.previous_root, first.root_hash)
        self.assertTrue(ledger.verify())
        self.assertTrue(ledger.verify_receipt(first))
        self.assertTrue(ledger.verify_receipt(second))

    def test_duplicate_event_id_is_rejected(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        ledger.append(self.event("evt-1", "training_started"))
        with self.assertRaisesRegex(LearningAuditError, "already committed"):
            ledger.append(self.event("evt-1", "training_completed"))

    def test_unknown_parent_is_rejected(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        with self.assertRaisesRegex(LearningAuditError, "parent_event_id"):
            ledger.append(
                self.event("evt-2", "training_completed", parent="evt-missing")
            )

    def test_unsupported_event_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(LearningAuditError, "unsupported"):
            self.event("evt-x", "arbitrary_mutation")

    def test_receipt_detects_node_payload_tampering(self) -> None:
        backend = _MemoryBackend()
        ledger = LearningAuditLedger(backend)
        receipt = ledger.append(self.event("evt-1", "training_started"))
        slot = ("ai-learning-audit-v1", f"node:{receipt.root_hash}")
        record = backend.records[slot]
        node = record.value
        self.assertIsInstance(node, EvidenceNode)
        assert isinstance(node, EvidenceNode)
        tampered = EvidenceNode(
            sequence=node.sequence,
            previous_hash=node.previous_hash,
            node_hash=node.node_hash,
            kind=node.kind,
            payload={**dict(node.payload), "decision": "deny"},
        )
        backend.records[slot] = _Record(record.revision + 1, tampered)
        self.assertFalse(ledger.verify())
        self.assertFalse(ledger.verify_receipt(receipt))

    def test_event_digest_binds_subject_policy_and_evidence(self) -> None:
        event = self.event("evt-1", "evaluation_completed")
        changed = LearningAuditEvent(
            event_id=event.event_id,
            kind=event.kind,
            actor_principal=event.actor_principal,
            subject_id=event.subject_id,
            subject_digest=sha("different-model"),
            policy_digest=event.policy_digest,
            decision=event.decision,
            evidence_root=event.evidence_root,
            code_revision=event.code_revision,
            details=event.details,
        )
        self.assertNotEqual(event.event_digest, changed.event_digest)

    def test_model_lifecycle_sequence_can_be_chained(self) -> None:
        ledger = LearningAuditLedger(_MemoryBackend())
        ids = []
        parent = None
        for index, kind in enumerate(
            (
                "dataset_admitted",
                "training_started",
                "training_checkpointed",
                "training_completed",
                "evaluation_completed",
                "promotion_proposed",
                "promotion_approved",
                "artifact_load_admitted",
                "model_activated",
            ),
            start=1,
        ):
            event_id = f"evt-{index}"
            ledger.append(self.event(event_id, kind, parent=parent))
            ids.append(event_id)
            parent = event_id
        self.assertEqual(ledger.length(), len(ids))
        self.assertTrue(ledger.verify())


if __name__ == "__main__":
    unittest.main()
