"""SQLite durable offline AI job lifecycle and exact request identity."""
from __future__ import annotations

import sqlite3
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec, make_result, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.store import JobStore
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied


class TestDurableJobStore(unittest.TestCase):
    def setUp(self):
        self.store=make_store()
        self.spec=make_spec()

    def tearDown(self):
        self.store.db.close()

    def test_submit_no_duplicate_job(self):
        self.assertEqual(self.store.submit(self.spec,now_ms=1000),"admitted")
        self.assertEqual(self.store.submit(self.spec,now_ms=1000),"replayed")
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"pending")
        self.assertEqual(len(self.store.audit("job_1",OWNER)),1)

    def test_request_id_collision_denied(self):
        self.store.submit(self.spec,now_ms=1000)
        with self.assertRaises(JobDenied):
            self.store.submit(make_spec(name="another",request_id="job_1"),
                              now_ms=1000)
        with self.assertRaises(JobDenied):
            self.store.submit(make_spec(name="job_1",question="different"),now_ms=1000)

    def test_claim_and_complete_verified(self):
        self.store.submit(self.spec,now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertEqual(claim.owner,OWNER)
        self.assertEqual(claim.attempt,1)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"running")
        result=make_result(self.spec,text="Local model result.")
        self.assertEqual(self.store.finish(claim,result,now_ms=1200),"committed")
        self.assertEqual(self.store.finish(claim,result,now_ms=1200),"replayed")
        self.assertEqual(self.store.receipt("job_1",OWNER),result)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"completed")

    def test_result_identity_binds_model(self):
        self.store.submit(self.spec,now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        with self.assertRaises(JobDenied):
            self.store.finish(claim,make_result(self.spec,model_sha="c"*64),
                              now_ms=1200)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"running")

    def test_failed_transaction_not_partially_committed(self):
        self.store.submit(self.spec,now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        with self.assertRaises(JobDenied):
            self.store.finish(claim,make_result(self.spec,output_tokens=1000),
                              now_ms=1200)
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"running")
        self.assertEqual(len(self.store.audit("job_1",OWNER)),2)

    def test_wrong_owner_read_denied(self):
        from skeleton.ai.runtime.operational_ai.durable_jobs.spec import JobIdentity
        self.store.submit(self.spec,now_ms=1000)
        outside=JobIdentity("other","user","session","a"*64,"b"*64)
        with self.assertRaises(JobDenied):
            self.store.inspect("job_1",outside)
        with self.assertRaises(JobDenied):
            self.store.receipt("job_1",outside)


if __name__=="__main__":
    unittest.main()
