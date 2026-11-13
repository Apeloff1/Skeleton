"""SQLite WAL vault crash recovery, rotation, immutable history and cold audit."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_session_vault import (
    NativeSessionVault,NativeSessionVaultError,
)


class NativeSessionVaultTests(NativeQuestBatchTests):
    def make(self,location):
        return NativeSessionVault(location,session_id="local-quest-demo")

    def test_resume_after_reopen_and_payload_rotation_preserves_receipts(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"vault.sqlite"
            snapshots=[self.replay(through_frame=i)["head_checkpoint"] for i in (0,1,2,4)]
            receipts=[]
            for i,cp in enumerate(snapshots):
                with self.make(path) as vault:
                    stored=vault.append(
                        cp,self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
                    self.assertEqual(stored["serial"],i)
                    receipts.append(stored["receipt_digest"])
                    opened=vault.recover(
                        self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
                    self.assertEqual(opened["checkpoint"],cp)
            with self.make(path) as vault:
                outcome=vault.rotate(keep_latest=2)
                self.assertEqual(outcome["retained_snapshots"],2)
                self.assertEqual(outcome["archived_receipts"],4)
                self.assertEqual(outcome["head_receipt_digest"],receipts[-1])
            with self.make(path) as vault:
                recovered=vault.recover(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(recovered["compacted_snapshot_count"],2)
                self.assertEqual(recovered["checkpoint"],snapshots[-1])
                self.assertEqual(recovered["vault_receipt_digest"],receipts[-1])
                repeated=vault.append(
                    snapshots[-1],self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertTrue(repeated["reused_existing"])

    def test_full_retained_history_audit_after_compaction(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"history.sqlite"
            checkpoints=[self.replay(through_frame=i)["head_checkpoint"] for i in (0,1,2,4)]
            with self.make(path) as vault:
                for cp in checkpoints:
                    vault.append(cp,self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
                audit=vault.audit_retained_history(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(audit["retained_snapshots_cold_replayed"],4)
                self.assertEqual(audit["ancestry_receipts_verified"],4)
                self.assertEqual(audit["compacted_payloads_not_replayable"],0)
                vault.rotate(keep_latest=2)
            with self.make(path) as vault:
                proof=vault.audit_retained_history(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(proof["ancestry_receipts_verified"],4)
                self.assertEqual(proof["retained_snapshots_cold_replayed"],2)
                self.assertEqual(proof["compacted_payloads_not_replayable"],2)
                self.assertEqual(proof["last_cold_replayed_frame"],4)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE game_native_quest_vault SET snapshot_json='{}' "
                           "WHERE serial=2")
            with self.make(path) as vault:
                with self.assertRaises(NativeSessionVaultError):
                    vault.audit_retained_history(
                        self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)

    def test_sqlite_storage_health_separate_from_game_canon_proof(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"health.sqlite"
            with self.make(path) as vault:
                health=vault.inspect_storage_integrity()
                self.assertEqual(health["sqlite_check"],"ok")
                self.assertEqual(health["journal_mode"],"wal")
                self.assertEqual(health["synchronous"],"full")
                self.assertGreaterEqual(health["page_count"],1)
                vault._db.execute("PRAGMA synchronous=NORMAL")
                with self.assertRaisesRegex(NativeSessionVaultError,"WAL and FULL sync"):
                    vault.inspect_storage_integrity()
                vault._db.execute("PRAGMA synchronous=FULL")
                self.assertEqual(vault.inspect_storage_integrity()["sqlite_check"],"ok")

    def test_exported_external_recovery_manifest_checks_all_save_sources(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"external.sqlite"
            cp=self.replay(through_frame=4)["head_checkpoint"]
            with self.make(path) as vault:
                vault.append(cp,self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                data=vault.export_recovery_manifest(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(data["latest_verified_frame"],4)
                self.assertEqual(data["retained_receipts"],1)
                self.assertEqual(data["sqlite_health"]["sqlite_check"],"ok")
                self.assertTrue(vault.verify_external_recovery_manifest(
                    self.journal,self.pages,self.graph,self.approved,data,
                    actor_id="hero",scene_candidate_digest="d"*64))
                forged=dict(data,retained_receipts=999)
                with self.assertRaises(NativeSessionVaultError):
                    vault.verify_external_recovery_manifest(
                        self.journal,self.pages,self.graph,self.approved,forged,
                        actor_id="hero",scene_candidate_digest="d"*64)

    def test_crash_before_commit_does_not_leave_partial_save(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"vault.sqlite"
            first=self.replay(through_frame=0)["head_checkpoint"]
            next_one=self.replay(through_frame=2)["head_checkpoint"]
            with self.make(path) as vault:
                vault.append(first,self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                with self.assertRaisesRegex(NativeSessionVaultError,"injected"):
                    vault.append(next_one,self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64,
                        inject_crash_before_commit=True)
            with self.make(path) as vault:
                recovered=vault.recover(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(recovered["frame"],0)
                self.assertEqual(recovered["retained_receipt_count"],1)
                saved=vault.append(next_one,self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(saved["serial"],1)

    def test_altered_saved_checkpoint_and_receipt_chain_rejected(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"vault.sqlite"
            cp=self.replay(through_frame=4)["head_checkpoint"]
            with self.make(path) as vault:
                vault.append(cp,self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE game_native_quest_vault SET snapshot_json='{}'")
            with self.make(path) as vault:
                with self.assertRaises(NativeSessionVaultError):
                    vault.recover(self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE game_native_quest_vault SET receipt_digest=?",("0"*64,))
            with self.make(path) as vault:
                with self.assertRaises(NativeSessionVaultError):
                    vault.rotate()

    def test_reject_forged_checkpoint_and_wrong_session_identity(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"vault.sqlite"
            cp=self.replay()["head_checkpoint"]
            with self.make(path) as vault:
                wrong=deepcopy(cp)
                wrong["flags"]["forged"]=True
                with self.assertRaises(ValueError):
                    vault.append(wrong,self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
                with self.assertRaises(NativeSessionVaultError):
                    vault.append(dict(cp,session_id="other"),self.journal,
                        self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64)
                with self.assertRaises(NativeSessionVaultError):
                    vault.rotate(keep_latest=0)
