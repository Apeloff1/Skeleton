from __future__ import annotations

import hashlib
import unittest

from skeleton.ai.learning.training_integrity import (
    IntegritySignal,
    TrainingIntegrityError,
    TrainingIntegrityGate,
    TransformIdentity,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TrainingIntegrityTests(unittest.TestCase):
    def transform(self) -> TransformIdentity:
        return TransformIdentity(
            transform_id="normalize-v1",
            implementation_digest=sha("transform-code"),
            configuration_digest=sha("transform-config"),
            signer_ref="sigstore:fixture",
        )

    def signals(self, source_id: str, *, fail_kind: str | None = None):
        rows = []
        for kind in (
            "content-anomaly",
            "label-anomaly",
            "source-ablation",
            "trigger-canary",
        ):
            rows.append(
                IntegritySignal(
                    source_id=source_id,
                    kind=kind,
                    detector_id=f"detector:{kind}",
                    detector_digest=sha(f"detector:{kind}:v1"),
                    passed=kind != fail_kind,
                    evidence_ref=f"evidence:{source_id}:{kind}",
                    score=0.1,
                )
            )
        return tuple(rows)

    def test_complete_integrity_evidence_admits_dataset(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        receipt = gate.evaluate(
            dataset_id="dataset-1",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a"), "source:b": sha("b")},
            transforms=(self.transform(),),
            signals=self.signals("source:a") + self.signals("source:b"),
        )
        self.assertTrue(receipt.admitted)
        gate.require_admitted(receipt)
        self.assertEqual(len(receipt.digest), 64)

    def test_failed_trigger_canary_quarantines_dataset(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        receipt = gate.evaluate(
            dataset_id="dataset-1",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a")},
            transforms=(self.transform(),),
            signals=self.signals("source:a", fail_kind="trigger-canary"),
        )
        self.assertFalse(receipt.admitted)
        self.assertEqual(receipt.source_decisions[0].disposition, "quarantine")
        with self.assertRaisesRegex(TrainingIntegrityError, "quarantined"):
            gate.require_admitted(receipt)

    def test_missing_signal_quarantines_source(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        rows = tuple(
            signal for signal in self.signals("source:a")
            if signal.kind != "source-ablation"
        )
        receipt = gate.evaluate(
            dataset_id="dataset-1",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a")},
            transforms=(self.transform(),),
            signals=rows,
        )
        self.assertFalse(receipt.admitted)
        self.assertIn("source-ablation", receipt.source_decisions[0].rationale)

    def test_unknown_source_signal_is_rejected(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        with self.assertRaisesRegex(TrainingIntegrityError, "unknown source"):
            gate.evaluate(
                dataset_id="dataset-1",
                dataset_digest=sha("dataset"),
                source_digests={"source:a": sha("a")},
                transforms=(self.transform(),),
                signals=self.signals("source:other"),
            )

    def test_unsigned_transform_lineage_is_rejected(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        with self.assertRaisesRegex(TrainingIntegrityError, "signed transform"):
            gate.evaluate(
                dataset_id="dataset-1",
                dataset_digest=sha("dataset"),
                source_digests={"source:a": sha("a")},
                transforms=(),
                signals=self.signals("source:a"),
            )

    def test_integrity_receipt_is_deterministic(self) -> None:
        gate = TrainingIntegrityGate(policy_digest=sha("policy-v1"))
        kwargs = dict(
            dataset_id="dataset-1",
            dataset_digest=sha("dataset"),
            source_digests={"source:a": sha("a")},
            transforms=(self.transform(),),
            signals=self.signals("source:a"),
        )
        self.assertEqual(gate.evaluate(**kwargs).digest, gate.evaluate(**kwargs).digest)


if __name__ == "__main__":
    unittest.main()
