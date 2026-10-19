"""Durable chunk receipt journal: transaction, replay, corruption, rollback."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameObject, GDDFrameNote, bind_signed_gdd, advance_frame,
)
from skeleton.jeeves.game_frontier_receipt_journal import (
    FrameReceiptJournal, FrameJournalError,
)
from tests.test_game_frontier_position_frames import gdd


def actors(position: float):
    return (FrameObject("hero",Vec3(position,0,1),Vec3(6,0,0),"a"*64),
            FrameObject("wall",Vec3(65,0,0),Vec3(0,0,0),"b"*64))


class DurableJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database=Path(self.temp.name)/"receipts.sqlite"
        self.anchor=bind_signed_gdd(gdd())

    def test_30_50_60_120_fps_transaction_and_reopen_replay(self):
        for fps in (30,50,60,120):
            db=Path(self.temp.name)/f"fps_{fps}.sqlite"
            with FrameReceiptJournal(db,self.anchor) as journal:
                zero=journal.advance(actors(31.99),fps=fps)
                one=journal.advance(actors(32.01),fps=fps,
                    notes=(GDDFrameNote(1,"design_context",
                      "Massive physics and game map continuity."),))
                self.assertEqual(zero["frame"],0)
                self.assertEqual(one["frame"],1)
                self.assertEqual(len(one["chunk_evidence_digest"]),64)
                frame,proof=journal.load(1)
                self.assertEqual(frame.note_from_previous[0].world_law_index,1)
                self.assertEqual(proof["cross_chunk_migrations"],1)
                self.assertEqual(proof["retired_chunk_count"],1)
                self.assertEqual(proof["previous_evidence_digest"],
                                 zero["chunk_evidence_digest"])
                self.assertEqual(journal.replay()["verified_frames"],2)
            with FrameReceiptJournal(db,self.anchor) as reopened:
                self.assertEqual(reopened.load(1)[0].receipt_digest,one["frame_digest"])
                self.assertEqual(reopened.replay()["head_frame_digest"],one["frame_digest"])

    def test_rollback_forks_verified_prefix_without_deleting_history(self):
        with FrameReceiptJournal(self.database,self.anchor) as original:
            for i in range(5):
                original.advance(actors(3+i*.05),fps=60,
                                 notes=(GDDFrameNote(1,"quality","Retain GDD physics"),)
                                 if i else ())
            original_head=original.load(4)[0].receipt_digest
            original.fork("branch_2",through=2)
            self.assertEqual(original.stats()["deduplicated_blobs"],10)
            with self.assertRaises(sqlite3.IntegrityError):
                original.fork("branch_2",through=2)
        with FrameReceiptJournal(self.database,self.anchor,
                                 track="branch_2") as fork:
            self.assertEqual(fork.replay()["verified_frames"],3)
            fork.advance(actors(3.15),fps=60,
                         notes=(GDDFrameNote(1,"quality","Independent story edit"),))
            self.assertEqual(fork.replay()["verified_frames"],4)
        with FrameReceiptJournal(self.database,self.anchor) as original:
            self.assertEqual(original.stats()["head"],4)
            self.assertEqual(original.load(4)[0].receipt_digest,original_head)
            self.assertEqual(original.replay()["verified_frames"],5)
            # Fork reused the common blobs instead of duplicating frames 0..2.
            self.assertEqual(original.stats()["deduplicated_blobs"],12)

    def test_source_digest_tampering_is_detected_after_reopen(self):
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            record=journal.advance(actors(1),fps=60)
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                       (record["chunk_evidence_digest"],))
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            with self.assertRaises(FrameJournalError):
                journal.load(0)
            with self.assertRaises(FrameJournalError):
                journal.replay()
            with self.assertRaises(FrameJournalError):
                journal.advance(actors(1.05),fps=60)

    def test_stale_frame_duplicate_index_or_bad_gdd_rejected_without_commit(self):
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            first=journal.advance(actors(1))
            frame,_=journal.load(0)
            with self.assertRaises(FrameJournalError):
                journal.append(frame)
            self.assertEqual(journal.stats()["head"],0)
            with self.assertRaises(FrameJournalError):
                journal.append(replace(frame,receipt_digest="f"*64))
            self.assertEqual(journal.stats()["head"],0)
            with self.assertRaises(FrameJournalError):
                journal.advance(actors(999),fps=60)
            self.assertEqual(journal.replay()["verified_frames"],1)
        altered=replace(self.anchor,source_digest="e"*64)
        with self.assertRaises(FrameJournalError):
            FrameReceiptJournal(self.database,altered)

    def test_incorrect_supplied_evidence_is_rejected_and_transaction_rolled_back(self):
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            frame=advance_frame(frame_index=0,fps=60,gdd=self.anchor,objects=actors(1))
            with self.assertRaises(FrameJournalError):
                journal.append(frame,{"receipt_digest":"0"*64})
            self.assertEqual(journal.stats()["head"],-1)
            journal.append(frame)
            self.assertEqual(journal.replay()["verified_frames"],1)

    def test_long_running_incremental_80frame_recovery(self):
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            for i in range(80):
                journal.advance(actors(2 + .05*i),fps=60,
                    notes=(GDDFrameNote(1,"continuity","Keep signed wind axis."),)
                    if i else ())
            self.assertEqual(journal.replay()["verified_frames"],80)
            self.assertLessEqual(journal.stats()["deduplicated_blobs"],160)

    def test_explicit_head_and_missing_parent_rejected(self):
        with self.assertRaises(FrameJournalError):
            FrameReceiptJournal(self.database.with_name("x")/"missing.db",self.anchor)
        with self.assertRaises(FrameJournalError):
            FrameReceiptJournal(self.database,self.anchor,track="../bad")
        with FrameReceiptJournal(self.database,self.anchor) as journal:
            with self.assertRaises(FrameJournalError):
                journal.fork("cannot",through=0)
            with self.assertRaises(FrameJournalError):
                journal.replay(through=0)


if __name__=="__main__":
    unittest.main()
