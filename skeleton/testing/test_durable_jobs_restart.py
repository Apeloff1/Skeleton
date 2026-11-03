"""Actual on-disk SQLite durability; no native model fixture claims."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.store import JobStore
from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import (
    OWNER, make_spec,make_result,
)
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.invariants import verify_store


class TestRestartDurability(unittest.TestCase):
    def test_uncommitted_native_claim_survives_restart_as_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"jobs.sqlite3"
            with sqlite3.connect(path,isolation_level=None) as db:
                store=JobStore(db)
                store.submit(make_spec(),now_ms=1000)
                claim=store.claim("worker",now_ms=1000,lease_ms=500)
                self.assertEqual(store.inspect("job_1",OWNER)["state"],"running")
            with sqlite3.connect(path,isolation_level=None) as db:
                store=JobStore(db)
                self.assertEqual(store.inspect("job_1",OWNER)["state"],"running")
                self.assertIsNone(store.claim("second_worker",now_ms=1100))
                store.sweep(now_ms=1500)
                self.assertEqual(store.inspect("job_1",OWNER)["state"],"held")
                self.assertTrue(verify_store(store)["verified"])

    def test_committed_result_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"jobs.sqlite3"
            spec=make_spec()
            with sqlite3.connect(path,isolation_level=None) as db:
                store=JobStore(db)
                store.submit(spec,now_ms=1000)
                claim=store.claim("worker",now_ms=1000,lease_ms=500)
                store.finish(claim,make_result(spec),now_ms=1200)
            with sqlite3.connect(path,isolation_level=None) as db:
                store=JobStore(db)
                result=store.receipt("job_1",OWNER)
                self.assertEqual(result.original_request_id,"job_1")
                self.assertEqual(store.inspect("job_1",OWNER)["state"],"completed")
                self.assertTrue(verify_store(store)["verified"])
                self.assertIsNone(store.claim("worker_2",now_ms=1300))


if __name__=="__main__":
    unittest.main()
