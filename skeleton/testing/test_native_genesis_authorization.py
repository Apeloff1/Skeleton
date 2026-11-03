"""Training success cannot authorize production model routing or release."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.result_boundaries import (
    OperationalBoundaries,
)
from skeleton.ai.runtime.operational_ai.native_genesis.failure_codes import classify
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestNativeGenesisAuthorization(unittest.TestCase):
    def test_unqualified_work_is_never_release_ready(self):
        record=OperationalBoundaries(
            True,True,True,True,False,False,False,False,False,
        ).report()
        self.assertTrue(record["candidate_ready"])
        self.assertFalse(record["independent_quality_ready"])
        self.assertFalse(record["release_certified"])
        self.assertFalse(record["automatic_promotion"])

    def test_all_input_booleans_still_not_self_certification(self):
        record=OperationalBoundaries(
            True,True,True,True,True,True,True,True,True,
        ).report()
        self.assertTrue(record["independent_quality_ready"])
        self.assertFalse(record["release_certified"])

    def test_unknown_gate_status_cannot_be_cast_from_integer(self):
        with self.assertRaises(GenesisRejected):
            OperationalBoundaries(True,True,True,True,True,True,True,True,1)

    def test_unknown_failures_still_hold(self):
        report=classify("unclassified_runtime_failure")
        self.assertEqual(report["category"],"unclassified")
        self.assertFalse(report["retry_without_manual_review"])
        self.assertFalse(report["production_authorized"])

    def test_checkpoint_tamper_cannot_be_retried(self):
        proof=classify("checkpoint-hash-mismatch")
        self.assertEqual(proof["category"],"artifact-tamper")
        self.assertFalse(proof["retry_without_manual_review"])


if __name__=="__main__":
    unittest.main()
