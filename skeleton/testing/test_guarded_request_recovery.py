"""SQLite nonce and effect recovery are durable across process-style reopen."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.guarded_request.nonce_fence import NonceFence
from skeleton.ai.runtime.operational_ai.guarded_request.receipts import EffectReceipts
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied


class TestGuardedRecovery(unittest.TestCase):
    def test_nonce_remains_fenced_after_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            dbfile = Path(folder) / "nonce.sqlite"
            with sqlite3.connect(dbfile, isolation_level=None) as db:
                nonce = NonceFence(db)
                nonce.reserve("tenant", "req_1", 9, "a" * 64)
                self.assertEqual(nonce.head("tenant"), 9)
            with sqlite3.connect(dbfile, isolation_level=None) as db:
                nonce = NonceFence(db)
                self.assertEqual(nonce.reserve("tenant", "req_1", 9, "a" * 64), "replayed")
                with self.assertRaises(GateDenied):
                    nonce.reserve("tenant", "req_2", 9, "b" * 64)
                self.assertEqual(nonce.reserve("tenant", "req_2", 10, "b" * 64), "admitted")

    def test_unresolved_effect_is_visible_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            dbfile = Path(folder) / "effects.sqlite"
            with sqlite3.connect(dbfile, isolation_level=None) as db:
                ledger = EffectReceipts(db)
                ledger.prepare(scope="tenant", effect_id="send_1", args_sha="a" * 64)
            with sqlite3.connect(dbfile, isolation_level=None) as db:
                ledger = EffectReceipts(db)
                self.assertEqual(len(ledger.pending("tenant")), 1)
                with self.assertRaises(GateDenied):
                    ledger.prepare(scope="tenant", effect_id="send_1", args_sha="b" * 64)
                self.assertEqual(ledger.pending("tenant")[0]["effect_id"], "send_1")


if __name__ == "__main__":
    unittest.main()
