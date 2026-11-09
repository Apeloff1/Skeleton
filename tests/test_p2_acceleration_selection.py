from __future__ import annotations

import unittest

from skeleton.native.selection import (
    AccelerationSelectionError,
    ProfileEvidence,
    SelectionPolicy,
    evaluate_candidate,
)


class AccelerationSelectionTests(unittest.TestCase):
    def _evidence(
        self,
        evidence_id: str,
        *,
        source: str = "sha-a",
        reference_ns: int = 1_000,
        candidate_ns: int = 500,
        correctness: bool = True,
        error: float = 0.0,
        crashes: int = 0,
        timeouts: int = 0,
    ) -> ProfileEvidence:
        return ProfileEvidence(
            evidence_id=evidence_id,
            candidate_id="ACCEL-NATIVE-VECTOR",
            source_identity=source,
            environment_id="linux-x86_64-py311",
            sample_count=100,
            reference_median_ns=reference_ns,
            candidate_median_ns=candidate_ns,
            correctness_passed=correctness,
            max_abs_error=error,
            crash_count=crashes,
            timeout_count=timeouts,
        )

    def test_policy_mapping_does_not_coerce_strings_or_booleans(self) -> None:
        base = {
            "minimum_profile_runs": 2,
            "minimum_distinct_environment_ids": 1,
            "minimum_speedup": 1.2,
            "maximum_abs_error": 1e-5,
            "maximum_crashes": 0,
            "maximum_timeouts": 0,
        }
        bad_bool = dict(base, minimum_profile_runs=True)
        with self.assertRaises(TypeError):
            from skeleton.native.selection import policy_from_mapping
            policy_from_mapping(bad_bool)
        bad_string = dict(base, minimum_speedup="1.2")
        with self.assertRaises(TypeError):
            policy_from_mapping(bad_string)

    def test_selection_policy_rejects_boolean_numeric_fields(self) -> None:
        with self.assertRaises(TypeError):
            SelectionPolicy(minimum_profile_runs=True)
        with self.assertRaises(TypeError):
            SelectionPolicy(maximum_crashes=False)
        with self.assertRaises(TypeError):
            SelectionPolicy(minimum_speedup=True)

    def test_selection_inputs_do_not_coerce_invalid_types(self) -> None:
        with self.assertRaisesRegex(
            AccelerationSelectionError,
            "candidate_id",
        ):
            evaluate_candidate(
                candidate_id=123,
                current_source_identity="sha-a",
                reference_available=True,
                isolation_satisfied=True,
                protocol_compatible=True,
                evidence=[],
                policy=SelectionPolicy(),
            )
        with self.assertRaises(TypeError):
            evaluate_candidate(
                candidate_id="ACCEL-NATIVE-VECTOR",
                current_source_identity="sha-a",
                reference_available=1,
                isolation_satisfied=True,
                protocol_compatible=True,
                evidence=[],
                policy=SelectionPolicy(),
            )
        with self.assertRaises(TypeError):
            evaluate_candidate(
                candidate_id="ACCEL-NATIVE-VECTOR",
                current_source_identity="sha-a",
                reference_available=True,
                isolation_satisfied=True,
                protocol_compatible=True,
                evidence="not-evidence",
                policy=SelectionPolicy(),
            )

    def test_no_evidence_uses_reference(self) -> None:
        result = evaluate_candidate(
            candidate_id="ACCEL-NATIVE-VECTOR",
            current_source_identity="sha-a",
            reference_available=True,
            isolation_satisfied=True,
            protocol_compatible=True,
            evidence=[],
            policy=SelectionPolicy(),
        )
        self.assertFalse(result.qualified)
        self.assertEqual(result.route, "reference")
        self.assertIn("insufficient_profile_runs", result.reason_codes)

    def test_two_strong_runs_can_qualify(self) -> None:
        result = evaluate_candidate(
            candidate_id="ACCEL-NATIVE-VECTOR",
            current_source_identity="sha-a",
            reference_available=True,
            isolation_satisfied=True,
            protocol_compatible=True,
            evidence=[self._evidence("e1"), self._evidence("e2")],
            policy=SelectionPolicy(),
        )
        self.assertTrue(result.qualified)
        self.assertEqual(result.route, "accelerated")
        self.assertGreaterEqual(result.worst_speedup or 0.0, 1.2)

    def test_duplicate_profile_receipt_cannot_satisfy_run_count(self) -> None:
        receipt = self._evidence("e1")
        result = evaluate_candidate(
            candidate_id="ACCEL-NATIVE-VECTOR",
            current_source_identity="sha-a",
            reference_available=True,
            isolation_satisfied=True,
            protocol_compatible=True,
            evidence=[receipt, receipt],
            policy=SelectionPolicy(),
        )
        self.assertFalse(result.qualified)
        self.assertIn("duplicate_profile_evidence", result.reason_codes)

    def test_stale_source_fails_closed(self) -> None:
        result = evaluate_candidate(
            candidate_id="ACCEL-NATIVE-VECTOR",
            current_source_identity="sha-new",
            reference_available=True,
            isolation_satisfied=True,
            protocol_compatible=True,
            evidence=[self._evidence("e1"), self._evidence("e2")],
            policy=SelectionPolicy(),
        )
        self.assertFalse(result.qualified)
        self.assertIn("stale_source_identity", result.reason_codes)

    def test_crash_or_correctness_failure_is_non_compensable(self) -> None:
        result = evaluate_candidate(
            candidate_id="ACCEL-NATIVE-VECTOR",
            current_source_identity="sha-a",
            reference_available=True,
            isolation_satisfied=True,
            protocol_compatible=True,
            evidence=[
                self._evidence("e1", reference_ns=10_000, candidate_ns=100),
                self._evidence("e2", reference_ns=10_000, candidate_ns=100, correctness=False, crashes=1),
            ],
            policy=SelectionPolicy(),
        )
        self.assertFalse(result.qualified)
        self.assertIn("correctness_failure", result.reason_codes)
        self.assertIn("crash_budget_exceeded", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
