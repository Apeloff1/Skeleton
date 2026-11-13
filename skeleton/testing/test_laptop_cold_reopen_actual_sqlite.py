"""Actual canonical SQLite cold reopen, with a synthetic token generator.

This is NOT a live GGUF run. It reuses the production SpineDatabase, session
flock, atomic commit, immutable request identity, read-only replay and two
separate SupervisedAI workers. The installed-source witness is mocked.
"""
from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Conflict, Busy, IntegrityFailure, Identity,
)
from skeleton.testing.laptop_native_sqlite_reopen_support import (
    RealSQLiteSyntheticGGUFRig, MODEL, TOKENIZER, SOURCE,
)


@unittest.skipUnless(
    os.name == "posix" and Path("/proc/self/fd").is_dir(),
    "canonical descriptor-backed SQLite requires Linux",
)
class TestRealSQLiteColdReopen(unittest.TestCase):
    def setUp(self):
        self.rig = RealSQLiteSyntheticGGUFRig()
        self.addCleanup(self.rig.close)

    def test_two_distinct_spines_share_one_committed_sqlite_turn(self):
        rig = self.rig
        with rig.patch() as (activate, first_source, second_source):
            record = cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.calls, 2)
        self.assertEqual(rig.events, [
            "activated_1", "closed_1", "activated_2", "closed_2",
        ])
        self.assertIsNot(rig.workers[0], rig.workers[1])
        self.assertIsNot(rig.workers[0].spine, rig.workers[1].spine)
        self.assertIsNot(rig.backends[0], rig.backends[1])
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(first_source.call_count, 2)
        self.assertEqual(second_source.call_count, 2)
        self.assertEqual(
            rig.query_one("SELECT COUNT(*) FROM turns"), (1,)
        )
        self.assertEqual(
            rig.query_one("SELECT COUNT(*) FROM outbox"), (1,)
        )
        self.assertEqual(
            rig.query_one("SELECT state FROM requests"), ("committed",)
        )
        self.assertEqual(
            rig.query_one(
                "SELECT request_id FROM turns WHERE session=?",
                (record["session_id"],),
            ),
            (record["request_id"],),
        )
        self.assertEqual(record["model_sha256"], MODEL)
        self.assertEqual(record["tokenizer_sha256"], TOKENIZER)
        self.assertTrue(record["sqlite_replay_after_cold_reopen"])
        self.assertTrue(record["source_verified_twice"])
        self.assertFalse(record["second_generation_attempted"])
        self.assertFalse(record["physical_device_qualified"])
        self.assertFalse(record["release_certified"])
        self.assertNotIn("real SQLite, synthetic model", str(record))

    def test_sqlite_response_tamper_after_close_denied_on_reopen(self):
        rig = self.rig
        rig.after_first_close = lambda: rig.mutate(
            "UPDATE turns SET response=?", (b"tampered output",)
        )
        with rig.patch():
            with self.assertRaises(IntegrityFailure):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.calls, 2)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertIn("closed_2", rig.events)
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (1,))

    def test_sqlite_receipt_sha_tamper_denied_without_reinference(self):
        rig = self.rig
        rig.after_first_close = lambda: rig.mutate(
            "UPDATE turns SET receipt_sha256=?", ("f" * 64,)
        )
        with rig.patch():
            with self.assertRaises(IntegrityFailure):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertIn("closed_2", rig.events)

    def test_marking_committed_request_pending_does_not_regenerate(self):
        rig = self.rig
        rig.after_first_close = lambda: rig.mutate(
            "UPDATE requests SET state='pending'"
        )
        with rig.patch():
            with self.assertRaisesRegex(
                ContractViolation, "not authoritative"
            ):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT state FROM requests"), ("pending",))
        self.assertIn("closed_2", rig.events)

    def test_missing_transactional_turn_holds_committed_claim(self):
        rig = self.rig
        rig.after_first_close = lambda: rig.mutate(
            "DELETE FROM turns"
        )
        with rig.patch():
            with self.assertRaises(IntegrityFailure):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT state FROM requests"), ("committed",))
        self.assertIn("closed_2", rig.events)

    def test_foreign_subject_cannot_reuse_identical_gguf_model(self):
        rig = self.rig
        rig.second_owner = Identity("local", "foreign", MODEL, TOKENIZER)
        with rig.patch():
            with self.assertRaisesRegex(ContractViolation, "another principal"):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (1,))
        self.assertIn("closed_2", rig.events)

    def test_foreign_tenant_cannot_reuse_identical_gguf_model(self):
        rig = self.rig
        rig.second_owner = Identity("foreign", "operator", MODEL, TOKENIZER)
        with rig.patch():
            with self.assertRaisesRegex(ContractViolation, "another principal"):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (1,))

    def test_second_source_custody_failure_leaves_first_commit_intact(self):
        rig = self.rig
        rig.second_source = {**SOURCE, "source_sha": "f" * 40}
        with rig.patch():
            with self.assertRaisesRegex(ContractViolation, "source changed"):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (1,))
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM outbox"), (1,))
        self.assertIn("closed_2", rig.events)


if __name__ == "__main__":
    unittest.main()
