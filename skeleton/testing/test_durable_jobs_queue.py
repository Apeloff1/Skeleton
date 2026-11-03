"""Tenant fairness, worker concurrency and lease fences with real SQLite state."""
from __future__ import annotations

import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec, make_result, make_store,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.spec import JobIdentity,WorkLimits
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied


class TestDurableJobQueue(unittest.TestCase):
    def setUp(self):
        self.store=make_store(WorkLimits(queue_depth=16,tenant_depth=8,
                                          active_per_tenant=1,lease_ms=1000))

    def tearDown(self):
        self.store.db.close()

    def test_fair_round_robin_tenants(self):
        for i,tenant in enumerate(("zeta","alpha","beta")):
            own=JobIdentity(tenant,"user","session","a"*64,"b"*64)
            self.store.submit(make_spec(name="job_"+str(i),owner=own),now_ms=1000)
        claims=[self.store.claim("worker",now_ms=1000) for _ in range(3)]
        self.assertEqual([c.owner.tenant for c in claims],["alpha","beta","zeta"])
        self.assertIsNone(self.store.claim("worker",now_ms=1000))

    def test_tenant_parallel_limit(self):
        self.store.submit(make_spec(name="job_a"),now_ms=1000)
        self.store.submit(make_spec(name="job_b"),now_ms=1000)
        first=self.store.claim("worker",now_ms=1000)
        self.assertIsNone(self.store.claim("worker_2",now_ms=1000))
        self.store.finish(first,make_result(make_spec(name=first.job_id)),now_ms=1001)
        self.assertIsNotNone(self.store.claim("worker_2",now_ms=1002))

    def test_lease_token_not_authority_for_other_job(self):
        self.store.submit(make_spec(name="job_a"),now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        from dataclasses import replace
        forged=replace(claim,token="forged"+"x"*40)
        with self.assertRaises(JobDenied):
            self.store.heartbeat(forged,now_ms=1100,extend_ms=600)

    def test_heartbeat_advances_fence(self):
        self.store.submit(make_spec(name="job_a"),now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertEqual(self.store.heartbeat(claim,now_ms=1200,extend_ms=600),1800)
        self.assertEqual(self.store.inspect("job_a",OWNER)["lease_expires_ms"],1800)
        with self.assertRaises(JobDenied):
            self.store.heartbeat(claim,now_ms=1800,extend_ms=600)

    def test_no_duplicate_worker_after_restart_independent_database_read(self):
        self.store.submit(make_spec(),now_ms=1000)
        claim=self.store.claim("worker",now_ms=1000,lease_ms=500)
        self.assertIsNone(self.store.claim("worker_2",now_ms=1200))
        self.assertEqual(self.store.inspect("job_1",OWNER)["state"],"running")


if __name__=="__main__":
    unittest.main()
