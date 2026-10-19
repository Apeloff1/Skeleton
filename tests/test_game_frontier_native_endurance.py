"""Bounded real-source restart endurance with crash rollback + rotation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tests.test_game_frontier_native_quest_batch import NativeQuestBatchTests
from skeleton.jeeves.game_frontier_native_endurance import (
    exercise_native_session_endurance,
)
from skeleton.jeeves.game_frontier_native_session_vault import (
    NativeSessionVault,NativeSessionVaultError,
)


class NativeEnduranceTests(NativeQuestBatchTests):
    def test_restart_after_rollback_and_rotation_twelve_cycles(self):
        with TemporaryDirectory() as root:
            dest=Path(root)/"restarts.sqlite"
            report=exercise_native_session_endurance(
                self.journal,self.pages,self.graph,self.approved,
                actor_id="hero",scene_candidate_digest="d"*64,
                vault_path=dest,cycles=12,window_frames=2,
                retain_latest=2,crash_interval=2)
            self.assertEqual(report["cycles_executed"],12)
            self.assertGreaterEqual(report["crash_rollbacks_executed"],1)
            self.assertGreaterEqual(report["idempotent_duplicate_saves"],1)
            self.assertEqual(report["source_frames_cold_replayed"],5)
            self.assertGreaterEqual(report["on_disk_vault_bytes"],4096)
            self.assertGreater(report["peak_cycle_elapsed_ns"],0)
            self.assertGreater(report["peak_measured_vault_disk_bytes"],0)
            self.assertTrue(all(row["cycle_wall_elapsed_ns"]>0 for row in report["cycle_evidence"]))
            self.assertEqual(len(report["cycle_evidence"]),12)
            self.assertEqual(len(report["final_retained_history_audit_digest"]),64)
            self.assertTrue(all(
                item["retained_history_verified_frames"]==item["replayed_through"]
                for item in report["cycle_evidence"]))
            self.assertEqual(report["cycle_evidence"][-1]["replayed_through"],4)
            self.assertEqual(len(report["receipt_digest"]),64)
            with NativeSessionVault(dest,session_id=self.approved["session_id"]) as reopened:
                recovered=reopened.recover(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(recovered["checkpoint"]["quests"]["chapter_1"]["stage"],
                                 "ending")
                self.assertEqual(recovered["vault_receipt_digest"],
                                 report["final_vault_receipt_digest"])

    def test_fail_closed_invalid_endurance_controls(self):
        with TemporaryDirectory() as root:
            for profile in ({"cycles":0},{"cycles":1025},
                            {"window_frames":0},{"retain_latest":0},
                            {"crash_interval":-1}):
                with self.subTest(profile=profile),self.assertRaises(NativeSessionVaultError):
                    exercise_native_session_endurance(
                        self.journal,self.pages,self.graph,self.approved,
                        actor_id="hero",scene_candidate_digest="d"*64,
                        vault_path=Path(root)/"not-created.sqlite",**profile)

    def test_small_disk_budget_fails_closed_without_corrupting_vault(self):
        with TemporaryDirectory() as root:
            dest=Path(root)/"disk-budget.sqlite"
            with self.assertRaisesRegex(NativeSessionVaultError,"disk growth budget"):
                exercise_native_session_endurance(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64,
                    vault_path=dest,cycles=3,max_vault_bytes=1)
            with NativeSessionVault(dest,session_id=self.approved["session_id"]) as vault:
                # Failure is after a transaction commit: independently
                # recovering the last save must still work.
                restored=vault.recover(
                    self.journal,self.pages,self.graph,self.approved,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(restored["frame"],1)

    def test_no_unapproved_quest_completion_during_endurance(self):
        with TemporaryDirectory() as root:
            approvals=self.fixture.approval(authorized=())
            result=exercise_native_session_endurance(
                self.journal,self.pages,self.graph,approvals,
                actor_id="hero",scene_candidate_digest="d"*64,
                vault_path=Path(root)/"unapproved.sqlite",
                cycles=5,window_frames=1,crash_interval=2)
            with NativeSessionVault(
                Path(root)/"unapproved.sqlite",session_id=approvals["session_id"]
            ) as vault:
                actual=vault.recover(
                    self.journal,self.pages,self.graph,approvals,
                    actor_id="hero",scene_candidate_digest="d"*64)
                self.assertEqual(actual["checkpoint"]["quests"],{})
                self.assertEqual(result["source_frames_cold_replayed"],5)
