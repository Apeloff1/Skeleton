from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "record_p2_acceleration_profile",
    ROOT / "scripts" / "record_p2_acceleration_profile.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

from skeleton.native.profiling import source_identity


class AccelerationReceiptTests(unittest.TestCase):
    def _policy(self) -> dict:
        return json.loads(
            (ROOT / "machine/acceleration_policy.json").read_text(encoding="utf-8")
        )

    def _receipt(
        self,
        policy: dict,
        evidence_id: str,
        *,
        candidate_id: str = "ACCEL-NATIVE-VECTOR",
        source: str | None = None,
        reference_ns: int = 1_000,
        candidate_ns: int = 500,
        correctness: bool = True,
        error: float = 0.0,
        crashes: int = 0,
        timeouts: int = 0,
    ) -> dict:
        candidate = next(
            item for item in policy["candidates"]
            if item["id"] == candidate_id
        )
        identity = source or source_identity(
            ROOT,
            candidate["source_identity_paths"],
        )
        return {
            "evidence_id": evidence_id,
            "candidate_id": candidate_id,
            "source_identity": identity,
            "environment_id": "test-linux-x86_64-py311",
            "sample_count": 100,
            "reference_median_ns": reference_ns,
            "candidate_median_ns": candidate_ns,
            "correctness_passed": correctness,
            "max_abs_error": error,
            "crash_count": crashes,
            "timeout_count": timeouts,
        }

    def test_one_receipt_remains_unqualified(self) -> None:
        policy = self._policy()
        updated, decision = MODULE.apply_receipt(
            policy,
            self._receipt(policy, "receipt-1"),
            root=ROOT,
        )
        candidate = next(
            item for item in updated["candidates"]
            if item["id"] == "ACCEL-NATIVE-VECTOR"
        )
        self.assertFalse(decision.qualified)
        self.assertFalse(candidate["automatic_selection"])
        self.assertEqual(candidate["state"], "candidate_unpromoted")
        self.assertIn("insufficient_profile_runs", decision.reason_codes)

    def test_two_strong_receipts_qualify_without_activation(self) -> None:
        policy = self._policy()
        once, _ = MODULE.apply_receipt(
            policy,
            self._receipt(policy, "receipt-1"),
            root=ROOT,
        )
        twice, decision = MODULE.apply_receipt(
            once,
            self._receipt(once, "receipt-2"),
            root=ROOT,
        )
        candidate = next(
            item for item in twice["candidates"]
            if item["id"] == "ACCEL-NATIVE-VECTOR"
        )
        self.assertTrue(decision.qualified)
        self.assertFalse(candidate["automatic_selection"])
        self.assertEqual(candidate["state"], "evidence_qualified_unpromoted")
        self.assertEqual(
            candidate["selection_decision"]["evidence_ids"],
            ["receipt-1", "receipt-2"],
        )

    def test_activation_requires_qualified_evidence(self) -> None:
        policy = self._policy()
        with self.assertRaisesRegex(
            MODULE.ReceiptIngestionError,
            "activation rejected",
        ):
            MODULE.apply_receipt(
                policy,
                self._receipt(policy, "receipt-1"),
                root=ROOT,
                activate=True,
            )

    def test_activation_after_qualified_history_is_explicit(self) -> None:
        policy = self._policy()
        once, _ = MODULE.apply_receipt(
            policy,
            self._receipt(policy, "receipt-1"),
            root=ROOT,
        )
        twice, _ = MODULE.apply_receipt(
            once,
            self._receipt(once, "receipt-2"),
            root=ROOT,
        )
        activated, decision = MODULE.apply_receipt(
            twice,
            self._receipt(twice, "receipt-3"),
            root=ROOT,
            activate=True,
        )
        candidate = next(
            item for item in activated["candidates"]
            if item["id"] == "ACCEL-NATIVE-VECTOR"
        )
        self.assertTrue(decision.qualified)
        self.assertTrue(candidate["automatic_selection"])
        self.assertEqual(candidate["state"], "profile_selected_unpromoted")

    def test_stale_source_identity_rejects(self) -> None:
        policy = self._policy()
        stale = self._receipt(policy, "receipt-stale", source="stale")
        with self.assertRaisesRegex(
            MODULE.ReceiptIngestionError,
            "source identity is stale",
        ):
            MODULE.apply_receipt(policy, stale, root=ROOT)

    def test_duplicate_receipt_id_rejects(self) -> None:
        policy = self._policy()
        once, _ = MODULE.apply_receipt(
            policy,
            self._receipt(policy, "receipt-1"),
            root=ROOT,
        )
        with self.assertRaisesRegex(
            MODULE.ReceiptIngestionError,
            "duplicate profile evidence id",
        ):
            MODULE.apply_receipt(
                once,
                self._receipt(once, "receipt-1"),
                root=ROOT,
            )

    def test_failed_correctness_never_activates(self) -> None:
        policy = self._policy()
        first, _ = MODULE.apply_receipt(
            policy,
            self._receipt(
                policy,
                "receipt-bad-1",
                reference_ns=100_000,
                candidate_ns=100,
                correctness=False,
            ),
            root=ROOT,
        )
        with self.assertRaisesRegex(
            MODULE.ReceiptIngestionError,
            "activation rejected",
        ):
            MODULE.apply_receipt(
                first,
                self._receipt(
                    first,
                    "receipt-bad-2",
                    reference_ns=100_000,
                    candidate_ns=100,
                    correctness=False,
                ),
                root=ROOT,
                activate=True,
            )

    def test_activation_authority_requires_boolean(self) -> None:
        policy = self._policy()
        for ambiguous in (1, "true", None):
            with self.subTest(activate=ambiguous):
                with self.assertRaisesRegex(
                    MODULE.ReceiptIngestionError,
                    "activate must be boolean",
                ):
                    MODULE.apply_receipt(
                        policy,
                        self._receipt(policy, f"receipt-{ambiguous!r}"),
                        root=ROOT,
                        activate=ambiguous,
                    )

    def test_receipt_identity_fields_require_canonical_text(self) -> None:
        policy = self._policy()
        for field in ("evidence_id", "candidate_id", "source_identity", "environment_id"):
            receipt = self._receipt(policy, "receipt-canonical")
            receipt[field] = " " + str(receipt[field])
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    MODULE.ReceiptIngestionError,
                    "canonical text",
                ):
                    MODULE.apply_receipt(policy, receipt, root=ROOT)

    def test_loader_rejects_duplicate_authority_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            path.write_text(
                '{"evidence_id":"trusted","evidence_id":"shadow"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.ReceiptIngestionError,
                "duplicate JSON object key: evidence_id",
            ):
                MODULE._load_object(path, label="profile receipt")

    def test_loader_rejects_nonfinite_json_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            for token in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(token=token):
                    path.write_text(
                        '{"max_abs_error":' + token + '}',
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        MODULE.ReceiptIngestionError,
                        "non-finite JSON token rejected",
                    ):
                        MODULE._load_object(path, label="profile receipt")


if __name__ == "__main__":
    unittest.main()
