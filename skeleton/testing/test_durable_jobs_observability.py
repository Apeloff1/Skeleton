"""Integrity-coupled owner-specific projections never reveal raw questions."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER,make_spec,make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.invariants import verify_store
from skeleton.ai.runtime.operational_ai.durable_jobs.observer import metrics
from skeleton.ai.runtime.operational_ai.durable_jobs.read_model import list_jobs
from skeleton.ai.runtime.operational_ai.durable_jobs.pagination import CursorCodec


class TestDurableObservability(unittest.TestCase):
    def setUp(self):
        self.store=make_store()
        for i in range(5):
            self.store.submit(make_spec(name="job_"+str(i),
                                        question="PRIVATE QUESTION SECRET "+str(i)),
                              now_ms=1000)

    def tearDown(self):
        self.store.db.close()

    def test_integrity_proof_is_not_model_qualification(self):
        proof=verify_store(self.store)
        self.assertEqual(proof["jobs"],5)
        self.assertTrue(proof["verified"])
        self.assertFalse(proof["native_model_qualified"])

    def test_keyset_owner_pagination(self):
        first=list_jobs(self.store,OWNER,page_size=2)
        self.assertEqual(len(first["items"]),2)
        self.assertTrue(first["has_more"])
        second=list_jobs(self.store,OWNER,page_size=2,
                         last_job_id=first["next_job_id"])
        self.assertEqual(len(second["items"]),2)
        ids={x["job_id"] for x in first["items"]+second["items"]}
        self.assertEqual(len(ids),4)
        self.assertNotIn("question",str(first))

    def test_audit_backed_metrics_are_bounded(self):
        state=metrics(self.store,"tenant",top=3)
        self.assertTrue(state["verified"])
        self.assertEqual(state["states"]["pending"],5)
        self.assertEqual(len(state["recent"]),3)
        self.assertNotIn("PRIVATE QUESTION",str(state))

    def test_tamper_blocks_projection(self):
        self.store.db.execute("UPDATE ai_job_audit SET previous_sha=?",("f"*64,))
        with self.assertRaises(JobDenied):
            metrics(self.store,"tenant")

    def test_tenant_cursor_key_not_reusable(self):
        codec=CursorCodec(b"secret"*8)
        cursor=codec.seal(tenant="tenant",last_job_id="job_1",
                          issued_ms=1000,expires_ms=2000)
        self.assertEqual(codec.open(cursor,tenant="tenant",now_ms=1500),"job_1")
        with self.assertRaises(JobDenied):
            codec.open(cursor,tenant="other",now_ms=1500)


if __name__=="__main__":
    unittest.main()
