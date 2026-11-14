"""Authenticated candidate event history and exact replay across SQLite reopen."""
from __future__ import annotations
import sqlite3
import tempfile
from pathlib import Path
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.ledger import CandidateLedger
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestCandidateEventLedger(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/"events.sqlite"

    def tearDown(self):
        self.folder.cleanup()

    def test_replay_and_conflicting_payload(self):
        with sqlite3.connect(self.path,isolation_level=None) as db:
            ledger=CandidateLedger(db,key=b"L"*32)
            self.assertFalse(ledger.append("run_1","e_1","verified",{"digest":"a"*64})["replayed"])
            self.assertTrue(ledger.append("run_1","e_1","verified",{"digest":"a"*64})["replayed"])
            with self.assertRaises(CandidateRejected):
                ledger.append("run_1","e_1","verified",{"digest":"b"*64})

    def test_reopen_preserves_chain(self):
        with sqlite3.connect(self.path,isolation_level=None) as db:
            CandidateLedger(db,key=b"L"*32).append("run_1","e_1","verified",{"v":1})
        with sqlite3.connect(self.path,isolation_level=None) as db:
            proof=CandidateLedger(db,key=b"L"*32).verify("run_1")
            self.assertTrue(proof["verified"])
            self.assertEqual(proof["count"],1)

    def test_wrong_mac_key_refuses_history(self):
        with sqlite3.connect(self.path,isolation_level=None) as db:
            CandidateLedger(db,key=b"L"*32).append("run_1","e_1","verified",{"v":1})
            with self.assertRaises(CandidateRejected):
                CandidateLedger(db,key=b"X"*32).verify("run_1")

    def test_pinned_tail_refuses_missing_final_event(self):
        with sqlite3.connect(self.path,isolation_level=None) as db:
            ledger=CandidateLedger(db,key=b"L"*32)
            ledger.append("run_1","e_1","verified",{"v":1})
            ledger.append("run_1","e_2","training",{"v":2})
            head=ledger.verify("run_1")["head_mac"]
            db.execute("DELETE FROM candidate_training_events WHERE event_id='e_2'")
            with self.assertRaises(CandidateRejected):
                ledger.verify("run_1",expected_head=head)


if __name__ == "__main__":
    unittest.main()
