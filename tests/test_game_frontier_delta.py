"""Content-addressed source-frame deltas and durable selective delta replay."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from skeleton.jeeves.game_frontier_frame_coherence import (
    bind_signed_gdd, FrameObject, GDDFrameNote, advance_frame, digest,
)
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.jeeves.game_frontier_delta import (
    create_frame_delta, restore_frame_delta, verify_frame_delta, FrameDeltaError,
)
from skeleton.jeeves.game_frontier_receipt_journal import (
    FrameReceiptJournal, FrameJournalError,
)
from tests.test_game_frontier_position_frames import gdd


def players(x=1., count=8):
    return tuple(FrameObject(f"actor-{i}",
                             Vec3(x if i==0 else i*10+1,0,2),
                             Vec3(6 if i==0 else 0,0,0),
                             f"{i%10}"*64) for i in range(count))


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.gdd=bind_signed_gdd(gdd())

    def test_four_presentation_rates_reconstruct_exact_frame(self):
        for fps in (30,50,60,120):
            old=advance_frame(frame_index=0,fps=fps,gdd=self.gdd,
                              objects=players(31.99))
            delta0=create_frame_delta(old,self.gdd)
            self.assertEqual(restore_frame_delta(delta0,self.gdd),old)
            new=advance_frame(frame_index=1,fps=fps,gdd=self.gdd,
                              previous=old,objects=players(32.01),
                              notes=(GDDFrameNote(1,"quality","Preserve GDD"),))
            compact=create_frame_delta(new,self.gdd,previous=old)
            self.assertEqual(len(compact["changed_objects"]),1)
            self.assertEqual(compact["unchanged_count"],7)
            self.assertTrue(any(v["retired"] for v in compact["touched_chunks"]))
            self.assertEqual(restore_frame_delta(compact,self.gdd,previous=old),new)
            self.assertEqual(verify_frame_delta(compact,new,self.gdd,previous=old),
                             (True,True))

    def test_unchanged_frame_compresses_actor_states(self):
        a=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=players())
        b=advance_frame(frame_index=1,fps=60,gdd=self.gdd,
                        objects=players(),previous=a)
        p=create_frame_delta(b,self.gdd,previous=a)
        self.assertEqual(p["changed_objects"],[])
        self.assertEqual(p["unchanged_count"],8)
        self.assertEqual(p["touched_chunks"],[])
        self.assertEqual(restore_frame_delta(p,self.gdd,previous=a),b)

    def test_wrong_actor_source_and_rehashed_delta_refused(self):
        a=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=players())
        b=advance_frame(frame_index=1,fps=60,gdd=self.gdd,objects=players(1.05),
                        previous=a)
        normal=create_frame_delta(b,self.gdd,previous=a)
        for variant in (
            {"source_frame_digest":"a"*64},
            {"previous_frame_digest":"b"*64},
            {"object_count":20},
            {"unchanged_count":0},
        ):
            forged=dict(normal)
            forged.update(variant)
            forged["receipt_digest"]=digest({
                k:v for k,v in forged.items() if k!="receipt_digest"})
            with self.assertRaises(FrameDeltaError):
                restore_frame_delta(forged,self.gdd,previous=a)
        mismatch=dict(normal)
        updates=[dict(x) for x in normal["changed_objects"]]
        updates[0]["source"]="b"*64
        mismatch["changed_objects"]=updates
        mismatch["receipt_digest"]=digest({
            k:v for k,v in mismatch.items() if k!="receipt_digest"})
        with self.assertRaises(FrameDeltaError):
            restore_frame_delta(mismatch,self.gdd,previous=a)

    def test_cannot_rollback_to_another_signed_world_law(self):
        a=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=players())
        proof=create_frame_delta(a,self.gdd)
        altered=replace(self.gdd,source_digest="f"*64)
        with self.assertRaises(FrameDeltaError):
            restore_frame_delta(proof,altered)
        with self.assertRaises(FrameDeltaError):
            restore_frame_delta(proof,self.gdd,previous=a)

    def test_unauthorized_entity_birth_removal_refused(self):
        a=advance_frame(frame_index=0,fps=60,gdd=self.gdd,objects=players())
        # The source engine's frame verifier also rejects actor birth.
        with self.assertRaises(Exception):
            advance_frame(frame_index=1,fps=60,gdd=self.gdd,
                          previous=a,objects=players(count=7))


class DurableDeltaTests(unittest.TestCase):
    def setUp(self):
        self.gdd=bind_signed_gdd(gdd())
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"frame_deltas.db"

    def test_journal_delta_transaction_replay_and_rollback_fork(self):
        with FrameReceiptJournal(self.path,self.gdd) as source:
            for i in range(16):
                source.advance(players(2+i*.05),fps=60,include_delta=True)
            self.assertEqual(source.replay()["verified_frames"],16)
            for index in range(16):
                self.assertEqual(source.frame_delta(index)["frame_index"],index)
                self.assertEqual(source.frame_delta(index)["source_frame_digest"],
                                 source.load(index)[0].receipt_digest)
            size=source.stats()["deduplicated_blobs"]
            self.assertEqual(size,48)
            source.fork("undo_8",through=8)
        with FrameReceiptJournal(self.path,self.gdd,track="undo_8") as replay:
            self.assertEqual(replay.replay()["verified_frames"],9)
            replay.advance(players(2.45),fps=60,include_delta=True)
            self.assertEqual(replay.replay()["verified_frames"],10)
        with FrameReceiptJournal(self.path,self.gdd) as original:
            self.assertEqual(original.stats()["head"],15)
            self.assertEqual(original.stats()["deduplicated_blobs"],size+3)

    def test_journal_defaults_to_no_delta_for_legacy_users(self):
        with FrameReceiptJournal(self.path,self.gdd) as source:
            source.advance(players(),fps=60)
            self.assertIsNone(source.frame_delta(0))
            self.assertEqual(source.stats()["deduplicated_blobs"],2)
            self.assertEqual(source.replay()["verified_frames"],1)

    def test_rehashed_delta_corruption_rejected_after_restart(self):
        with FrameReceiptJournal(self.path,self.gdd) as source:
            zero=source.advance(players(),fps=60,include_delta=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                         (zero["delta_digest"],))
        with FrameReceiptJournal(self.path,self.gdd) as source:
            with self.assertRaises(FrameJournalError):
                source.replay()

    def test_corrupt_delta_prevents_fork(self):
        with FrameReceiptJournal(self.path,self.gdd) as source:
            zero=source.advance(players(),fps=60,include_delta=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE frontier_blobs SET content='{}' WHERE digest=?",
                         (zero["delta_digest"],))
        with FrameReceiptJournal(self.path,self.gdd) as source:
            with self.assertRaises(FrameJournalError):
                source.fork("unsafe",through=0)


if __name__=="__main__":
    unittest.main()
