"""Real canonical SQLite pending, replay and crash custody after cold reopen.

A deterministic token generator substitutes for real GGUF only in this
regression suite. The database, transaction/CAS and cross-process flock
implementations are the production components.
"""
from __future__ import annotations

import os
from pathlib import Path
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    cold_reopen_acceptance,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Busy, Conflict, Identity, InferenceRequest,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import (
    SpineDatabase,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import receipts
from skeleton.testing.laptop_native_sqlite_reopen_support import (
    RealSQLiteSyntheticGGUFRig, MODEL, TOKENIZER,
)


@unittest.skipUnless(
    os.name == "posix" and Path("/proc/self/fd").is_dir(),
    "canonical descriptor-backed SQLite requires Linux",
)
class TestDurableUncertainNativeCustody(unittest.TestCase):
    def setUp(self):
        self.rig = RealSQLiteSyntheticGGUFRig()
        self.addCleanup(self.rig.close)

    def test_first_native_uncertainty_preserves_pending_after_full_close(self):
        rig = self.rig
        rig.first_backend_fails = True
        with rig.patch() as (activate, first_source, second_source):
            with self.assertRaisesRegex(RuntimeError, "aborted"):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.calls, 1)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.query_one("SELECT state FROM requests"), ("pending",))
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (0,))
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM outbox"), (0,))
        self.assertEqual(rig.events, ["activated_1", "closed_1"])
        self.assertEqual(first_source.call_count, 1)
        second_source.assert_not_called()

    def test_real_sqlite_reopen_proves_pending_without_auto_retry(self):
        rig = self.rig
        rig.first_backend_fails = True
        with rig.patch():
            with self.assertRaises(RuntimeError):
                cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.calls, 1)
        rig.first_backend_fails = False
        stack, worker, _ = rig.activate(
            model_root=rig.model_root, state_dir=rig.root,
            tenant="local", subject="operator",
        )
        with stack:
            row = rig.query_one("SELECT session,request_id FROM requests")
            self.assertEqual(len(row), 2)
            prompt = rig.args["prompt"]
            self.assertIsNone(
                worker.spine.replay(
                    row[0], row[1], prompt, seed=17, temperature=0.8,
                )
            )
            with self.assertRaises(Busy):
                worker.turn(
                    row[0], row[1], prompt, seed=17, temperature=0.8,
                )
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        self.assertEqual(rig.query_one("SELECT state FROM requests"), ("pending",))
        self.assertEqual(rig.events, [
            "activated_1", "closed_1", "activated_2", "closed_2",
        ])

    def test_canonical_sqlite_refuses_changed_prompt_after_cold_close(self):
        rig = self.rig
        with rig.patch():
            record = cold_reopen_acceptance.run(**rig.args)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)
        request = InferenceRequest(
            Identity("local", "operator", MODEL, TOKENIZER),
            record["session_id"], record["request_id"],
            "changed malicious payload", 17, 0.8,
        )
        # This is a brand-new read-only SQLite handle opened AFTER both
        # production ExecutionSpine handles were fully closed.
        with SpineDatabase(rig.root, readonly=True) as db:
            with db.snapshot() as conn:
                with self.assertRaises(Conflict):
                    receipts.replay(conn, request)
        self.assertEqual(rig.query_one("SELECT COUNT(*) FROM turns"), (1,))
        self.assertEqual(rig.query_one("SELECT state FROM requests"), ("committed",))

    def test_canonical_sqlite_refuses_changed_sampler_after_cold_close(self):
        rig = self.rig
        with rig.patch():
            record = cold_reopen_acceptance.run(**rig.args)
        request = InferenceRequest(
            Identity("local", "operator", MODEL, TOKENIZER),
            record["session_id"], record["request_id"],
            rig.args["prompt"], 18, 0.8,
        )
        with SpineDatabase(rig.root, readonly=True) as db:
            with db.snapshot() as conn:
                with self.assertRaises(Conflict):
                    receipts.replay(conn, request)
        self.assertEqual(rig.backends[0].calls, 1)
        self.assertEqual(rig.backends[1].calls, 0)

    def test_invalid_input_refused_before_opening_real_sqlite(self):
        rig = self.rig
        with rig.patch() as (activate, _, _):
            with self.assertRaises(ContractViolation):
                cold_reopen_acceptance.run(
                    **{**rig.args, "prompt": "   \r\n "}
                )
        activate.assert_not_called()
        self.assertEqual(rig.calls, 0)
        self.assertFalse((rig.root / "ai-spine.sqlite").exists())

    def test_invalid_private_identity_refused_before_opening_sqlite(self):
        rig = self.rig
        for tenant in ("", "foreign/tenant", " "):
            with self.subTest(tenant=tenant), rig.patch() as (activate, _, _):
                with self.assertRaises(ContractViolation):
                    cold_reopen_acceptance.run(
                        **{**rig.args, "tenant": tenant}
                    )
                activate.assert_not_called()
        self.assertEqual(rig.calls, 0)
        self.assertFalse((rig.root / "ai-spine.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
