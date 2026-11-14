"""Explicit native-replay hold and source-bound operator recovery."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec, make_result, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.recovery import inspect_hold


class TestDurableRecovery(unittest.TestCase):
    def setUp(self):
        self.store=make_store()
        self.store.submit(make_spec(),now_ms=1000)

    def tearDown(self):
        self.store.db.close()

    def test_ambiguous_native_failure_never_automatically_requeued(self):
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertEqual(self.store.fail(claim,now_ms=1200,
                                         code="native-ambiguous",ambiguous=True),"held")
        self.assertIsNone(self.store.claim("worker",now_ms=1300))
        proof=inspect_hold(self.store,"job_1",OWNER,now_ms=1300)
        self.assertFalse(proof["automatic_retry_allowed"])

    def test_no_effect_proof_required(self):
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.store.fail(claim,now_ms=1200,code="ambiguous",ambiguous=True)
        with self.assertRaises(JobDenied):
            self.store.manual_resume("job_1",OWNER,now_ms=1300,
                                     no_effect_proof_sha256="a"*64,
                                     operator_approved=True,proof_verifier=None)
        with self.assertRaises(JobDenied):
            self.store.manual_resume("job_1",OWNER,now_ms=1300,
                                     no_effect_proof_sha256="a"*64,
                                     operator_approved=True,proof_verifier=lambda spec,proof:False)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"held")

    def test_operator_bounded_verified_manual_resume(self):
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.store.fail(claim,now_ms=1200,code="ambiguous",ambiguous=True)
        approved=lambda spec,proof:spec.request_id=="job_1" and proof=="a"*64
        self.assertEqual(self.store.manual_resume(
            "job_1",OWNER,now_ms=1300,no_effect_proof_sha256="a"*64,
            operator_approved=True,proof_verifier=approved),"pending")
        new_claim=self.store.claim("worker_2",now_ms=1301,lease_ms=500)
        self.assertEqual(new_claim.attempt,2)

    def test_stale_inference_held_by_sweep(self):
        self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertEqual(self.store.sweep(now_ms=1500)["held_running"],1)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"held")
        self.assertIsNone(self.store.claim("worker",now_ms=1501))

    def test_pending_expiration_does_not_infer(self):
        self.assertEqual(self.store.sweep(now_ms=10000)["expired_pending"],1)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"cancelled")
        self.assertIsNone(self.store.claim("worker",now_ms=10001))

    def test_cancellation_running_preserves_audit(self):
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertEqual(self.store.cancel("job_1",OWNER,now_ms=1200),"cancel_requested")
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"cancel_requested")
        self.assertEqual(self.store.finish(
            claim,make_result(make_spec()),now_ms=1300),"committed")


if __name__=="__main__":
    unittest.main()
