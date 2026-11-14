"""Published candidate effect receipts cannot duplicate or rewrite outcomes."""
from __future__ import annotations
import sqlite3
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.training_outbox import CandidateOutbox
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestCandidateOutbox(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:",isolation_level=None)
        self.outbox=CandidateOutbox(self.db)

    def tearDown(self):
        self.db.close()

    def test_prepared_requires_independent_reconciliation(self):
        self.assertEqual(self.outbox.prepare("run_1","a"*64),"prepared")
        self.assertEqual(len(self.outbox.pending()),1)
        self.assertEqual(self.outbox.prepare("run_1","a"*64),"prepared")

    def test_conflicting_candidate_digest_refused(self):
        self.outbox.prepare("run_1","a"*64)
        with self.assertRaises(CandidateRejected):
            self.outbox.prepare("run_1","b"*64)

    def test_exact_terminal_replay(self):
        self.outbox.prepare("run_1","a"*64)
        self.assertEqual(self.outbox.finish("run_1","a"*64,"c"*64),"published")
        self.assertEqual(self.outbox.finish("run_1","a"*64,"c"*64),"replayed")
        self.assertEqual(self.outbox.pending(),[])

    def test_mutated_terminal_receipt_denied(self):
        self.outbox.prepare("run_1","a"*64)
        self.outbox.finish("run_1","a"*64,"c"*64)
        with self.assertRaises(CandidateRejected):
            self.outbox.finish("run_1","a"*64,"d"*64)


if __name__ == "__main__":
    unittest.main()
