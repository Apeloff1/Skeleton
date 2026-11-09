from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import unittest

from skeleton.quality.final_assembly import (
    FinalAssemblyError,
    FinalAssemblyEvidence,
    GateReceipt,
    RiskDisposition,
    evaluate_promotion,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_p2_final_assembly",
    ROOT / "scripts" / "run_p2_final_assembly.py",
)
assert RUNNER_SPEC and RUNNER_SPEC.loader
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(RUNNER)


def d(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class FinalAssemblyTests(unittest.TestCase):
    def evidence(self, **changes):
        values = dict(
            source_sha="a" * 40,
            environment={
                "os": "ubuntu-24.04",
                "python": "3.11.16",
                "architecture": "x86_64",
            },
            gate_receipts=(GateReceipt("G1", True, d(b"out"), d(b"err")),),
            risk_dispositions=(
                RiskDisposition("R1", "closed", ("evidence://r1",)),
            ),
            dependency_snapshot_sha256=d(b"pip-freeze"),
            builder_id="builder-a",
            verifier_id="verifier-b",
            verified_at_utc="2026-10-01T00:00:00Z",
        )
        values.update(changes)
        return FinalAssemblyEvidence(**values)

    def decision(
        self,
        evidence,
        *,
        presented_digest=None,
        expected_source_sha="a" * 40,
        expected_environment=None,
        required_gate_ids=("G1",),
    ):
        return evaluate_promotion(
            evidence,
            presented_digest=presented_digest or evidence.evidence_digest,
            expected_source_sha=expected_source_sha,
            expected_environment=expected_environment
            or {
                "os": "ubuntu-24.04",
                "python": "3.11.16",
                "architecture": "x86_64",
            },
            required_gate_ids=required_gate_ids,
        )

    def test_matching_verified_evidence_can_promote(self) -> None:
        evidence = self.evidence()
        decision = self.decision(evidence)
        self.assertTrue(decision.ready)

    def test_digest_mismatch_blocks(self) -> None:
        evidence = self.evidence()
        decision = self.decision(evidence, presented_digest="0" * 64)
        self.assertFalse(decision.ready)
        self.assertIn("digest mismatch", decision.blockers[0])

    def test_failed_gate_and_blocking_risk_block(self) -> None:
        evidence = self.evidence(
            gate_receipts=(GateReceipt("G1", False, d(b""), d(b"failure")),),
            risk_dispositions=(
                RiskDisposition("R1", "blocking", ("masterplan://r1",)),
            ),
        )
        decision = self.decision(evidence)
        self.assertFalse(decision.ready)
        self.assertGreaterEqual(len(decision.blockers), 2)

    def test_missing_required_gate_receipt_blocks(self) -> None:
        evidence = self.evidence()
        decision = self.decision(evidence, required_gate_ids=("G1", "G2"))
        self.assertFalse(decision.ready)
        self.assertIn("final assembly gate receipt coverage mismatch", decision.blockers)

    def test_source_sha_mismatch_blocks(self) -> None:
        evidence = self.evidence()
        decision = self.decision(evidence, expected_source_sha="b" * 40)
        self.assertFalse(decision.ready)
        self.assertIn("final assembly source SHA mismatch", decision.blockers)

    def test_environment_mismatch_blocks(self) -> None:
        evidence = self.evidence()
        decision = self.decision(
            evidence,
            expected_environment={
                "os": "ubuntu-24.04",
                "python": "3.11.16",
                "architecture": "arm64",
            },
        )
        self.assertFalse(decision.ready)
        self.assertIn("final assembly environment mismatch", decision.blockers)

    def test_harness_rejects_non_head_source_before_execution(self) -> None:
        with self.assertRaisesRegex(
            RUNNER.FinalAssemblyHarnessError,
            "not exact checked-out HEAD",
        ):
            RUNNER.execute("0" * 40, root=ROOT)

    def test_risk_dispositions_default_fail_closed(self) -> None:
        control = {
            "masterplan_bindings": [
                {"volume_ref": "VOL-X", "risks": ["risk-a", "risk-b"]}
            ]
        }
        risks = RUNNER.build_risk_dispositions(control)
        self.assertEqual([risk.status for risk in risks], ["blocking", "blocking"])

    def test_complete_reviewed_risk_dispositions_can_close_or_accept(self) -> None:
        control = {
            "masterplan_bindings": [
                {"volume_ref": "VOL-X", "risks": ["risk-a", "risk-b"]}
            ]
        }
        risks = RUNNER.build_risk_dispositions(
            control,
            [
                {
                    "risk_id": "VOL-X:risk:001",
                    "status": "closed",
                    "evidence_refs": ["run://risk-a"],
                },
                {
                    "risk_id": "VOL-X:risk:002",
                    "status": "accepted",
                    "evidence_refs": ["review://risk-b"],
                    "authority_ref": "authority://release-board",
                },
            ],
        )
        self.assertEqual([risk.status for risk in risks], ["closed", "accepted"])

    def test_unknown_risk_disposition_id_is_rejected(self) -> None:
        control = {
            "masterplan_bindings": [
                {"volume_ref": "VOL-X", "risks": ["risk-a"]}
            ]
        }
        with self.assertRaisesRegex(
            RUNNER.FinalAssemblyHarnessError,
            "unknown IDs",
        ):
            RUNNER.build_risk_dispositions(
                control,
                [
                    {
                        "risk_id": "VOL-X:risk:999",
                        "status": "closed",
                        "evidence_refs": ["run://unknown"],
                    }
                ],
            )

    def test_dependency_snapshot_is_digest_bound(self) -> None:
        first = self.evidence(dependency_snapshot_sha256=d(b"one"))
        second = self.evidence(dependency_snapshot_sha256=d(b"two"))
        self.assertNotEqual(first.evidence_digest, second.evidence_digest)

    def test_builder_cannot_self_verify(self) -> None:
        with self.assertRaises(FinalAssemblyError):
            self.evidence(verifier_id="builder-a")

    def test_accepted_risk_requires_authority(self) -> None:
        with self.assertRaises(ValueError):
            RiskDisposition("R1", "accepted", ("evidence://r1",))


if __name__ == "__main__":
    unittest.main()
