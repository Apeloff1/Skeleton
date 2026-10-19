"""Bounded, source-verified evidence timeline for game studio and replay."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_receipt_journal import (
    FrameReceiptJournal,FrameJournalError,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    bind_signed_gdd,FrameObject,GDDFrameNote,
)
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_native_capture import GodotPhysicsCaptureIngestor
from tests.test_game_frontier_position_frames import gdd


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.anchor=bind_signed_gdd(gdd())
        self.directory=TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/"timeline.sqlite"

    @staticmethod
    def actors(x=31.95):
        return (
            FrameObject("hero",Vec3(x,0,2),Vec3(6,0,0),"a"*64),
            FrameObject("tower",Vec3(70,0,0),Vec3(0,0,0),"b"*64),
        )

    def test_70_frame_paginated_and_filtered_source_cursors(self):
        with FrameReceiptJournal(self.path,self.anchor) as journal:
            for i in range(70):
                journal.advance(self.actors(31.95+i*.03),fps=60,
                    notes=(GDDFrameNote(1,"continuity",
                        "Weather and sky-island positioning.") if i==1 else None,)
                    if i==1 else ())
            current=0
            pages=[]
            while True:
                page=journal.evidence_page(start_frame=current,limit=17)
                self.assertEqual(len(page["receipt_digest"]),64)
                self.assertLessEqual(len(page["entries"]),17)
                pages.extend(page["entries"])
                if page["next_frame"] is None:
                    break
                self.assertGreater(page["next_frame"],current)
                current=page["next_frame"]
            self.assertEqual(len(pages),70)
            self.assertEqual(pages[-1]["frame"],69)
            self.assertTrue(any(x["migration_count"]==1 for x in pages))
            self.assertEqual(pages[0]["signed_gdd_digest"],
                             self.anchor.source_digest)
            self.assertTrue(all(x["chunk_evidence_digest"] for x in pages))
            self.assertTrue(all(x["native_evidence_digest"] is None for x in pages))
            self.assertEqual(journal.evidence_page(start_frame=70)["entries"],[])

    def test_actor_and_chunk_filters_and_note_anchors(self):
        with FrameReceiptJournal(self.path,self.anchor) as journal:
            journal.advance(self.actors(),fps=60)
            journal.advance(self.actors(32.03),fps=60,
                notes=(GDDFrameNote(1,"design_context",
                    "Review cross-region character movement."),))
            page=journal.evidence_page(chunk_xy=(0,0),limit=2)
            self.assertEqual(len(page["entries"]),2)
            self.assertEqual(page["entries"][1]["migration_count"],1)
            self.assertGreater(page["entries"][1]["gdd_note_count"],0)
            self.assertTrue(page["entries"][1]["moved_actor_ids"])
            absent=journal.evidence_page(actor_id="nobody")
            self.assertEqual(absent["entries"],[])
            movers=journal.evidence_page(changes_only=True)
            self.assertEqual([x["frame"] for x in movers["entries"]],[1])

    def test_source_forgery_refused_in_timeline(self):
        with FrameReceiptJournal(self.path,self.anchor) as journal:
            journal.advance(self.actors(),fps=60)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE frontier_blobs SET content='{}' WHERE digest IN "
                "(SELECT evidence_digest FROM frontier_commits WHERE frame=0)")
        with FrameReceiptJournal(self.path,self.anchor) as journal:
            with self.assertRaises(FrameJournalError):
                journal.evidence_page()

    def test_query_limits_and_invalid_cursors_rejected(self):
        with FrameReceiptJournal(self.path,self.anchor) as journal:
            for kwargs in (
                {"start_frame":-1},{"limit":0},{"limit":10000},
                {"actor_id":""},{"chunk_xy":("1",0)},
                {"changes_only":1},{"start_frame":2},
            ):
                with self.assertRaises(FrameJournalError):
                    journal.evidence_page(**kwargs)
            self.assertEqual(journal.evidence_page()["entries"],[])


if __name__=="__main__":
    unittest.main()
