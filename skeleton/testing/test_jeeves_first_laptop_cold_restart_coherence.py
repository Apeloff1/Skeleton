"""cold_restart: independently accepted observations must share one epoch."""
from __future__ import annotations
import unittest
from skeleton.jeeves.native_fabric.laptop_ops.casebook import (
    successful_evidence, mutation_cases,
)
from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from skeleton.jeeves.native_fabric.laptop_ops.runner import evaluate_domain
from skeleton.jeeves.native_fabric.laptop_ops.domains.cold_restart.registry import (
    STAGES, STAGE_TYPES, contracts,
)

class TestCoherence(unittest.TestCase):
    def test_consistent_source_is_not_a_real_cold_reopen(self):
        verdict = evaluate_domain("cold_restart", successful_evidence(STAGE_TYPES))
        self.assertTrue(verdict.accepted)
        self.assertIs(verdict.to_record()["release_certified"], False)

    def test_conflicting_cross_stage_recovery_claims_refused(self):
        e = successful_evidence(STAGE_TYPES)
        e["loaded_checkpoint"] = {"expected_sha256":"b"*64, "observed_sha256":"b"*64}
        with self.assertRaises(LaptopGateHold):
            evaluate_domain("cold_restart", e)

    def test_independent_stage_failure_retains_denial(self):
        stage,e = mutation_cases(STAGE_TYPES)[0]
        record = evaluate_domain("cold_restart", e)
        self.assertFalse(record.accepted)
        self.assertIn(stage,[s.stage for s in record.stages if not s.accepted])
