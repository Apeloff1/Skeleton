"""Prove that original engine audit does actual replay and does not fake training."""
from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from skeleton.jeeves.game_studio_engine_audit import (
    audit_studio_engines, inspect_engine, save_report,
)


class StudioEngineAuditTests(unittest.TestCase):
    def test_replay_contract_reports_measured_single_engine(self):
        result=inspect_engine("economy",seed=17,max_steps=4)
        self.assertEqual(result["status"],"verified_reference_execution",result)
        self.assertTrue(result["source_replay_verified"])
        self.assertTrue(result["scene_replay_verified"])
        self.assertTrue(result["learning_snapshot_verified"])
        self.assertFalse(result["production_neural_weights_modified"])
        self.assertEqual(result["candidate_q_updates"],0)
        self.assertTrue(result["verified_action"])

    def test_training_is_explicitly_rights_gated_and_real(self):
        with self.assertRaises(PermissionError):
            inspect_engine("economy",seed=17,max_steps=3,train_episodes=2)
        result=inspect_engine("economy",seed=17,max_steps=3,
                              train_episodes=2,authorized=True,rights_cleared=True)
        self.assertEqual(result["status"],"verified_reference_execution",result)
        self.assertGreater(result["candidate_q_updates"],0)
        self.assertTrue(result["candidate_only"])

    def test_report_integrity_and_overwrite_refusal(self):
        report=audit_studio_engines(["economy"],seed=17,max_steps=3)
        self.assertEqual(report["selected_engine_count"],1)
        self.assertEqual(report["declared_engine_count"],43)
        self.assertEqual(report["verified_reference_engines"],1)
        self.assertEqual(report["actual_neural_optimizer_updates"],0)
        with TemporaryDirectory() as root:
            dest=Path(root)/"checked.json"
            digest=save_report(dest,report)
            self.assertEqual(len(digest),64)
            with self.assertRaises(FileExistsError):
                save_report(dest,report)
            tampered=deepcopy(report)
            tampered["verified_reference_engines"]+=1
            with self.assertRaises(ValueError):
                save_report(Path(root)/"tampered.json",tampered)

    def test_unknown_engine_or_forged_permission_cannot_mint_pass(self):
        with self.assertRaises(ValueError):
            audit_studio_engines(["missing-engine"])
        with self.assertRaises(ValueError):
            audit_studio_engines(["economy","economy"])
        with self.assertRaises(PermissionError):
            audit_studio_engines(["economy"],train_episodes=2,
                                 authorized=True,rights_cleared=False)


if __name__=="__main__":
    unittest.main()
